"""Tests for polaris_graph.scope.scope_decision schemas + assembly."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from polaris_graph.scope.scope_decision import (
    AmbiguityAxes,
    AmbiguityAxis,
    ScopeClass,
    ScopeDecision,
    assemble_scope_decision,
)


# ---------- ScopeClass ----------

def test_scope_class_regex_hit_max_confidence():
    sc = ScopeClass(
        value="clinical_efficacy",
        confidence=1.0,
        provenance="regex",
        matched_pattern="cochrane_efficacy_v1",
    )
    assert sc.value == "clinical_efficacy"
    assert sc.confidence == 1.0
    assert sc.provenance == "regex"


def test_scope_class_llm_fallback():
    sc = ScopeClass(value="clinical_safety", confidence=0.78, provenance="llm_fallback")
    assert sc.matched_pattern is None  # LLM fallback has no regex pattern


def test_scope_class_rejects_confidence_above_one():
    with pytest.raises(ValidationError):
        ScopeClass(value="clinical_efficacy", confidence=1.5, provenance="regex")


def test_scope_class_rejects_negative_confidence():
    with pytest.raises(ValidationError):
        ScopeClass(value="clinical_efficacy", confidence=-0.1, provenance="regex")


def test_scope_class_rejects_invalid_provenance():
    with pytest.raises(ValidationError):
        ScopeClass(value="clinical_efficacy", confidence=0.9, provenance="bogus")  # type: ignore[arg-type]


# ---------- AmbiguityAxis ----------

def test_ambiguity_axis_single_interpretation_not_ambiguous():
    ax = AmbiguityAxis(
        axis="population",
        plausible_interpretations=["adults with chronic LBP"],
        needs_clarification=False,
    )
    assert not ax.needs_clarification


def test_ambiguity_axis_multiple_interpretations_needs_clarification():
    ax = AmbiguityAxis(
        axis="outcome",
        plausible_interpretations=["overall_survival", "progression_free_survival"],
        needs_clarification=True,
    )
    assert ax.needs_clarification


def test_ambiguity_axis_rejects_empty_interpretations():
    with pytest.raises(ValidationError):
        AmbiguityAxis(
            axis="population",
            plausible_interpretations=[],
            needs_clarification=False,
        )


def test_ambiguity_axis_rejects_more_than_5_interpretations():
    with pytest.raises(ValidationError):
        AmbiguityAxis(
            axis="intervention",
            plausible_interpretations=["a", "b", "c", "d", "e", "f"],
            needs_clarification=True,
        )


def test_ambiguity_axis_rejects_invalid_axis():
    with pytest.raises(ValidationError):
        AmbiguityAxis(
            axis="comparator",  # type: ignore[arg-type]
            plausible_interpretations=["x"],
            needs_clarification=False,
        )


# ---------- AmbiguityAxes ----------

def _clear(axis: str) -> AmbiguityAxis:
    return AmbiguityAxis(
        axis=axis,  # type: ignore[arg-type]
        plausible_interpretations=[f"clear_{axis}"],
        needs_clarification=False,
    )


def _ambiguous(axis: str) -> AmbiguityAxis:
    return AmbiguityAxis(
        axis=axis,  # type: ignore[arg-type]
        plausible_interpretations=[f"alt1_{axis}", f"alt2_{axis}"],
        needs_clarification=True,
    )


def test_ambiguity_axes_all_clear_not_ambiguous():
    axes = AmbiguityAxes(
        population=_clear("population"),
        intervention=_clear("intervention"),
        outcome=_clear("outcome"),
        is_ambiguous=False,
    )
    assert not axes.is_ambiguous


def test_ambiguity_axes_one_ambiguous_propagates():
    axes = AmbiguityAxes(
        population=_clear("population"),
        intervention=_clear("intervention"),
        outcome=_ambiguous("outcome"),
        is_ambiguous=True,
    )
    assert axes.is_ambiguous


def test_ambiguity_axes_field_axis_must_match_name():
    """AmbiguityAxes.population must have axis='population' (not 'outcome')."""
    with pytest.raises(ValidationError):
        AmbiguityAxes(
            population=_clear("outcome"),  # wrong axis label for the field
            intervention=_clear("intervention"),
            outcome=_clear("outcome"),
            is_ambiguous=False,
        )


# ---------- ScopeDecision ----------

def test_scope_decision_in_scope_minimal():
    d = ScopeDecision(status="in_scope", scope_class="clinical_efficacy")
    assert d.status == "in_scope"
    assert d.scope_class == "clinical_efficacy"
    assert d.ambiguity_axes == []
    assert d.decision_id  # uuid auto-populated
    assert d.decided_at_utc.tzinfo is not None


def test_scope_decision_out_of_scope_no_class():
    d = ScopeDecision(status="out_of_scope", scope_class="out_of_scope")
    assert d.status == "out_of_scope"


def test_scope_decision_refused_no_class():
    d = ScopeDecision(status="refused", scope_class=None)
    assert d.status == "refused"
    assert d.scope_class is None


def test_scope_decision_latency_must_be_non_negative():
    with pytest.raises(ValidationError):
        ScopeDecision(status="in_scope", scope_class="clinical_efficacy", latency_ms=-1)


# ---------- assemble_scope_decision ----------

def test_assemble_refused_path():
    d = assemble_scope_decision(
        scope_class=None, ambiguity=None,
        refused=True, refusal_reason="instruction_override_attempt",
        latency_ms=42,
    )
    assert d.status == "refused"
    assert d.scope_class is None
    assert d.ambiguity_axes == []
    assert d.provenance.get("refusal_reason") == "instruction_override_attempt"
    assert d.latency_ms == 42


def test_assemble_out_of_scope_path():
    sc = ScopeClass(value="out_of_scope", confidence=1.0, provenance="regex")
    d = assemble_scope_decision(scope_class=sc, ambiguity=None, latency_ms=5)
    assert d.status == "out_of_scope"
    assert d.scope_class == "out_of_scope"
    assert d.ambiguity_axes == []
    assert d.provenance["classifier_layer"] == "regex"


def test_assemble_in_scope_no_ambiguity():
    sc = ScopeClass(value="clinical_efficacy", confidence=1.0, provenance="regex")
    axes = AmbiguityAxes(
        population=_clear("population"),
        intervention=_clear("intervention"),
        outcome=_clear("outcome"),
        is_ambiguous=False,
    )
    d = assemble_scope_decision(scope_class=sc, ambiguity=axes, latency_ms=12)
    assert d.status == "in_scope"
    assert d.scope_class == "clinical_efficacy"
    assert len(d.ambiguity_axes) == 3
    assert d.clarifications_needed == []
    assert d.provenance["ambiguity_detector_layer"] == "pico_axes_v1"


def test_assemble_in_scope_with_outcome_ambiguity():
    sc = ScopeClass(value="clinical_efficacy", confidence=1.0, provenance="regex")
    axes = AmbiguityAxes(
        population=_clear("population"),
        intervention=_clear("intervention"),
        outcome=_ambiguous("outcome"),
        is_ambiguous=True,
    )
    d = assemble_scope_decision(scope_class=sc, ambiguity=axes, latency_ms=8)
    assert d.status == "ambiguous_needs_clarification"
    assert len(d.clarifications_needed) == 1
    assert "outcome" in d.clarifications_needed[0].lower()


def test_assemble_in_scope_with_multi_axis_ambiguity():
    sc = ScopeClass(value="clinical_efficacy", confidence=1.0, provenance="regex")
    axes = AmbiguityAxes(
        population=_ambiguous("population"),
        intervention=_clear("intervention"),
        outcome=_ambiguous("outcome"),
        is_ambiguous=True,
    )
    d = assemble_scope_decision(scope_class=sc, ambiguity=axes)
    assert d.status == "ambiguous_needs_clarification"
    assert len(d.clarifications_needed) == 2  # population + outcome
    # Ordering: P, I, O — population clarification before outcome
    pop_idx = next(i for i, c in enumerate(d.clarifications_needed) if "population" in c.lower())
    out_idx = next(i for i, c in enumerate(d.clarifications_needed) if "outcome" in c.lower())
    assert pop_idx < out_idx


def test_assemble_raises_when_in_scope_classifier_but_no_ambiguity():
    sc = ScopeClass(value="clinical_efficacy", confidence=1.0, provenance="regex")
    with pytest.raises(ValueError, match="ambiguity is required"):
        assemble_scope_decision(scope_class=sc, ambiguity=None)


def test_assemble_raises_when_no_class_and_not_refused():
    with pytest.raises(ValueError, match="scope_class is required"):
        assemble_scope_decision(scope_class=None, ambiguity=None, refused=False)


# ---------- Round-trip JSON serialization (golden test compat) ----------

def test_scope_decision_serializes_to_json():
    sc = ScopeClass(value="clinical_efficacy", confidence=1.0, provenance="regex")
    axes = AmbiguityAxes(
        population=_clear("population"),
        intervention=_clear("intervention"),
        outcome=_ambiguous("outcome"),
        is_ambiguous=True,
    )
    d = assemble_scope_decision(scope_class=sc, ambiguity=axes, latency_ms=12)
    payload = d.model_dump(mode="json")
    assert payload["status"] == "ambiguous_needs_clarification"
    assert payload["scope_class"] == "clinical_efficacy"
    assert isinstance(payload["decided_at_utc"], str)  # ISO 8601 string
    assert isinstance(payload["latency_ms"], int)
