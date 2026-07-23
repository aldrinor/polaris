"""Domain-neutral tests for atom citation validation and gap rendering."""

from __future__ import annotations

import json

from src.polaris_graph.generator.atom_refusal_validator import (
    RefusalAction,
    RefusalReason,
    build_gaps_document,
    extract_atom_citations,
    extract_ev_citations,
    has_ev_citation_for_factual_claim,
    requires_atom_citation,
    split_sentences,
    validate_section,
    validate_sentence,
    write_gaps_sidecar,
)
from src.polaris_graph.generator.claim_atom_extractor import ClaimAtom


def _atom(
    atom_id: str,
    value: str,
    *,
    measure: str = "median latency",
    entity: str = "Model Orion",
    unit: str = "ms",
) -> ClaimAtom:
    return ClaimAtom(
        atom_id=atom_id,
        evidence_id="ev_001",
        span_start=0,
        span_end=80,
        literal_text=f"{entity} reported {measure} of {value} {unit}.",
        entity=entity,
        endpoint=measure,
        comparator="Model Vega",
        timepoint="30 days",
        value=value,
        unit=unit,
        primary_section="Performance",
        section_tags=("Performance",),
        tier="T1",
        value_signed=value.startswith("-"),
        confidence="high",
        provenance_class="direct",
        source_paper_title="ORION-4 evaluation",
    )


_CATALOG = {
    "atom_001": _atom("atom_001", "18.4"),
    "atom_002": _atom("atom_002", "24.6", entity="Model Vega"),
    "atom_003": _atom(
        "atom_003",
        "7.5",
        measure="energy consumption",
        unit="kWh",
    ),
}


def test_number_with_source_derived_measure_requires_atom() -> None:
    assert requires_atom_citation(
        "Model Orion reduced median latency by 18.4 ms."
    ) == (True, "trigger_A_number_plus_endpoint")


def test_unlabelled_result_number_requires_atom() -> None:
    assert requires_atom_citation(
        "The measured effect was 0.32."
    ) == (True, "trigger_A_number_plus_endpoint")


def test_structural_numbers_do_not_require_atom() -> None:
    for sentence in (
        "ORION-4 was evaluated in phase 3.",
        "The evaluation lasted 30 days.",
        "The dataset contained N=480 requests.",
        "The report was published in 2024.",
        "Profile B was configured at 15 units.",
    ):
        assert requires_atom_citation(sentence)[0] is False


def test_identifier_suffix_is_not_treated_as_a_result() -> None:
    assert requires_atom_citation("The source identifier is ORION-4.")[0] is False


def test_qualitative_comparison_requires_atom() -> None:
    required, trigger = requires_atom_citation(
        "Model Orion produced lower latency than Model Vega."
    )
    assert required
    assert trigger == "trigger_qualitative_comparative"


def test_nonnumeric_explanation_remains_narrative() -> None:
    assert requires_atom_citation(
        "The scheduler routes work through a bounded priority queue."
    )[0] is False


def test_result_attribution_remains_detected_inside_design_context() -> None:
    required, _ = requires_atom_citation(
        "In a phase 3 evaluation, median latency was 18.4 ms."
    )
    assert required


def test_comparative_result_with_timepoint_requires_atom() -> None:
    required, _ = requires_atom_citation(
        "After 30 days, Model Orion reduced latency by 18.4 ms "
        "compared with Model Vega."
    )
    assert required


def test_citation_parsers_are_stable() -> None:
    sentence = "Values were 18.4 atom_001 and 24.6 atom_002 [ev_017]."
    assert extract_atom_citations(sentence) == ["atom_001", "atom_002"]
    assert extract_ev_citations(sentence) == ["ev_017"]


def test_ev_citation_alone_does_not_satisfy_numeric_claim() -> None:
    assert has_ev_citation_for_factual_claim(
        "Median latency was 18.4 ms [ev_017]."
    )
    assert not has_ev_citation_for_factual_claim(
        "The evaluation protocol is described in [ev_017]."
    )


