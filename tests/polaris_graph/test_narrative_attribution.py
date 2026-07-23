"""STEP 4: real source metadata reaches the writer without source loss."""

import src.polaris_graph.generator.multi_section_generator as generator
from src.polaris_graph.generator.source_attribution import build_attribution_coverage


def _rows():
    return [
        {
            "evidence_id": "ev_a",
            "statement": "A supported statement.",
            "direct_quote": "A supported statement.",
            "source_url": "https://example.invalid/a",
            "authors": [{"display_name": "A. Person"}],
            "venue": "Archive Alpha",
            "publication_year": 2021,
            "composition_weight": 0.82,
        },
        {
            "evidence_id": "ev_b",
            "statement": "Another supported statement.",
            "direct_quote": "Another supported statement.",
            "source_url": "https://example.invalid/b",
            "composition_weight": 0.19,
        },
    ]


def test_default_off_writer_blocks_are_unchanged(monkeypatch):
    monkeypatch.delenv("PG_NARRATIVE_ATTRIBUTION", raising=False)
    monkeypatch.delenv("PG_BASKET_SYNTHESIS", raising=False)
    text = generator._build_writer_evidence_blocks(_rows())
    assert "source_metadata:" not in text
    assert text.count("<<<evidence:") == 2


def test_actual_author_venue_year_and_weight_reach_writer(monkeypatch):
    monkeypatch.setenv("PG_NARRATIVE_ATTRIBUTION", "1")
    monkeypatch.delenv("PG_BASKET_SYNTHESIS", raising=False)
    text = generator._build_writer_evidence_blocks(_rows())
    assert "evidence_id=ev_a" in text
    assert "author=A. Person" in text
    assert "venue=Archive Alpha" in text
    assert "year=2021" in text
    assert "prominence_weight=0.820000" in text
    # Missing metadata is omitted, not filled with an invented placeholder.
    ev_b_block = text.split("<<<evidence:ev_b>>>", 1)[1]
    assert "author=" not in ev_b_block and "venue=" not in ev_b_block and "year=" not in ev_b_block


def test_attribution_coverage_is_lossless_even_when_metadata_missing():
    coverage = build_attribution_coverage(_rows())
    assert coverage["input_count"] == coverage["packed_count"] == 2
    assert coverage["missing_metadata_count"] == 1
    assert [record["evidence_id"] for record in coverage["records"]] == ["ev_a", "ev_b"]


def test_prompt_directive_uses_continuous_prominence_without_threshold():
    directive = generator._NARRATIVE_ATTRIBUTION_DIRECTIVE.lower()
    assert "continuously" in directive
    assert "never invent" in directive
    assert "lower-weight sources remain available" in directive
    assert "top-" not in directive and "threshold" not in directive


def test_reduce_sidecar_pack_covers_every_row_and_carries_basket_ids(monkeypatch):
    monkeypatch.setenv("PG_NARRATIVE_ATTRIBUTION", "1")
    monkeypatch.setenv("PG_BASKET_SYNTHESIS", "1")
    rows = [
        {"evidence_id": "ev_a", "author": "A. One", "evidence_basket_ids": ["c1"]},
        {"evidence_id": "ev_b", "year": 2022, "evidence_basket_ids": ["c1", "c2"]},
    ]
    pack = generator._build_writer_sidecar_pack(rows)
    assert len(pack.splitlines()) == len(rows)
    assert "evidence_id=ev_a" in pack and "basket_ids=c1" in pack
    assert "evidence_id=ev_b" in pack and "basket_ids=c1, c2" in pack


def test_contract_narrative_receives_actual_frame_row_metadata(monkeypatch):
    monkeypatch.setenv("PG_NARRATIVE_ATTRIBUTION", "1")
    prompt = "Source citation marker (use verbatim with no modification): [entity_a]"
    pack = generator._contract_narrative_metadata_pack(
        prompt,
        {
            "entity_a": {
                "evidence_id": "entity_a",
                "authors": ["A. One"],
                "journal": "Actual Venue",
                "year": 2021,
            },
            "entity_b": {"evidence_id": "entity_b", "author": "Must Not Leak"},
        },
    )
    assert "evidence_id=entity_a" in pack
    assert "author=A. One" in pack
    assert "venue=Actual Venue" in pack
    assert "year=2021" in pack
    assert "entity_b" not in pack and "Must Not Leak" not in pack
