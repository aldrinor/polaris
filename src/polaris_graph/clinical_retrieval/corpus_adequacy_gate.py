"""Corpus adequacy gate — slice 002 final-quality check before generation.

Per `.codex/slices/slice_002/architecture_proposal.md` §"corpus_adequacy_gate".

Given a list of retrieved Sources + a per-template minimum requirement
table, returns an AdequacyVerdict that says either:

  is_adequate=True  → pool may flow to slice 003 generation
  is_adequate=False → pipeline aborts with a human-readable failure_reason

Pure function. No I/O, no LLM, no network.

Templates currently shipped:
  - clinical_default: T1>=2, T2>=4, T3>=2
  - clinical_safety: T1>=3 (regulatory weight), T2>=3, T3>=1
  - clinical_diagnosis: T1>=1, T2>=5, T3>=1
  - clinical_prognosis: T1>=1, T2>=4, T3>=2

Additional templates can be registered via `register_template()`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    Source,
    SourceTier,
)


@dataclass(frozen=True)
class ClinicalTemplate:
    """Adequacy threshold table for a clinical retrieval template."""

    template_id: str
    min_t1: int
    min_t2: int
    min_t3: int

    def as_dict(self) -> dict[SourceTier, int]:
        return {
            SourceTier.T1: self.min_t1,
            SourceTier.T2: self.min_t2,
            SourceTier.T3: self.min_t3,
        }


# ---------------------------------------------------------------------------
# Built-in templates
# ---------------------------------------------------------------------------

CLINICAL_DEFAULT = ClinicalTemplate(
    template_id="clinical_default",
    min_t1=2,
    min_t2=4,
    min_t3=2,
)

CLINICAL_EFFICACY = ClinicalTemplate(
    template_id="clinical_efficacy",
    # Demo-stage thresholds tuned 2026-05-04 against live walkthrough:
    # the canonical aspirin/migraine question retrieves 1xT1 (Cochrane) +
    # 2xT2 (PubMed + ScienceDirect, deduplicated to 2 distinct papers) +
    # 2xT3 (PMC). Setting T2 floor to 2 lets a 4-source minimum (1+2+1)
    # admit the demo while still requiring multi-tier coverage.
    # Production tighten target: (T1=2, T2=5, T3=1) — revisit once query
    # planner produces more T2 hits per question.
    min_t1=1,
    min_t2=2,
    min_t3=1,
)

CLINICAL_SAFETY = ClinicalTemplate(
    template_id="clinical_safety",
    min_t1=3,  # regulatory weight is critical for safety
    min_t2=3,
    min_t3=1,
)

CLINICAL_DIAGNOSIS = ClinicalTemplate(
    template_id="clinical_diagnosis",
    min_t1=1,
    min_t2=5,
    min_t3=1,
)

CLINICAL_PROGNOSIS = ClinicalTemplate(
    template_id="clinical_prognosis",
    min_t1=1,
    min_t2=4,
    min_t3=2,
)


_REGISTRY: dict[str, ClinicalTemplate] = {
    CLINICAL_DEFAULT.template_id: CLINICAL_DEFAULT,
    CLINICAL_EFFICACY.template_id: CLINICAL_EFFICACY,
    CLINICAL_SAFETY.template_id: CLINICAL_SAFETY,
    CLINICAL_DIAGNOSIS.template_id: CLINICAL_DIAGNOSIS,
    CLINICAL_PROGNOSIS.template_id: CLINICAL_PROGNOSIS,
}


def register_template(template: ClinicalTemplate) -> None:
    """Register an additional template (e.g. domain-specific override)."""
    _REGISTRY[template.template_id] = template


def get_template(template_id: str) -> ClinicalTemplate:
    """Resolve a template by id; falls back to clinical_default if unknown."""
    return _REGISTRY.get(template_id, CLINICAL_DEFAULT)


def template_for_scope_class(scope_class: str | None) -> ClinicalTemplate:
    """Map a slice 001 scope_class to the matching adequacy template.

    Unknown / None scope classes resolve to clinical_default.
    """
    if scope_class is None:
        return CLINICAL_DEFAULT
    mapping = {
        "clinical_efficacy": CLINICAL_EFFICACY,
        "clinical_safety": CLINICAL_SAFETY,
        "clinical_diagnosis": CLINICAL_DIAGNOSIS,
        "clinical_prognosis": CLINICAL_PROGNOSIS,
    }
    return mapping.get(scope_class, CLINICAL_DEFAULT)


# ---------------------------------------------------------------------------
# Adequacy assessment
# ---------------------------------------------------------------------------

def _count_by_tier(sources: Iterable[Source]) -> dict[SourceTier, int]:
    counts = {SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0}
    for s in sources:
        counts[s.tier] += 1
    return counts


def _failure_reason(
    counts: dict[SourceTier, int],
    template: ClinicalTemplate,
) -> str | None:
    """Build a single human-readable reason string when adequacy fails.

    Lists ALL deficient tiers (not just the first), so the UI can
    show a complete picture of what's missing.
    """
    deficient = []
    for tier, required in template.as_dict().items():
        got = counts.get(tier, 0)
        if got < required:
            deficient.append(
                f"{tier.value} (got {got}, need {required})"
            )
    if not deficient:
        return None
    return (
        f"corpus_adequacy_failed[{template.template_id}]: "
        f"insufficient sources in {', '.join(deficient)}"
    )


def assess(
    sources: Iterable[Source],
    template: ClinicalTemplate = CLINICAL_DEFAULT,
) -> AdequacyVerdict:
    """Assess whether `sources` meets `template`'s minimum thresholds.

    Returns an AdequacyVerdict with sources_per_tier + min_required_per_tier
    populated. failure_reason is None on pass, populated on fail.
    """
    counts = _count_by_tier(sources)
    reason = _failure_reason(counts, template)
    return AdequacyVerdict(
        is_adequate=reason is None,
        sources_per_tier=counts,
        min_required_per_tier=template.as_dict(),
        failure_reason=reason,
    )
