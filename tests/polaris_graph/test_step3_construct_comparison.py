"""I-deepfix-001 (#1369) DEPTH Step 3 — construct-level cross-source numeric comparison.

Proves two numbers from DIFFERENT subjects that share a unit + a KNOWN construct (Frey-Osborne vs
Eloundou vs ILO exposure %) now license the non-directional "; for comparison, " connective, while a
different construct (exposure % vs wage pp) or an unknown construct does NOT pair (fail-closed). Also
proves the candidacy predicate admits a construct pair when the numeric key lookup is threaded. Pure /
offline: deterministic key tuples, zero network.
"""

import types

import pytest

from src.polaris_graph.generator.numeric_comparator import license_numeric_comparison
from src.polaris_graph.generator import cross_source_synthesis as css

# legacy numeric merge key shape: ("numeric", subject, predicate, value, unit, dose, arm, endpoint)
# arm must NOT be "treatment" (that is the unknown sentinel -> fail-closed).
K_EXPOSE_46 = ("numeric", "share of jobs", "highly exposed to llms", 46.0, "%", "na", "overall", "na")
K_EXPOSE_24 = ("numeric", "clerical tasks", "highly exposed", 24.0, "%", "na", "overall", "na")
K_WAGE_PP = ("numeric", "wages", "reduced by", 0.42, "pp", "na", "overall", "na")   # LABOR_EFFECT, pp
K_UNKNOWN = ("numeric", "gizmos", "counted in the depot", 100.0, "widgets", "na", "overall", "na")  # no construct


def _on(monkeypatch):
    monkeypatch.setenv("PG_NUMERIC_COMPARATOR", "1")
    monkeypatch.setenv("PG_NUMERIC_CONSTRUCT_COMPARISON", "1")


def test_same_construct_different_subject_pairs(monkeypatch):
    _on(monkeypatch)
    # 46% of jobs exposed vs 24% of clerical tasks exposed — both EXPOSURE_SHARE in %, different subjects.
    assert license_numeric_comparison(K_EXPOSE_46, K_EXPOSE_24) == "comparison"


def test_different_construct_does_not_pair(monkeypatch):
    _on(monkeypatch)
    # exposure % vs wage pp — different construct (EXPOSURE_SHARE vs LABOR_EFFECT) AND different unit.
    assert license_numeric_comparison(K_EXPOSE_46, K_WAGE_PP) is None


def test_unknown_construct_not_comparable(monkeypatch):
    _on(monkeypatch)
    # no lexicon hit -> _construct_tag None -> fail-closed, not comparable.
    assert license_numeric_comparison(K_EXPOSE_46, K_UNKNOWN) is None


def test_gate_off_no_construct_pair(monkeypatch):
    monkeypatch.setenv("PG_NUMERIC_COMPARATOR", "1")
    monkeypatch.setenv("PG_NUMERIC_CONSTRUCT_COMPARISON", "0")  # construct path OFF
    # different subjects -> exact-discriminator path can't match; construct path disabled -> None.
    assert license_numeric_comparison(K_EXPOSE_46, K_EXPOSE_24) is None


def test_exact_identity_path_still_licenses(monkeypatch):
    _on(monkeypatch)
    # SAME discriminators, DIFFERENT value -> the pre-existing exact path still returns "comparison".
    k_same_a = ("numeric", "jobs", "exposed", 46.0, "%", "na", "overall", "na")
    k_same_b = ("numeric", "jobs", "exposed", 30.0, "%", "na", "overall", "na")
    assert license_numeric_comparison(k_same_a, k_same_b) == "comparison"


def test_identical_values_never_compare(monkeypatch):
    _on(monkeypatch)
    same_val = ("numeric", "clerical tasks", "highly exposed", 46.0, "%", "na", "overall", "na")
    assert license_numeric_comparison(K_EXPOSE_46, same_val) is None  # equal values -> no comparison


def test_candidacy_admits_construct_pair(monkeypatch):
    """_pair_is_plan_candidate admits a construct pair when the numeric key lookup is threaded."""
    _on(monkeypatch)
    a = types.SimpleNamespace(claim_cluster_id="ca", subject="share of jobs", predicate="exposed")
    b = types.SimpleNamespace(claim_cluster_id="cb", subject="clerical tasks", predicate="exposed")
    lookup = {"ca": K_EXPOSE_46, "cb": K_EXPOSE_24}
    admitted = css._pair_is_plan_candidate(
        a, b, "ca", "cb", edges=None, agree_map=None, equiv_clusters=None,
        numeric_key_by_cluster=lookup,
    )
    assert admitted is True
    # a different-construct pair is NOT admitted on the numeric leg (no facet/edge either)
    c = types.SimpleNamespace(claim_cluster_id="cc", subject="wages", predicate="reduced")
    lookup2 = {"ca": K_EXPOSE_46, "cc": K_WAGE_PP}
    assert css._pair_is_plan_candidate(
        a, c, "ca", "cc", edges=None, agree_map=None, equiv_clusters=None,
        numeric_key_by_cluster=lookup2,
    ) is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
