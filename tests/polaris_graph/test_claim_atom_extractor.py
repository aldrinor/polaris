from __future__ import annotations

from src.polaris_graph.generator.claim_atom_extractor import (
    ClaimAtom,
    build_atom_catalog,
    extract_atoms_from_evidence,
    extract_verbatim_value_unit_spans,
    filter_atoms_for_section,
    format_atom_catalog_for_prompt,
    format_refusal_for_missing_atom,
    normalize_value_unit,
)


def _row(
    quote: str,
    *,
    evidence_id: str = "ev_001",
    section: str = "",
) -> dict[str, str]:
    row = {
        "evidence_id": evidence_id,
        "tier": "T1",
        "title": "ORION-4 evaluation",
        "direct_quote": quote,
    }
    if section:
        row["section"] = section
    return row


def test_extracts_complete_nonclinical_frame() -> None:
    atoms = extract_atoms_from_evidence(_row(
        "Model Orion reduced median latency by 18.4 ms compared with "
        "Model Vega at 30 days."
    ))
    assert len(atoms) == 1
    atom = atoms[0]
    assert atom.entity == "Model Orion"
    assert atom.endpoint == "median latency"
    assert atom.comparator == "Model Vega"
    assert atom.timepoint == "30 days"
    assert atom.value == "18.4"
    assert atom.unit == "ms"
    assert atom.confidence == "high"


def test_atom_schema_and_source_span_are_stable() -> None:
    quote = "Model Orion reduced latency by -18.4 ms."
    atom = extract_atoms_from_evidence(_row(quote))[0]
    assert set(atom.__dataclass_fields__) == {
        "atom_id", "evidence_id", "span_start", "span_end", "literal_text",
        "entity", "endpoint", "comparator", "timepoint", "value", "unit",
        "primary_section", "section_tags", "tier", "value_signed",
        "confidence", "provenance_class", "source_paper_title",
    }
    assert atom.atom_id == "atom_001"
    assert atom.literal_text in quote
    assert atom.value_signed is True


def test_multiple_values_in_source_list_are_preserved() -> None:
    atoms = extract_atoms_from_evidence(_row(
        "Median latency decreased by 18.4 ms under Profile A, "
        "21.2 ms under Profile B, and 24.6 ms under Profile C."
    ))
    assert {atom.value for atom in atoms} == {"18.4", "21.2", "24.6"}
    assert {atom.unit for atom in atoms} == {"ms"}


def test_unitless_effect_measure_survives_but_interval_numbers_do_not() -> None:
    atoms = extract_atoms_from_evidence(_row(
        "Model A reported a hazard ratio of 0.74 "
        "(95% CI 0.62 to 0.88)."
    ))
    assert [(atom.endpoint, atom.value, atom.unit) for atom in atoms] == [
        ("hazard ratio", "0.74", ""),
    ]


def test_design_identifiers_and_timepoints_are_not_outcome_atoms() -> None:
    atoms = extract_atoms_from_evidence(_row(
        "ORION-4 was a phase 3 study lasting 30 days with N=480."
    ))
    assert atoms == []


def test_generic_markdown_table_uses_source_headers() -> None:
    atoms = extract_atoms_from_evidence(_row(
        "| Measure | Model A | Model B |\n"
        "|---|---:|---:|\n"
        "| Failure rate | 17.4% | 22.1% |\n"
        "| Median latency | 18.4 ms | 24.6 ms |"
    ))
    assert {(a.entity, a.value, a.unit) for a in atoms} == {
        ("Model A", "17.4", "%"),
        ("Model B", "22.1", "%"),
        ("Model A", "18.4", "ms"),
        ("Model B", "24.6", "ms"),
    }
    assert {a.endpoint for a in atoms} == {"Failure rate", "Median latency"}


def test_metadata_supplies_measure_and_entity_without_ontology() -> None:
    atoms = extract_atoms_from_evidence({
        "evidence_id": "ev_meta",
        "metric": "cycle efficiency",
        "entity": "Reactor Q",
        "direct_quote": "The reported value was 91.7%.",
    })
    assert len(atoms) == 1
    assert atoms[0].endpoint == "cycle efficiency"
    assert atoms[0].entity == "Reactor Q"


def test_row_section_metadata_controls_routing() -> None:
    catalog = build_atom_catalog([
        _row("Model A reduced latency by 18.4 ms.", section="Performance"),
        _row(
            "Model A reduced energy use by 7.5 kWh.",
            evidence_id="ev_002",
            section="Energy",
        ),
    ])
    performance = filter_atoms_for_section(catalog, "Performance results")
    assert {atom.evidence_id for atom in performance.values()} == {"ev_001"}
    assert all(atom.primary_section == "Performance" for atom in performance.values())


def test_unlabeled_section_local_atoms_remain_available() -> None:
    catalog = build_atom_catalog([
        _row("Model A reduced latency by 18.4 ms."),
    ])
    assert filter_atoms_for_section(catalog, "Any evidence section") == catalog


def test_catalog_numbering_continues_across_rows() -> None:
    catalog = build_atom_catalog([
        _row("Model A reduced latency by 18.4 ms."),
        _row("Model B reduced latency by 24.6 ms.", evidence_id="ev_002"),
    ])
    assert list(catalog) == ["atom_001", "atom_002"]
    assert all(isinstance(atom, ClaimAtom) for atom in catalog.values())


def test_prompt_catalog_contains_only_source_derived_frame() -> None:
    catalog = build_atom_catalog([
        _row(
            "Model Orion reduced median latency by 18.4 ms compared "
            "with Model Vega at 30 days."
        ),
    ])
    rendered = format_atom_catalog_for_prompt(catalog)
    assert "value=18.4 ms" in rendered
    assert "measure=median latency" in rendered
    assert "entity=Model Orion" in rendered
    assert "compared_with=Model Vega" in rendered


def test_empty_prompt_catalog_and_refusal_are_explicit() -> None:
    assert "(empty" in format_atom_catalog_for_prompt({})
    refusal = format_refusal_for_missing_atom(
        endpoint="median latency",
        entity="Model Orion",
        timepoint="30 days",
    )
    assert "median latency" in refusal
    assert "Model Orion" in refusal
    assert "30 days" in refusal


def test_verbatim_span_and_unit_normalization_are_generic() -> None:
    spans = extract_verbatim_value_unit_spans(
        "The values were −18.4 ms, 22.0 percent, and 7.5 kWh."
    )
    assert [span.literal_text for span in spans] == [
        "−18.4 ms", "22.0 percent", "7.5 kWh",
    ]
    assert normalize_value_unit("percentage") == "%"
