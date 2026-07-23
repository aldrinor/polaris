"""Domain-neutral claim-frame and deterministic study-summary tests."""

from __future__ import annotations

import inspect

from src.polaris_graph.generator.multi_section_generator import (
    MultiSectionResult,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    _m42b_extract_from_quote,
    _m42b_year_from_row,
    _m66_row_passes_quality_gate,
    build_trial_summary_and_timeline_from_evidence,
    generate_multi_section_report,
)
from src.polaris_graph.retrieval.live_retriever import refetch_for_extraction


_ORION_QUOTE = (
    "In ORION-4, the dataset contained N=480 requests. "
    "Baseline median latency was 42.0 ms. "
    "Model Orion was compared with Model Vega. "
    "The primary measure was median latency at 30 days. "
    "Model Orion reduced median latency by 18.4 ms "
    "(95% CI 16.1 to 20.7)."
)
_NOVA_QUOTE = (
    "In NOVA-2, the sample size was 512 records. "
    "Initial median latency was 48.0 ms. "
    "Model Nova was compared with Model Atlas. "
    "The primary outcome was median latency after 45 days. "
    "Model Nova reduced median latency by 24.6 ms "
    "(95% CI 21.0 to 28.2)."
)


def _rows() -> list[dict[str, str]]:
    return [
        {
            "evidence_id": "ev_orion",
            "title": "ORION-4 evaluation",
            "url": "https://example.test/2023/orion",
            "direct_quote": _ORION_QUOTE,
        },
        {
            "evidence_id": "ev_nova",
            "title": "NOVA-2 evaluation",
            "url": "https://example.test/2024/nova",
            "direct_quote": _NOVA_QUOTE,
        },
    ]


def _bibliography() -> list[dict[str, object]]:
    return [
        {"num": 1, "evidence_id": "ev_orion"},
        {"num": 2, "evidence_id": "ev_nova"},
    ]


def test_writer_prompt_preserves_general_claim_frame_capability() -> None:
    prompt = SECTION_SYSTEM_PROMPT_TEMPLATE
    assert "Claim-frame discipline" in prompt
    for phrase in (
        "population or sample size",
        "baseline value",
        "comparator or control condition",
        "primary endpoint with its timepoint",
        "evidence-supplied frame elements",
    ):
        assert phrase in prompt


def test_writer_prompt_formats_without_literal_placeholder_collision() -> None:
    rendered = SECTION_SYSTEM_PROMPT_TEMPLATE.format(
        title="Performance",
        focus="Compare source-reported latency.",
    )
    assert 'writing the "Performance" section' in rendered
    assert "Compare source-reported latency." in rendered


def test_extracts_complete_source_frame() -> None:
    assert _m42b_extract_from_quote(_ORION_QUOTE) == {
        "n": "480",
        "baseline": "42.0 ms",
        "comparator": "Model Vega",
        "endpoint": "median latency",
        "timepoint": "30 days",
        "effect": "18.4 ms",
    }


def test_identifier_digits_do_not_become_baseline_values() -> None:
    cells = _m42b_extract_from_quote(
        "Baseline Signal-A1c was 8.28 units. "
        "The main measure was Signal-A1c at 40 days. "
        "Signal-A1c changed by 2.30 units (95% CI 2.1 to 2.5)."
    )
    assert cells["baseline"] == "8.28 units"
    assert cells["baseline"] != "1c"


def test_row_metadata_fills_missing_source_frame_fields() -> None:
    cells = _m42b_extract_from_quote(
        "The source reports a measured result.",
        {
            "sample_size": "73",
            "baseline_value": "12.0 units",
            "reference_group": "Configuration B",
            "measure": "cycle efficiency",
            "timepoint": "6 hours",
            "effect_estimate": "4.2 percent",
        },
    )
    assert cells == {
        "n": "73",
        "baseline": "12.0 units",
        "comparator": "Configuration B",
        "endpoint": "cycle efficiency",
        "timepoint": "6 hours",
        "effect": "4.2 percent",
    }


def test_empty_quote_has_empty_frame() -> None:
    assert set(_m42b_extract_from_quote("").values()) == {""}


def test_year_is_derived_from_url_quote_or_refetch() -> None:
    assert _m42b_year_from_row({
        "url": "https://example.test/2023/article",
    }) == "2023"
    assert _m42b_year_from_row({
        "url": "https://example.test/article",
        "direct_quote": "Ng et al. reported the evaluation in 2022.",
    }) == "2022"
    assert _m42b_year_from_row({
        "url": "https://example.test/article",
        "direct_quote": "No date here.",
        "_m42b_refetched_quote": "The source was released in 2021.",
    }) == "2021"


