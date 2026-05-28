"""Fixtures for the two-lane claim-audit scorer (I-safety-002b / #925). Pure logic, no model."""

from __future__ import annotations

import pytest

from src.polaris_graph.benchmark.claim_audit_scorer import (
    ClaimRow,
    RubricElement,
    SystemQuestionLedger,
    aggregate,
    lane1_faithfulness,
    lane2_coverage,
    system_passes_question,
)


# --- ClaimRow validation (every non-VERIFIED material verdict needs evidence) ---
def test_unreachable_requires_subtype() -> None:
    with pytest.raises(ValueError, match="unreachable_subtype"):
        ClaimRow("c1", "S1", "UNREACHABLE", "cit1", None)
    ok = ClaimRow("c1", "S1", "UNREACHABLE", "cit1", None, unreachable_subtype="paywall")
    assert ok.unreachable_subtype == "paywall"


def test_subtype_only_for_unreachable() -> None:
    with pytest.raises(ValueError, match="only valid for UNREACHABLE"):
        ClaimRow("c1", "S1", "VERIFIED", "cit1", "span", unreachable_subtype="paywall")


def test_fabricated_requires_span() -> None:
    with pytest.raises(ValueError, match="requires a span_quote"):
        ClaimRow("c1", "S1", "FABRICATED", "cit1", None)
    ClaimRow("c1", "S1", "FABRICATED", "cit1", "the source says the opposite")  # ok


def test_unsupported_cited_requires_traceability() -> None:
    # cited but no span and no note -> must fail (traceability, Codex P2)
    with pytest.raises(ValueError, match="traceability"):
        ClaimRow("c1", "S1", "UNSUPPORTED", "cit1", None)
    # explicit no-support note is acceptable
    ClaimRow("c1", "S1", "UNSUPPORTED", "cit1", None, audit_note="no supporting span found")
    # UNCITED unsupported claim needs nothing extra (it is unsupported BY CITATION)
    ClaimRow("c2", "S1", "UNSUPPORTED", None, None)


# --- Lane 1: material-only (S3 excluded), partial weighting, hard-fail count ---
def test_lane1_s3_excluded_and_partial_weight() -> None:
    rows = [
        ClaimRow("c1", "S1", "VERIFIED", "a", "s"),
        ClaimRow("c2", "S2", "PARTIAL", "b", "partial span"),
        ClaimRow("c3", "S2", "UNSUPPORTED", "c", None, audit_note="no supporting span in cited source"),
        ClaimRow("c4", "S3", "FABRICATED", "d", "ignored stylistic"),  # S3 -> excluded
    ]
    l1 = lane1_faithfulness(rows)
    assert l1["material_atoms"] == 3            # S3 excluded
    assert l1["observed_S3_excluded"] == 1
    # weighted bad = UNSUPPORTED(1) + 0.5*PARTIAL(1) = 1.5 ; rate = 1.5/3 = 0.5
    assert l1["weighted_unsupported_or_worse"] == pytest.approx(1.5)
    assert l1["unsupported_or_worse_rate"] == pytest.approx(0.5)
    assert l1["hard_fail_count"] == 1           # only UNSUPPORTED (PARTIAL is not a hard fail)


def test_lane1_unreachable_counts_but_not_hard_fail() -> None:
    rows = [
        ClaimRow("c1", "S1", "VERIFIED", "a", "s"),
        ClaimRow("c2", "S1", "UNREACHABLE", "b", None, unreachable_subtype="paywall"),
    ]
    l1 = lane1_faithfulness(rows)
    # UNREACHABLE counts in the rate (full weight) but is NOT a hard fail (distinct from FABRICATED)
    assert l1["unsupported_or_worse_rate"] == pytest.approx(0.5)
    assert l1["hard_fail_count"] == 0


# --- Lane 2: only covered-AND-citation-supported counts ---
def test_lane2_requires_citation_support() -> None:
    rubric = [
        RubricElement("e1", covered=True, citation_supported=True),
        RubricElement("e2", covered=True, citation_supported=False),  # covered but not supported
        RubricElement("e3", covered=False, citation_supported=False),
    ]
    l2 = lane2_coverage(rubric)
    assert l2["covered"] == 2
    assert l2["covered_and_citation_supported"] == 1
    assert l2["coverage_fraction"] == pytest.approx(1 / 3)
    assert set(l2["missing"]) == {"e2", "e3"}


# --- system_passes: BOTH gates (zero hard-fail AND coverage >= 0.70) ---
def _good_rubric(n_supported: int, total: int) -> list[RubricElement]:
    return [RubricElement(f"e{i}", covered=i < n_supported, citation_supported=i < n_supported)
            for i in range(total)]


def test_system_passes_both_gates() -> None:
    rows = [ClaimRow("c1", "S1", "VERIFIED", "a", "s"), ClaimRow("c2", "S2", "VERIFIED", "b", "s")]
    res = system_passes_question(rows, _good_rubric(8, 10))  # 0.80 coverage
    assert res["passed"] is True
    assert res["reasons"] == []


def test_system_fails_on_hard_fail_even_with_coverage() -> None:
    rows = [ClaimRow("c1", "S1", "FABRICATED", "a", "source refutes it")]
    res = system_passes_question(rows, _good_rubric(10, 10))  # perfect coverage
    assert res["passed"] is False
    assert any("FABRICATED" in r for r in res["reasons"])


def test_system_fails_on_low_coverage_even_if_faithful() -> None:
    # terse but faithful: 1 verified claim, but only 0.50 coverage -> fails (anti-terse-gaming)
    rows = [ClaimRow("c1", "S1", "VERIFIED", "a", "s")]
    res = system_passes_question(rows, _good_rubric(5, 10))  # 0.50 < 0.70
    assert res["passed"] is False
    assert any("coverage" in r for r in res["reasons"])


def test_coverage_threshold_boundary() -> None:
    rows = [ClaimRow("c1", "S1", "VERIFIED", "a", "s")]
    assert system_passes_question(rows, _good_rubric(7, 10))["passed"] is True   # 0.70 == threshold
    assert system_passes_question(rows, _good_rubric(6, 10))["passed"] is False  # 0.60 < 0.70


# --- aggregate: per-system, no cross-system "wins" ---
def test_aggregate_no_wins_field() -> None:
    rows_good = [ClaimRow("c1", "S1", "VERIFIED", "a", "s")]
    rows_bad = [ClaimRow("c1", "S1", "FABRICATED", "a", "refuted")]
    ledgers = [
        SystemQuestionLedger("polaris", "Q02", rows_good, _good_rubric(8, 10)),
        SystemQuestionLedger("chatgpt", "Q02", rows_bad, _good_rubric(8, 10)),
    ]
    agg = aggregate(ledgers)
    assert "wins" not in str(agg).lower() or "superiority" in agg["note"]
    assert agg["by_system"]["polaris"]["passed"] == 1
    assert agg["by_system"]["chatgpt"]["passed"] == 0
    assert agg["by_system"]["chatgpt"]["hard_fails"] == 1
