"""Evidence-derived cross-study synthesis tests."""

from __future__ import annotations

from src.polaris_graph.generator.cross_trial_synthesis import (
    CrossStudySynthesisBlock,
    build_cross_study_synthesis,
    build_cross_trial_synthesis,
    render_cross_study_synthesis_block,
    render_cross_trial_synthesis_block,
)
from src.polaris_graph.generator.slot_fill import SlotFieldFill, SlotFillPayload


def _payload(
    entity_id: str,
    fields: dict[str, str],
    *,
    title: str = "",
) -> SlotFillPayload:
    return SlotFillPayload(
        slot_id=f"slot_{entity_id}",
        entity_id=entity_id,
        subsection_title=title,
        bound_ev_id=f"ev_{entity_id}",
        fields=tuple(
            SlotFieldFill(
                field_name=name,
                status="extracted",
                value=value,
                bound_ev_id=f"ev_{entity_id}",
                source_span=value,
            )
            for name, value in fields.items()
        ),
        provenance_class="direct",
    )


def _study_payloads() -> list[SlotFillPayload]:
    return [
        _payload(
            "orion_4",
            {
                "median_latency": "18.4 ms",
                "comparison_condition": "Model Vega",
                "sample_size": "480",
            },
            title="ORION-4",
        ),
        _payload(
            "nova_2",
            {
                "median_latency": "24.6 ms",
                "comparison_condition": "Model Atlas",
                "sample_size": "512",
            },
            title="NOVA-2",
        ),
    ]


def test_shared_source_fields_generate_cross_study_patterns() -> None:
    block = build_cross_study_synthesis(_study_payloads())
    patterns = block.get_for_section("Cross-study synthesis")
    summaries = [pattern.summary for pattern in patterns]
    assert any(
        "median latency" in summary
        and "ORION-4: 18.4 ms" in summary
        and "NOVA-2: 24.6 ms" in summary
        for summary in summaries
    )
    assert any(
        pattern.pattern_type == "comparison_conditions"
        for pattern in patterns
    )


def test_field_names_and_values_come_from_payloads() -> None:
    payloads = [
        _payload("alpha", {"spectral_flux": "4.2 Jy"}, title="Alpha"),
        _payload("beta", {"spectral_flux": "5.8 Jy"}, title="Beta"),
    ]
    block = build_cross_study_synthesis(payloads)
    summaries = [
        pattern.summary
        for pattern in block.get_for_section("Cross-study synthesis")
    ]
    assert summaries == [
        "Across the evidence units, spectral flux is reported as follows: "
        "Alpha: 4.2 Jy; Beta: 5.8 Jy."
    ]


def test_single_payload_does_not_claim_a_cross_study_pattern() -> None:
    block = build_cross_study_synthesis([
        _payload("orion_4", {"median_latency": "18.4 ms"}),
    ])
    assert block.section_to_patterns == {}


def test_payload_without_extracted_fields_is_skipped() -> None:
    payload = SlotFillPayload(
        slot_id="slot_empty",
        entity_id="empty",
        subsection_title="Empty",
        bound_ev_id="ev_empty",
        fields=(
            SlotFieldFill(
                field_name="median_latency",
                status="not_extractable",
                value=None,
                bound_ev_id="ev_empty",
                source_span=None,
            ),
        ),
        provenance_class="direct",
    )
    assert build_cross_study_synthesis([payload, *_study_payloads()]).get_for_section(
        "Cross-study synthesis"
    )


def test_field_reported_by_only_one_source_is_not_synthesized() -> None:
    payloads = _study_payloads()
    payloads[0] = _payload(
        "orion_4",
        {
            "median_latency": "18.4 ms",
            "unique_field": "source-only value",
        },
        title="ORION-4",
    )
    summaries = [
        pattern.summary
        for pattern in build_cross_study_synthesis(payloads).get_for_section(
            "Cross-study synthesis"
        )
    ]
    assert all("unique field" not in summary for summary in summaries)


def test_renderer_includes_source_values_and_evidence_markers() -> None:
    rendered = render_cross_study_synthesis_block(
        "Cross-study synthesis",
        build_cross_study_synthesis(_study_payloads()),
    )
    assert "CROSS-STUDY SYNTHESIS CONTEXT" in rendered
    assert "18.4 ms" in rendered
    assert "24.6 ms" in rendered
    assert "[ev_orion_4]" in rendered
    assert "[ev_nova_2]" in rendered


def test_renderer_does_not_infer_direction_or_causality() -> None:
    rendered = render_cross_study_synthesis_block(
        "Cross-study synthesis",
        build_cross_study_synthesis(_study_payloads()),
    )
    instruction = rendered.casefold()
    assert "do not add a trend, mechanism, or conclusion" in instruction


def test_unknown_section_has_no_context() -> None:
    block = build_cross_study_synthesis(_study_payloads())
    assert block.get_for_section("Methods") == []
    assert render_cross_study_synthesis_block("Methods", block) == ""


def test_empty_block_renders_empty() -> None:
    assert render_cross_study_synthesis_block(
        "Cross-study synthesis",
        CrossStudySynthesisBlock(),
    ) == ""


def test_historical_api_aliases_delegate_to_general_behavior() -> None:
    canonical = build_cross_study_synthesis(_study_payloads())
    historical = build_cross_trial_synthesis(_study_payloads())
    assert historical == canonical
    assert render_cross_trial_synthesis_block(
        "Cross-study synthesis",
        historical,
    ) == render_cross_study_synthesis_block(
        "Cross-study synthesis",
        canonical,
    )
