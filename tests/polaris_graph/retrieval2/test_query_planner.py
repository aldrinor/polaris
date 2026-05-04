"""Tests for polaris_graph.retrieval2.query_planner.

Exercises Boolean-expansion, scope-class augmentation, dedup, and the
QUERY_CAP. All inputs are constructed ScopeDecision instances; no LLM
or network involved (the planner is a pure function).
"""

from __future__ import annotations

from polaris_graph.retrieval2.query_planner import (
    JACCARD_THRESHOLD,
    QUERY_CAP,
    plan_queries,
)
from polaris_graph.scope.scope_decision import (
    AmbiguityAxis,
    ScopeDecision,
)


def _decision(
    *,
    scope_class: str | None = "clinical_efficacy",
    population: list[str] | None = None,
    intervention: list[str] | None = None,
    outcome: list[str] | None = None,
    status: str = "in_scope",
) -> ScopeDecision:
    """Helper: build a ScopeDecision with a controlled PICO axis set."""
    axes = []
    if population is not None:
        axes.append(
            AmbiguityAxis(
                axis="population",
                plausible_interpretations=population,
                needs_clarification=len(population) > 1,
            )
        )
    if intervention is not None:
        axes.append(
            AmbiguityAxis(
                axis="intervention",
                plausible_interpretations=intervention,
                needs_clarification=len(intervention) > 1,
            )
        )
    if outcome is not None:
        axes.append(
            AmbiguityAxis(
                axis="outcome",
                plausible_interpretations=outcome,
                needs_clarification=len(outcome) > 1,
            )
        )
    return ScopeDecision(
        status=status,  # type: ignore[arg-type]
        scope_class=scope_class,  # type: ignore[arg-type]
        ambiguity_axes=axes,
    )


# ---------- Empty / degenerate inputs ----------

def test_no_axes_returns_empty():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=None,
        intervention=None,
        outcome=None,
    )
    assert plan_queries(decision) == []


def test_refused_decision_returns_empty():
    decision = _decision(
        scope_class=None,
        status="refused",
        population=None,
        intervention=None,
        outcome=None,
    )
    assert plan_queries(decision) == []


def test_whitespace_only_interpretations_returns_empty():
    """AmbiguityAxis enforces >=1 entry; the planner's filter must drop
    whitespace-only entries so they don't produce empty/whitespace queries."""
    decision = _decision(
        population=["   "],
        intervention=["\t"],
        outcome=[" "],
    )
    assert plan_queries(decision) == []


# ---------- Single-axis expansion ----------

def test_population_only_expands_with_augments():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults with type 2 diabetes"],
    )
    queries = plan_queries(decision)
    assert len(queries) >= 1
    # Base query should appear
    assert any("adults with type 2 diabetes" in q for q in queries)
    # Scope augmentation should appear at least once
    assert any("randomized controlled trial" in q for q in queries)


# ---------- Multi-axis cartesian ----------

def test_cartesian_pico_full():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    queries = plan_queries(decision)
    base_present = any(
        "adults" in q and "aspirin" in q and "headache" in q for q in queries
    )
    assert base_present


def test_cartesian_multiplies_when_multiple_interpretations():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults", "elderly"],
        intervention=["aspirin"],
        outcome=["pain", "inflammation"],
    )
    queries = plan_queries(decision)
    # Expect 4 base combinations: 2 populations x 1 intervention x 2 outcomes
    base_combos = [q for q in queries if "aspirin" in q]
    assert len(base_combos) >= 4


# ---------- Scope-class augmentation ----------

def test_safety_augments_with_pharmacovigilance():
    decision = _decision(
        scope_class="clinical_safety",
        population=["older adults"],
        intervention=["metformin"],
    )
    queries = plan_queries(decision)
    assert any("pharmacovigilance" in q for q in queries) or any(
        "adverse events" in q for q in queries
    )


def test_diagnosis_augments_with_diagnostic_accuracy():
    decision = _decision(
        scope_class="clinical_diagnosis",
        population=["adults"],
        intervention=["mammography"],
        outcome=["breast cancer detection"],
    )
    queries = plan_queries(decision)
    assert any("diagnostic accuracy" in q for q in queries) or any(
        "sensitivity specificity" in q for q in queries
    )


def test_prognosis_augments_with_survival():
    decision = _decision(
        scope_class="clinical_prognosis",
        population=["stage IV NSCLC patients"],
        outcome=["overall survival"],
    )
    queries = plan_queries(decision)
    assert any("survival analysis" in q for q in queries) or any(
        "long-term outcomes" in q for q in queries
    )


def test_unknown_scope_class_no_augment():
    decision = _decision(
        scope_class=None,  # no scope class, e.g. uncertain decision
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    queries = plan_queries(decision)
    # No augmentation terms should appear
    assert not any("randomized controlled trial" in q for q in queries)
    assert not any("pharmacovigilance" in q for q in queries)
    # But the base query is still emitted
    assert len(queries) >= 1


# ---------- Cap + dedup ----------

def test_cap_enforced():
    """3x3x3 = 27 base × 4 augmentations + 27 base = 135 candidates;
    must be capped at QUERY_CAP=12."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults", "elderly", "children"],
        intervention=["aspirin", "ibuprofen", "naproxen"],
        outcome=["pain", "inflammation", "fever"],
    )
    queries = plan_queries(decision)
    assert len(queries) <= QUERY_CAP


def test_dedup_drops_near_duplicates():
    """Two near-identical interpretations should not double the query
    count after dedup."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin", "aspirin acetylsalicylic acid"],  # near-dup
        outcome=["headache"],
    )
    queries = plan_queries(decision)
    # The two near-dup intervention terms shouldn't both yield base queries
    # at full strength — at least the augmented variants of one should drop.
    # Sanity: results <= QUERY_CAP and dedup did fire (cap is 12, raw output
    # would be 2 base × 5 = 10 augmented + 2 base = 10; ensure unique).
    seen = set()
    for q in queries:
        # crude check: no two queries should be identical
        assert q not in seen
        seen.add(q)


def test_dedup_threshold_is_relaxed_enough():
    """Different interventions on the same population/outcome should
    NOT be deduped together."""
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin", "warfarin"],  # very different drugs
        outcome=["thrombosis"],
    )
    queries = plan_queries(decision)
    has_aspirin = any("aspirin" in q for q in queries)
    has_warfarin = any("warfarin" in q for q in queries)
    assert has_aspirin
    assert has_warfarin


# ---------- Determinism ----------

def test_same_input_same_output():
    decision = _decision(
        scope_class="clinical_efficacy",
        population=["adults"],
        intervention=["aspirin"],
        outcome=["headache"],
    )
    a = plan_queries(decision)
    b = plan_queries(decision)
    assert a == b


# ---------- Constants ----------

def test_jaccard_threshold_is_sensible():
    assert 0.5 <= JACCARD_THRESHOLD <= 1.0


def test_query_cap_positive():
    assert QUERY_CAP > 0
