"""Static section blueprints per clinical scope_class.

Per `.codex/slices/slice_003/architecture_proposal.md` §"section_blueprint".

A blueprint is the ordered list of sections the generator will attempt
to write for a given scope_class. Each section has a stable id (used
for VerifiedSentence.section_id + UI anchors) and a human-readable title.

Pure-data module. No I/O.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SectionPlan:
    """One section in a generator blueprint."""

    section_id: str
    section_title: str
    section_brief: str  # one-line guidance for the generator prompt


@dataclass(frozen=True)
class Blueprint:
    """The full ordered set of sections for a scope_class."""

    scope_class: str
    sections: tuple[SectionPlan, ...]


# ---------------------------------------------------------------------------
# Built-in clinical blueprints
# ---------------------------------------------------------------------------

CLINICAL_EFFICACY = Blueprint(
    scope_class="clinical_efficacy",
    sections=(
        SectionPlan(
            "sec_population",
            "Population",
            "Describe the patient population the cited evidence covers — "
            "demographics, eligibility criteria, sample sizes.",
        ),
        SectionPlan(
            "sec_intervention",
            "Intervention",
            "Describe the intervention as studied — dose, regimen, "
            "comparators, follow-up.",
        ),
        SectionPlan(
            "sec_outcomes",
            "Outcomes",
            "Report effect sizes for primary outcomes with confidence "
            "intervals; cite each numeric claim to a source span.",
        ),
        SectionPlan(
            "sec_limitations",
            "Limitations",
            "Note risk-of-bias issues, generalizability gaps, and where "
            "evidence is sparse or contradictory.",
        ),
    ),
)

CLINICAL_SAFETY = Blueprint(
    scope_class="clinical_safety",
    sections=(
        SectionPlan(
            "sec_population",
            "Population",
            "Identify who has been exposed to the intervention in safety "
            "studies — age range, comorbidities, exposure duration.",
        ),
        SectionPlan(
            "sec_adverse_events",
            "Adverse Events",
            "Enumerate adverse events reported with rates; distinguish "
            "common from serious; cite numeric rates to source spans.",
        ),
        SectionPlan(
            "sec_risk_factors",
            "Risk Factors",
            "Describe known risk modifiers (concomitant drugs, organ "
            "function, age) per regulatory + pharmacovigilance evidence.",
        ),
        SectionPlan(
            "sec_monitoring",
            "Monitoring",
            "Outline recommended monitoring per regulatory labels and "
            "society guidelines.",
        ),
    ),
)

CLINICAL_DIAGNOSIS = Blueprint(
    scope_class="clinical_diagnosis",
    sections=(
        SectionPlan(
            "sec_test_characteristics",
            "Test Characteristics",
            "Report sensitivity, specificity, PPV, NPV, and AUC where "
            "available; cite each metric to a source span.",
        ),
        SectionPlan(
            "sec_population",
            "Population",
            "Define the population in which the test was validated; "
            "note prevalence and clinical context.",
        ),
        SectionPlan(
            "sec_comparators",
            "Comparators",
            "Compare against the reference standard and alternative tests.",
        ),
        SectionPlan(
            "sec_clinical_utility",
            "Clinical Utility",
            "Note downstream impact on management and outcomes.",
        ),
    ),
)

CLINICAL_PROGNOSIS = Blueprint(
    scope_class="clinical_prognosis",
    sections=(
        SectionPlan(
            "sec_population",
            "Population",
            "Describe the cohort whose outcomes are being projected.",
        ),
        SectionPlan(
            "sec_prognostic_factors",
            "Prognostic Factors",
            "List validated factors that modify outcome with effect sizes.",
        ),
        SectionPlan(
            "sec_outcomes",
            "Outcomes",
            "Report time-to-event outcomes with hazard ratios + CIs; "
            "cite each numeric to a source span.",
        ),
        SectionPlan(
            "sec_confounders",
            "Confounders",
            "Discuss residual confounding + selection bias risks.",
        ),
    ),
)


_BLUEPRINTS: dict[str, Blueprint] = {
    CLINICAL_EFFICACY.scope_class: CLINICAL_EFFICACY,
    CLINICAL_SAFETY.scope_class: CLINICAL_SAFETY,
    CLINICAL_DIAGNOSIS.scope_class: CLINICAL_DIAGNOSIS,
    CLINICAL_PROGNOSIS.scope_class: CLINICAL_PROGNOSIS,
}


# Default blueprint when scope_class is unknown / not yet registered.
# Conservative: matches efficacy structure, which is the most common case.
DEFAULT_BLUEPRINT = CLINICAL_EFFICACY


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def blueprint_for_scope_class(scope_class: str | None) -> Blueprint:
    """Resolve the blueprint for `scope_class`.

    Unknown / None classes fall back to DEFAULT_BLUEPRINT (efficacy
    structure). This matches the slice 002 corpus_adequacy_gate behavior
    of falling back to clinical_default rather than failing.
    """
    if scope_class is None:
        return DEFAULT_BLUEPRINT
    return _BLUEPRINTS.get(scope_class, DEFAULT_BLUEPRINT)


def known_scope_classes() -> tuple[str, ...]:
    return tuple(sorted(_BLUEPRINTS.keys()))


def register_blueprint(blueprint: Blueprint) -> None:
    """Register an additional blueprint (e.g. domain-specific override).

    Used for test injection + future domain extensions.
    """
    _BLUEPRINTS[blueprint.scope_class] = blueprint