def test_builder_renders_source_derived_table_and_timeline() -> None:
    table, timeline = build_trial_summary_and_timeline_from_evidence(
        selected_rows=_rows(),
        primary_trial_anchors=["ORION-4", "NOVA-2"],
        bibliography=_bibliography(),
    )
    assert table.splitlines()[0] == (
        "| Study | N | Baseline | Comparator | Measure | Result | Ref |"
    )
    assert "| ORION-4 | 480 | 42.0 ms | Model Vega | median latency | " in table
    assert "| NOVA-2 | 512 | 48.0 ms | Model Atlas | median latency | " in table
    assert "[1]" in table and "[2]" in table
    assert "| 2023 | ORION-4 | 18.4 ms | [1] |" in timeline
    assert "| 2024 | NOVA-2 | 24.6 ms | [2] |" in timeline


def test_thin_quote_is_not_replaced_by_statement_text() -> None:
    rows = _rows()
    rows[0]["direct_quote"] = "Thin."
    rows[0]["statement"] = _ORION_QUOTE
    table, timeline = build_trial_summary_and_timeline_from_evidence(
        selected_rows=rows,
        primary_trial_anchors=["ORION-4", "NOVA-2"],
        bibliography=_bibliography(),
        refetch_fn=None,
    )
    assert table == ""
    assert timeline == ""


def test_refetch_can_restore_a_thin_source_quote() -> None:
    rows = _rows()
    rows[0]["direct_quote"] = "Thin."

    def _refetch(url: str, max_chars: int = 2000) -> str:
        del max_chars
        return _ORION_QUOTE if "orion" in url else ""

    table, timeline = build_trial_summary_and_timeline_from_evidence(
        selected_rows=rows,
        primary_trial_anchors=["ORION-4", "NOVA-2"],
        bibliography=_bibliography(),
        refetch_fn=_refetch,
    )
    assert "ORION-4" in table and "NOVA-2" in table
    assert "2023" in timeline and "2024" in timeline
    assert rows[0]["_m42b_refetched_quote"] == _ORION_QUOTE


def test_row_without_bibliography_match_is_not_rendered() -> None:
    table, timeline = build_trial_summary_and_timeline_from_evidence(
        selected_rows=_rows(),
        primary_trial_anchors=["ORION-4", "NOVA-2"],
        bibliography=[{"num": 1, "evidence_id": "ev_other"}],
    )
    assert table == ""
    assert timeline == ""


def test_no_configured_identifiers_returns_empty() -> None:
    assert build_trial_summary_and_timeline_from_evidence(
        selected_rows=_rows(),
        primary_trial_anchors=[],
        bibliography=_bibliography(),
    ) == ("", "")


def test_quality_gate_rejects_dangling_comparator_fragment() -> None:
    assert not _m66_row_passes_quality_gate({
        "n": "480",
        "baseline": "42.0 ms",
        "comparator": "Configuration B with",
        "endpoint": "median latency",
        "timepoint": "30 days",
        "effect": "18.4 ms",
    })


def test_quality_gate_rejects_timepoint_only_placeholder() -> None:
    assert not _m66_row_passes_quality_gate({
        "n": "",
        "baseline": "",
        "comparator": "Configuration B",
        "endpoint": "",
        "timepoint": "30 days",
        "effect": "",
    })


def test_quality_gate_keeps_partial_but_numeric_source_frame() -> None:
    assert _m66_row_passes_quality_gate({
        "n": "480",
        "baseline": "",
        "comparator": "Configuration B",
        "endpoint": "median latency",
        "timepoint": "30 days",
        "effect": "",
    })


def test_refetch_helper_contract_is_stable() -> None:
    signature = inspect.signature(refetch_for_extraction)
    assert list(signature.parameters) == ["url", "max_chars"]
    assert signature.parameters["max_chars"].default == 2000


def test_result_schema_and_generation_signature_retain_compatibility() -> None:
    result = MultiSectionResult(
        sections=[],
        outline=[],
        bibliography=[],
        total_words=0,
        total_sentences_verified=0,
        total_sentences_dropped=0,
        total_input_tokens=0,
        total_output_tokens=0,
    )
    assert result.trial_timeline_text == ""
    signature = inspect.signature(generate_multi_section_report)
    assert signature.parameters["primary_trial_anchors"].default is None
