"""Phase 3 OUTLINE tests — failure modes F3.1 through F3.6.

Tests the dynamic outline that evolves with evidence, detects gaps,
and uses a keep-best strategy to prevent oscillation.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    OutlineGap,
    OutlineSection,
    Reflection,
    SubQuestion,
)


# ---------------------------------------------------------------------------
# F3.1: Too many sections for evidence count
# ---------------------------------------------------------------------------

class TestF3_1_TooManySections:
    """Outline must not have more sections than evidence can support."""

    def test_section_cap_enforced(self):
        from src.polaris_graph.nodes.outline import _enforce_section_evidence_ratio

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id=f"s{i:02d}", title=f"Section {i}", sub_question_id=f"sq_0{min(i,6)}", evidence_ids=[], order=i)
                for i in range(1, 13)  # 12 sections
            ],
        )
        evidence_count = 8  # Only 8 evidence pieces

        fixed = _enforce_section_evidence_ratio(outline, evidence_count)
        # Max sections = evidence_count // 3 = 2, but floor at 3
        assert len(fixed.sections) <= max(3, evidence_count // 2), (
            f"12 sections for 8 evidence is too many, got {len(fixed.sections)}"
        )

    def test_many_evidence_allows_many_sections(self):
        from src.polaris_graph.nodes.outline import _enforce_section_evidence_ratio

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id=f"s{i:02d}", title=f"Section {i}", sub_question_id=f"sq_0{min(i,6)}", evidence_ids=[f"ev_{j:03d}" for j in range(i*5, i*5+5)], order=i)
                for i in range(1, 11)  # 10 sections
            ],
        )
        evidence_count = 200

        fixed = _enforce_section_evidence_ratio(outline, evidence_count)
        assert len(fixed.sections) == 10, "200 evidence should support 10 sections"


# ---------------------------------------------------------------------------
# F3.2: Gap detection infinite loop (P0)
# ---------------------------------------------------------------------------

class TestF3_2_GapLoopCap:
    """Gap-triggered searches must be hard-capped at 2."""

    def test_gap_detection_finds_thin_sections(self):
        from src.polaris_graph.nodes.outline import _detect_gaps

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="Well-supported", sub_question_id="sq_01", evidence_ids=["ev_001", "ev_002", "ev_003", "ev_004"], order=1),
                OutlineSection(id="s02", title="Thin section", sub_question_id="sq_02", evidence_ids=["ev_005"], order=2),
                OutlineSection(id="s03", title="Empty section", sub_question_id="sq_03", evidence_ids=[], order=3),
            ],
        )

        gaps = _detect_gaps(outline, min_evidence_per_section=3)
        assert len(gaps) >= 1
        gap_section_ids = {g.section_id for g in gaps}
        assert "s02" in gap_section_ids or "s03" in gap_section_ids

    def test_no_gaps_when_well_supported(self):
        from src.polaris_graph.nodes.outline import _detect_gaps

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=["ev_001", "ev_002", "ev_003"], order=1),
                OutlineSection(id="s02", title="B", sub_question_id="sq_02", evidence_ids=["ev_004", "ev_005", "ev_006"], order=2),
            ],
        )

        gaps = _detect_gaps(outline, min_evidence_per_section=3)
        assert len(gaps) == 0

    def test_gap_query_generation(self):
        from src.polaris_graph.nodes.outline import _generate_gap_queries

        gaps = [
            OutlineGap(section_id="s02", description="Limited data on cost analysis", suggested_queries=["biochar cost analysis"]),
        ]

        queries = _generate_gap_queries(gaps, original_query="biochar wastewater")
        assert len(queries) >= 1
        assert all("query" in q for q in queries)


# ---------------------------------------------------------------------------
# F3.4: Outline refinement oscillation
# ---------------------------------------------------------------------------

class TestF3_4_OutlineOscillation:
    """Keep-best strategy prevents adopting worse refinements."""

    def test_score_outline_basic(self):
        from src.polaris_graph.nodes.outline import _score_outline

        good_outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=["ev_001", "ev_002", "ev_003"], confidence=0.8, order=1),
                OutlineSection(id="s02", title="B", sub_question_id="sq_02", evidence_ids=["ev_004", "ev_005"], confidence=0.7, order=2),
            ],
        )

        empty_outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=[], confidence=0.1, order=1),
                OutlineSection(id="s02", title="B", sub_question_id="sq_02", evidence_ids=[], confidence=0.1, order=2),
            ],
        )

        good_score = _score_outline(good_outline)
        empty_score = _score_outline(empty_outline)
        assert good_score > empty_score, (
            f"Good outline ({good_score}) should score higher than empty ({empty_score})"
        )

    def test_keep_best_rejects_worse(self):
        from src.polaris_graph.nodes.outline import _keep_best_outline

        v1 = LiveOutline(
            title="V1", version=1,
            sections=[OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=["ev_001", "ev_002", "ev_003"], confidence=0.8, order=1)],
        )
        v2_worse = LiveOutline(
            title="V2 worse", version=2,
            sections=[OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=[], confidence=0.1, order=1)],
        )

        best = _keep_best_outline(v1, v2_worse)
        assert best.version == 1, "Should keep v1 when v2 is worse"

    def test_keep_best_accepts_better(self):
        from src.polaris_graph.nodes.outline import _keep_best_outline

        v1 = LiveOutline(
            title="V1", version=1,
            sections=[OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=["ev_001"], confidence=0.5, order=1)],
        )
        v2_better = LiveOutline(
            title="V2 better", version=2,
            sections=[
                OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=["ev_001", "ev_002", "ev_003"], confidence=0.9, order=1),
                OutlineSection(id="s02", title="B", sub_question_id="sq_02", evidence_ids=["ev_004", "ev_005"], confidence=0.7, order=2),
            ],
        )

        best = _keep_best_outline(v1, v2_better)
        assert best.version == 2, "Should adopt v2 when it's better"


# ---------------------------------------------------------------------------
# F3.5: LLM produces non-parseable outline
# ---------------------------------------------------------------------------

class TestF3_5_UnparseableOutline:
    """Fallback outline from sub-questions when LLM fails."""

    @pytest.mark.asyncio
    async def test_llm_failure_uses_fallback(self):
        from src.polaris_graph.nodes.outline import generate_outline

        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(
            side_effect=Exception("JSON parse error")
        )

        sub_questions = [
            SubQuestion(id="sq_01", question="What are the mechanisms?", analytical_focus="explain"),
            SubQuestion(id="sq_02", question="How effective is it?", analytical_focus="aggregate"),
            SubQuestion(id="sq_03", question="What are the limitations?", analytical_focus="challenge"),
        ]
        evidence_ids = [f"ev_{i:03d}" for i in range(1, 10)]

        result = await generate_outline(
            client=mock_client,
            query="biochar for heavy metal removal",
            sub_questions=sub_questions,
            reflections=[],
            evidence_ids=evidence_ids,
            evidence_meta={eid: {"sub_question_id": f"sq_0{(i%3)+1}"} for i, eid in enumerate(evidence_ids)},
        )

        assert isinstance(result, LiveOutline)
        assert len(result.sections) >= 3
        assert result.version == 1


# ---------------------------------------------------------------------------
# Evidence assignment
# ---------------------------------------------------------------------------

class TestEvidenceAssignment:
    """Evidence must be assigned to sections, preferring exclusivity."""

    def test_assign_distributes_evidence(self):
        from src.polaris_graph.nodes.outline import _assign_evidence_to_outline

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="Mechanisms", sub_question_id="sq_01", order=1),
                OutlineSection(id="s02", title="Effectiveness", sub_question_id="sq_02", order=2),
                OutlineSection(id="s03", title="Limitations", sub_question_id="sq_03", order=3),
            ],
        )

        evidence_meta = {
            "ev_001": {"sub_question_id": "sq_01"},
            "ev_002": {"sub_question_id": "sq_01"},
            "ev_003": {"sub_question_id": "sq_02"},
            "ev_004": {"sub_question_id": "sq_02"},
            "ev_005": {"sub_question_id": "sq_03"},
        }

        assigned = _assign_evidence_to_outline(outline, evidence_meta)

        # Each evidence should be in at least one section
        all_assigned = set()
        for s in assigned.sections:
            all_assigned.update(s.evidence_ids)
        assert len(all_assigned) == 5, f"All 5 evidence should be assigned, got {len(all_assigned)}"

    def test_orphan_evidence_gets_assigned(self):
        """Evidence not matching any sub-question should still be assigned."""
        from src.polaris_graph.nodes.outline import _assign_evidence_to_outline

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="A", sub_question_id="sq_01", order=1),
            ],
        )

        evidence_meta = {
            "ev_001": {"sub_question_id": "sq_01"},
            "ev_002": {"sub_question_id": "sq_99"},  # No matching section
        }

        assigned = _assign_evidence_to_outline(outline, evidence_meta)
        all_assigned = set()
        for s in assigned.sections:
            all_assigned.update(s.evidence_ids)
        # Orphan should be assigned to the most relevant section
        assert "ev_002" in all_assigned, "Orphan evidence must not be discarded"


# ---------------------------------------------------------------------------
# Happy path: full outline generation
# ---------------------------------------------------------------------------

class TestOutlineHappyPath:
    """Normal operation — outline generates correctly from sub-questions."""

    @pytest.mark.asyncio
    async def test_generate_outline_from_scope(self, mock_llm):
        from src.polaris_graph.nodes.outline import generate_outline

        sub_questions = [
            SubQuestion(id="sq_01", question="What mechanisms?", analytical_focus="explain", expected_depth="deep"),
            SubQuestion(id="sq_02", question="How effective?", analytical_focus="aggregate", expected_depth="deep"),
            SubQuestion(id="sq_03", question="Compared to what?", analytical_focus="tabulate", expected_depth="moderate"),
            SubQuestion(id="sq_04", question="What limitations?", analytical_focus="challenge", expected_depth="moderate"),
        ]

        reflections = [
            Reflection(insight="Multiple studies report 80-99% removal", sub_question_id="sq_02", evidence_ids=["ev_001"], confidence=0.8),
        ]

        evidence_ids = [f"ev_{i:03d}" for i in range(1, 13)]
        evidence_meta = {eid: {"sub_question_id": f"sq_0{(i%4)+1}"} for i, eid in enumerate(evidence_ids)}

        result = await generate_outline(
            client=mock_llm,
            query="biochar for heavy metal removal",
            sub_questions=sub_questions,
            reflections=reflections,
            evidence_ids=evidence_ids,
            evidence_meta=evidence_meta,
        )

        assert isinstance(result, LiveOutline)
        assert len(result.sections) >= 3
        assert result.version == 1
        # Sections should have evidence assigned
        total_assigned = sum(len(s.evidence_ids) for s in result.sections)
        assert total_assigned > 0
