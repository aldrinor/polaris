"""V34 — M-14 cross-jurisdiction synthesizer (Phase C).

Per FINAL_PLAN.md Phase C deliverable #1: close the LB Regulatory
gap by surfacing FDA / EMA / MHRA / PMDA / NICE / HC divergence
or convergence on label/indication/post-marketing fields.

This module layers ON TOP of M-70 regulatory_synthesizer. M-70
extracts per-jurisdiction prose for a single regulatory entity
(one FDA label, one EMA EPAR, etc). M-14 takes a SET of such
per-jurisdiction extractions and emits cross-jurisdiction
paragraphs that explicitly call out which jurisdictions agree
and which diverge.

## LAW II safeguard

The dominant Phase C risk for V34 is over-claim — the easy
failure mode is to flatten genuine divergence into bland
consensus prose ("Regulators worldwide approved drug X for
condition Y") that misrepresents reality.

The safeguard:
  - Every emitted sentence carries inline jurisdiction tags
    (e.g., "FDA, EMA approved..." not "Regulators approved...").
  - Every emitted sentence carries inline evidence citations
    bound to the SOURCE-jurisdiction-tagged evidence_id.
  - When jurisdictions disagree, the synthesizer emits a
    DIVERGENCE paragraph naming each jurisdiction's position
    + citation, NOT a single consensus paragraph.

## Pipeline

1. INPUT: a list of `JurisdictionFinding` records (one per
   jurisdiction × field), each carrying:
     - jurisdiction (FDA/EMA/MHRA/PMDA/NICE/HC)
     - field_name ("indications", "boxed_warning", ...)
     - value (the M-70-synthesized prose for this field)
     - bound_ev_id (source evidence id)

2. GROUP BY field_name. For each field group:
     - If only ONE jurisdiction has a non-empty value, emit a
       single-jurisdiction paragraph (no divergence claim).
     - If MULTIPLE jurisdictions have values:
         - Score pairwise similarity (token Jaccard, lowercase,
           stopword-filtered) to detect convergence vs divergence.
         - If similarity above threshold across all pairs, emit
           a CONVERGENCE paragraph naming all jurisdictions and
           binding all citations.
         - Otherwise, emit a DIVERGENCE paragraph: one sentence
           per jurisdiction, each with its own citation, prefixed
           by the divergence-flag clause.

3. OUTPUT: rendered Markdown block + a structured payload
   capturing the divergence/convergence verdict per field for
   downstream consumers (Inspector, audit bundle).

## Determinism

The synthesizer is fully deterministic: no LLM calls. All prose
is templated from the JurisdictionFinding records. This is
deliberate — Phase C V34's job is to DETECT divergence, not to
generate flowery prose. M-70's LLM-synthesized per-jurisdiction
prose is reused verbatim inside M-14's templated paragraphs.

## Why a separate module from M-70

M-70 operates on ONE jurisdiction at a time. M-14 operates on
a SET of M-70 outputs. Splitting keeps M-70's LLM-bound
extraction concerns separate from M-14's deterministic
divergence-detection concerns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Canonical jurisdiction enum (string-typed for JSON friendliness)
# ---------------------------------------------------------------------------


_KNOWN_JURISDICTIONS: frozenset[str] = frozenset({
    "FDA",   # United States
    "EMA",   # European Union
    "MHRA",  # United Kingdom
    "PMDA",  # Japan
    "NICE",  # UK NICE technology appraisals
    "HC",    # Health Canada
    "TGA",   # Australia
})


def is_known_jurisdiction(j: str) -> bool:
    """True if the string is a recognized regulatory jurisdiction."""
    return j.upper() in _KNOWN_JURISDICTIONS


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JurisdictionFinding:
    """One per-jurisdiction × field extraction (M-70 output projected
    into a flatter shape for M-14 consumption).

    Attributes:
      jurisdiction: One of _KNOWN_JURISDICTIONS, uppercase.
      field_name: Canonical field key (e.g. "indications",
                  "boxed_warning"). Compared case-insensitively
                  across jurisdictions.
      value: The M-70-synthesized prose for this field. Empty
             string means M-70 emitted not_extractable; M-14
             treats that as "no finding" rather than "explicit
             absence".
      bound_ev_id: Evidence id binding this finding to its source.
      source_url: Optional source URL for renderer link-out.
    """

    jurisdiction: str
    field_name: str
    value: str
    bound_ev_id: str
    source_url: str | None = None

    def __post_init__(self) -> None:
        # Normalize jurisdiction case so callers don't have to.
        # Frozen dataclass: use object.__setattr__.
        object.__setattr__(self, "jurisdiction", self.jurisdiction.upper())


@dataclass(frozen=True)
class FieldVerdict:
    """Cross-jurisdiction verdict for one field across multiple
    jurisdictions. Used by Inspector and audit bundle.

    Attributes:
      field_name: Canonical field key.
      verdict: One of "convergence" / "divergence" / "single_source"
               / "no_findings".
      jurisdictions: Tuple of jurisdiction strings represented in
                     this verdict.
      bound_ev_ids: Tuple of evidence ids cited (one per
                    jurisdiction). Same order as `jurisdictions`.
      similarity: Pairwise minimum Jaccard similarity across
                  jurisdiction values. 1.0 if only one source.
    """

    field_name: str
    verdict: str
    jurisdictions: tuple[str, ...]
    bound_ev_ids: tuple[str, ...]
    similarity: float


@dataclass(frozen=True)
class CrossJurisdictionSynthesis:
    """Top-level output of `synthesize_cross_jurisdiction()`."""

    paragraphs: tuple[str, ...]
    verdicts: tuple[FieldVerdict, ...]


def synthesis_to_dict(s: CrossJurisdictionSynthesis) -> dict[str, Any]:
    return {
        "paragraphs": list(s.paragraphs),
        "verdicts": [
            {
                "field_name": v.field_name,
                "verdict": v.verdict,
                "jurisdictions": list(v.jurisdictions),
                "bound_ev_ids": list(v.bound_ev_ids),
                "similarity": v.similarity,
            }
            for v in s.verdicts
        ],
    }


# ---------------------------------------------------------------------------
# Tokenization + similarity (mirrors M-10 template_classifier patterns)
# ---------------------------------------------------------------------------


_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Stopwords identical to template_classifier so ranking stays
# consistent across the codebase. This list is small + conservative
# (English question scaffold + clinical filler verbs); it is NOT a
# medical NER stoplist.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the",
    "and", "or", "but",
    "of", "in", "on", "at", "to", "for", "from", "with", "by",
    "is", "are", "was", "were", "be", "been", "being",
    "this", "that", "these", "those",
    "as", "if", "than", "then", "so", "such",
    "use", "used", "using", "uses",
    "given", "taking", "received", "receiving",
})


def _expand_contractions(text: str) -> str:
    """Codex M-14 v3 review fix: expand English contractions
    BEFORE the _TOKEN_RE splits on apostrophes. v2 tokenized
    "isn't approved" as {"isn", "approved"} — fragments — and
    the negation guard never saw "not". Expansion via word-
    boundary regex on lowercased text.
    """
    if not text:
        return text
    out = text.lower()
    # Word-boundary replace each contraction. We iterate the
    # static dict in length-DESC order so longer keys
    # (e.g. "couldn't") match before shorter ones.
    for raw in sorted(_CONTRACTIONS, key=len, reverse=True):
        # Use re.sub so word boundaries are respected.
        # Apostrophe is not a word char, so \b at the start
        # works for the apostrophe-style key; for non-apostrophe
        # keys (cant, dont) standard \b applies.
        if "'" in raw:
            # Match the contraction literally (apostrophe-aware).
            pattern = re.compile(r"\b" + re.escape(raw))
        else:
            pattern = re.compile(r"\b" + re.escape(raw) + r"\b")
        out = pattern.sub(_CONTRACTIONS[raw], out)
    return out


def _tokens(text: str) -> frozenset[str]:
    """Lowercased, stopword-filtered content tokens.

    Codex M-14 v3 review fix: contractions expanded BEFORE
    tokenization so "isn't" → "is not" → contributes "not" to
    the token bag.
    """
    if not text:
        return frozenset()
    expanded = _expand_contractions(text)
    raw = _TOKEN_RE.findall(expanded)
    return frozenset(t for t in raw if t not in _STOPWORDS and len(t) > 1)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    if not union:
        return 0.0
    return len(inter) / len(union)


# Codex M-14 v2 review fix: convergence threshold raised from 0.5
# to 0.7. v1 default of 0.5 let direct negations cross the floor
# ("approved for adults" vs "not approved for adults" → Jaccard
# 0.667 → falsely convergence). 0.7 alone is not enough — see
# the force-divergence qualifier guards below — but it's a
# necessary tightening.
_DEFAULT_CONVERGENCE_FLOOR = 0.7


# Codex M-14 v2 review fix: hard force-divergence qualifier guards.
# Token-set Jaccard alone treats "X" and "not X" as 0.667 similar,
# which is the exact LAW II over-claim failure Phase C is trying
# to prevent. These guards force DIVERGENCE when ANY pair of
# values differs on a qualifier that flips the meaning, BEFORE
# Jaccard is even consulted.
#
# Each guard is a tuple of (token_set, name). If one value
# contains any token from the set and another value does NOT,
# the guard fires.

# Negation tokens: their presence vs absence flips meaning
# entirely. "approved" vs "not approved" must never converge.
# Codex M-14 v3 review fix: contractions need an EXPANSION step
# before tokenization. v2 tokenized "isn't approved" as
# {"isn","approved"} (the apostrophe split the contraction into
# fragments) and the negation guard never saw "not". This map
# normalizes contractions to their expanded form BEFORE _tokens()
# runs, so "isn't" / "aren't" / "can't" / "won't" etc. all
# contribute "not" to the token bag and trigger the negation
# guard.
_CONTRACTIONS: dict[str, str] = {
    "isn't": "is not", "isnt": "is not",
    "aren't": "are not", "arent": "are not",
    "wasn't": "was not", "wasnt": "was not",
    "weren't": "were not", "werent": "were not",
    "can't": "can not", "cant": "can not",
    "cannot": "can not",
    "couldn't": "could not", "couldnt": "could not",
    "won't": "will not", "wont": "will not",
    "wouldn't": "would not", "wouldnt": "would not",
    "shouldn't": "should not", "shouldnt": "should not",
    "doesn't": "does not", "doesnt": "does not",
    "don't": "do not", "dont": "do not",
    "didn't": "did not", "didnt": "did not",
    "hasn't": "has not", "hasnt": "has not",
    "haven't": "have not", "havent": "have not",
    "hadn't": "had not", "hadnt": "had not",
    "shan't": "shall not", "shant": "shall not",
    "mustn't": "must not", "mustnt": "must not",
    "needn't": "need not", "neednt": "need not",
}


_NEGATION_TOKENS: frozenset[str] = frozenset({
    "not", "no", "never", "without",
    "contraindicated", "withheld", "denied", "rejected",
    "withdrawn", "suspended",
    # Codex M-14 v3 review fix: also catch refusal verbs that
    # don't contain "not" but flip meaning regardless.
    "refused", "revoked", "negative",
})

# Status-pending tokens: regulatory positions still in flux
# don't converge with finalized positions, even if the wording
# overlaps.
_PENDING_TOKENS: frozenset[str] = frozenset({
    "pending", "review", "ongoing", "preliminary",
    "interim", "provisional",
})

# Scope-limiter tokens: "only", "exclusively", "restricted to"
# materially change the indicated population. Their presence vs
# absence is a divergence signal.
_SCOPE_LIMITER_TOKENS: frozenset[str] = frozenset({
    "only", "exclusively", "restricted",
    "limited",  # "limited to adults" vs "all adults"
})


def _force_divergence(values: list[str]) -> bool:
    """Return True if the qualifier guards detect a hard
    divergence between any pair of values.

    Codex M-14 v2 review fix: applied BEFORE Jaccard so that
    negation/scope/pending mismatches force DIVERGENCE regardless
    of token overlap.
    """
    if len(values) < 2:
        return False
    for guard in (_NEGATION_TOKENS, _PENDING_TOKENS, _SCOPE_LIMITER_TOKENS):
        flags = [bool(_tokens(v) & guard) for v in values]
        # If ANY value has a guard token and ANY OTHER value does
        # NOT, the guard fires.
        if any(flags) and not all(flags):
            return True
    # Codex M-14 v2: numeric mismatch guard. Different numeric
    # values in the prose (dose mg, age cutoffs, percentages) flip
    # meaning even if the surrounding tokens overlap.
    numerics = [_extract_numeric_tokens(v) for v in values]
    if any(numerics):
        # If two values both have numerics and the sets disagree
        # at all, force divergence.
        nonempty = [n for n in numerics if n]
        if len(nonempty) >= 2:
            for i in range(len(nonempty)):
                for j in range(i + 1, len(nonempty)):
                    if nonempty[i] != nonempty[j]:
                        return True
        # Asymmetric: one value has numerics, another doesn't.
        if any(n for n in numerics) and any(not n for n in numerics):
            return True
    return False


# Codex M-14 v3 review fix: extended regex to consume thousands-
# separator commas so "1,000 mg" and "1000 mg" produce the same
# numeric token. v2 regex `\b\d+(?:\.\d+)?\b` saw "1,000" as
# {"1", "000"} and falsely diverged from {"1000"}.
_NUMERIC_RE = re.compile(r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b")


def _extract_numeric_tokens(text: str) -> frozenset[str]:
    """Extract bare numeric tokens (integers, decimals) from text.
    Used by the numeric-mismatch divergence guard.

    Codex M-14 v3 review fix: thousands-separator commas are
    stripped from the matched token so "1,000" and "1000"
    normalize to the same canonical form.
    """
    if not text:
        return frozenset()
    raw = _NUMERIC_RE.findall(text)
    return frozenset(s.replace(",", "") for s in raw)


# Codex M-14 v2 review fix: divergence-flattening prose guard.
# Even on the divergence path (where bullets list per-jurisdiction
# values verbatim), if an upstream M-70 prose contains language
# that itself flattens jurisdictions ("regulators worldwide", etc.)
# the bullet would silently preserve it. Detect + neutralize.
#
# Codex M-14 v3 review fix: v2 was exact-substring match. Variants
# like "approved worldwide", "approved globally", "internationally
# approved", "consensus across jurisdictions" bypassed it. v3
# uses regex with `\b` word boundaries and matches the trigger
# WORDS (worldwide, globally, internationally, consensus,
# unanimous, international) rather than fixed phrases — any prose
# containing those flattening signals gets neutralized regardless
# of surrounding word order.
_FLATTENING_TRIGGERS: tuple[str, ...] = (
    "worldwide",
    "globally",
    "internationally",
    "international consensus",
    "global consensus",
    "consensus across jurisdictions",
    "unanimous",
    "unanimously",  # adverb form — regex \b requires explicit listing
    "all regulators",
    "all jurisdictions",
    "every jurisdiction",
    "every regulator",
    "regulators worldwide",
    "regulators globally",
)

# Build a single regex that matches any trigger as a word boundary.
_FLATTENING_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(t) for t in _FLATTENING_TRIGGERS) + r")\b",
    flags=re.IGNORECASE,
)


def _strip_flattening_phrases(text: str) -> str:
    """Replace flattening triggers with explicit single-
    jurisdiction framing so the divergence path can never
    preserve smuggled consensus language inside a bullet.

    Codex M-14 v3 review fix: regex with word boundaries replaces
    the v2 exact-substring match. Catches "approved worldwide",
    "approved globally", "internationally approved", "unanimously
    approved", "consensus across jurisdictions", etc.
    """
    if not text:
        return text
    return _FLATTENING_RE.sub("[this jurisdiction]", text)


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def _format_field_label(field_name: str) -> str:
    """`indications` → 'Indications'; `boxed_warning` → 'Boxed warning'."""
    label = field_name.replace("_", " ")
    return label[:1].upper() + label[1:] if label else label


def _join_jurisdictions(juris: list[str]) -> str:
    """Format a list of jurisdiction names as 'A, B, and C'."""
    if not juris:
        return ""
    if len(juris) == 1:
        return juris[0]
    if len(juris) == 2:
        return f"{juris[0]} and {juris[1]}"
    return f"{', '.join(juris[:-1])}, and {juris[-1]}"


def _emit_single_source_paragraph(
    field_name: str,
    finding: JurisdictionFinding,
) -> str:
    """When only one jurisdiction has a value, emit a single-source
    paragraph that explicitly names the jurisdiction (not a generic
    'regulators agree' claim).

    Codex M-14 v2 review fix: citation rendered as `[cite:ev_id]`
    (renderer-only contract distinct from the V30 strict_verify
    `[#ev:id:start-end]` token). This module emits cross-
    jurisdiction synthesis prose; per-sentence span-bound
    provenance is the responsibility of the upstream M-70 prose,
    which is reused verbatim here. Renderers that need
    machine-readable citation IDs use the FieldVerdict.bound_ev_ids
    field, not regex parsing of the prose.
    """
    label = _format_field_label(field_name)
    value = _strip_flattening_phrases(finding.value).rstrip(".").strip()
    return (
        f"**{label} ({finding.jurisdiction} only).** {value} "
        f"[cite:{finding.bound_ev_id}]. Other jurisdictions in scope did not "
        f"surface a {field_name.replace('_', ' ')} finding for this entity."
    )


def _emit_convergence_paragraph(
    field_name: str,
    findings: list[JurisdictionFinding],
) -> str:
    """All jurisdictions surface substantively similar prose AND
    pass the qualifier guards. Emit a CONVERGENCE paragraph that
    lists every contributing jurisdiction by name and binds every
    citation.

    Codex M-14 v2 review fix: deterministic canonical selection
    via (length DESC, jurisdiction ASC) sort key. Pure max-by-len
    was order-sensitive when two values had the same length.
    Citation order is also (jurisdiction ASC).
    """
    label = _format_field_label(field_name)
    juris = sorted(f.jurisdiction for f in findings)
    juris_clause = _join_jurisdictions(juris)
    # Canonical = longest value; ties broken by jurisdiction name
    # (alphabetical) for determinism across input permutations.
    canonical = sorted(
        findings, key=lambda f: (-len(f.value), f.jurisdiction),
    )[0]
    # Sanitize the canonical prose so smuggled flattening language
    # inside an upstream M-70 value can't reach the renderer.
    value = _strip_flattening_phrases(canonical.value).rstrip(".").strip()
    # Citations sorted by jurisdiction so the order is invariant
    # under input permutation.
    cite_tokens = [
        f"[cite:{f.bound_ev_id}]"
        for f in sorted(findings, key=lambda x: x.jurisdiction)
    ]
    citations = " ".join(cite_tokens)
    return (
        f"**{label} (convergence: {juris_clause}).** {value}. "
        f"Citations: {citations}."
    )


def _emit_divergence_paragraph(
    field_name: str,
    findings: list[JurisdictionFinding],
) -> str:
    """Jurisdictions surface materially different prose. Emit a
    DIVERGENCE paragraph: one bullet per jurisdiction, each with
    its own citation. The opening clause flags divergence
    explicitly so renderers can highlight it.

    Codex M-14 v2 review fix: bullet bodies pass through
    `_strip_flattening_phrases` so even if upstream M-70 prose
    smuggled in "regulators worldwide" language, it gets
    neutralized before rendering.
    """
    label = _format_field_label(field_name)
    juris = sorted(f.jurisdiction for f in findings)
    juris_clause = _join_jurisdictions(juris)
    bullets = []
    for f in sorted(findings, key=lambda x: x.jurisdiction):
        value = _strip_flattening_phrases(f.value).rstrip(".").strip()
        bullets.append(
            f"- **{f.jurisdiction}.** {value} [cite:{f.bound_ev_id}]."
        )
    bullet_block = "\n".join(bullets)
    return (
        f"**{label} (divergence across {juris_clause}).** Regulatory "
        f"positions differ on this field. Per-jurisdiction findings:\n"
        f"{bullet_block}"
    )


def _verdict_for_field(
    field_name: str,
    findings: list[JurisdictionFinding],
    convergence_floor: float,
) -> tuple[FieldVerdict, str]:
    """Compute the verdict + paragraph for a single field group."""
    nonempty = [f for f in findings if f.value.strip()]
    if not nonempty:
        verdict = FieldVerdict(
            field_name=field_name,
            verdict="no_findings",
            jurisdictions=(),
            bound_ev_ids=(),
            similarity=0.0,
        )
        return verdict, ""

    if len(nonempty) == 1:
        f = nonempty[0]
        verdict = FieldVerdict(
            field_name=field_name,
            verdict="single_source",
            jurisdictions=(f.jurisdiction,),
            bound_ev_ids=(f.bound_ev_id,),
            similarity=1.0,
        )
        return verdict, _emit_single_source_paragraph(field_name, f)

    # Multi-jurisdiction case — compute pairwise minimum Jaccard.
    tokens_per = [(f, _tokens(f.value)) for f in nonempty]
    min_sim = 1.0
    for i in range(len(tokens_per)):
        for j in range(i + 1, len(tokens_per)):
            s = _jaccard(tokens_per[i][1], tokens_per[j][1])
            if s < min_sim:
                min_sim = s

    juris_sorted = sorted(f.jurisdiction for f in nonempty)
    ev_ids_sorted = tuple(
        f.bound_ev_id for f in sorted(nonempty, key=lambda x: x.jurisdiction)
    )

    # Codex M-14 v2 review fix: hard force-divergence guards run
    # BEFORE the Jaccard threshold check. Negation/scope-limiter/
    # pending-status/numeric-mismatch differences must NEVER be
    # silently flattened to convergence regardless of how high
    # the token overlap scores. Pure Jaccard treats "X" and
    # "not X" as 0.667 similar.
    forced_divergence = _force_divergence([f.value for f in nonempty])

    if (not forced_divergence) and min_sim >= convergence_floor:
        verdict = FieldVerdict(
            field_name=field_name,
            verdict="convergence",
            jurisdictions=tuple(juris_sorted),
            bound_ev_ids=ev_ids_sorted,
            similarity=min_sim,
        )
        return verdict, _emit_convergence_paragraph(field_name, nonempty)

    verdict = FieldVerdict(
        field_name=field_name,
        verdict="divergence",
        jurisdictions=tuple(juris_sorted),
        bound_ev_ids=ev_ids_sorted,
        similarity=min_sim,
    )
    return verdict, _emit_divergence_paragraph(field_name, nonempty)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def synthesize_cross_jurisdiction(
    findings: list[JurisdictionFinding],
    convergence_floor: float = _DEFAULT_CONVERGENCE_FLOOR,
) -> CrossJurisdictionSynthesis:
    """Group findings by field_name and emit per-field cross-
    jurisdiction synthesis.

    Returns a CrossJurisdictionSynthesis with one paragraph per
    field that has at least one non-empty finding, plus a
    structured `verdicts` tuple parallel to the paragraphs.

    Raises ValueError on unknown jurisdiction strings to surface
    upstream catalog drift loudly (LAW II — never silently
    classify "FRD" as "FDA" via fuzzy matching).
    """
    if not (0.0 <= convergence_floor <= 1.0):
        raise ValueError(
            f"convergence_floor must be in [0,1]; got {convergence_floor}"
        )
    for f in findings:
        if not is_known_jurisdiction(f.jurisdiction):
            raise ValueError(
                f"unknown jurisdiction: {f.jurisdiction!r}; "
                f"add to _KNOWN_JURISDICTIONS or fix the upstream tag"
            )

    # Group by canonical field_name (case-insensitive).
    groups: dict[str, list[JurisdictionFinding]] = {}
    for f in findings:
        key = f.field_name.strip().lower()
        if not key:
            continue
        groups.setdefault(key, []).append(f)

    paragraphs: list[str] = []
    verdicts: list[FieldVerdict] = []
    # Stable ordering: alphabetical by field_name.
    for field_name in sorted(groups):
        verdict, para = _verdict_for_field(
            field_name, groups[field_name], convergence_floor,
        )
        verdicts.append(verdict)
        if para:
            paragraphs.append(para)

    return CrossJurisdictionSynthesis(
        paragraphs=tuple(paragraphs),
        verdicts=tuple(verdicts),
    )
