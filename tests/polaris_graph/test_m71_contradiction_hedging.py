"""Evidence-derived section routing for contradiction hedging."""

from __future__ import annotations

from src.polaris_graph.generator.contradiction_hedging import (
    SectionContradictionHint,
    _is_high_severity,
    _section_keywords_for,
    filter_section_contradictions,
    render_section_hedging_block,
)


def _contradiction(
    predicate: str,
    values: list[float],
    *,
    subject: str = "Model Orion",
    tiers: list[str] | None = None,
    **metadata,
) -> dict[str, object]:
    return {
        "subject": subject,
        "predicate": predicate,
        "values": values,
        "tiers": tiers or ["T1", "T2", "T4"],
        **metadata,
    }


def test_section_keywords_come_only_from_title() -> None:
    assert _section_keywords_for("Latency and Energy Performance") == frozenset({
        "latency",
        "and",
        "energy",
        "performance",
    })
    assert _section_keywords_for("") == frozenset()


def test_high_severity_gate_is_domain_independent() -> None:
    assert _is_high_severity(
        _contradiction("median latency", [5.0, 10.0, 20.0])
    )


def test_too_few_values_fails_severity_gate() -> None:
    assert not _is_high_severity(
        _contradiction("median latency", [5.0, 20.0])
    )


def test_narrow_spread_fails_severity_gate() -> None:
    assert not _is_high_severity(
        _contradiction("median latency", [10.0, 11.0, 12.0])
    )


def test_required_source_tier_is_enforced() -> None:
    assert not _is_high_severity(
        _contradiction(
            "median latency",
            [5.0, 10.0, 20.0],
            tiers=["T2", "T4", "T6"],
        )
    )


def test_predicate_vocabulary_routes_to_matching_section() -> None:
    contradictions = [
        _contradiction("median latency", [5.0, 10.0, 20.0]),
        _contradiction("energy consumption", [2.0, 8.0, 16.0]),
    ]
    hints = filter_section_contradictions(
        "Latency performance",
        contradictions,
    )
    assert [hint.predicate for hint in hints] == ["median latency"]


def test_explicit_record_section_metadata_controls_routing() -> None:
    contradictions = [
        _contradiction(
            "failure rate",
            [1.0, 8.0, 16.0],
            section="Reliability",
        ),
    ]
    hints = filter_section_contradictions("Reliability", contradictions)
    assert len(hints) == 1
    assert hints[0].predicate == "failure rate"


def test_comparative_section_routes_generic_comparison_context() -> None:
    contradictions = [
        _contradiction(
            "throughput",
            [10.0, 20.0, 40.0],
            context="Model Orion compared with Model Vega",
        ),
    ]
    hints = filter_section_contradictions(
        "Comparative analysis",
        contradictions,
    )
    assert len(hints) == 1
    assert hints[0].predicate == "throughput"


def test_unrelated_section_excludes_contradiction() -> None:
    hints = filter_section_contradictions(
        "Legal history",
        [_contradiction("median latency", [5.0, 10.0, 20.0])],
    )
    assert hints == []


def test_low_severity_record_is_filtered_after_routing() -> None:
    hints = filter_section_contradictions(
        "Latency",
        [_contradiction("median latency", [10.0, 11.0, 12.0])],
    )
    assert hints == []


def test_requested_section_limit_keeps_largest_spreads() -> None:
    contradictions = [
        _contradiction("latency metric one", [1.0, 2.0, 10.0]),
        _contradiction("latency metric two", [1.0, 2.0, 50.0]),
        _contradiction("latency metric three", [1.0, 2.0, 30.0]),
    ]
    hints = filter_section_contradictions(
        "Latency",
        contradictions,
        max_per_section=2,
    )
    assert [hint.value_range for hint in hints] == ["1 to 50", "1 to 30"]


def test_empty_inputs_return_no_hints() -> None:
    assert filter_section_contradictions("Latency", None) == []
    assert filter_section_contradictions("Latency", []) == []
    assert filter_section_contradictions("", [
        _contradiction("median latency", [5.0, 10.0, 20.0]),
    ]) == []


def test_renderer_carries_record_values_without_domain_copy() -> None:
    block = render_section_hedging_block([
        SectionContradictionHint(
            section_title="Latency",
            subject="Model Orion",
            predicate="median latency",
            value_range="5 to 20",
            tiers=("T1", "T2", "T4"),
        ),
    ])
    assert "M-71" in block
    assert "INCLUDE ONE HEDGED SENTENCE" in block
    assert "Model Orion" in block
    assert "median latency" in block
    assert "5 to 20" in block
    assert "T1/T2/T4" in block


def test_empty_hints_render_empty() -> None:
    assert render_section_hedging_block([]) == ""
