"""PICO ambiguity detector for clinical questions.

Per slice 001 architecture proposal §"PICO axes for ambiguity (not free-form)".
Detects ambiguity along three axes: Population, Intervention, Outcome.

Approach:
    1. Heuristic extraction — pattern-match each axis from the question.
    2. Dictionary lookup — known-ambiguous terms (e.g., "diabetes" without
       type qualifier) flag the axis as ambiguous.
    3. Default — single-interpretation when not matched as ambiguous.

This is deterministic, fast (sub-millisecond), and explainable. The
ambiguity dictionary lives inline rather than a YAML file because slice 1's
clinical scope is narrow and the dictionary entries inform the regex
extraction logic directly. Future slices may externalize.

For production: a future enhancement could add LLM-based ambiguity
detection (similar pattern to clinical_classifier.llm_fallback_classify)
when the heuristic returns no matches at all. Slice 1 ships heuristic-only.
"""

from __future__ import annotations

import re

from polaris_graph.scope.scope_decision import (
    AmbiguityAxes,
    AmbiguityAxis,
)

# ---------------------------------------------------------------------------
# Population ambiguity dictionary
# ---------------------------------------------------------------------------
# Each entry: (regex_to_detect_class, list of plausible-interpretation labels).
# A match flags the population axis as ambiguous.

_POPULATION_AMBIGUOUS = [
    (
        re.compile(r"\bpatients?\s+with\s+diabetes\b(?!\s+type\s+\d|\s+mellitus\s+type)", re.IGNORECASE),
        ["type_1_diabetes", "type_2_diabetes", "gestational_diabetes", "prediabetes"],
    ),
    (
        re.compile(r"\bpatients?\s+with\s+cancer\b(?!\s+(?:stage|type|of))", re.IGNORECASE),
        ["solid_tumor", "hematologic_malignancy", "metastatic_cancer", "early_stage_cancer"],
    ),
    (
        re.compile(r"\b(?:adults?|elderly|seniors?)\s*$|\b(?:adults?|elderly)\s+\w+\s+(?:patients?|population)\b", re.IGNORECASE),
        ["adults_18_65", "elderly_over_65", "adults_with_comorbidities"],
    ),
    (
        re.compile(r"\bpatients?\s+with\s+heart\s+(?:disease|conditions?)\b", re.IGNORECASE),
        ["coronary_artery_disease", "heart_failure", "arrhythmia", "valvular_disease"],
    ),
]

