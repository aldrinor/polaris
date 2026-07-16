"""Candidate constraint adapter (Research Planning Gate — S0).

Reconciles the two independent deterministic "rule readers" the champion tree
now carries into ONE list of candidate constraints, each with exact prompt
spans and an origin tag:

  * the ported adversarial rule-reader
    (:mod:`src.polaris_graph.instruction.constraint_extractor`), which returns a
    :class:`~...instruction.constraint_extractor.Constraints` bundle
    (source_types / languages / recency / required_coverage / exclusions /
    format / length / tone); and
  * the champion intake extractors
    (:mod:`src.polaris_graph.retrieval.intake_constraint_extractor`) — the
    deterministic regex passes ``extract_constraints_regex`` (dates + language +
    journal-only + timeline strictness), ``extract_instruction_slots_regex``
    (comparisons / enumerations / topics / structure), and
    ``extract_scope_constraints_regex`` (source-type / jurisdiction facets +
    named sources).

Design contract (S0 — port + reconcile, NO behavior change)
-----------------------------------------------------------
* **This is a candidate list, NOT a pinned contract.** The output is the
  high-recall raw material a later contract compiler validates and pins. Nothing
  here hard-gates, excludes, or filters anything, and nothing here is wired into
  the pipeline. Callers decide what (if anything) to do with the result.
* **Deterministic wins on overlap.** When a rule-reader value and an intake
  regex value describe the same ``(dimension, canonical value)``, the intake
  (regex) candidate is authoritative for span + force; the rule-reader only
  *fills gaps* it uniquely found. Origin is recorded so the merge is auditable.
* **Exact spans preserved.** Every candidate carries the verbatim prompt spans
  that fired it, recovered as ``prompt[start:end]`` with quote equality. A span
  is emitted ONLY when the trigger substring is actually located in the prompt;
  an offset is never fabricated. Values whose trigger phrase cannot be located
  keep the value but carry an empty span list (so the compiler can still see the
  candidate, but can never treat it as span-supported / ``explicit``).
* **Force is observed, never invented.** ``hard`` appears only where a
  deterministic source already marked an exclusivity / prohibition token (intake
  ``strictness == 'hard'``, a named-exclude, or a rule-reader exclusion). Every
  other candidate is ``prefer``. This module never promotes a soft phrasing to
  hard — that is the mechanical no-invention guarantee at the candidate layer.
* **Pure + offline.** No network, no LLM construction. The rule-reader's live
  pass is the caller's responsibility; this adapter takes its already-computed
  ``Constraints`` (or dict) as input. Default: if the caller passes no
  rule-reader result, the adapter reconciles the intake extractors alone.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from src.polaris_graph.instruction.constraint_extractor import Constraints
from src.polaris_graph.retrieval.intake_constraint_extractor import (
    _JOURNAL_ONLY_RE,
    InstructionSlot,
    ScopeConstraints,
    UserConstraints,
    extract_constraints_regex,
    extract_instruction_slots_regex,
    extract_scope_constraints_regex,
)

# ---------------------------------------------------------------------------
# Origin + force vocab (candidate layer — deliberately small)
# ---------------------------------------------------------------------------

# Where a candidate came from. `deterministic` = one of the intake regex passes
# (authoritative on overlap). `rule_reader` = the ported adversarial extractor
# (gap-filler). `merged` = both sources agreed on the same (dimension, value).
ORIGIN_DETERMINISTIC = "deterministic"
ORIGIN_RULE_READER = "rule_reader"
ORIGIN_MERGED = "merged"

# Observed force. NEVER invented: `hard` only when a deterministic source already
# marked an exclusivity/prohibition; everything else is `prefer`.
FORCE_HARD = "hard"
FORCE_PREFER = "prefer"


# ---------------------------------------------------------------------------
# GENERIC candidate→canonical REGISTRY (data-driven; NOT per-type if-branches)
# ---------------------------------------------------------------------------
# One row per candidate DIMENSION. Each row declares, generically:
#   canonical      the canonical contract dimension the projection reads
#   subject        the IR subject axis (source / evidence / output / section / topic)
#   attribute      the IR attribute axis (kind / quality / language / published_at / ...)
#   operator       the default generic operator this dimension asserts
#   stage_owner    which stage OWNS the term (no category leakage: a deliverable
#                  format term is owned by render, never retrieval)
# Adding a new constraint family = one row here, not a new Python branch. Source
# KIND normalization is driven by the ONTOLOGY facet's own ``dimension`` field
# (see ``_from_scope_constraints``), never by substring "journal"/"peer" matching.
#
# ``operator`` here is the GENERIC relation used to build the IR; the legacy
# ``dimension``/``value`` still carry the flat value the current projection reads.

@dataclass(frozen=True)
class _RegistryRow:
    canonical: str
    subject: str
    attribute: str
    operator: str          # IN / NOT_IN / EQ / GTE / BETWEEN / REQUIRE / PREFER
    stage_owner: str       # retrieval / ranking / eligibility / compose / render


# Operators mirror planning_gate_schema.OPERATORS (kept as bare strings so this
# module stays import-light; validate_contract checks membership).
_OP_IN = "IN"
_OP_NOT_IN = "NOT_IN"
_OP_EQ = "EQ"
_OP_GTE = "GTE"
_OP_BETWEEN = "BETWEEN"
_OP_REQUIRE = "REQUIRE"
_OP_PREFER = "PREFER"

CANDIDATE_REGISTRY: dict[str, _RegistryRow] = {
    # source-side constraints → shape the citable source set (retrieval/eligibility)
    "source.types":       _RegistryRow("scope.source_types",     "source", "kind",         _OP_IN,      "eligibility"),
    "source.quality":     _RegistryRow("scope.source_quality",   "source", "quality",      _OP_EQ,      "eligibility"),
    "source.language":    _RegistryRow("scope.source_languages", "source", "language",     _OP_IN,      "eligibility"),
    "source.scope_facet": _RegistryRow("scope.source_types",     "source", "kind",         _OP_IN,      "eligibility"),
    "source.jurisdiction":_RegistryRow("scope.jurisdiction",     "source", "jurisdiction", _OP_IN,      "retrieval"),
    "source.named":       _RegistryRow("scope.named_source",     "source", "identity",     _OP_IN,      "retrieval"),
    "date.recency":       _RegistryRow("scope.date",             "source", "published_at", _OP_GTE,     "retrieval"),
    # content-side → planning / compose obligations & exclusions
    "content.exclusion":  _RegistryRow("content.exclusion",      "source", "kind",         _OP_NOT_IN,  "eligibility"),
    "content.coverage":   _RegistryRow("content.coverage",       "topic",  "coverage",     _OP_REQUIRE, "compose"),
    "content.comparison": _RegistryRow("content.comparison",     "topic",  "comparison",   _OP_REQUIRE, "compose"),
    "deliverable.structure": _RegistryRow("deliverable.structure", "output", "structure",  _OP_REQUIRE, "render"),
    # deliverable / rhetoric → render/compose only (NEVER retrieval — no leakage)
    "deliverable.format": _RegistryRow("deliverable.format",     "output", "format",       _OP_EQ,      "render"),
    "deliverable.length": _RegistryRow("deliverable.length",     "output", "length",       _OP_EQ,      "render"),
    "rhetoric.tone":      _RegistryRow("rhetoric.tone",          "output", "tone",         _OP_PREFER,  "compose"),
}

# The subject/attribute pair for a candidate dimension, for merge reconciliation.
# Two candidates that share (subject, attribute) describe the SAME axis even if
# their raw ``(dimension, value)`` differ (e.g. rule-reader source.types
# "journal_article" and intake source.scope_facet "peer_reviewed_journal") — the
# old exact-(dimension,value) overlap key missed that (RECON-2 §3).


# Value-level normalization: some source-type TOKENS are really QUALITY markers,
# not kinds (a "high_quality"/"peer_reviewed" directive selects a quality profile
# over metadata, per RECON-2 §4 — it must NOT be treated as a literal source kind
# nor invented from a plain "journal" facet). This is a small DATA map, keyed by
# value, applied uniformly wherever a source-type value arrives — it never fires
# off substring "journal"/"peer" in a facet id (that was the invented-quality bug).
_QUALITY_VALUE_TOKENS: dict[str, str] = {
    "high_quality": "high",
    "high": "high",
    "peer_reviewed": "high",
    "peer-reviewed": "high",
    "peer_review": "high",
}


def _ontology_source_type_index(
    ontology: "dict[str, Any] | None",
) -> dict[str, str]:
    """Build a synonym→facet_id index for ``source_type`` facets from the ontology.

    This is the generic candidate→canonical alias table (RECON-2 §4): it maps
    every surface phrasing AND the canonical facet_id itself to the facet_id, so a
    rule-reader alias ("journal_article"/"journal article") and an intake facet
    ("peer_reviewed_journal") reconcile to ONE canonical value BEFORE the overlap
    key runs — closing the alias-under-different-dimensions merge gap (RECON-2 §3).
    Adding a source kind is a YAML block, not a Python branch. Fail-soft to {}.
    """
    idx: dict[str, str] = {}
    try:
        if ontology is None:
            from src.polaris_graph.retrieval.scope_facet_classifier import (  # noqa: PLC0415
                load_scope_ontology,
            )
            ontology = load_scope_ontology()
        for facet in (ontology.get("facets") or []):
            if not isinstance(facet, dict):
                continue
            if str(facet.get("dimension") or "source_type") != "source_type":
                continue
            fid = str(facet.get("id") or "").strip()
            if not fid:
                continue
            idx[fid.lower()] = fid
            idx[fid.replace("_", " ").lower()] = fid
            for syn in (facet.get("synonyms") or []):
                s = str(syn).strip().lower()
                if s:
                    idx[s] = fid
    except Exception:  # noqa: BLE001 — fail-open: no alias index, no reconciliation
        return {}
    return idx


def _canonicalize_source_type(
    value: Optional[str], alias_index: dict[str, str]
) -> tuple[Optional[str], bool]:
    """Map a source-type value to its ontology facet_id. Returns (canonical,
    mapped). Tries the value, its underscore/space variants, and a plural-stripped
    form. Unmapped → (value, False) so an unknown kind stays a first-class OPAQUE
    value, never dropped."""
    if not value:
        return value, False
    for cand in (
        value.strip().lower(),
        value.strip().replace("_", " ").lower(),
        value.strip().replace(" ", "_").lower(),
        value.strip().rstrip("s").lower(),
    ):
        if cand in alias_index:
            return alias_index[cand], True
    return value, False


def _registry_row(dimension: str) -> Optional[_RegistryRow]:
    return CANDIDATE_REGISTRY.get(dimension)


def _reroute_quality(dimension: str, value: Optional[str]) -> tuple[str, Optional[str]]:
    """If ``value`` is a QUALITY marker on a source-type dimension, reroute it to
    ``source.quality`` with the canonical quality value. Otherwise pass through.
    Data-driven (``_QUALITY_VALUE_TOKENS``), never substring branching."""
    if dimension in ("source.types",):
        q = _QUALITY_VALUE_TOKENS.get((value or "").strip().lower())
        if q is not None:
            return "source.quality", q
    return dimension, value


def candidate_term_id(c: "CandidateConstraint") -> str:
    """A STABLE term_id for a candidate, so the deterministic-authoritative core
    and the monotonicity validator can address the same term across compile.

    Keyed by canonical (subject, attribute, casefolded value) — stable across
    re-runs and independent of list order. This is the id the compiler pins and
    ``validate_monotonicity`` checks survived."""
    row = _registry_row(c.dimension)
    subj = row.subject if row else "source"
    attr = row.attribute if row else (c.dimension.split(".", 1)[-1] or "value")
    val = (c.value or "").strip().casefold()
    val = re.sub(r"[^a-z0-9]+", "_", val).strip("_") or "any"
    return f"det.{subj}.{attr}.{val}"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptSpan:
    """A verbatim prompt span. ``quote`` MUST equal ``prompt[start:end]``.

    Constructed only via :func:`_locate_span`, which guarantees that invariant;
    a value whose trigger phrase is not found in the prompt yields NO span (the
    candidate is emitted with an empty span list) rather than a fabricated one.
    """

    start: int
    end: int
    quote: str

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "quote": self.quote}


@dataclass
class CandidateConstraint:
    """One reconciled candidate constraint (NOT a pinned contract term).

    ``dimension`` is a stable string in the same open family the gate schema
    uses (e.g. ``source.types``, ``source.language``, ``date.recency``,
    ``content.coverage``, ``content.comparison``, ``deliverable.format``,
    ``deliverable.length``, ``rhetoric.tone``, ``source.named``,
    ``source.scope_facet``, ``source.jurisdiction``).
    """

    dimension: str
    value: Optional[str]
    force: str = FORCE_PREFER          # observed force; never invented as hard
    origin: str = ORIGIN_DETERMINISTIC
    spans: list[PromptSpan] = field(default_factory=list)
    # free-form provenance so the reconciliation stays auditable (which raw
    # source(s) contributed, the raw trigger phrase, any op/strictness, etc.).
    detail: dict[str, Any] = field(default_factory=dict)
    # generic-IR annotations (registry-derived; OPTIONAL). ``normalization_status``
    # is 'opaque' for a kind the registry couldn't map — preserved, never dropped.
    subject: str = ""
    attribute: str = ""
    operator: str = ""
    stage_owner: str = ""
    normalization_status: str = ""     # exact | proposed | opaque

    def canonical_dimension(self) -> str:
        row = _registry_row(self.dimension)
        return row.canonical if row else self.dimension

    def to_dict(self) -> dict[str, Any]:
        out = {
            "dimension": self.dimension,
            "value": self.value,
            "force": self.force,
            "origin": self.origin,
            "spans": [s.to_dict() for s in self.spans],
            "detail": dict(self.detail),
        }
        if self.subject:
            out["subject"] = self.subject
        if self.attribute:
            out["attribute"] = self.attribute
        if self.operator:
            out["operator"] = self.operator
        if self.stage_owner:
            out["stage_owner"] = self.stage_owner
        if self.normalization_status:
            out["normalization_status"] = self.normalization_status
        return out


# ---------------------------------------------------------------------------
# Span recovery (exact, quote-equality-guaranteed, never fabricated)
# ---------------------------------------------------------------------------

def _locate_span(prompt: str, phrase: Optional[str]) -> Optional[PromptSpan]:
    """Return the first exact occurrence of ``phrase`` in ``prompt`` as a span.

    Guarantees ``span.quote == prompt[span.start:span.end]``. Returns ``None``
    (no span) when ``phrase`` is empty or cannot be located verbatim — the
    adapter never invents an offset for a phrase it can't find.
    """
    if not prompt or not phrase:
        return None
    idx = prompt.find(phrase)
    if idx == -1:
        # Fall back to a case-insensitive locate, but keep the ACTUAL prompt
        # substring as the quote so quote-equality still holds exactly.
        low_i = prompt.lower().find(phrase.lower())
        if low_i == -1:
            return None
        return PromptSpan(low_i, low_i + len(phrase), prompt[low_i:low_i + len(phrase)])
    return PromptSpan(idx, idx + len(phrase), prompt[idx:idx + len(phrase)])


def _spans_for(prompt: str, phrases: list[Optional[str]]) -> list[PromptSpan]:
    """Locate each phrase; drop those not found; dedup by (start, end)."""
    out: list[PromptSpan] = []
    seen: set[tuple[int, int]] = set()
    for ph in phrases:
        sp = _locate_span(prompt, ph)
        if sp is None:
            continue
        key = (sp.start, sp.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(sp)
    return out


def _stamp_ir(c: CandidateConstraint, *, opaque: bool = False) -> CandidateConstraint:
    """Fill a candidate's generic-IR fields from the registry (in place).

    The candidate's RAW dimension keys the registry; the row supplies the
    canonical subject/attribute/operator/stage_owner. ``normalization_status`` is
    ``exact`` when the registry recognized the dimension, else ``opaque`` — an
    opaque candidate is a FIRST-CLASS constraint we preserve verbatim, never drop
    (the monotonic-lossless core principle). Returns the same candidate.
    """
    row = _registry_row(c.dimension)
    if row is not None:
        c.subject = row.subject
        c.attribute = row.attribute
        # exclusion flips IN→NOT_IN already encoded in the row; a hard "only X"
        # keeps the row operator. A soft candidate stays PREFER-shaped only when
        # the row itself is PREFER; otherwise the operator reflects the relation
        # (force carries hard/soft separately).
        c.operator = row.operator
        c.stage_owner = row.stage_owner
        c.normalization_status = "opaque" if opaque else "exact"
    else:
        # unknown dimension: keep it, mark opaque, route generically.
        c.subject = "source"
        c.attribute = c.dimension.split(".", 1)[-1] or "value"
        c.normalization_status = "opaque"
    return c


# ---------------------------------------------------------------------------
# Per-dimension candidate builders from each deterministic source
# ---------------------------------------------------------------------------

def _from_user_constraints(
    prompt: str, uc: UserConstraints
) -> list[CandidateConstraint]:
    """Intake ``extract_constraints_regex`` -> candidates (dates, language,
    journal-only, timeline strictness)."""
    out: list[CandidateConstraint] = []

    # Language (ISO code). Recover the span from the raw directive that named it.
    if uc.language:
        spans = _spans_for(prompt, list(uc.raw_directives))
        out.append(_stamp_ir(CandidateConstraint(
            dimension="source.language",
            value=uc.language,
            force=FORCE_PREFER,
            origin=ORIGIN_DETERMINISTIC,
            spans=spans,
            detail={"source": "intake_regex", "raw_directives": list(uc.raw_directives)},
        )))

    # Date window (start/end). Force reflects the extractor's own strictness.
    if uc.date_start_year is not None or uc.date_end_year is not None:
        force = FORCE_HARD if uc.timeline_strictness == "hard" else FORCE_PREFER
        trigger_phrases: list[Optional[str]] = list(uc.raw_directives)
        if uc.timeline_trigger_span:
            trigger_phrases.append(uc.timeline_trigger_span)
        out.append(_stamp_ir(CandidateConstraint(
            dimension="date.recency",
            value=_date_value(uc),
            force=force,
            origin=ORIGIN_DETERMINISTIC,
            spans=_spans_for(prompt, trigger_phrases),
            detail={
                "source": "intake_regex",
                "date_start_iso": uc.date_start_iso(),
                "date_end_iso": uc.date_end_iso(),
                "timeline_strictness": uc.timeline_strictness,
                "timeline_trigger_span": uc.timeline_trigger_span,
            },
        )))

    # Journal-only is EXTRACTED-but-DORMANT in the champion (operator veto). It
    # is a real deterministic signal, so it becomes a candidate — never a hard
    # gate from this path alone. SPAN-LOSS FIX (RECON-2 §2.2): the regex DID match
    # a verbatim substring; re-locate that exact match phrase in the prompt so the
    # candidate carries a real span and is promotable/explicit — not spans=[].
    if uc.journal_only:
        m = _JOURNAL_ONLY_RE.search(prompt or "")
        spans = _spans_for(prompt, [m.group(0)]) if m else []
        out.append(_stamp_ir(CandidateConstraint(
            dimension="source.types",
            value="journal_article",
            force=FORCE_PREFER,
            origin=ORIGIN_DETERMINISTIC,
            spans=spans,
            detail={
                "source": "intake_regex",
                "journal_only_dormant": True,
                "raw_trigger": m.group(0) if m else "",
            },
        )))

    return out


def _date_value(uc: UserConstraints) -> Optional[str]:
    lo = uc.date_start_iso()
    hi = uc.date_end_iso()
    if lo and hi:
        return f"{lo}..{hi}"
    return lo or hi


def _from_instruction_slots(
    prompt: str, slots: list[InstructionSlot]
) -> list[CandidateConstraint]:
    """Intake ``extract_instruction_slots_regex`` -> content/coverage candidates.

    Comparisons, enumerations, requested topics and structure are coverage
    obligations (NOT headings — that mapping is deliberately not ported). Each
    slot's verbatim ``text`` recovers its span.
    """
    out: list[CandidateConstraint] = []
    for slot in slots:
        dim = {
            "comparison": "content.comparison",
            "enumeration": "content.coverage",
            "topic": "content.coverage",
            "structure": "deliverable.structure",
        }.get(slot.kind, "content.coverage")
        out.append(_stamp_ir(CandidateConstraint(
            dimension=dim,
            value=", ".join(slot.entities) if slot.entities else slot.text,
            force=FORCE_PREFER,
            origin=ORIGIN_DETERMINISTIC,
            spans=_spans_for(prompt, [slot.text]),
            detail={
                "source": "intake_regex",
                "slot_id": slot.slot_id,
                "slot_kind": slot.kind,
                "entities": list(slot.entities),
            },
        )))
    return out


def _from_scope_constraints(
    prompt: str, sc: ScopeConstraints
) -> list[CandidateConstraint]:
    """Intake ``extract_scope_constraints_regex`` -> scope-facet / named-source
    candidates. Force mirrors the facet's own strictness (hard only where the
    extractor already saw an exclusivity/prohibition token)."""
    out: list[CandidateConstraint] = []

    for facet in sc.facets:
        # GENERIC candidate→canonical (RECON-2 §4): route by the ONTOLOGY facet's
        # OWN ``dimension`` field, NOT by substring "journal"/"peer" matching. A
        # ``source_type`` facet → source.scope_facet (→ scope.source_types); a
        # ``language`` facet → source.language; jurisdiction/geography → their own
        # canonical dimension. Adding a facet family is data (a YAML block), not
        # a Python branch.
        fdim = (facet.dimension or "source_type").strip().lower()
        dim = {
            "jurisdiction": "source.jurisdiction",
            "geography": "source.jurisdiction",
            "language": "source.language",
        }.get(fdim, "source.scope_facet")
        # An ``exclude`` op is a NOT_IN exclusion, not an inclusion.
        if facet.op == "exclude":
            dim = "content.exclusion"
        force = FORCE_HARD if facet.strictness == "hard" else FORCE_PREFER
        out.append(_stamp_ir(CandidateConstraint(
            dimension=dim,
            value=facet.facet_id,
            force=force,
            origin=ORIGIN_DETERMINISTIC,
            # locate the RAW trigger phrase the user wrote (facet.trigger_span is a
            # verbatim prompt slice), NOT the canonical facet_id — the span-loss-
            # safe pattern this whole rebuild generalizes (RECON-2 §2.4).
            spans=_spans_for(prompt, [facet.trigger_span]),
            detail={
                "source": "intake_regex",
                "op": facet.op,
                "strictness": facet.strictness,
                "facet_dimension": facet.dimension,
                "raw_trigger": facet.trigger_span,
            },
        )))

    for named in list(sc.named_include) + list(sc.named_exclude):
        # A named-exclude is always hard (identity-enforced downstream); a
        # named-include is a boost (prefer).
        force = FORCE_HARD if named.strictness == "hard" else FORCE_PREFER
        dim = "source.named" if named.op != "exclude" else "content.exclusion"
        out.append(_stamp_ir(CandidateConstraint(
            dimension=dim,
            value=named.label,
            force=force,
            origin=ORIGIN_DETERMINISTIC,
            spans=_spans_for(prompt, [named.label]),
            detail={
                "source": "intake_regex",
                "op": named.op,
                "strictness": named.strictness,
                "identity": dict(named.identity),
                "raw_trigger": named.label,
            },
        )))

    return out


def _from_rule_reader(
    prompt: str, rr: Constraints
) -> list[CandidateConstraint]:
    """Ported adversarial rule-reader ``Constraints`` -> candidates.

    The rule-reader carries no character offsets, so spans are recovered by
    locating each value verbatim in the prompt. When a value's phrase is not
    present verbatim (the LLM paraphrased it), the candidate is still emitted but
    with an empty span list — never a fabricated offset. Exclusions are the only
    rule-reader dimension that carries ``hard`` force (an explicit "exclude").
    """
    out: list[CandidateConstraint] = []

    for st in rr.source_types:
        # SPAN-LOSS FIX (RECON-2 §2.1): the rule-reader emits a CANONICAL token
        # ("journal_article"); the prompt says "journal articles". Locating the
        # canonical token verbatim misses. Try the canonical token first, then its
        # de-canonicalized surface form (underscore→space) so a source-type the
        # user DID write recovers a real span (and can be promoted/explicit).
        # A quality marker ("high_quality") reroutes to source.quality (data map).
        dim, val = _reroute_quality("source.types", st)
        out.append(_stamp_ir(CandidateConstraint(
            dimension=dim, value=val, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER,
            spans=_spans_for(prompt, [st, str(st).replace("_", " ")]),
            detail={"source": "rule_reader", "raw_value": st},
        )))
    for lang in rr.languages:
        # The rule-reader emits a NORMALIZED ISO code (e.g. "en"); a bare 2-char
        # code matches stray substrings ("...intellig-en-ce..."), so we do NOT
        # try to span-locate it. The deterministic intake pass owns the real
        # language span; on overlap the merge keeps that authoritative span.
        out.append(_stamp_ir(CandidateConstraint(
            dimension="source.language", value=lang, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=[],
            detail={"source": "rule_reader", "no_span": "normalized_iso_code"},
        )))
    if rr.recency:
        out.append(_stamp_ir(CandidateConstraint(
            dimension="date.recency", value=rr.recency, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.recency]),
            detail={"source": "rule_reader"},
        )))
    for cov in rr.required_coverage:
        out.append(_stamp_ir(CandidateConstraint(
            dimension="content.coverage", value=cov, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [cov]),
            detail={"source": "rule_reader"},
        )))
    for exc in rr.exclusions:
        out.append(_stamp_ir(CandidateConstraint(
            dimension="content.exclusion", value=exc, force=FORCE_HARD,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [exc]),
            detail={"source": "rule_reader", "kind": "exclusion"},
        )))
    if rr.format:
        out.append(_stamp_ir(CandidateConstraint(
            dimension="deliverable.format", value=rr.format, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.format]),
            detail={"source": "rule_reader"},
        )))
    if rr.length:
        out.append(_stamp_ir(CandidateConstraint(
            dimension="deliverable.length", value=rr.length, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.length]),
            detail={"source": "rule_reader"},
        )))
    if rr.tone:
        out.append(_stamp_ir(CandidateConstraint(
            dimension="rhetoric.tone", value=rr.tone, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.tone]),
            detail={"source": "rule_reader"},
        )))

    return out


# ---------------------------------------------------------------------------
# Reconciliation (deterministic wins on overlap; rule-reader fills gaps)
# ---------------------------------------------------------------------------

# Overlap is keyed by the CANONICAL (subject, attribute, value) — NOT the raw
# (dimension, value). This reconciles aliases expressed under different raw
# dimensions (rule-reader ``source.types=journal_article`` and intake
# ``source.scope_facet=peer_reviewed_journal`` both canonicalize to
# source/kind/journal…), which the old exact-(dimension,value) key never merged
# (RECON-2 §3). Values still normalize the same way across the two sources.
def _overlap_key(c: CandidateConstraint) -> tuple[str, str, str]:
    row = _registry_row(c.dimension)
    subj = row.subject if row else (c.subject or "source")
    attr = row.attribute if row else (c.attribute or c.dimension)
    return (subj, attr, (c.value or "").strip().casefold())


def _merge_pair(
    det: CandidateConstraint, rr: CandidateConstraint
) -> CandidateConstraint:
    """Deterministic candidate wins on span + force; record that both agreed and
    union the spans (the rule-reader may have located a span the regex path
    didn't, and vice-versa)."""
    merged_spans = list(det.spans)
    seen = {(s.start, s.end) for s in merged_spans}
    for s in rr.spans:
        if (s.start, s.end) not in seen:
            merged_spans.append(s)
            seen.add((s.start, s.end))
    detail = dict(det.detail)
    detail["also_seen_by"] = "rule_reader"
    detail["rule_reader_detail"] = dict(rr.detail)
    return _stamp_ir(CandidateConstraint(
        dimension=det.dimension,
        value=det.value,            # deterministic value is authoritative
        force=det.force,            # deterministic force is authoritative
        origin=ORIGIN_MERGED,
        spans=merged_spans,
        detail=detail,
    ))


def reconcile_candidates(
    prompt: str,
    *,
    rule_reader: "Constraints | dict[str, Any] | None" = None,
    ontology: "dict[str, Any] | None" = None,
) -> list[CandidateConstraint]:
    """Reconcile the deterministic intake extractors with the rule-reader.

    Parameters
    ----------
    prompt:
        The raw task prompt (spans are recovered against this exact text).
    rule_reader:
        The ported adversarial rule-reader result — a
        :class:`~...instruction.constraint_extractor.Constraints`, its
        ``to_dict()`` form, or ``None`` to reconcile the intake extractors
        alone. This adapter NEVER runs the live rule-reader itself; the caller
        supplies an already-computed result (keeping the adapter offline/pure).
    ontology:
        Optional scope ontology override forwarded to
        ``extract_scope_constraints_regex`` (tests inject a fixture; production
        loads the default).

    Returns
    -------
    list[CandidateConstraint]
        High-recall candidates with exact spans + origin. Deterministic
        candidates come first (they win on overlap); rule-reader-only candidates
        follow. This is a candidate list, NOT a pinned contract.
    """
    prompt = prompt or ""

    # --- deterministic pass (the three champion intake regex extractors) ---
    uc = extract_constraints_regex(prompt)
    slots = extract_instruction_slots_regex(prompt)
    try:
        sc = extract_scope_constraints_regex(prompt, ontology=ontology)
    except Exception:  # noqa: BLE001 — fail-open: no scope facets on ontology miss
        sc = ScopeConstraints(source="regex")

    deterministic: list[CandidateConstraint] = []
    deterministic.extend(_from_user_constraints(prompt, uc))
    deterministic.extend(_from_instruction_slots(prompt, slots))
    deterministic.extend(_from_scope_constraints(prompt, sc))

    # --- rule-reader pass (gap-filler) ---
    rr_obj: Optional[Constraints] = None
    if isinstance(rule_reader, Constraints):
        rr_obj = rule_reader
    elif isinstance(rule_reader, dict):
        rr_obj = _constraints_from_dict(rule_reader)
    rule_candidates = _from_rule_reader(prompt, rr_obj) if rr_obj is not None else []

    # --- ONTOLOGY ALIAS NORMALIZATION (RECON-2 §3/§4): canonicalize every
    # source-type value to its ontology facet_id so a rule-reader alias
    # ("journal_article") and an intake facet ("peer_reviewed_journal") collapse
    # to ONE canonical value and MERGE (deterministic-hard wins). An unmapped kind
    # is left verbatim + marked opaque (first-class, never dropped).
    alias_index = _ontology_source_type_index(ontology)
    if alias_index:
        for cand in deterministic + rule_candidates:
            if cand.dimension in ("source.types", "source.scope_facet"):
                canon, mapped = _canonicalize_source_type(cand.value, alias_index)
                cand.value = canon
                cand.dimension = "source.types"
                if not mapped:
                    cand.normalization_status = "opaque"

    # --- reconcile: deterministic wins on overlap; rule-reader fills gaps ---
    by_key: dict[tuple[str, str], CandidateConstraint] = {}
    ordered: list[CandidateConstraint] = []
    for c in deterministic:
        key = _overlap_key(c)
        by_key[key] = c
        ordered.append(c)

    for rc in rule_candidates:
        key = _overlap_key(rc)
        existing = by_key.get(key)
        if existing is not None and existing.origin != ORIGIN_RULE_READER:
            # overlap -> merge into the deterministic winner in place
            idx = ordered.index(existing)
            merged = _merge_pair(existing, rc)
            ordered[idx] = merged
            by_key[key] = merged
        elif existing is None:
            by_key[key] = rc
            ordered.append(rc)
        # (a rule-reader/rule-reader dup collapses onto the first)

    return ordered


def _constraints_from_dict(d: dict[str, Any]) -> Constraints:
    """Rebuild a :class:`Constraints` from its ``to_dict()`` form (tolerant)."""
    def _list(v: Any) -> list[str]:
        return [str(x) for x in v] if isinstance(v, (list, tuple)) else ([] if v in (None, "") else [str(v)])

    def _opt(v: Any) -> Optional[str]:
        return None if v in (None, "") else str(v)

    return Constraints(
        source_types=_list(d.get("source_types")),
        languages=_list(d.get("languages")),
        recency=_opt(d.get("recency")),
        required_coverage=_list(d.get("required_coverage")),
        exclusions=_list(d.get("exclusions")),
        format=_opt(d.get("format")),
        length=_opt(d.get("length")),
        tone=_opt(d.get("tone")),
    )
