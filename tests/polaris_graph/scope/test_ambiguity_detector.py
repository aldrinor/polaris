"""Tests for ambiguity_detector_clinical — PICO axes detection."""

from __future__ import annotations

import pytest

from polaris_graph.scope.ambiguity_detector_clinical import detect_ambiguity


# ---------- Population ambiguity ----------

def test_diabetes_without_type_flagged_population():
    """Test 002 golden case: 'patients with diabetes' is ambiguous on type."""
    result = detect_ambiguity(
        "Does metformin improve cardiovascular outcomes in patients with diabetes?"
    )
    assert result.population.needs_clarification is True
    assert "type_1_diabetes" in result.population.plausible_interpretations
    assert "type_2_diabetes" in result.population.plausible_interpretations


def test_diabetes_with_type_not_flagged_population():
    """If user specifies type 2, population should be clear."""
    result = detect_ambiguity(
        "Does metformin help patients with diabetes type 2?"
    )
    assert result.population.needs_clarification is False


def test_cancer_without_stage_flagged():
    result = detect_ambiguity(
        "What is the efficacy of immunotherapy in patients with cancer?"
    )
    assert result.population.needs_clarification is True
    assert any("tumor" in i or "cancer" in i for i in result.population.plausible_interpretations)


def test_cancer_with_stage_not_flagged():
    result = detect_ambiguity(
        "What is the efficacy of immunotherapy in patients with stage IV lung cancer?"
    )
    assert result.population.needs_clarification is False


# ---------- Intervention ambiguity ----------

def test_physical_therapy_without_modality_flagged():
    """Test 003 golden case: 'physical therapy' is ambiguous on modality."""
    result = detect_ambiguity(
        "Is physical therapy effective for reducing chronic lower back pain in adults?"
    )
    assert result.intervention.needs_clarification is True
    assert "manual_therapy" in result.intervention.plausible_interpretations


def test_physical_therapy_with_specific_protocol_not_flagged():
    """If user specifies the modality (e.g., 'physical therapy program'), not flagged."""
    result = detect_ambiguity(
        "Is physical therapy program X effective for chronic lower back pain in adults?"
    )
    # 'physical therapy program' has a follow-up qualifier so doesn't match
    assert result.intervention.needs_clarification is False


def test_drug_therapy_without_specific_drug_flagged():
    result = detect_ambiguity("Does drug therapy improve pain")
    assert result.intervention.needs_clarification is True


# ---------- Outcome ambiguity ----------

def test_outcomes_without_specifier_flagged():
    """Test 001 golden case: 'outcomes of immunotherapy' is ambiguous (OS vs PFS vs QoL)."""
    result = detect_ambiguity(
        "What is the empirical evidence on outcomes of immunotherapy for lung cancer in patients over 65?"
    )
    assert result.outcome.needs_clarification is True
    assert "overall_survival" in result.outcome.plausible_interpretations


def test_cardiovascular_outcomes_flagged():
    """Test 002 golden case: 'cardiovascular outcomes' is ambiguous (MACE/mortality types)."""
    result = detect_ambiguity(
        "Does metformin improve cardiovascular outcomes in patients with diabetes?"
    )
    assert result.outcome.needs_clarification is True
    assert "major_adverse_cardiovascular_events" in result.outcome.plausible_interpretations


def test_specific_outcome_not_flagged():
    """If user specifies the outcome metric, not flagged."""
    result = detect_ambiguity(
        "Does aspirin reduce all-cause mortality measured at 12 months"
    )
    # No bare 'outcomes' or 'effects' — specific metric specified
    assert result.outcome.needs_clarification is False


# ---------- Multi-axis ----------

def test_multiple_ambiguity_axes_at_once():
    """Test 002 golden case has BOTH population (diabetes type) AND outcome
    (cardiovascular) ambiguity. Both should be flagged."""
    result = detect_ambiguity(
        "Does metformin improve cardiovascular outcomes in patients with diabetes?"
    )
    assert result.population.needs_clarification is True
    assert result.outcome.needs_clarification is True
    # Intervention (metformin) is specific — should NOT be flagged
    assert result.intervention.needs_clarification is False
    assert result.is_ambiguous is True


def test_no_ambiguity_when_question_fully_specified():
    """All three axes specific → not ambiguous."""
    result = detect_ambiguity(
        "Does metformin reduce all-cause mortality at 12 months in patients with diabetes type 2?"
    )
    assert result.population.needs_clarification is False
    assert result.intervention.needs_clarification is False
    # 'all-cause mortality' is specific (not bare 'outcomes')
    assert result.outcome.needs_clarification is False
    assert result.is_ambiguous is False


# ---------- AmbiguityAxes structure ----------

def test_returns_correct_axis_labels():
    result = detect_ambiguity("Does aspirin help adults?")
    assert result.population.axis == "population"
    assert result.intervention.axis == "intervention"
    assert result.outcome.axis == "outcome"


def test_each_axis_has_at_least_one_interpretation():
    """Even fully-clear axes have a default interpretation entry."""
    result = detect_ambiguity("Does metformin reduce all-cause mortality at 12 months in patients with diabetes type 2?")
    assert len(result.population.plausible_interpretations) >= 1
    assert len(result.intervention.plausible_interpretations) >= 1
    assert len(result.outcome.plausible_interpretations) >= 1


# ---------- Type validation ----------

def test_rejects_non_string():
    with pytest.raises(TypeError):
        detect_ambiguity(42)  # type: ignore[arg-type]


# ---------- Determinism ----------

def test_deterministic():
    text = "Does metformin improve cardiovascular outcomes in patients with diabetes?"
    r1 = detect_ambiguity(text)
    r2 = detect_ambiguity(text)
    assert r1.is_ambiguous == r2.is_ambiguous
    assert r1.population.plausible_interpretations == r2.population.plausible_interpretations
    assert r1.intervention.plausible_interpretations == r2.intervention.plausible_interpretations
    assert r1.outcome.plausible_interpretations == r2.outcome.plausible_interpretations


# ---------- Empty / edge cases ----------

def test_empty_clinical_question_returns_default_axes():
    """Even minimal text returns valid AmbiguityAxes (caller guarantees non-empty)."""
    result = detect_ambiguity("does X help Y in Z")
    # No population/intervention/outcome ambiguity terms matched
    assert result.is_ambiguous is False
    assert result.population.axis == "population"
