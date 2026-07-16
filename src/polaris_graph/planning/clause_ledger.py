"""Lossless clause ledger (Research Planning Gate — Phase B, generality gap).

The post-inversion compiler guarantees monotonicity only over constraints a
*deterministic extractor* produces a candidate for. A stated constraint with no
extractor (a bare quality adjective, a source kind absent from the ontology, an
exclusion of an unknown kind) is INVISIBLE to ``validate_monotonicity`` — the
survival set is the image of the extractors, not the image of the prompt. When
the LLM omits such a constraint, nothing fails and it silently vanishes.

This module closes that gap WITHOUT trusting a cleverer extractor. It keys off
the PROMPT, not the extractor output:

  1. **Deterministic segmentation** — the whole prompt is split into stable
     clause/span IDs (sentence + coordinated-phrase granularity). Segmentation
     and IDs are owned by code, quote-equality guaranteed (never fabricated).
  2. **Deontic-driven constraint detection** — a clause carrying a modal/deontic
     cue (``only``, ``must``, ``do not``, ``no ___``, ``exclude``, ``avoid``,
     ``from YYYY onward``, ``at least``, a quality adjective, …) is
     DETERMINISTICALLY marked constraint-bearing. Such a clause MUST yield a
     :class:`ContractTerm` — normalized or opaque. The LLM may refine but can
     never downgrade a deontic-marked clause to non-constraint.
  3. **Deterministic parsers** (generic, lexicon-driven — no per-task branch):
     quality, negation/exclusion, coordination (``A and B`` → ``IN {A,B}``), and
     date-hardness inheritance (``only … from YYYY onward`` → date GTE, hard).
     Each emits an ordinary :class:`CandidateConstraint` so the existing
     deterministic-authoritative merge author them as explicit terms.
  4. **Opaque preservation** — a deontic-marked clause that NO candidate covers
     becomes a first-class OPAQUE :class:`ContractTerm` (``normalization_status
     = opaque``, force inherited from its deontic cue, raw clause text + span,
     ``stage_owner`` best-guess). Preserved + disclosed, never silent.
  5. **Completeness validator** — every deontic-marked constraint clause must
     have a corresponding term (normalized or opaque). A clause with none →
     ``clause_undispositioned``. This is the check the candidate-only
     monotonicity validator structurally cannot make.

Everything here is CONSULTED only when ``gate_enabled()`` (PG_GATE) is ON; the
OFF path never calls into this module, so the compiled contract stays
byte-identical to the champion. The champion-shared intake extractor and the
frozen faithfulness code are NOT touched — the new parsers live here and augment
``reconcile_candidates`` output additively.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.polaris_graph.planning.candidate_adapter import (
    CandidateConstraint,
    _canonicalize_source_type,
    _ontology_source_type_index,
    _stamp_ir,
)
from src.polaris_graph.planning.candidate_adapter import (
    PromptSpan as CandSpan,
)
from src.polaris_graph.planning.planning_gate_schema import (
    FORCE_HARD,
    FORCE_PREFER,
    NORM_OPAQUE,
    OP_GTE,
    OP_IN,
    OP_NOT_IN,
    ORIGIN_EXPLICIT,
    ContractTerm,
    PromptSpan,
    ValidationError,
)

# ---------------------------------------------------------------------------
# Clause dispositions
# ---------------------------------------------------------------------------
# Every segmented clause gets exactly one disposition. ``explicit_constraint`` is
# the deontic-marked, MUST-yield-a-term class the completeness validator guards.
DISP_OBJECTIVE = "objective"                # the research question / task itself
DISP_EXPLICIT_CONSTRAINT = "explicit_constraint"  # deontic-marked; MUST yield a term
DISP_DELIVERABLE = "deliverable"            # output shape (format / length / structure)
DISP_CONTEXT = "context"                    # background / non-instructional
DISP_UNRESOLVED = "unresolved"              # segmented but not yet classified

DISPOSITIONS: frozenset[str] = frozenset({
    DISP_OBJECTIVE, DISP_EXPLICIT_CONSTRAINT, DISP_DELIVERABLE,
    DISP_CONTEXT, DISP_UNRESOLVED,
})


# ---------------------------------------------------------------------------
# Deontic / modal cue lexicon (generic; drives constraint-bearing detection)
# ---------------------------------------------------------------------------
# A clause matching ANY of these is DETERMINISTICALLY constraint-bearing. The
# lexicon is intentionally domain-neutral: it recognises the GRAMMAR of an
# instruction (restriction, prohibition, obligation, bound, quality) rather than
# any particular source noun — so a never-before-seen source kind under an
# "only …" scope is still caught. Ordered longest-first within a family so the
# matched cue phrase is the most specific verbatim trigger.

# Restriction / exclusivity (→ hard inclusion of whatever it scopes).
_CUE_RESTRICT = (
    "exclusively", "restricted to", "restrict to", "limited to", "solely",
    "strictly", "only",
)
# Prohibition / exclusion (→ hard NOT_IN of whatever it scopes). STRONG cues are
# explicit prohibition verbs (fire on any noun); the WEAK "no "/"without " cues are
# handled separately (they fire only before a source noun — see _deontic_hit) so
# ordinary prose ("no clear consensus", "without interruption") is not mistaken
# for a source exclusion.
_CUE_EXCLUDE = (
    "do not use", "do not cite", "do not quote", "do not include", "do not view",
    "don't use", "must not", "exclude", "avoid",
)
# Obligation (→ hard requirement).
_CUE_OBLIGE = (
    "must", "ensure", "required to", "you must", "make sure", "at least",
    "have to",
)
# Quality adjectives (→ source quality profile; hard under a restriction scope).
_CUE_QUALITY = (
    "high-quality", "high quality", "peer-reviewed", "peer reviewed",
    "top-tier", "top tier", "authoritative", "reputable", "credible",
)
# Preference cues (constraint-bearing but SOFT — never hard).
_CUE_PREFER = (
    "prefer", "prioritize", "prioritise", "focus on", "emphasize", "emphasise",
    "ideally", "where possible", "primarily", "mainly",
)

# Date lower-bound: "from 2024 onward(s)", "since 2024", "after 2024".
_DATE_FROM_RE = re.compile(
    r"\b(?:from|since|after)\s+(\d{4})(?:\s+onwards?)?\b", re.I
)
_DATE_ONWARD_RE = re.compile(r"\b(\d{4})\s+onwards?\b", re.I)


# A cue → (force, kind) table so a clause records WHY it is a constraint and how
# hard. ``kind`` is advisory (drives the opaque term's attribute best-guess).
def _deontic_hit(clause_text: str) -> "Optional[DeonticCue]":
    """Return the most-specific deontic cue in ``clause_text`` (or None).

    Detection is generic: any restriction/prohibition/obligation/quality/bound
    cue makes the clause constraint-bearing. Restriction+prohibition+obligation
    are HARD; a bare preference cue is SOFT; a quality adjective is HARD only when
    a restriction cue also scopes the clause (else soft). This mirrors the
    candidate layer's "force is observed, never invented" rule at the clause
    level. The returned ``cue`` is the verbatim matched phrase (a real span).
    """
    low = clause_text.lower()

    def _find(cues: tuple[str, ...]) -> Optional[str]:
        best: Optional[str] = None
        best_at = len(low) + 1
        for c in cues:
            at = low.find(c)
            if at != -1 and at < best_at:
                best, best_at = c, at
        return best

    restrict = _find(_CUE_RESTRICT)
    exclude = _find(_CUE_EXCLUDE)
    weak_exclude = _find(_EXCLUDE_LEAD_WEAK)
    oblige = _find(_CUE_OBLIGE)
    quality = _find(_CUE_QUALITY)
    prefer = _find(_CUE_PREFER)
    date_hit = _DATE_FROM_RE.search(clause_text) or _DATE_ONWARD_RE.search(clause_text)

    # A WEAK "no X"/"without X" is a hard exclusion ONLY when X is a source noun
    # (so "no blogs" fires but "no clear consensus" does not — no fabricated rule).
    if weak_exclude and not exclude:
        at = low.find(weak_exclude)
        noun = clause_text[at + len(weak_exclude):].strip().strip("\"'")
        if _is_source_noun(noun.split(",")[0].split(".")[0]):
            return DeonticCue(cue=_verbatim(clause_text, weak_exclude),
                              family="exclude", force=FORCE_HARD, attribute="kind")

    # Prohibition (a "do not"/"exclude"/"avoid X" is unambiguously a hard exclusion).
    if exclude:
        return DeonticCue(cue=_verbatim(clause_text, exclude), family="exclude",
                          force=FORCE_HARD, attribute="kind")
    if restrict:
        return DeonticCue(cue=_verbatim(clause_text, restrict), family="restrict",
                          force=FORCE_HARD, attribute="kind")
    if oblige:
        return DeonticCue(cue=_verbatim(clause_text, oblige), family="oblige",
                          force=FORCE_HARD, attribute="coverage")
    if date_hit:
        return DeonticCue(cue=date_hit.group(0), family="date",
                          force=FORCE_PREFER, attribute="published_at")
    if quality:
        return DeonticCue(cue=_verbatim(clause_text, quality), family="quality",
                          force=FORCE_PREFER, attribute="quality")
    if prefer:
        return DeonticCue(cue=_verbatim(clause_text, prefer), family="prefer",
                          force=FORCE_PREFER, attribute="")
    return None


def _verbatim(clause_text: str, low_cue: str) -> str:
    """Recover the verbatim (original-case) cue substring from ``clause_text``."""
    at = clause_text.lower().find(low_cue)
    if at == -1:
        return low_cue
    return clause_text[at:at + len(low_cue)]


@dataclass(frozen=True)
class DeonticCue:
    """The deontic cue that made a clause constraint-bearing."""

    cue: str           # verbatim matched phrase (a real prompt substring)
    family: str        # exclude | restrict | oblige | date | quality | prefer
    force: str         # hard | preference (observed from the cue family)
    attribute: str     # best-guess IR attribute (kind / quality / published_at / …)


# ---------------------------------------------------------------------------
# Clause segmentation (deterministic, stable IDs, quote-equality guaranteed)
# ---------------------------------------------------------------------------

# Split on sentence terminators / semicolons / newlines that separate independent
# instructions. We DELIBERATELY do NOT split on "and": a coordinated source phrase
# ("news and company press releases") and a trailing date modifier ("from 2024
# onward") must stay in ONE clause so the enclosing "Only …" restriction scope
# spans both — splitting on "and" would detach the coordination and the date bound
# from their hardness scope. Coordination is a WITHIN-clause parser, not a segment
# boundary. Offsets are kept exact by splitting over the ORIGINAL text and carrying
# (start, end) — never re-joining/normalizing.
_SEGMENT_RE = re.compile(r"[.;\n]+")


@dataclass
class Clause:
    """One segmented prompt clause with a stable id + verbatim span.

    ``text == prompt[start:end]`` always holds (quote-equality). ``disposition``
    is deterministic for a deontic-marked clause and may be refined (never
    downgraded) by the LLM. ``deontic`` is set iff a deontic cue fired.
    """

    clause_id: str
    start: int
    end: int
    text: str
    disposition: str = DISP_UNRESOLVED
    deontic: Optional[DeonticCue] = None
    term_ids: list[str] = field(default_factory=list)

    def is_constraint_bearing(self) -> bool:
        return self.deontic is not None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "clause_id": self.clause_id,
            "start": self.start,
            "end": self.end,
            "text": self.text,
            "disposition": self.disposition,
            "term_ids": list(self.term_ids),
        }
        if self.deontic is not None:
            out["deontic"] = {
                "cue": self.deontic.cue,
                "family": self.deontic.family,
                "force": self.deontic.force,
                "attribute": self.deontic.attribute,
            }
        return out


def segment_clauses(prompt: str) -> list[Clause]:
    """Segment ``prompt`` into stable clauses with exact spans + dispositions.

    Deterministic: same prompt → same clause ids and offsets. IDs are
    ``clause_000``, ``clause_001``, … in reading order (stable + order-addressable
    for the LLM to reference). Each clause's disposition is pre-classified from
    its deontic cue; the objective (first non-trivial clause with no cue) is
    tagged ``objective``.
    """
    prompt = prompt or ""
    clauses: list[Clause] = []
    pos = 0
    raw_segments: list[tuple[int, int]] = []
    for m in _SEGMENT_RE.finditer(prompt):
        seg_start, seg_end = pos, m.start()
        if seg_end > seg_start:
            raw_segments.append((seg_start, seg_end))
        pos = m.end()
    if pos < len(prompt):
        raw_segments.append((pos, len(prompt)))

    idx = 0
    seen_objective = False
    for (s, e) in raw_segments:
        # trim leading/trailing whitespace while keeping exact offsets.
        text = prompt[s:e]
        lstrip = len(text) - len(text.lstrip())
        rstrip = len(text) - len(text.rstrip())
        cs, ce = s + lstrip, e - rstrip
        text = prompt[cs:ce]
        if not text.strip():
            continue
        cue = _deontic_hit(text)
        clause = Clause(
            clause_id=f"clause_{idx:03d}",
            start=cs, end=ce, text=text, deontic=cue,
        )
        if cue is not None:
            if cue.family in ("exclude", "restrict", "oblige", "date", "quality", "prefer"):
                clause.disposition = DISP_EXPLICIT_CONSTRAINT
        elif not seen_objective and _looks_like_objective(text):
            clause.disposition = DISP_OBJECTIVE
            seen_objective = True
        else:
            clause.disposition = DISP_CONTEXT
        clauses.append(clause)
        idx += 1
    return clauses


# Verb-stem prefixes (no trailing \b so inflections match: "summarize",
# "analyzing", "compared"). A leading \b keeps them word-anchored.
_OBJECTIVE_HINTS = re.compile(
    r"\b(analy[sz]|compar|assess|evaluat|writ|produc|research|report|"
    r"summar|investigat|explain|describ|review|examin|study|"
    r"discuss|explor|what|how|why|which)", re.I
)


def _looks_like_objective(text: str) -> bool:
    return bool(_OBJECTIVE_HINTS.search(text)) or text.rstrip().endswith("?")


# ---------------------------------------------------------------------------
# Deterministic parsers (generic; each emits ordinary CandidateConstraints)
# ---------------------------------------------------------------------------
# These run over the WHOLE prompt and AUGMENT reconcile_candidates. They close the
# specific extractor gaps the recon named (quality adjective, unknown-kind
# exclusion, coordination, date-hardness inheritance) — generically, lexicon /
# registry driven, never a per-task branch. Every emitted candidate carries a
# verbatim span, so the existing authoritative merge treats it as an explicit
# term (or, for an unmappable value, an opaque one).


def _span(prompt: str, phrase: str) -> list[CandSpan]:
    """Locate ``phrase`` verbatim; empty list if not found (never fabricated)."""
    if not prompt or not phrase:
        return []
    at = prompt.find(phrase)
    if at == -1:
        low = prompt.lower().find(phrase.lower())
        if low == -1:
            return []
        return [CandSpan(low, low + len(phrase), prompt[low:low + len(phrase)])]
    return [CandSpan(at, at + len(phrase), prompt[at:at + len(phrase)])]


# (a) QUALITY --------------------------------------------------------------
_QUALITY_ADJ = {
    "high-quality": "high", "high quality": "high",
    "peer-reviewed": "high", "peer reviewed": "high",
    "top-tier": "high", "top tier": "high",
    "authoritative": "high", "reputable": "high", "credible": "high",
}


def parse_quality(prompt: str, *, hard_scopes: list[tuple[int, int]]) -> list[CandidateConstraint]:
    """Standalone quality adjectives → ``source.quality=high``.

    Closes the recon gap: a bare "high-quality sources" with no journal/peer
    token produced NO candidate. Hardness is inherited: a quality span sitting
    inside a hard restriction scope ("only high-quality …") is hard; otherwise a
    preference. Data-driven over ``_QUALITY_ADJ`` — never substring "journal".
    """
    out: list[CandidateConstraint] = []
    low = prompt.lower()
    seen: set[tuple[int, int]] = set()
    for adj, val in _QUALITY_ADJ.items():
        start = 0
        while True:
            at = low.find(adj, start)
            if at == -1:
                break
            start = at + len(adj)
            key = (at, at + len(adj))
            if key in seen:
                continue
            seen.add(key)
            hard = any(lo <= at and at + len(adj) <= hi for lo, hi in hard_scopes)
            out.append(_stamp_ir(CandidateConstraint(
                dimension="source.quality",
                value=val,
                force=FORCE_HARD if hard else FORCE_PREFER,
                origin="deterministic",
                spans=[CandSpan(at, at + len(adj), prompt[at:at + len(adj)])],
                detail={"source": "clause_ledger.quality", "adjective": adj},
            )))
    return out


# (b) NEGATION / EXCLUSION -------------------------------------------------
# "do not cite blogs", "no blogs", "exclude X", "avoid X" → a content.exclusion
# NOT_IN {X}. Fires even when X is NOT a known ontology facet (the recon's "do not
# cite blogs" miss) — the excluded token stays a first-class value; it is NEVER
# rendered as a positive query token.
#
# STRONG cues are explicit prohibition verbs — an author writing "do not cite X" /
# "exclude X" / "avoid X" unambiguously means a source exclusion, so they fire on
# ANY noun. WEAK cues ("no X" / "without X") appear constantly in ordinary prose
# ("no clear consensus", "without interruption"), so they fire ONLY when the noun
# is a plausible SOURCE KIND (a curated lexicon or a "… sources/media/…" pattern) —
# this stops the false-positive exclusions that would poison retrieval.
_EXCLUDE_LEAD_STRONG = (
    "do not cite", "do not use", "do not quote", "do not include", "do not view",
    "don't use", "must not use", "must not cite", "exclude", "avoid",
)
_EXCLUDE_LEAD_WEAK = ("no ", "without ")

# Source-kind nouns a WEAK negation ("no blogs") is allowed to exclude. Domain-
# neutral and small; anything else under "no"/"without" is left to the opaque net
# (never a fabricated exclusion). "sources"/"media" etc. also license a compound
# ("no paywalled sources").
_SOURCE_NOUN_TOKENS = (
    "blog", "blogs", "wikipedia", "forum", "forums", "social media", "tweet",
    "tweets", "preprint", "preprints", "press release", "press releases",
    "op-ed", "op-eds", "opinion piece", "opinion pieces", "tabloid", "tabloids",
    "sources", "source", "media", "outlets", "outlet", "websites", "website",
)
# Stop the excluded noun-phrase at a clause boundary / conjunction.
_EXCL_TAIL_RE = re.compile(r"[.,;:]|\b(?:and|or|but|from|when|where|which|that)\b", re.I)


def _is_source_noun(noun: str) -> bool:
    low = noun.lower().strip()
    return any(tok == low or low.endswith(" " + tok) or low.endswith(tok)
               for tok in _SOURCE_NOUN_TOKENS)


def parse_exclusions(prompt: str) -> list[CandidateConstraint]:
    """Generic negation/exclusion → ``content.exclusion`` NOT_IN {noun}.

    Lexicon-driven; fires on an unknown noun (the recon's blog gap). The excluded
    noun-phrase is the verbatim text between the cue and the next clause boundary.
    Always hard (an explicit prohibition) and always NOT_IN — never a positive
    query token (the projection bug the recon flagged). The verbatim span covers
    the cue through the LOCATED noun (anchored, not arithmetic — no off-by-one).

    STRONG cues fire on any noun; WEAK cues ("no"/"without") fire only on a
    plausible source-kind noun, so ordinary prose ("no clear consensus") never
    fabricates an exclusion.
    """
    out: list[CandidateConstraint] = []
    low = prompt.lower()
    seen_vals: set[str] = set()
    # (cue, is_weak); longest strong cues first so "do not cite" wins over prefixes.
    leads = [(c, False) for c in sorted(_EXCLUDE_LEAD_STRONG, key=len, reverse=True)]
    leads += [(c, True) for c in _EXCLUDE_LEAD_WEAK]
    for lead, is_weak in leads:
        start = 0
        while True:
            at = low.find(lead, start)
            if at == -1:
                break
            start = at + len(lead)
            cue_end = at + len(lead)
            rest = prompt[cue_end:]
            # skip whitespace so the located noun offset is exact.
            ws = len(rest) - len(rest.lstrip())
            noun_at = cue_end + ws
            rest = prompt[noun_at:]
            m = _EXCL_TAIL_RE.search(rest)
            noun = (rest[:m.start()] if m else rest).strip().strip("\"'")
            if not noun or len(noun) > 60:
                continue
            # a WEAK cue only excludes a plausible source kind (never prose).
            if is_weak and not _is_source_noun(noun):
                continue
            val = noun.rstrip("s").lower() if noun.lower().endswith("s") else noun.lower()
            if val in seen_vals:
                continue
            seen_vals.add(val)
            noun_end = noun_at + len(noun)
            out.append(_stamp_ir(CandidateConstraint(
                dimension="content.exclusion",
                value=noun.lower(),
                force=FORCE_HARD,
                origin="deterministic",
                spans=[CandSpan(at, noun_end, prompt[at:noun_end])],
                detail={"source": "clause_ledger.exclusion", "cue": lead.strip()},
            )))
    return out


# (c) COORDINATION ---------------------------------------------------------
# "A and B", "A, B, or C" inside a source/kind phrase → value_set IN {A,B,C}. The
# IR supports OP_IN/value_set but nothing populated boolean_group; this does.
#
# A coordinated SOURCE list: a source-lead ("only use", "cite", "sources are"),
# then a list of noun-phrases joined by commas + a final "and"/"or". We capture
# the WHOLE list in one regex group so overlapping leads don't produce garbage
# members, then split it cleanly and drop trailing prepositional/date fragments.
_COORD_RE = re.compile(
    r"\b(?:only\s+)?(?:use|cite|include|sources?\s+(?:are|of|from|include)|"
    r"(?:limited|restricted)\s+to)\s+"
    r"(?P<list>[A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3}"
    r"(?:\s*,\s*[A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})*"
    r"\s*(?:,\s*)?(?:and|or)\s+"
    r"[A-Za-z][\w\-]*(?:\s+[A-Za-z][\w\-]*){0,3})",
    re.I,
)

# a trailing preposition/date fragment on the last member ("… releases from") is
# not part of the source kind — strip it.
_MEMBER_TAIL_RE = re.compile(
    r"\s+\b(?:from|since|after|before|in|on|of|for|dated?)\b.*$", re.I
)


def parse_coordination(prompt: str, *, hard_scopes: list[tuple[int, int]]) -> list[CandidateConstraint]:
    """Coordinated source-kind sets ("news and company press releases") →
    one candidate per member sharing a ``boolean_group`` (IN semantics).

    Generic: it does not hard-code the member nouns. Each member becomes a
    ``source.types`` candidate; an unknown member stays a first-class value the
    reconcile-alias pass later marks opaque. Hard iff the coordinated phrase sits
    inside a restriction scope. The shared ``boolean_group`` id lets the IR read
    the members as one allowed set. Overlapping leads are de-duplicated by the
    captured list span.
    """
    out: list[CandidateConstraint] = []
    seen_lists: set[tuple[int, int]] = set()
    for m in _COORD_RE.finditer(prompt):
        list_start, list_end = m.start("list"), m.end("list")
        if (list_start, list_end) in seen_lists:
            continue
        seen_lists.add((list_start, list_end))
        raw = prompt[list_start:list_end]
        members = _clean_members(_split_members(raw))
        if len(members) < 2:
            continue
        hard = any(lo <= list_start and list_end <= hi for lo, hi in hard_scopes)
        group_id = f"coord.{list_start}_{list_end}"
        for member in members:
            cand = _stamp_ir(CandidateConstraint(
                dimension="source.types",
                value=member.lower(),
                force=FORCE_HARD if hard else FORCE_PREFER,
                origin="deterministic",
                spans=_span(prompt, member),
                detail={
                    "source": "clause_ledger.coordination",
                    "boolean_group": group_id,
                    "member_of": raw.strip(),
                },
            ))
            cand.operator = OP_IN
            out.append(cand)
    return out


_SPLIT_RE = re.compile(r"\s*,\s*|\s+\band\b\s+|\s+\bor\b\s+", re.I)
# a leading conjunction the split left behind on an Oxford-comma member
# (", and analyst reports" → "and analyst reports" → "analyst reports").
_LEADING_CONJ_RE = re.compile(r"^(?:and|or)\s+", re.I)


def _split_members(raw: str) -> list[str]:
    return [p for p in _SPLIT_RE.split(raw.strip()) if p and p.strip()]


def _clean_members(members: list[str]) -> list[str]:
    """Strip a leading conjunction (Oxford comma) and a trailing preposition/date
    fragment from each member; drop empties/dupes (order-preserving)."""
    out: list[str] = []
    seen: set[str] = set()
    for mem in members:
        mem = _LEADING_CONJ_RE.sub("", mem)
        mem = _MEMBER_TAIL_RE.sub("", mem).strip()
        if not mem:
            continue
        key = mem.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(mem)
    return out


# (d) DATE-HARDNESS INHERITANCE -------------------------------------------
# "only … from 2024 onward" → date GTE 2024 with force=HARD. The existing
# language-inside-a-hard-only inheritance (research_planning_gate:600) is
# generalized here to a date bound: a date lower-bound span inside a hard
# restriction scope inherits hardness.


def parse_date_bound(prompt: str, *, hard_scopes: list[tuple[int, int]]) -> list[CandidateConstraint]:
    """"from/since/after YYYY [onward]" → ``date.recency`` GTE YYYY-01-01.

    Hard iff the date span sits inside a hard restriction scope ("only … from
    2024 onward"). This is the date analogue of the language hardness-inheritance
    the post-inversion core already does for source-language — generalized so a
    date bound under an "only" scope is not silently soft.
    """
    out: list[CandidateConstraint] = []
    seen_years: set[str] = set()
    # _DATE_FROM_RE is the more specific pattern (it captures "from … onward"), so
    # run it first; _DATE_ONWARD_RE only fills a bare "2024 onwards" with no lead.
    for rx in (_DATE_FROM_RE, _DATE_ONWARD_RE):
        for m in rx.finditer(prompt):
            year = m.group(1)
            if year in seen_years:
                continue
            seen_years.add(year)
            at, end = m.start(), m.end()
            hard = any(lo <= at and end <= hi for lo, hi in hard_scopes)
            cand = _stamp_ir(CandidateConstraint(
                dimension="date.recency",
                value=f"{year}-01-01",
                force=FORCE_HARD if hard else FORCE_PREFER,
                origin="deterministic",
                spans=[CandSpan(at, end, prompt[at:end])],
                detail={"source": "clause_ledger.date_bound", "year": year},
            ))
            cand.operator = OP_GTE
            out.append(cand)
    return out


# ---------------------------------------------------------------------------
# Hard restriction scopes (the enclosing spans that confer hardness)
# ---------------------------------------------------------------------------

def hard_restriction_scopes(clauses: list[Clause]) -> list[tuple[int, int]]:
    """Verbatim spans of every clause whose deontic cue is a HARD restriction /
    prohibition / obligation. A quality/date/coordination span enclosed by one of
    these inherits its hardness — the generalized "only"-scope rule."""
    scopes: list[tuple[int, int]] = []
    for c in clauses:
        if c.deontic is not None and c.deontic.family in ("restrict", "exclude", "oblige") \
                and c.deontic.force == FORCE_HARD:
            scopes.append((c.start, c.end))
    return scopes


# ---------------------------------------------------------------------------
# Ledger parsers driver — augment reconcile_candidates output
# ---------------------------------------------------------------------------

def ledger_candidates(
    prompt: str, clauses: list[Clause], *, ontology: "dict[str, Any] | None" = None,
) -> list[CandidateConstraint]:
    """Run every deterministic ledger parser and return the augmenting candidates.

    Additive to ``reconcile_candidates``: these catch the constraints the champion
    intake extractor structurally misses (bare quality, unknown-kind exclusion,
    coordination, date-hardness inheritance). All hardness is scope-inherited from
    the clause segmentation — never invented.

    Source-kind values are canonicalized against the same ontology alias index
    ``reconcile_candidates`` uses, and an UNMAPPED kind is marked ``opaque`` (a
    first-class value, honestly surfaced as blocked_unsupported rather than
    silently claimed enforceable) — mirroring the adapter's own opaque discipline.
    """
    scopes = hard_restriction_scopes(clauses)
    out: list[CandidateConstraint] = []
    out.extend(parse_quality(prompt, hard_scopes=scopes))
    out.extend(parse_exclusions(prompt))
    out.extend(parse_coordination(prompt, hard_scopes=scopes))
    out.extend(parse_date_bound(prompt, hard_scopes=scopes))

    # Ontology-canonicalize source-kind members; an unmapped kind stays verbatim
    # and is marked opaque (never dropped) — the same pass reconcile_candidates
    # applies, so a ledger member and an intake facet reconcile identically.
    alias_index = _ontology_source_type_index(ontology)
    if alias_index:
        for cand in out:
            if cand.dimension == "source.types":
                canon, mapped = _canonicalize_source_type(cand.value, alias_index)
                cand.value = canon
                if not mapped:
                    cand.normalization_status = NORM_OPAQUE
    return out


# ---------------------------------------------------------------------------
# Opaque preservation — a deontic clause no TERM covered becomes a term
# ---------------------------------------------------------------------------

def opaque_terms_for_uncovered(
    prompt: str, clauses: list[Clause], contract: Any,
) -> list[ContractTerm]:
    """Author an OPAQUE :class:`ContractTerm` for every deontic-marked constraint
    clause that NO existing CONTRACT TERM span overlaps.

    This is the lossless guarantee that does not depend on an extractor existing:
    a constraint-bearing clause the deterministic parsers could not normalize into
    a surviving term is preserved verbatim as ``normalization_status=opaque`` —
    force inherited from its deontic cue, raw clause text + span, ``stage_owner``
    best-guess. It is ``origin=explicit`` (a real span) so it is authoritative,
    but opaque so the enforcement state honestly becomes ``blocked_unsupported`` —
    never silence.

    Coverage is keyed on the CONTRACT'S OWN TERMS (LLM + deterministic-authored),
    the SAME basis :func:`validate_completeness` uses. So a clause covered only by
    a candidate that never became a term (e.g. a deliverable candidate the merge
    path does not author) still gets an opaque term here, and completeness cannot
    then flag it — the two checks share one coverage definition (no phantom
    ``clause_undispositioned``).
    """
    # every contract-term span (opaque or normalized).
    term_spans: list[tuple[int, int]] = [
        (sp.start, sp.end) for term in contract.all_terms() for sp in term.spans
    ]

    def _covered(clause: Clause) -> bool:
        for (s, e) in term_spans:
            if s < clause.end and e > clause.start:
                return True
        return False

    terms: list[ContractTerm] = []
    n = 0
    for clause in clauses:
        if not clause.is_constraint_bearing():
            continue
        if _covered(clause):
            continue
        cue = clause.deontic
        assert cue is not None
        n += 1
        # subject/attribute best-guess from the cue family.
        subject = "source"
        stage_owner = "eligibility"
        if cue.family == "oblige":
            subject, stage_owner = "topic", "compose"
        term = ContractTerm(
            term_id=f"opaque.{clause.clause_id}",
            dimension="scope.opaque" if subject == "source" else "content.opaque",
            value=clause.text,
            origin=ORIGIN_EXPLICIT,
            force=cue.force,
            spans=[PromptSpan(clause.start, clause.end, clause.text)],
            subject=subject,
            attribute=cue.attribute or "constraint",
            operator=OP_NOT_IN if cue.family == "exclude" else OP_IN,
            value_set=[clause.text],
            stage_owner=stage_owner,
            normalization_status=NORM_OPAQUE,
            enforcement_stages=["retrieval"],
            rationale=(
                f"lossless opaque: deontic clause ({cue.family!r} cue "
                f"{cue.cue!r}) has no deterministic normalization — preserved "
                f"verbatim, surfaced as blocked_unsupported (never dropped)"
            ),
        )
        clause.term_ids.append(term.term_id)
        terms.append(term)
    return terms


# ---------------------------------------------------------------------------
# Completeness validator — every deontic constraint clause has a term
# ---------------------------------------------------------------------------

def _clause_covered_by_terms(
    clause: Clause, term_spans: list[tuple[int, int, str]],
) -> Optional[str]:
    """Return a covering term_id if any contract term's span overlaps the clause."""
    for (s, e, tid) in term_spans:
        if s < clause.end and e > clause.start:
            return tid
    return None


def validate_completeness(
    clauses: list[Clause], contract: Any,
) -> list[ValidationError]:
    """COMPLETENESS invariant (the lossless gate): every deontic-marked constraint
    clause has a corresponding :class:`ContractTerm` (normalized OR opaque).

    Keys off the PROMPT (the ledger), not the extractor output — this is the check
    ``validate_monotonicity`` structurally cannot make. A constraint-bearing clause
    with no covering term → ``clause_undispositioned`` (fatal interactive;
    autonomous preserves it as opaque and marks ``degraded_lossless``). Also flags
    ``clause_downgraded`` if a deontic clause's disposition was moved off
    ``explicit_constraint`` (the LLM tried to demote a hard constraint to context).
    """
    errors: list[ValidationError] = []
    # index every contract-term span (opaque terms included).
    term_spans: list[tuple[int, int, str]] = []
    for term in contract.all_terms():
        for sp in term.spans:
            term_spans.append((sp.start, sp.end, term.term_id))

    for clause in clauses:
        if not clause.is_constraint_bearing():
            continue
        # A deontic constraint clause must remain dispositioned as a constraint.
        if clause.disposition not in (DISP_EXPLICIT_CONSTRAINT, DISP_DELIVERABLE):
            errors.append(ValidationError(
                "clause_downgraded",
                f"deontic constraint clause {clause.clause_id!r} "
                f"({clause.deontic.cue!r}) was downgraded to "
                f"disposition={clause.disposition!r}",
                term_id=clause.clause_id,
            ))
        covering = _clause_covered_by_terms(clause, term_spans)
        if covering is None and not clause.term_ids:
            errors.append(ValidationError(
                "clause_undispositioned",
                f"deontic constraint clause {clause.clause_id!r} "
                f"(cue {clause.deontic.cue!r}, text {clause.text!r}) has no "
                f"corresponding contract term — a stated constraint would vanish",
                term_id=clause.clause_id,
            ))
    return errors
