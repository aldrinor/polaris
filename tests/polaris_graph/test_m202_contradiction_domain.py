"""Regression tests for one evidence-derived contradiction path in all domains."""

from __future__ import annotations

from src.polaris_graph.retrieval.contradiction_detector import (
    detect_contradictions,
    extract_numeric_claims,
)


def _row(evidence_id: str, quote: str) -> dict[str, str]:
    return {
        "evidence_id": evidence_id,
        "direct_quote": quote,
        "source_url": f"https://example.test/{evidence_id}",
        "tier": "T1",
    }


def test_same_extractor_handles_several_source_vocabularies() -> None:
    rows = [
        _row(
            "ev_latency",
            "Model Orion reported median latency of 18.4 ms compared with "
            "Model Vega at 30 days.",
        ),
        _row(
            "ev_adoption",
            "The agency reported adoption rate of 34% among small firms.",
        ),
        _row(
            "ev_revenue",
            "Company Atlas reported revenue growth of 23% year over year.",
        ),
    ]
    claims = extract_numeric_claims(rows)
    assert {(claim.predicate, claim.value) for claim in claims} == {
        ("median latency", 18.4),
        ("adoption rate", 34.0),
        ("revenue growth", 23.0),
    }


def test_domain_argument_does_not_select_a_vocabulary_table() -> None:
    rows = [
        _row(
            "ev_a",
            "Model Orion reported median latency of 18.4 ms compared with "
            "Model Vega at 30 days.",
        ),
    ]
    baseline = extract_numeric_claims(rows)
    for label in ("technology", "policy", "finance", "health", "unknown"):
        assert extract_numeric_claims(rows, domain=label) == baseline


def test_nonclinical_same_frame_disagreement_is_detected() -> None:
    claims = extract_numeric_claims([
        _row(
            "ev_a",
            "Model Orion reported median latency of 18.4 ms compared with "
            "Model Vega at 30 days.",
        ),
        _row(
            "ev_b",
            "Model Orion reported median latency of 24.6 ms compared with "
            "Model Vega at 30 days.",
        ),
    ])
    records = detect_contradictions(
        claims,
        rel_threshold=0.1,
        abs_threshold=0.1,
    )
    assert len(records) == 1
    assert records[0].subject == "model orion"
    assert records[0].predicate == "median latency"
    assert {claim.evidence_id for claim in records[0].claims} == {
        "ev_a",
        "ev_b",
    }


def test_domain_compatibility_argument_is_inert_in_detection() -> None:
    claims = extract_numeric_claims([
        _row(
            "ev_a",
            "Model Orion reported median latency of 18.4 ms compared with "
            "Model Vega at 30 days.",
        ),
        _row(
            "ev_b",
            "Model Orion reported median latency of 24.6 ms compared with "
            "Model Vega at 30 days.",
        ),
    ])
    kwargs = {"rel_threshold": 0.1, "abs_threshold": 0.1}
    assert detect_contradictions(claims, is_clinical=True, **kwargs) == (
        detect_contradictions(claims, is_clinical=False, **kwargs)
    )


def test_distinct_source_measures_do_not_collapse() -> None:
    claims = extract_numeric_claims([
        _row("ev_latency", "Model Orion reported median latency of 18.4 ms."),
        _row("ev_energy", "Model Orion reported energy consumption of 7.5 kWh."),
    ])
    assert {claim.predicate for claim in claims} == {
        "median latency",
        "energy consumption",
    }
    assert detect_contradictions(
        claims,
        rel_threshold=0.0,
        abs_threshold=0.0,
    ) == []
