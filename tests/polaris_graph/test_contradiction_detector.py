"""
Tests for Phase 3 contradiction detector.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.contradiction_detector import (
    ContradictionRecord,
    detect_contradictions,
    extract_numeric_claims,
    format_contradictions_for_user,
)


def _ev(
    ev_id: str,
    quote: str,
    tier: str = "T1",
    url: str | None = None,
) -> dict:
    # A17 same-source guard: a CROSS-source contradiction requires the disagreeing numbers to come
    # from DIFFERENT sources. Real evidence from two trials/publications carries two URLs, so the
    # default source_url is distinct per evidence_id (the old shared placeholder was an unrealistic
    # artifact that the guard now correctly treats as one within-source span). Pass an explicit
    # shared `url=` to exercise the same-source (not_comparable) path.
    return {
        "evidence_id": ev_id,
        "direct_quote": quote,
        "tier": tier,
        "source_url": url if url is not None else f"https://example.com/{ev_id}",
    }


def test_weight_loss_contradiction_detected() -> None:
    # STEP 1 vs STEP 5 semaglutide weight loss disagreement
    evidence = [
        _ev("ev_step1",
            "Adults receiving semaglutide 2.4 mg achieved a mean weight loss of "
            "14.9% at week 68.",
        ),
        _ev("ev_step5",
            "Semaglutide 2.4 mg produced a mean weight loss of 17.4% at week 104 "
            "in the STEP 5 trial.",
        ),
    ]
    claims = extract_numeric_claims(evidence)
    assert len(claims) == 2
    records = detect_contradictions(claims)
    assert len(records) == 1
    r = records[0]
    assert r.subject == "semaglutide"
    # Fix-1: predicate now carries dose suffix like "weight loss (2.4 mg)".
    assert r.predicate.startswith("weight loss")
    # Values 14.9 and 17.4 -> relative diff ~0.168, abs 2.5
    assert r.relative_difference > 0.10
    assert r.absolute_difference >= 2.5
    assert r.severity in {"medium", "high"}


def test_no_contradiction_for_aligned_values() -> None:
    evidence = [
        _ev("ev1", "Semaglutide produced weight loss of 15.0% at 68 weeks."),
        _ev("ev2", "Semaglutide achieved a mean weight loss of 15.2% in adults."),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    # 15.0 vs 15.2 — rel diff ~1.3% — below threshold
    assert records == []


def test_single_claim_no_contradiction() -> None:
    evidence = [_ev("ev1", "Weight loss was 14.9% with semaglutide.")]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    assert records == []


def test_three_way_contradiction() -> None:
    evidence = [
        _ev("ev_low", "semaglutide weight loss 10.0% at week 52"),
        _ev("ev_mid", "semaglutide weight loss 14.9% at week 68"),
        _ev("ev_high", "semaglutide weight loss 17.4% at week 104"),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    assert len(records) == 1
    # All three claims should be grouped together; min = 10, max = 17.4
    assert len(records[0].claims) == 3
    assert records[0].absolute_difference > 7.0


def test_different_predicates_not_grouped() -> None:
    evidence = [
        _ev("ev1", "semaglutide weight loss of 14.9% at week 68"),
        _ev("ev2", "semaglutide hba1c reduction of 1.6 percentage points"),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    # Different predicates — no single-group contradiction possible
    assert records == []


def test_different_drugs_not_grouped() -> None:
    evidence = [
        _ev("ev1", "semaglutide weight loss of 14.9% at 68 weeks"),
        _ev("ev2", "tirzepatide weight loss of 22.5% at 72 weeks"),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    # Different drugs — no cross-drug contradiction
    assert records == []


def test_abs_threshold_prevents_false_positives_on_small_values() -> None:
    evidence = [
        _ev("ev1", "incidence of pancreatitis was 0.1% in semaglutide arm"),
        _ev("ev2", "incidence of pancreatitis was 0.3% in semaglutide arm"),
    ]
    claims = extract_numeric_claims(evidence)
    # rel diff = 200% but abs diff = 0.2 (below abs_threshold=1.0 default)
    records = detect_contradictions(claims)
    assert records == []


def test_format_contradictions_output() -> None:
    evidence = [
        _ev("ev_low", "semaglutide weight loss 10.0% at week 52"),
        _ev("ev_high", "semaglutide weight loss 17.4% at week 104"),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    text = format_contradictions_for_user(records)
    assert "Detected 1" in text
    assert "semaglutide" in text
    assert "weight loss" in text
    assert "ev_low" in text
    assert "ev_high" in text


def test_same_source_numeric_span_not_a_cross_source_contradiction() -> None:
    # A17 same-source guard (iarch007 FETCH-P0): two conflicting numbers from the SAME source are a
    # within-source numeric span, NOT a cross-source contradiction. They are DISCLOSED as a
    # not_comparable bucket (never dropped — §-1.3) and kept OUT of the headline contradiction count.
    shared = "https://example.com/one-review-article"
    evidence = [
        _ev("ev_a", "semaglutide weight loss 10.0% at week 52", url=shared),
        _ev("ev_b", "semaglutide weight loss 17.4% at week 104", url=shared),
    ]
    claims = extract_numeric_claims(evidence)
    records = detect_contradictions(claims)
    # The bucket is surfaced (disclosed), but marked not_comparable — no hard cross-source assertion.
    assert len(records) == 1
    assert records[0].not_comparable is True
    assert "[not_comparable]" in records[0].predicate
    # Excluded from the headline count: format reports zero cross-source contradictions.
    text = format_contradictions_for_user(records)
    assert "Detected 0" in text
    assert "not-comparable" in text.lower()


def test_format_empty_contradictions() -> None:
    text = format_contradictions_for_user([])
    assert "No contradictions" in text


def test_custom_thresholds_override_env() -> None:
    # 14.9 vs 15.2 — below defaults, above strict
    evidence = [
        _ev("ev1", "semaglutide weight loss 14.9% at 68 weeks"),
        _ev("ev2", "semaglutide weight loss 15.2% at 68 weeks"),
    ]
    claims = extract_numeric_claims(evidence)
    # Default: no contradiction
    assert detect_contradictions(claims) == []
    # Strict: threshold 0.01 (1%) + abs 0.0 -> contradiction
    records = detect_contradictions(claims, rel_threshold=0.01, abs_threshold=0.0)
    assert len(records) == 1
