"""Unit tests for MoST Phase E: Evidence Self-Exploration."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.polaris_graph.schemas import SectionDraft
from src.polaris_graph.synthesis.evidence_explorer import (
    _find_unused_evidence,
    _match_evidence_to_sections,
    explore_unused_evidence,
)


def _make_section(sid: str, title: str, content: str) -> SectionDraft:
    return SectionDraft(
        section_id=sid, title=title, content=content,
        claims_made=[], evidence_ids=[],
    )


def _make_evidence(eid: str, statement: str, relevance: float = 0.5) -> dict:
    return {
        "evidence_id": eid,
        "statement": statement,
        "relevance_score": relevance,
        "source_url": "https://example.com",
        "source_title": "Example Source",
    }


class TestFindUnusedEvidence:
    def test_identifies_uncited(self):
        sections = [
            _make_section("s01", "Intro", "Content [CITE:ev_aaa] and [CITE:ev_bbb]"),
        ]
        evidence = [
            _make_evidence("ev_aaa", "Fact A", 0.9),
            _make_evidence("ev_bbb", "Fact B", 0.8),
            _make_evidence("ev_ccc", "Fact C", 0.7),
            _make_evidence("ev_ddd", "Fact D", 0.6),
        ]
        unused = _find_unused_evidence(sections, evidence)
        unused_ids = [e["evidence_id"] for e in unused]
        assert "ev_ccc" in unused_ids
        assert "ev_ddd" in unused_ids
        assert "ev_aaa" not in unused_ids
        assert "ev_bbb" not in unused_ids

    def test_all_cited_returns_empty(self):
        sections = [
            _make_section("s01", "All", "[CITE:ev_aaa] [CITE:ev_bbb]"),
        ]
        evidence = [
            _make_evidence("ev_aaa", "A"),
            _make_evidence("ev_bbb", "B"),
        ]
        assert _find_unused_evidence(sections, evidence) == []

    def test_sorted_by_relevance(self):
        sections = [_make_section("s01", "X", "no citations here")]
        evidence = [
            _make_evidence("ev_low", "Low", 0.2),
            _make_evidence("ev_high", "High", 0.9),
            _make_evidence("ev_mid", "Mid", 0.5),
        ]
        unused = _find_unused_evidence(sections, evidence)
        assert unused[0]["evidence_id"] == "ev_high"
        assert unused[1]["evidence_id"] == "ev_mid"
        assert unused[2]["evidence_id"] == "ev_low"


class TestMatchEvidenceToSections:
    def test_respects_threshold(self):
        unused = [_make_evidence("ev_x", "completely unrelated gibberish topic xyz")]
        sections = [_make_section("s01", "Water Filtration Methods", "Methods of filtering water")]
        matches = _match_evidence_to_sections(unused, sections, threshold=0.99)
        assert len(matches) == 0  # Threshold too high

    def test_caps_per_section(self):
        unused = [_make_evidence(f"ev_{i}", f"water filtration method {i} analysis") for i in range(10)]
        sections = [_make_section("s01", "Water Filtration Analysis Methods", "water filtration analysis methods")]
        matches = _match_evidence_to_sections(unused, sections, threshold=0.01, max_per_section=3)
        assert len(matches.get("s01", [])) <= 3


@pytest.mark.asyncio
async def test_explore_noop_when_all_cited():
    client = MagicMock()
    sections = [_make_section("s01", "Intro", "[CITE:ev_aaa]")]
    evidence = [_make_evidence("ev_aaa", "Fact A")]
    result = await explore_unused_evidence(client, sections, evidence, {}, "query")
    assert len(result) == 1
    assert result[0].content == "[CITE:ev_aaa]"


@pytest.mark.asyncio
async def test_explore_empty_evidence():
    client = MagicMock()
    sections = [_make_section("s01", "Intro", "Content")]
    result = await explore_unused_evidence(client, sections, [], {}, "query")
    assert len(result) == 1


@pytest.mark.asyncio
async def test_enrich_adds_citations_to_section(monkeypatch):
    """Phase E enriches a section with new citations from unused evidence."""
    monkeypatch.setenv("PG_EXPLORE_SIMILARITY_THRESHOLD", "0.01")
    monkeypatch.setenv("PG_EXPLORE_MAX_NEW_PER_SECTION", "5")

    original_content = (
        "Water filtration methods are critical for public health [CITE:ev_aaa]. "
        "Reverse osmosis and activated carbon are the most common approaches "
        "used in municipal water treatment facilities across the country."
    )

    sections = [
        _make_section("s01", "Water Filtration Methods", original_content),
    ]
    evidence = [
        _make_evidence("ev_aaa", "Water filtration is critical for public health", 0.9),
        _make_evidence(
            "ev_aaa001",
            "Advanced water filtration methods including nanofiltration "
            "achieve 99.9% pathogen removal in municipal treatment facilities",
            0.8,
        ),
    ]

    # Mock LLM to return enriched content with new citation
    enriched_content = (
        "Water filtration methods are critical for public health [CITE:ev_aaa]. "
        "Reverse osmosis and activated carbon are the most common approaches "
        "used in municipal water treatment facilities across the country. "
        "Advanced nanofiltration methods can achieve 99.9% pathogen removal "
        "in similar facilities [CITE:ev_aaa001]."
    )
    mock_resp = MagicMock()
    mock_resp.content = enriched_content
    client = AsyncMock()
    client.generate = AsyncMock(return_value=mock_resp)

    result = await explore_unused_evidence(client, sections, evidence, {}, "water filtration")
    assert len(result) == 1

    enriched_sec = result[0]
    # New citation should be present
    assert "[CITE:ev_aaa001]" in enriched_sec.content
    # Original citation preserved
    assert "[CITE:ev_aaa]" in enriched_sec.content
    # Word count should be >= original (enrichment adds, not removes)
    assert len(enriched_sec.content.split()) >= len(original_content.split())
    # evidence_ids should include the new ID
    assert "ev_aaa001" in enriched_sec.evidence_ids