_POPULATION_EXTRACTION = re.compile(
    r"\b(?:in|for|among)\s+(patients?\s+with\s+\w+(?:\s+\w+){0,4}|"
    r"adults?(?:\s+\w+){0,3}|"
    r"children|infants|elderly(?:\s+\w+){0,3})",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Intervention ambiguity dictionary
# ---------------------------------------------------------------------------

_INTERVENTION_AMBIGUOUS = [
    (
        re.compile(r"\bphysical\s+therapy\b(?!\s+(?:protocol|program|with|using))", re.IGNORECASE),
        ["manual_therapy", "exercise_therapy", "manipulation", "electrotherapy", "combined_multimodal_program"],
    ),
    (
        # Generic "drug therapy" / "medication therapy" without specific drug name.
        # Match if next non-stop word is a verb ("improve", "help") rather than
        # a drug name. Heuristic: just match the bare phrase; specific drug
        # names usually appear before the word "therapy" (e.g., "aspirin
        # therapy") not after.
        re.compile(r"\b(?:does\s+)?(?:drug|medication)\s+therapy\b", re.IGNORECASE),
        ["pharmacotherapy_unspecified"],
    ),
    (
        re.compile(r"\b(?:behavioral|behaviour)\s+(?:therapy|intervention)\b(?!\s+\w)", re.IGNORECASE),
        ["cbt", "dbt", "act", "mindfulness_based"],
    ),
    (
        re.compile(r"\b(?:supplement|vitamin)s?\b(?!\s+\w+\s+\d)", re.IGNORECASE),
        ["vitamin_d", "vitamin_b12", "omega_3", "multivitamin", "specific_mineral"],
    ),
]

_INTERVENTION_EXTRACTION = re.compile(
    r"\b(?:does|of|effect\s+of|efficacy\s+of|safety\s+of)\s+"
    r"(\w+(?:\s+\w+){0,3})",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Outcome ambiguity dictionary
# ---------------------------------------------------------------------------

_OUTCOME_AMBIGUOUS = [
    # ORDERING: more-specific patterns FIRST so generic 'outcomes' doesn't
    # win over 'cardiovascular outcomes'.
    (
        re.compile(r"\bcardiovascular\s+outcomes?\b(?!\s+\w+\s+defined)", re.IGNORECASE),
        ["major_adverse_cardiovascular_events", "all_cause_mortality", "cardiovascular_mortality"],
    ),
    (
        re.compile(r"\boutcomes?\b(?!\s+(?:include|defined|measured|specifically))", re.IGNORECASE),
        ["overall_survival", "progression_free_survival", "quality_of_life", "treatment_response_rate"],
    ),
    (
        re.compile(r"\beffects?\b(?!\s+(?:on\s+\w+\s+specifically|defined|measured))", re.IGNORECASE),
        ["primary_effect", "side_effects", "long_term_effects"],
    ),
    (
        re.compile(r"\b(?:improvements?|improves?|improving)\b(?!\s+\w+\s+specifically)", re.IGNORECASE),
        ["functional_improvement", "symptomatic_improvement", "quality_of_life_improvement"],
    ),
]


def _detect_axis(
    text: str,
    ambiguity_dict: list[tuple[re.Pattern[str], list[str]]],
    axis_name: str,
    default_interpretation: str,
) -> AmbiguityAxis:
    """Match text against an axis's ambiguity dictionary."""
    for pattern, interpretations in ambiguity_dict:
        if pattern.search(text):
            return AmbiguityAxis(
                axis=axis_name,  # type: ignore[arg-type]
                plausible_interpretations=interpretations,
                needs_clarification=True,
            )
    return AmbiguityAxis(
        axis=axis_name,  # type: ignore[arg-type]
        plausible_interpretations=[default_interpretation],
        needs_clarification=False,
    )


def detect_ambiguity(normalized_text: str) -> AmbiguityAxes:
    """Detect PICO-axis ambiguity in a clinical question.

    Args:
        normalized_text: post-normalization question text. Should be from
                         intake.normalize() — pass NormalizedQuestion.normalized.

    Returns:
        AmbiguityAxes with population, intervention, and outcome axes.
        Each axis: (plausible_interpretations, needs_clarification).
        is_ambiguous = True iff ANY axis needs_clarification.

    Raises:
        TypeError if normalized_text is not a str.
    """
    if not isinstance(normalized_text, str):
        raise TypeError(
            f"detect_ambiguity expected str, got {type(normalized_text).__name__}"
        )

    # When no ambiguity is detected we fall back to the normalized
    # question text itself as the single "interpretation" for each axis.
    # This is honest: slice 001 doesn't ship a real PICO extractor, so
    # downstream slice 002 retrieval consumes the user's question
    # verbatim rather than a meaningless placeholder. Golden tests
    # assert on needs_clarification, not interpretation content, so
    # this change is backward-compatible with the slice 001 fitness suite.
    fallback = normalized_text.strip() or normalized_text
    population = _detect_axis(
        normalized_text, _POPULATION_AMBIGUOUS, "population", fallback
    )
    intervention = _detect_axis(
        normalized_text, _INTERVENTION_AMBIGUOUS, "intervention", fallback
    )
    outcome = _detect_axis(
        normalized_text, _OUTCOME_AMBIGUOUS, "outcome", fallback
    )

    is_ambiguous = (
        population.needs_clarification
        or intervention.needs_clarification
        or outcome.needs_clarification
    )

    return AmbiguityAxes(
        population=population,
        intervention=intervention,
        outcome=outcome,
        is_ambiguous=is_ambiguous,
    )
