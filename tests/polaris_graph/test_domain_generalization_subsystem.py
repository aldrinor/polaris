"""Behavioral replay for the domain-general evidence-analysis subsystem."""

from __future__ import annotations

from src.polaris_graph.generator.atom_refusal_validator import (
    requires_atom_citation,
)
from src.polaris_graph.generator.claim_atom_extractor import (
    extract_atoms_from_evidence,
)
from src.polaris_graph.generator.cross_trial_synthesis import (
    build_cross_study_synthesis,
)
from src.polaris_graph.generator.evidence_value_extractor import (
    build_allow_list_for_evidence,
)
from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _m42b_extract_from_quote,
    _m44_inject_primaries_into_outline,
    _m47_validate_quantitative_process_extraction,
)
from src.polaris_graph.generator.slot_fill import SlotFieldFill, SlotFillPayload
from src.polaris_graph.retrieval.contradiction_detector import (
    detect_contradictions,
    extract_numeric_claims,
)
from src.polaris_graph.retrieval.primary_trial_expander import (
    expand_primary_source_queries,
    get_primary_source_anchors_for_slug,
)


def _latency_row(evidence_id: str, value: str) -> dict[str, str]:
    return {
        "evidence_id": evidence_id,
        "title": "ORION-4 latency study",
        "entity": "Model Orion",
        "metric": "median latency",
        "tier": "T1",
        "direct_quote": (
            f"Model Orion reduced median latency by {value} ms compared "
            "with Model Vega at 30 days."
        ),
    }


def test_nonclinical_claim_frame_and_refusal_trigger() -> None:
    atoms = extract_atoms_from_evidence(_latency_row("ev_a", "18.4"))
    assert len(atoms) == 1
    atom = atoms[0]
    assert atom.entity == "Model Orion"
    assert atom.endpoint == "median latency"
    assert atom.comparator == "Model Vega"
    assert atom.timepoint == "30 days"
    assert atom.value == "18.4"
    assert atom.unit == "ms"
    assert requires_atom_citation(
        "Model Orion reduced median latency by 18.4 ms compared with Model Vega."
    )[0]


def test_nonclinical_contradiction_uses_shared_source_frame() -> None:
    claims = extract_numeric_claims([
        _latency_row("ev_a", "18.4"),
        _latency_row("ev_b", "24.6"),
    ])
    records = detect_contradictions(
        claims,
        rel_threshold=0.1,
        abs_threshold=0.1,
    )
    assert len(records) == 1
    assert records[0].subject == "model orion"
    assert records[0].predicate == "median latency"
    assert {claim.evidence_id for claim in records[0].claims} == {"ev_a", "ev_b"}


def test_study_frame_builder_derives_measure_and_units() -> None:
    quote = (
        "The dataset contained N=480 requests. Baseline median latency was "
        "42.0 ms. The primary measure was median latency at 30 days. "
        "Model Orion reduced median latency by 18.4 ms "
        "(95% CI 16.1 to 20.7) compared with Model Vega."
    )
    cells = _m42b_extract_from_quote(
        quote,
        {
            "evidence_id": "ev_a",
            "title": "ORION-4 latency study",
            "direct_quote": quote,
        },
    )
    assert cells == {
        "n": "480",
        "baseline": "42.0 ms",
        "comparator": "Model Vega",
        "endpoint": "median latency",
        "timepoint": "30 days",
        "effect": "18.4 ms",
    }


def test_primary_source_routing_uses_evidence_vocabulary() -> None:
    plans = [
        SectionPlan("Performance", "Compare median latency results.", ["ev_other"]),
        SectionPlan("Energy", "Compare energy consumption.", ["ev_energy"]),
    ]
    updated, log = _m44_inject_primaries_into_outline(
        plans,
        {"ORION-4": ["ev_primary"]},
        evidence_pool={
            "ev_primary": {
                "title": "ORION-4 latency study",
                "metric": "median latency",
            },
        },
    )
    assert updated[0].ev_ids[0] == "ev_primary"
    assert "ev_primary" not in updated[1].ev_ids
    assert any(item["action"] == "injected" for item in log)


def test_quantitative_process_validation_is_field_neutral() -> None:
    quote = (
        "Model Orion reduced median latency by 18.4 ms; "
        "throughput increased 22.0 percent; energy use fell 7.5 kWh."
    )
    result = _m47_validate_quantitative_process_extraction(
        (
            "Model Orion reduced median latency by 18.4 ms [1]. "
            "Throughput increased 22.0 percent [1]. "
            "Energy use fell 7.5 kWh [1]."
        ),
        {"ev_a": {"evidence_id": "ev_a", "direct_quote": quote}},
        ["ev_a"],
        [{"num": 1, "evidence_id": "ev_a"}],
    )
    assert result["any_passes_threshold"] is True
    assert result["per_paper"]["ev_a"]["match_count"] == 3


def test_allow_list_and_primary_query_copy_evidence_metadata() -> None:
    allow = build_allow_list_for_evidence(
        "ev_a",
        "Model Orion reported 18.4 ms.",
        "ORION-4 evaluated Model Orion.",
        metadata={
            "title": "ORION-4 evaluation",
            "model_name": "Model Orion",
        },
    )
    assert "18.4 ms" in allow.numbers
    assert "Model Orion" in allow.names
    template = {
        "per_query_primary_source_anchors": {
            "latency": ["ORION-4"],
        },
    }
    assert get_primary_source_anchors_for_slug(template, "latency") == ["ORION-4"]
    assert expand_primary_source_queries(
        "How do the systems compare?", template, "latency",
    ) == ['"ORION-4" How do the systems compare?']


def test_cross_study_synthesis_uses_shared_payload_fields() -> None:
    def payload(identifier: str, latency: str) -> SlotFillPayload:
        return SlotFillPayload(
            slot_id=f"slot_{identifier}",
            entity_id=identifier,
            subsection_title=identifier,
            bound_ev_id=f"ev_{identifier}",
            fields=(
                SlotFieldFill(
                    field_name="median_latency",
                    status="extracted",
                    value=latency,
                    bound_ev_id=f"ev_{identifier}",
                    source_span=latency,
                ),
            ),
            provenance_class="open_access",
        )

    block = build_cross_study_synthesis([
        payload("ORION-4", "18.4 ms"),
        payload("VEGA-2", "24.6 ms"),
    ])
    patterns = block.get_for_section("Cross-study synthesis")
    assert patterns
    assert "median latency" in patterns[0].summary
    assert "18.4 ms" in patterns[0].summary
    assert "24.6 ms" in patterns[0].summary
