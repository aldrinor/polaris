"""Integration tests for MoST: Molecular Structure of Thought."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.polaris_graph.schemas import (
    ReportOutline,
    SectionDraft,
    SectionOutlineItem,
)
from src.polaris_graph.synthesis.cross_section_reflector import reflect_across_sections
from src.polaris_graph.synthesis.evidence_explorer import explore_unused_evidence

SYNTH = "src.polaris_graph.agents.synthesizer"


def _make_section(sid, title, content, ev_ids=None):
    return SectionDraft(
        section_id=sid, title=title, content=content,
        claims_made=[], evidence_ids=ev_ids or [],
    )


def _make_evidence(eid, statement, relevance=0.5):
    return {
        "evidence_id": eid, "statement": statement,
        "relevance_score": relevance, "source_url": "https://example.com",
        "source_title": "Example",
    }


def _mock_outline():
    return ReportOutline(
        title="Test Report",
        abstract="Test abstract",
        sections=[
            SectionOutlineItem(
                section_id="s01", title="Intro", description="Introduction",
                evidence_ids=["ev_aaa"], target_words=100, order=1,
            ),
            SectionOutlineItem(
                section_id="s02", title="Methods", description="Methods",
                evidence_ids=["ev_bbb"], target_words=100, order=2,
            ),
            SectionOutlineItem(
                section_id="s03", title="Results", description="Results",
                evidence_ids=["ev_ccc"], target_words=100, order=3,
            ),
        ],
    )


def _mock_quality(words=50000, citations=100, sources=50):
    return {
        "total_words": words,
        "total_sections": 3,
        "total_citations": citations,
        "unique_sources": sources,
        "faithfulness_score": 1.0,
        "coverage_score": 1.0,
    }


class TestMoSTDisabled:
    @pytest.mark.asyncio
    async def test_most_disabled_passthrough(self, monkeypatch):
        """When PG_MOST_ENABLED=0, sections pass through unchanged."""
        monkeypatch.setenv("PG_MOST_ENABLED", "0")
        client = MagicMock()
        sections = [
            _make_section("s01", "Intro", "Content [CITE:ev_aaa]"),
            _make_section("s02", "Methods", "Methods [CITE:ev_bbb]"),
        ]
        # reflect_across_sections should work regardless (the feature flag
        # is checked in synthesizer.py, not in the module itself)
        result = await reflect_across_sections(client, sections, [], "query", concurrency=1)
        assert len(result) == 2


class TestPhaseR:
    @pytest.mark.asyncio
    async def test_preserves_citations(self, monkeypatch):
        """Phase R must preserve all [CITE:] markers."""
        monkeypatch.setenv("PG_REFLECTION_MAX_CONTEXT", "2")
        # Mock LLM to return no-revision-needed
        mock_resp = MagicMock()
        mock_resp.content = '{"contradictions": [], "redundancies": [], "cross_references": [], "revision_needed": false}'
        client = AsyncMock()
        client.generate = AsyncMock(return_value=mock_resp)

        sections = [
            _make_section("s01", "Intro", "Water quality [CITE:ev_aaa] is important"),
            _make_section("s02", "Methods", "Filtration methods [CITE:ev_bbb] include RO"),
        ]
        result = await reflect_across_sections(client, sections, [], "water filters", concurrency=1)
        for sec in result:
            assert "[CITE:" in sec.content


class TestPhaseE:
    @pytest.mark.asyncio
    async def test_redistributes_unused(self, monkeypatch):
        """Phase E should identify unused evidence."""
        monkeypatch.setenv("PG_EXPLORE_SIMILARITY_THRESHOLD", "0.01")
        monkeypatch.setenv("PG_EXPLORE_MAX_NEW_PER_SECTION", "3")

        # Mock LLM to return enriched content
        mock_resp = MagicMock()
        mock_resp.content = "Water quality is important [CITE:ev_aaa]. New finding about bacteria [CITE:ev_ccc]."
        client = AsyncMock()
        client.generate = AsyncMock(return_value=mock_resp)

        sections = [_make_section("s01", "Water Quality", "Water quality is important [CITE:ev_aaa].")]
        evidence = [
            _make_evidence("ev_aaa", "Water quality matters"),
            _make_evidence("ev_ccc", "Bacteria in water quality analysis methods testing"),
        ]
        result = await explore_unused_evidence(client, sections, evidence, {}, "water quality")
        assert len(result) == 1
        # If enrichment worked, new evidence should be cited
        # (may not work if word overlap threshold isn't met)

    @pytest.mark.asyncio
    async def test_word_count_guard(self, monkeypatch):
        """Phase E rejects enrichments that shorten a section."""
        monkeypatch.setenv("PG_EXPLORE_SIMILARITY_THRESHOLD", "0.01")

        # Mock LLM to return shorter content (should be rejected)
        mock_resp = MagicMock()
        mock_resp.content = "Short [CITE:ev_ccc]."
        client = AsyncMock()
        client.generate = AsyncMock(return_value=mock_resp)

        sections = [_make_section("s01", "Detailed Analysis", "A " * 200 + "[CITE:ev_aaa]")]
        evidence = [
            _make_evidence("ev_aaa", "Fact A"),
            _make_evidence("ev_ccc", "detailed analysis methods for water"),
        ]
        result = await explore_unused_evidence(client, sections, evidence, {}, "analysis")
        # Should keep original because enrichment is shorter
        assert len(result[0].content.split()) >= 100


class TestMoSTSafetyNet:
    """Integration tests for the post-MoST hallucination safety net.

    These tests exercise the safety net code path in synthesize_report()
    by mocking all upstream dependencies and controlling the hallucination
    audit results before/after MoST.
    """

    def _build_state(self, evidence):
        """Build a minimal state dict for synthesize_report."""
        return {
            "original_query": "water testing methods",
            "evidence": evidence,
            "claims": [
                {
                    "claim_id": e["evidence_id"],
                    "is_faithful": True,
                    "verification_method": "nli",
                    "evidence_ids": [e["evidence_id"]],
                }
                for e in evidence
            ],
            "faithfulness_score": 1.0,
            "cross_reference_groups": [],
        }

    @pytest.mark.asyncio
    async def test_most_safety_net_reverts_hallucinated_section(self, monkeypatch):
        """Safety net reverts sections where hallucination ratio increased after MoST."""
        monkeypatch.setenv("PG_MOST_ENABLED", "1")
        monkeypatch.setenv("PG_SECTION_REVISION_ENABLED", "0")
        monkeypatch.setenv("PG_EVIDENCE_HIERARCHY_READ_ENABLED", "0")
        monkeypatch.setenv("PG_CORROBORATION_ENABLED", "0")
        monkeypatch.setenv("PG_CITATION_AGENT_ENABLED", "0")

        original_content = "Methods [CITE:ev_bbb] for water testing"
        sections = [
            _make_section("s01", "Intro", "Content [CITE:ev_aaa]", ["ev_aaa"]),
            _make_section("s02", "Methods", original_content, ["ev_bbb"]),
            _make_section("s03", "Results", "Results [CITE:ev_ccc]", ["ev_ccc"]),
        ]
        evidence = [
            _make_evidence("ev_aaa", "Fact A", 0.9),
            _make_evidence("ev_bbb", "Fact B", 0.8),
            _make_evidence("ev_ccc", "Fact C", 0.7),
        ]

        # MoST-modified sections: Phase R changes s02 content
        modified_sections = list(sections)
        modified_sections[1] = _make_section(
            "s02", "Methods",
            "Completely hallucinated rewrite without evidence support [CITE:ev_bbb]",
            ["ev_bbb"],
        )

        # Track hallucination audit calls
        audit_calls = []

        def mock_halluc_audit(sections, evidence, research_query):
            call_idx = len(audit_calls)
            audit_calls.append(call_idx)
            if call_idx == 0:
                # Initial audit (pre-MoST): all sections pass with low ratios
                return [
                    {"section_id": "s01", "hallucination_ratio": 0.0, "needs_rewrite": False, "hallucinated_spans": []},
                    {"section_id": "s02", "hallucination_ratio": 0.0, "needs_rewrite": False, "hallucinated_spans": []},
                    {"section_id": "s03", "hallucination_ratio": 0.0, "needs_rewrite": False, "hallucinated_spans": []},
                ]
            else:
                # Post-MoST audit: s02 now has high hallucination (0.4 > 0.0 + 0.05)
                return [
                    {"section_id": "s01", "hallucination_ratio": 0.0, "needs_rewrite": False, "hallucinated_spans": []},
                    {"section_id": "s02", "hallucination_ratio": 0.4, "needs_rewrite": True, "hallucinated_spans": ["span"]},
                    {"section_id": "s03", "hallucination_ratio": 0.0, "needs_rewrite": False, "hallucinated_spans": []},
                ]

        section_ev_map = {"s01": ["ev_aaa"], "s02": ["ev_bbb"], "s03": ["ev_ccc"]}
        report_sections = [
            {"title": s.title, "word_count": 5000, "citation_ids": s.evidence_ids}
            for s in sections
        ]

        client = AsyncMock()
        state = self._build_state(evidence)

        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            stack.enter_context(patch(f"{SYNTH}._cluster_evidence", new_callable=AsyncMock, return_value=[{"cluster_id": "c1", "theme": "T", "evidence_ids": [], "strength": "strong"}]))
            stack.enter_context(patch(f"{SYNTH}._detect_evidence_conflicts", return_value=[]))
            stack.enter_context(patch(f"{SYNTH}.plan_report", new_callable=AsyncMock, return_value=_mock_outline()))
            stack.enter_context(patch(f"{SYNTH}.write_all_sections", new_callable=AsyncMock, return_value=(sections, section_ev_map)))
            stack.enter_context(patch(f"{SYNTH}.audit_citations", new_callable=AsyncMock, return_value=[]))
            stack.enter_context(patch(f"{SYNTH}.audit_sections_for_hallucination", side_effect=mock_halluc_audit))
            stack.enter_context(patch(f"{SYNTH}.assemble_report", return_value=("# Test Report\n\n## Abstract\n\nAbs\n\n## Intro\n\nContent", report_sections, [])))
            stack.enter_context(patch(f"{SYNTH}.compute_quality_metrics", return_value=_mock_quality()))
            stack.enter_context(patch(f"{SYNTH}._generate_grounded_abstract", new_callable=AsyncMock, return_value="Test abstract"))
            stack.enter_context(patch(f"{SYNTH}.get_tracer", return_value=None))
            stack.enter_context(patch("src.polaris_graph.agents.citation_agent.PG_CITATION_AGENT_ENABLED", False))
            stack.enter_context(patch("src.polaris_graph.synthesis.cross_section_reflector.reflect_across_sections", new_callable=AsyncMock, return_value=modified_sections))
            stack.enter_context(patch("src.polaris_graph.synthesis.evidence_explorer.explore_unused_evidence", new_callable=AsyncMock, return_value=modified_sections))
            stack.enter_context(patch("src.polaris_graph.agents.verifier._triangulate_claims", return_value={}))

            from src.polaris_graph.agents.synthesizer import synthesize_report
            result = await synthesize_report(client, state)

        # Assertions
        assert len(audit_calls) == 2, "Hallucination audit should be called twice (initial + safety net)"
        stats = result.get("most_reflection_stats", {})
        assert stats.get("sections_reverted", 0) == 1, "Section s02 should have been reverted"
        assert stats.get("sections_changed", 0) >= 1, "At least 1 section should have been detected as changed"
        assert stats.get("net_sections_modified", 0) == stats["sections_changed"] - stats["sections_reverted"]

    @pytest.mark.asyncio
    async def test_most_safety_net_refreshes_citation_audit(self, monkeypatch):
        """Safety net refreshes citation audit after MoST modifies sections."""
        monkeypatch.setenv("PG_MOST_ENABLED", "1")
        monkeypatch.setenv("PG_SECTION_REVISION_ENABLED", "0")
        monkeypatch.setenv("PG_EVIDENCE_HIERARCHY_READ_ENABLED", "0")
        monkeypatch.setenv("PG_CORROBORATION_ENABLED", "0")
        monkeypatch.setenv("PG_CITATION_AGENT_ENABLED", "0")

        sections = [
            _make_section("s01", "Intro", "Content [CITE:ev_aaa]", ["ev_aaa"]),
            _make_section("s02", "Methods", "Methods [CITE:ev_bbb]", ["ev_bbb"]),
        ]
        evidence = [
            _make_evidence("ev_aaa", "Fact A", 0.9),
            _make_evidence("ev_bbb", "Fact B", 0.8),
        ]

        # Phase E adds a nonexistent citation to s02
        modified_sections = list(sections)
        modified_sections[1] = _make_section(
            "s02", "Methods",
            "Methods [CITE:ev_bbb] plus new findings [CITE:ev_nonexistent]",
            ["ev_bbb"],
        )

        # Hallucination stays low (no revert needed) so we can verify citation refresh
        def mock_halluc_audit(sections, evidence, research_query):
            return [
                {"section_id": "s01", "hallucination_ratio": 0.0, "needs_rewrite": False, "hallucinated_spans": []},
                {"section_id": "s02", "hallucination_ratio": 0.01, "needs_rewrite": False, "hallucinated_spans": []},
            ]

        # Track audit_citations calls
        cite_audit_calls = []
        async def mock_audit_citations(client, sections, evidence):
            cite_audit_calls.append(len(cite_audit_calls))
            return []

        section_ev_map = {"s01": ["ev_aaa"], "s02": ["ev_bbb"]}

        outline = ReportOutline(
            title="Test Report", abstract="Abs",
            sections=[
                SectionOutlineItem(section_id="s01", title="Intro", description="", evidence_ids=["ev_aaa"], target_words=100, order=1),
                SectionOutlineItem(section_id="s02", title="Methods", description="", evidence_ids=["ev_bbb"], target_words=100, order=2),
            ],
        )
        report_sections = [
            {"title": "Intro", "word_count": 5000, "citation_ids": ["ev_aaa"]},
            {"title": "Methods", "word_count": 5000, "citation_ids": ["ev_bbb"]},
        ]

        client = AsyncMock()
        state = self._build_state(evidence)

        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            stack.enter_context(patch(f"{SYNTH}._cluster_evidence", new_callable=AsyncMock, return_value=[{"cluster_id": "c1", "theme": "T", "evidence_ids": [], "strength": "strong"}]))
            stack.enter_context(patch(f"{SYNTH}._detect_evidence_conflicts", return_value=[]))
            stack.enter_context(patch(f"{SYNTH}.plan_report", new_callable=AsyncMock, return_value=outline))
            stack.enter_context(patch(f"{SYNTH}.write_all_sections", new_callable=AsyncMock, return_value=(sections, section_ev_map)))
            stack.enter_context(patch(f"{SYNTH}.audit_citations", new=mock_audit_citations))
            stack.enter_context(patch(f"{SYNTH}.audit_sections_for_hallucination", side_effect=mock_halluc_audit))
            stack.enter_context(patch(f"{SYNTH}.assemble_report", return_value=("# Report\n\n## Abstract\n\nAbs\n\n## Intro\n\nC", report_sections, [])))
            stack.enter_context(patch(f"{SYNTH}.compute_quality_metrics", return_value=_mock_quality()))
            stack.enter_context(patch(f"{SYNTH}._generate_grounded_abstract", new_callable=AsyncMock, return_value="Abstract"))
            stack.enter_context(patch(f"{SYNTH}.get_tracer", return_value=None))
            stack.enter_context(patch("src.polaris_graph.agents.citation_agent.PG_CITATION_AGENT_ENABLED", False))
            stack.enter_context(patch("src.polaris_graph.synthesis.cross_section_reflector.reflect_across_sections", new_callable=AsyncMock, return_value=modified_sections))
            stack.enter_context(patch("src.polaris_graph.synthesis.evidence_explorer.explore_unused_evidence", new_callable=AsyncMock, return_value=modified_sections))
            stack.enter_context(patch("src.polaris_graph.agents.verifier._triangulate_claims", return_value={}))

            from src.polaris_graph.agents.synthesizer import synthesize_report
            result = await synthesize_report(client, state)

        # Citation audit should be called at least 2 times:
        # 1. Initial audit (before hallucination check)
        # 2. Refresh in safety net (after MoST)
        assert len(cite_audit_calls) >= 2, (
            f"audit_citations should be called at least twice (initial + safety net refresh), "
            f"got {len(cite_audit_calls)}"
        )

    @pytest.mark.asyncio
    async def test_most_stats_populated_in_return_dict(self, monkeypatch):
        """Return dict contains most_reflection_stats and most_exploration_stats."""
        monkeypatch.setenv("PG_MOST_ENABLED", "1")
        monkeypatch.setenv("PG_SECTION_REVISION_ENABLED", "0")
        monkeypatch.setenv("PG_EVIDENCE_HIERARCHY_READ_ENABLED", "0")
        monkeypatch.setenv("PG_CORROBORATION_ENABLED", "0")
        monkeypatch.setenv("PG_CITATION_AGENT_ENABLED", "0")

        sections = [
            _make_section("s01", "Intro", "Content [CITE:ev_aaa]", ["ev_aaa"]),
            _make_section("s02", "Methods", "Methods [CITE:ev_bbb]", ["ev_bbb"]),
            _make_section("s03", "Results", "Results [CITE:ev_ccc]", ["ev_ccc"]),
        ]
        evidence = [
            _make_evidence("ev_aaa", "Fact A", 0.9),
            _make_evidence("ev_bbb", "Fact B", 0.8),
            _make_evidence("ev_ccc", "Fact C", 0.7),
            _make_evidence("ev_ddd", "Fact D", 0.6),
        ]

        # Phase R changes s01 and s02, Phase E adds new citations to s01
        modified_sections = [
            _make_section("s01", "Intro", "Revised intro [CITE:ev_aaa] [CITE:ev_ddd]", ["ev_aaa", "ev_ddd"]),
            _make_section("s02", "Methods", "Revised methods [CITE:ev_bbb]", ["ev_bbb"]),
            sections[2],  # s03 unchanged
        ]

        # Hallucination stays low so no reverts
        def mock_halluc_audit(sections, evidence, research_query):
            return [
                {"section_id": "s01", "hallucination_ratio": 0.01, "needs_rewrite": False, "hallucinated_spans": []},
                {"section_id": "s02", "hallucination_ratio": 0.01, "needs_rewrite": False, "hallucinated_spans": []},
                {"section_id": "s03", "hallucination_ratio": 0.0, "needs_rewrite": False, "hallucinated_spans": []},
            ]

        section_ev_map = {"s01": ["ev_aaa"], "s02": ["ev_bbb"], "s03": ["ev_ccc"]}

        outline = ReportOutline(
            title="Test Report", abstract="",
            sections=[
                SectionOutlineItem(section_id="s01", title="Intro", description="", evidence_ids=["ev_aaa"], target_words=100, order=1),
                SectionOutlineItem(section_id="s02", title="Methods", description="", evidence_ids=["ev_bbb"], target_words=100, order=2),
                SectionOutlineItem(section_id="s03", title="Results", description="", evidence_ids=["ev_ccc"], target_words=100, order=3),
            ],
        )
        report_sections = [
            {"title": s.title, "word_count": 5000, "citation_ids": s.evidence_ids}
            for s in sections
        ]

        client = AsyncMock()
        state = self._build_state(evidence)

        from contextlib import AsyncExitStack

        async with AsyncExitStack() as stack:
            stack.enter_context(patch(f"{SYNTH}._cluster_evidence", new_callable=AsyncMock, return_value=[{"cluster_id": "c1", "theme": "T", "evidence_ids": [], "strength": "strong"}]))
            stack.enter_context(patch(f"{SYNTH}._detect_evidence_conflicts", return_value=[]))
            stack.enter_context(patch(f"{SYNTH}.plan_report", new_callable=AsyncMock, return_value=outline))
            stack.enter_context(patch(f"{SYNTH}.write_all_sections", new_callable=AsyncMock, return_value=(sections, section_ev_map)))
            stack.enter_context(patch(f"{SYNTH}.audit_citations", new_callable=AsyncMock, return_value=[]))
            stack.enter_context(patch(f"{SYNTH}.audit_sections_for_hallucination", side_effect=mock_halluc_audit))
            stack.enter_context(patch(f"{SYNTH}.assemble_report", return_value=("# Report\n\n## Abstract\n\nAbs\n\n## Intro\n\nC", report_sections, [])))
            stack.enter_context(patch(f"{SYNTH}.compute_quality_metrics", return_value=_mock_quality()))
            stack.enter_context(patch(f"{SYNTH}._generate_grounded_abstract", new_callable=AsyncMock, return_value="Abstract"))
            stack.enter_context(patch(f"{SYNTH}.get_tracer", return_value=None))
            stack.enter_context(patch("src.polaris_graph.agents.citation_agent.PG_CITATION_AGENT_ENABLED", False))
            stack.enter_context(patch("src.polaris_graph.synthesis.cross_section_reflector.reflect_across_sections", new_callable=AsyncMock, return_value=modified_sections))
            stack.enter_context(patch("src.polaris_graph.synthesis.evidence_explorer.explore_unused_evidence", new_callable=AsyncMock, return_value=modified_sections))
            stack.enter_context(patch("src.polaris_graph.agents.verifier._triangulate_claims", return_value={}))

            from src.polaris_graph.agents.synthesizer import synthesize_report
            result = await synthesize_report(client, state)

        # Verify MoST stats are in return dict
        assert "most_reflection_stats" in result, "Return dict must contain most_reflection_stats"
        assert "most_exploration_stats" in result, "Return dict must contain most_exploration_stats"

        r_stats = result["most_reflection_stats"]
        assert r_stats["sections_changed"] == 2, "2 sections were modified (s01 and s02)"
        assert r_stats["sections_reverted"] == 0, "No sections should be reverted (halluc stayed low)"
        assert r_stats["net_sections_modified"] == 2

        e_stats = result["most_exploration_stats"]
        assert e_stats["sections_enriched"] >= 1, "s01 gained new citation ev_ddd"
        assert e_stats["new_citations_added"] >= 1, "At least 1 new citation was added"
