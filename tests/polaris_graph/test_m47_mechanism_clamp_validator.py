"""Evidence-derived quantitative-process extraction tests."""

from __future__ import annotations

from src.polaris_graph.generator.multi_section_generator import (
    _m47_extract_candidate_values,
    _m47_prose_contains_value,
    _m47_row_has_quantitative_process_evidence,
    _m47_validate_quantitative_process_extraction,
)


_SOURCE_QUOTE = (
    "At 30 days, Model Orion reduced median latency by 18.4 ms. "
    "Energy consumption fell by 7.5 kWh. "
    "Failure rate decreased by 22 percent."
)


def test_row_detection_depends_on_quoted_values_not_topic_words() -> None:
    assert _m47_row_has_quantitative_process_evidence({
        "title": "ORION-4 evaluation",
        "direct_quote": _SOURCE_QUOTE,
    })
    assert not _m47_row_has_quantitative_process_evidence({
        "title": "ORION-4 evaluation",
        "direct_quote": "The scheduler uses a bounded priority queue.",
    })


def test_candidate_values_keep_source_context_and_units() -> None:
    candidates = _m47_extract_candidate_values(_SOURCE_QUOTE)
    assert {(value, unit) for _, value, unit in candidates} >= {
        (18.4, "ms"),
        (7.5, "kwh"),
        (22.0, "%"),
    }
    latency = next(item for item in candidates if item[1:] == (18.4, "ms"))
    assert "median latency" in latency[0]


def test_empty_or_nonnumeric_quote_returns_no_candidates() -> None:
    assert _m47_extract_candidate_values("") == []
    assert _m47_extract_candidate_values(
        "The scheduler routes requests through a priority queue."
    ) == []


def test_exact_value_unit_context_and_citation_match() -> None:
    assert _m47_prose_contains_value(
        "Model Orion reduced median latency by 18.4 ms [1].",
        "ev_orion",
        "Model Orion reduced median latency by 18.4 ms",
        18.4,
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
        expected_unit="ms",
    )


def test_direct_evidence_marker_is_supported() -> None:
    assert _m47_prose_contains_value(
        "Energy consumption fell by 7.5 kWh [ev_orion].",
        "ev_orion",
        "Energy consumption fell by 7.5 kWh",
        7.5,
        expected_unit="kwh",
    )


def test_value_without_same_sentence_citation_does_not_match() -> None:
    assert not _m47_prose_contains_value(
        "The source is cited here [1]. Energy consumption fell by 7.5 kWh.",
        "ev_orion",
        "Energy consumption fell by 7.5 kWh",
        7.5,
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
        expected_unit="kwh",
    )


def test_same_number_with_wrong_context_does_not_match() -> None:
    assert not _m47_prose_contains_value(
        "Throughput reached 18.4 ms [1].",
        "ev_orion",
        "Model Orion reduced median latency by 18.4 ms",
        18.4,
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
        expected_unit="ms",
    )


def test_same_number_with_wrong_unit_does_not_match() -> None:
    assert not _m47_prose_contains_value(
        "Energy consumption fell by 7.5 Wh [1].",
        "ev_orion",
        "Energy consumption fell by 7.5 kWh",
        7.5,
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
        expected_unit="kwh",
    )


def test_small_source_rounding_difference_is_tolerated() -> None:
    assert _m47_prose_contains_value(
        "Model Orion reduced median latency by 18.2 ms [1].",
        "ev_orion",
        "Model Orion reduced median latency by 18.4 ms",
        18.4,
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
        expected_unit="ms",
    )


def test_validator_passes_only_source_linked_values() -> None:
    text = (
        "Model Orion reduced median latency by 18.4 ms [1]. "
        "Energy consumption fell by 7.5 kWh [1]. "
        "Failure rate decreased by 22 percent [1]."
    )
    result = _m47_validate_quantitative_process_extraction(
        verified_text=text,
        evidence_pool={
            "ev_orion": {
                "evidence_id": "ev_orion",
                "direct_quote": _SOURCE_QUOTE,
            },
        },
        ev_ids_in_subset=["ev_orion"],
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
    )
    assert result["evidence_rows_in_subset"] == ["ev_orion"]
    assert result["any_passes_threshold"] is True
    assert result["per_paper"]["ev_orion"]["match_count"] >= 3


def test_unrelated_numbers_do_not_satisfy_validator() -> None:
    result = _m47_validate_quantitative_process_extraction(
        verified_text=(
            "The dataset contained 480 records, ran for 30 days, "
            "and used profile 5 [1]."
        ),
        evidence_pool={
            "ev_orion": {
                "evidence_id": "ev_orion",
                "direct_quote": _SOURCE_QUOTE,
            },
        },
        ev_ids_in_subset=["ev_orion"],
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
    )
    assert result["any_passes_threshold"] is False
    assert result["per_paper"]["ev_orion"]["match_count"] == 0


def test_validator_uses_richer_refetched_source_quote() -> None:
    text = (
        "Model Orion reduced median latency by 18.4 ms [1]. "
        "Energy consumption fell by 7.5 kWh [1]. "
        "Failure rate decreased by 22 percent [1]."
    )
    result = _m47_validate_quantitative_process_extraction(
        verified_text=text,
        evidence_pool={
            "ev_orion": {
                "evidence_id": "ev_orion",
                "direct_quote": "thin",
                "_m42b_refetched_quote": _SOURCE_QUOTE + " " + ("context " * 20),
            },
        },
        ev_ids_in_subset=["ev_orion"],
        biblio_slice=[{"num": 1, "evidence_id": "ev_orion"}],
    )
    assert result["any_passes_threshold"] is True


def test_no_quantitative_rows_is_an_explicit_noop() -> None:
    result = _m47_validate_quantitative_process_extraction(
        verified_text="The scheduler uses a queue [1].",
        evidence_pool={
            "ev_arch": {
                "evidence_id": "ev_arch",
                "direct_quote": "The scheduler uses a bounded queue.",
            },
        },
        ev_ids_in_subset=["ev_arch"],
        biblio_slice=[{"num": 1, "evidence_id": "ev_arch"}],
    )
    assert result["no_quantitative_evidence"] is True
    assert result["evidence_rows_in_subset"] == []
