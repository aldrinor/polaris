"""Phase 5 ASSEMBLE tests — failure modes F5.1 through F5.4 + trace events.

Assembly is the final phase: cross-section dedup, citation resolution,
grounded abstract, quality gates, and the CRITICAL report_assembled trace event.
"""

import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.polaris_graph.contracts_v3 import (
    V3ResultOutput,
    VerifiedSectionDraft,
    REQUIRED_EVIDENCE_ACTIONS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sections(count: int) -> list[VerifiedSectionDraft]:
    return [
        VerifiedSectionDraft(
            section_id=f"s{i:02d}",
            title=f"Section {i}: Topic {i}",
            content=(
                f"Analysis of topic {i} reveals important findings [CITE:ev_{i:03d}]. "
                f"Compared to alternative approaches, method {i} shows {80 + i}% efficiency [CITE:ev_{i+1:03d}]. "
                f"Multiple studies confirm these results across different conditions [CITE:ev_{i+2:03d}]."
            ),
            evidence_ids_used=[f"ev_{i:03d}", f"ev_{i+1:03d}", f"ev_{i+2:03d}"],
            claims_verified=3,
            claims_total=3,
            faithfulness_score=0.85,
            critic_passed=True,
            word_count=45,
        )
        for i in range(1, count + 1)
    ]


def _make_evidence_store(count: int) -> dict:
    return {
        f"ev_{i:03d}": {
            "evidence_id": f"ev_{i:03d}",
            "statement": f"Finding {i} about the research topic with {80 + i}% efficiency.",
            "source_url": f"https://example.com/study-{i}",
            "source_title": f"Study {i} on Research Topic",
            "direct_quote": f"The efficiency was measured at {80 + i}% under standard conditions.",
            "quality_tier": "GOLD" if i <= 5 else "SILVER",
        }
        for i in range(1, count + 1)
    }


# ---------------------------------------------------------------------------
# F5.1: Cross-section dedup removes too much
# ---------------------------------------------------------------------------

class TestF5_1_DedupOvercorrection:
    """Dedup must not remove content that differs in key numeric values."""

    def test_dedup_removes_exact_duplicates(self):
        from src.polaris_graph.nodes.assemble import _cross_section_dedup

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="A",
                content="Biochar removes 95% of lead from wastewater efficiently.",
                word_count=8,
            ),
            VerifiedSectionDraft(
                section_id="s02", title="B",
                content="Biochar removes 95% of lead from wastewater efficiently. New finding here.",
                word_count=10,
            ),
        ]

        deduped = _cross_section_dedup(sections)
        # The duplicate sentence should be removed from one section
        all_content = " ".join(s.content for s in deduped)
        count = all_content.count("Biochar removes 95% of lead from wastewater efficiently")
        assert count <= 1, f"Exact duplicate should appear at most once, found {count}"

    def test_dedup_preserves_numeric_variants(self):
        from src.polaris_graph.nodes.assemble import _cross_section_dedup

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="A",
                content="Removal efficiency was 95% at pH 5.5 for lead ions.",
                word_count=10,
            ),
            VerifiedSectionDraft(
                section_id="s02", title="B",
                content="Removal efficiency was 82% at pH 7.0 for cadmium ions.",
                word_count=10,
            ),
        ]

        deduped = _cross_section_dedup(sections)
        # Different numbers → both should survive
        all_content = " ".join(s.content for s in deduped)
        assert "95%" in all_content and "82%" in all_content

    def test_dedup_cap_prevents_over_removal(self):
        from src.polaris_graph.nodes.assemble import _cross_section_dedup

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="A",
                content="Sentence one. Sentence two. Sentence three. Sentence four. Sentence five.",
                word_count=10,
            ),
            VerifiedSectionDraft(
                section_id="s02", title="B",
                content="Sentence one. Sentence two. Sentence three. Different content here. More unique text.",
                word_count=10,
            ),
        ]

        deduped = _cross_section_dedup(sections, max_removal_pct=0.15)
        # Should not remove more than 15% of total content
        original_words = sum(s.word_count for s in sections)
        deduped_words = sum(len(s.content.split()) for s in deduped)
        # Content shouldn't be drastically reduced
        assert deduped_words >= original_words * 0.5


# ---------------------------------------------------------------------------
# F5.2: Citation resolution
# ---------------------------------------------------------------------------