def test_missing_atom_citation_is_refused() -> None:
    record = validate_sentence(
        "Model Orion reduced median latency by 18.4 ms.",
        0,
        "performance",
        "Performance",
        _CATALOG,
    )
    assert record.action is RefusalAction.REFUSED
    assert record.reason is RefusalReason.MISSING_ATOM_CITATION
    assert "Insufficient verified atom-level evidence" in record.rendered_text


def test_invalid_atom_is_refused() -> None:
    record = validate_sentence(
        "Median latency was 18.4 ms atom_999.",
        0,
        "performance",
        "Performance",
        _CATALOG,
    )
    assert record.action is RefusalAction.REFUSED
    assert record.reason is RefusalReason.INVALID_ATOM_ID
    assert record.missing_atoms == ["atom_999"]


def test_ev_citation_for_claim_is_refused() -> None:
    record = validate_sentence(
        "Median latency was 18.4 ms [ev_017].",
        0,
        "performance",
        "Performance",
        _CATALOG,
    )
    assert record.action is RefusalAction.REFUSED
    assert record.reason is RefusalReason.EV_CITATION_FOR_CLAIM


def test_all_referenced_atoms_must_exist() -> None:
    record = validate_sentence(
        "Values were 18.4 atom_001 and 24.6 atom_999.",
        0,
        "performance",
        "Performance",
        _CATALOG,
    )
    assert record.action is RefusalAction.REFUSED
    assert record.missing_atoms == ["atom_999"]


def test_matching_atom_value_is_allowed() -> None:
    record = validate_sentence(
        "Model Orion reduced median latency by 18.4 ms atom_001.",
        0,
        "performance",
        "Performance",
        _CATALOG,
    )
    assert record.action is RefusalAction.ALLOWED
    assert record.reason is RefusalReason.NO_VIOLATION


def test_value_mismatch_is_logged_without_rewriting() -> None:
    sentence = "Model Orion reduced median latency by 19.8 ms atom_001."
    record = validate_sentence(
        sentence,
        0,
        "performance",
        "Performance",
        _CATALOG,
    )
    assert record.action is RefusalAction.LOGGED_ONLY
    assert record.reason is RefusalReason.SOFT_MISMATCH
    assert record.rendered_text == sentence


def test_narrative_sentence_is_allowed() -> None:
    record = validate_sentence(
        "The scheduler uses a bounded priority queue.",
        0,
        "architecture",
        "Architecture",
        _CATALOG,
    )
    assert record.action is RefusalAction.ALLOWED


def test_sentence_splitter_preserves_decimals_and_parentheticals() -> None:
    assert split_sentences(
        "Latency was 18.4 ms (CI 16.1 to 20.7). Energy fell by 7.5 kWh."
    ) == [
        "Latency was 18.4 ms (CI 16.1 to 20.7).",
        "Energy fell by 7.5 kWh.",
    ]


def test_validate_section_keeps_soft_mismatch_and_replaces_refusal() -> None:
    result = validate_section(
        "The scheduler uses a queue. "
        "Latency was 18.4 ms atom_001. "
        "Latency was 19.8 ms atom_001. "
        "Energy consumption decreased by 7.5 kWh.",
        "performance",
        "Performance",
        _CATALOG,
    )
    assert result.allowed_count == 2
    assert result.soft_mismatch_count == 1
    assert result.refusal_count == 1
    assert "Insufficient verified atom-level evidence" in result.rendered_text


def test_gaps_document_and_sidecar_schema(tmp_path) -> None:
    result = validate_section(
        "Median latency was 18.4 ms.",
        "performance",
        "Performance",
        _CATALOG,
    )
    document = build_gaps_document("doc-1", [result])
    assert document["totals"] == {
        "total_sentences": 1,
        "refused": 1,
        "soft_mismatch": 0,
        "allowed": 0,
    }
    path = write_gaps_sidecar(tmp_path, "doc-1", [result])
    assert json.loads(path.read_text(encoding="utf-8"))["document_id"] == "doc-1"
