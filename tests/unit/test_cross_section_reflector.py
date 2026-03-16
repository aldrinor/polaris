"""Unit tests for MoST Phase R: Cross-Section Self-Reflection."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.polaris_graph.schemas import SectionDraft
from src.polaris_graph.synthesis.cross_section_reflector import (
    _build_reflection_context,
    _detect_contradictions,
    _parse_reflection_json,
    reflect_across_sections,
)


def _make_section(sid: str, title: str, content: str, ev_ids: list[str] | None = None) -> SectionDraft:
    return SectionDraft(
        section_id=sid,
        title=title,
        content=content,
        claims_made=[],
        evidence_ids=ev_ids or [],
    )


class TestBuildReflectionContext:
    def test_selects_adjacent_sections(self):
        sections = [
            _make_section("s01", "Introduction", "First section [CITE:ev_aaa]"),
            _make_section("s02", "Methods", "Second section [CITE:ev_bbb]"),
            _make_section("s03", "Results", "Third section [CITE:ev_ccc]"),
        ]
        ev_map = {"s01": {"ev_aaa"}, "s02": {"ev_bbb"}, "s03": {"ev_ccc"}}
        idx_map = {"s01": 0, "s02": 1, "s03": 2}
        ctx = _build_reflection_context(
            target=sections[1], target_index=1, all_sections=sections,
            section_evidence_map=ev_map, section_index_map=idx_map, max_context=2,
        )
        assert "Introduction" in ctx or "Results" in ctx

    def test_selects_evidence_overlap_sections(self):
        sections = [
            _make_section("s01", "Alpha", "Content [CITE:ev_aa] [CITE:ev_bb] [CITE:ev_cc]"),
            _make_section("s02", "Beta", "Other [CITE:ev_xxx]"),
            _make_section("s03", "Gamma", "Unrelated filler content"),
            _make_section("s04", "Delta", "More [CITE:ev_aa] [CITE:ev_bb] [CITE:ev_cc]"),
        ]
        # s04 shares 3 evidence with s01; s02 is adjacent but shares 0
        ev_map = {
            "s01": {"ev_aa", "ev_bb", "ev_cc"},
            "s02": {"ev_xxx"},
            "s03": set(),
            "s04": {"ev_aa", "ev_bb", "ev_cc"},
        }
        idx_map = {"s01": 0, "s02": 1, "s03": 2, "s04": 3}
        ctx = _build_reflection_context(
            target=sections[0], target_index=0, all_sections=sections,
            section_evidence_map=ev_map, section_index_map=idx_map, max_context=1,
        )
        # s04 has perfect evidence overlap (Jaccard=1.0 * 2.0 = 2.0) > s02 adjacency bonus (1.0)
        assert "Delta" in ctx


class TestDetectContradictions:
    def test_parses_valid_json(self):
        reflection = {
            "contradictions": [
                {"claim": "Water is safe", "conflicts_with": "Water has toxins", "resolution": "Clarify scope"},
            ],
            "redundancies": [],
            "cross_references": [],
            "revision_needed": True,
        }
        result = _detect_contradictions(reflection)
        assert len(result) == 1
        assert result[0]["claim"] == "Water is safe"

    def test_handles_empty(self):
        assert _detect_contradictions({}) == []
        assert _detect_contradictions({"contradictions": "invalid"}) == []


class TestParseReflectionJson:
    def test_direct_json(self):
        result = _parse_reflection_json('{"revision_needed": true, "contradictions": []}')
        assert result is not None
        assert result["revision_needed"] is True

    def test_code_fenced(self):
        text = "Here is the result:\n```json\n{\"revision_needed\": false}\n```"
        result = _parse_reflection_json(text)
        assert result is not None
        assert result["revision_needed"] is False


@pytest.mark.asyncio
async def test_reflect_skips_single_section():
    client = MagicMock()
    sections = [_make_section("s01", "Only Section", "Content")]
    result = await reflect_across_sections(client, sections, [], "test query")
    assert len(result) == 1
    assert result[0].section_id == "s01"


@pytest.mark.asyncio
async def test_reflect_no_contradictions_no_revision(monkeypatch):
    monkeypatch.setenv("PG_MOST_ENABLED", "1")
    monkeypatch.setenv("PG_REFLECTION_MAX_CONTEXT", "2")

    mock_resp = MagicMock()
    mock_resp.content = '{"contradictions": [], "redundancies": [], "cross_references": [], "revision_needed": false}'
    client = AsyncMock()
    client.generate = AsyncMock(return_value=mock_resp)

    sections = [
        _make_section("s01", "Intro", "Intro content [CITE:ev_aaa]"),
        _make_section("s02", "Methods", "Methods content [CITE:ev_bbb]"),
    ]
    result = await reflect_across_sections(client, sections, [], "test query", concurrency=1)
    assert len(result) == 2
    # No revisions should have happened
    assert result[0].content == "Intro content [CITE:ev_aaa]"
    assert result[1].content == "Methods content [CITE:ev_bbb]"


@pytest.mark.asyncio
async def test_reflect_revises_contradicting_sections(monkeypatch):
    """Phase R detects contradiction and revises section with CASE_2 guard."""
    monkeypatch.setenv("PG_REFLECTION_MAX_CONTEXT", "2")

    original_content = (
        "Water filtration methods [CITE:ev_aaa] include reverse osmosis "
        "and activated carbon. These methods remove 99% of contaminants "
        "[CITE:ev_bbb] from municipal water supplies effectively."
    )

    # First LLM call: reflection — returns contradiction detected, revision needed
    reflection_resp = MagicMock()
    reflection_resp.content = (
        '{"contradictions": [{"claim": "remove 99% of contaminants", '
        '"conflicts_with": "only 85% removal in field studies", '
        '"resolution": "Qualify with field study caveat"}], '
        '"redundancies": [], "cross_references": [], "revision_needed": true}'
    )

    # Second LLM call: revision — returns revised prose (80-130% of original word count)
    revised_content = (
        "Water filtration methods [CITE:ev_aaa] include reverse osmosis "
        "and activated carbon. These methods remove up to 99% of contaminants "
        "[CITE:ev_bbb] in controlled conditions."
    )
    revision_resp = MagicMock()
    revision_resp.content = revised_content

    # generate() returns reflection first, then revision
    client = AsyncMock()
    client.generate = AsyncMock(side_effect=[reflection_resp, revision_resp])

    sections = [
        _make_section("s01", "Filtration", original_content, ["ev_aaa", "ev_bbb"]),
        _make_section("s02", "Context", "Context section [CITE:ev_ccc] with background"),
    ]

    result = await reflect_across_sections(
        client, sections, [], "water filtration methods", concurrency=1,
    )

    assert len(result) == 2
    # s01 should have been revised (revised content is >= 80% of original word count)
    assert result[0].content == revised_content
    assert "[CITE:ev_aaa]" in result[0].content
    assert "[CITE:ev_bbb]" in result[0].content
    # s02 should remain unchanged (no LLM call for it after s01 consumed both calls;
    # or it gets no-revision from generate). Actually, with side_effect exhausted,
    # the second section call will raise StopIteration. The code handles this via
    # the exception handler in _reflect_one, returning idx, None.
    # So s02 keeps original content.
    assert result[1].content == "Context section [CITE:ev_ccc] with background"