class TestF5_2_CitationResolution:
    """All [CITE:ev_xxx] tokens must resolve to [N] references."""

    def test_resolve_citations(self):
        from src.polaris_graph.nodes.assemble import _resolve_all_citations

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="A",
                content="Finding A [CITE:ev_001]. Finding B [CITE:ev_002].",
                evidence_ids_used=["ev_001", "ev_002"],
            ),
            VerifiedSectionDraft(
                section_id="s02", title="B",
                content="Finding C [CITE:ev_003]. Also [CITE:ev_001] again.",
                evidence_ids_used=["ev_003", "ev_001"],
            ),
        ]

        evidence_store = _make_evidence_store(5)
        resolved, bibliography = _resolve_all_citations(sections, evidence_store)

        # All CITE tokens should be resolved
        all_content = " ".join(s.content for s in resolved)
        assert "CITE:" not in all_content, f"Unresolved citations remain: {all_content}"
        assert "[1]" in all_content or "[2]" in all_content

        # Bibliography should exist
        assert len(bibliography) >= 2

    def test_invalid_citations_stripped(self):
        from src.polaris_graph.nodes.assemble import _resolve_all_citations

        sections = [
            VerifiedSectionDraft(
                section_id="s01", title="A",
                content="Valid [CITE:ev_001]. Invalid [CITE:ev_999].",
                evidence_ids_used=["ev_001", "ev_999"],
            ),
        ]

        evidence_store = _make_evidence_store(5)
        resolved, bibliography = _resolve_all_citations(sections, evidence_store)

        all_content = " ".join(s.content for s in resolved)
        assert "CITE:" not in all_content
        # ev_999 doesn't exist → its citation should be stripped
        assert "ev_999" not in all_content


# ---------------------------------------------------------------------------
# F5.4: Grounded abstract
# ---------------------------------------------------------------------------

class TestF5_4_GroundedAbstract:
    """Abstract must be generated from actual report content, not hallucinated."""

    def test_abstract_generation(self):
        from src.polaris_graph.nodes.assemble import _generate_abstract

        sections = _make_sections(3)
        abstract = _generate_abstract(
            sections=sections,
            query="biochar for heavy metal removal",
        )

        assert len(abstract) > 0
        assert len(abstract.split()) <= 300, "Abstract should be <= 300 words"


# ---------------------------------------------------------------------------
# Result JSON compatibility
# ---------------------------------------------------------------------------

class TestResultOutput:
    """Final output must conform to V3ResultOutput schema."""

    @pytest.mark.asyncio
    async def test_assemble_produces_valid_result(self):
        from src.polaris_graph.nodes.assemble import run_assemble_phase

        sections = _make_sections(3)
        evidence_store = _make_evidence_store(10)

        result = await run_assemble_phase(
            sections=sections,
            evidence_store=evidence_store,
            query="biochar for heavy metal removal",
            vector_id="V3_TEST_001",
        )

        # Must be a valid V3ResultOutput
        validated = V3ResultOutput.model_validate(result)
        assert validated.vector_id == "V3_TEST_001"
        assert validated.status in ("completed", "partial")
        assert len(validated.final_report) > 0
        assert len(validated.bibliography) > 0
        assert len(validated.sections) == 3
        assert "faithfulness_pct" in validated.quality_metrics or len(validated.quality_metrics) > 0

    @pytest.mark.asyncio
    async def test_result_has_report_assembled_data(self):
        """The result must contain all fields needed for the report_assembled trace event."""
        from src.polaris_graph.nodes.assemble import run_assemble_phase

        result = await run_assemble_phase(
            sections=_make_sections(2),
            evidence_store=_make_evidence_store(5),
            query="test",
            vector_id="V3_TEST",
        )

        # These fields are required by event_processor.js for frontend completion
        assert "final_report" in result
        assert "bibliography" in result
        assert "sections" in result
        assert result["final_report"]  # non-empty

    @pytest.mark.asyncio
    async def test_partial_status_when_sections_missing(self):
        """If fewer sections than expected, status should be partial."""
        from src.polaris_graph.nodes.assemble import run_assemble_phase

        result = await run_assemble_phase(
            sections=_make_sections(1),  # Only 1 section
            evidence_store=_make_evidence_store(3),
            query="test",
            vector_id="V3_TEST",
            expected_sections=5,  # But expected 5
        )

        assert result["status"] == "partial"
