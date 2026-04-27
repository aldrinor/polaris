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


def _tokens(text: str) -> frozenset[str]:
    """Lowercased, stopword-filtered content tokens."""
    if not text:
        return frozenset()
    raw = _TOKEN_RE.findall(text.lower())
    return frozenset(t for t in raw if t not in _STOPWORDS and len(t) > 1)


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    if not union:
        return 0.0
    return len(inter) / len(union)


# Codex M-14: convergence threshold. Pairs at ≥ this Jaccard are
# considered "saying the same thing" for cross-jurisdiction
# purposes. Empirically tunable; default biases toward DIVERGENCE
# (the safer failure mode under LAW II — over-flagging divergence
# makes operators look harder, while under-flagging silently
# flattens disagreement into consensus).
_DEFAULT_CONVERGENCE_FLOOR = 0.5


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
    'regulators agree' claim)."""
    label = _format_field_label(field_name)
    value = finding.value.rstrip(".").strip()
    return (
        f"**{label} ({finding.jurisdiction} only).** {value} "
        f"[{finding.bound_ev_id}]. Other jurisdictions in scope did not "
        f"surface a {field_name.replace('_', ' ')} finding for this entity."
    )


def _emit_convergence_paragraph(
    field_name: str,
    findings: list[JurisdictionFinding],
) -> str:
    """All jurisdictions surface substantively similar prose. Emit
    a CONVERGENCE paragraph that lists every contributing
    jurisdiction by name and binds every citation."""
    label = _format_field_label(field_name)
    juris = sorted(f.jurisdiction for f in findings)
    juris_clause = _join_jurisdictions(juris)
    # Use the longest of the converged values as the canonical
    # prose (most informative); could also use the first, but
    # length-biased preserves more detail.
    canonical = max(findings, key=lambda f: len(f.value))
    citations = " ".join(f"[{f.bound_ev_id}]" for f in findings)
    value = canonical.value.rstrip(".").strip()
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
    explicitly so renderers can highlight it."""
    label = _format_field_label(field_name)
    juris = sorted(f.jurisdiction for f in findings)
    juris_clause = _join_jurisdictions(juris)
    bullets = []
    for f in sorted(findings, key=lambda x: x.jurisdiction):
        value = f.value.rstrip(".").strip()
        bullets.append(f"- **{f.jurisdiction}.** {value} [{f.bound_ev_id}].")
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

    if min_sim >= convergence_floor:
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
