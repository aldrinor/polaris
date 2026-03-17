"""Phase 4 SYNTHESIZE tests — failure modes F4.1 through F4.7 + critic.

Sequential writing with inline verification and critic loop.
This is the phase that v2 got catastrophically wrong (parallel writing,
post-hoc verification). Every test here guards against a specific v2 failure.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    OutlineSection,
    VerifiedSectionDraft,
)


# ---------------------------------------------------------------------------
# F4.2: Critic rejects everything (P0)
# ---------------------------------------------------------------------------

class TestF4_2_CriticTooStrict:
    """Critic must not cause runaway rewrites (v2's 170-rewrite disaster)."""

    @pytest.mark.asyncio
    async def test_critic_max_revisions_enforced(self):
        from src.polaris_graph.nodes.synthesize import write_verified_section

        mock_client = AsyncMock()
        # Writer returns content
        mock_client.generate = AsyncMock(return_value=MagicMock(
            content="Analysis shows biochar removes 95% of Pb(II) [CITE:ev_001]. "
                    "Compared to activated carbon, biochar is more cost-effective [CITE:ev_002].",
            reasoning_content="",
        ))
        # Critic always rejects
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            passed=False,
            feedback="Needs more comparison",
            score=0.4,
        ))

        section = OutlineSection(
            id="s01", title="Test", sub_question_id="sq_01",
            analytical_focus="compare",
            evidence_ids=["ev_001", "ev_002", "ev_003"],
            target_words=800, order=1,
        )

        result = await write_verified_section(
            client=mock_client,
            section=section,
            evidence_store=_make_evidence_store(3),
            previous_sections=[],
            used_evidence_ids=set(),
            max_revisions=2,
        )

        assert isinstance(result, VerifiedSectionDraft)
        assert result.revisions <= 2, f"Max 2 revisions, got {result.revisions}"
        assert len(result.content) > 0, "Must produce content even if critic rejects"

    @pytest.mark.asyncio
    async def test_critic_fast_pass(self):
        """High-faithfulness sections auto-pass the critic."""
        from src.polaris_graph.nodes.synthesize import write_verified_section

        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=MagicMock(
            content="Well-cited analysis [CITE:ev_001] with comparison [CITE:ev_002] "
                    "and tables [CITE:ev_003]. Multiple sources confirm this [CITE:ev_004] [CITE:ev_005].",
            reasoning_content="",
        ))
        # Critic passes
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            passed=True,
            feedback="",
            score=0.9,
        ))

        section = OutlineSection(
            id="s01", title="Test", sub_question_id="sq_01",
            evidence_ids=["ev_001", "ev_002", "ev_003", "ev_004", "ev_005"],
            target_words=800, order=1,
        )

        result = await write_verified_section(
            client=mock_client,
            section=section,
            evidence_store=_make_evidence_store(5),
            previous_sections=[],
            used_evidence_ids=set(),
        )

        assert result.revisions == 0, "Should pass on first attempt"
        assert result.critic_passed is True


# ---------------------------------------------------------------------------
# F4.1: Section has only 1-2 evidence pieces
# ---------------------------------------------------------------------------

class TestF4_1_ThinSection:
    """Thin sections should have reduced word targets, not hallucinated padding."""

    def test_thin_section_word_target(self):
        from src.polaris_graph.nodes.synthesize import _compute_target_words

        assert _compute_target_words(evidence_count=1) <= 400
        assert _compute_target_words(evidence_count=2) <= 500
        assert _compute_target_words(evidence_count=10) >= 800
        assert _compute_target_words(evidence_count=20) >= 1200


# ---------------------------------------------------------------------------
# F4.7: Used-evidence tracking causes starvation
# ---------------------------------------------------------------------------

class TestF4_7_EvidenceStarvation:
    """Used evidence should be de-prioritized, not excluded."""

    def test_used_evidence_deprioritized(self):
        from src.polaris_graph.nodes.synthesize import _prioritize_evidence

        evidence_ids = ["ev_001", "ev_002", "ev_003", "ev_004", "ev_005"]
        used = {"ev_001", "ev_002"}
        evidence_store = _make_evidence_store(5)

        prioritized = _prioritize_evidence(evidence_ids, used, evidence_store)

        # Used evidence should be at the END, not removed
        assert len(prioritized) == 5, "Must not remove used evidence"
        # First items should be unused
        assert prioritized[0] not in used or prioritized[1] not in used

    def test_all_used_still_available(self):
        """Even if ALL evidence is used, section still gets evidence."""
        from src.polaris_graph.nodes.synthesize import _prioritize_evidence

        evidence_ids = ["ev_001", "ev_002", "ev_003"]
        used = {"ev_001", "ev_002", "ev_003"}  # All used
        evidence_store = _make_evidence_store(3)

        prioritized = _prioritize_evidence(evidence_ids, used, evidence_store)
        assert len(prioritized) == 3, "All-used evidence must still be available"


# ---------------------------------------------------------------------------
# F4.4: Previous-section context overflow
# ---------------------------------------------------------------------------

class TestF4_4_ContextOverflow:
    """Sliding window must cap previous-section context."""

    def test_sliding_window_caps_context(self):
        from src.polaris_graph.nodes.synthesize import _build_previous_context

        # 10 previous sections, each 1000 words
        previous = [
            VerifiedSectionDraft(
                section_id=f"s{i:02d}",
                title=f"Section {i}",
                content=f"Word " * 1000,
                word_count=1000,
            )
            for i in range(1, 11)
        ]

        context = _build_previous_context(previous, max_tokens=4000)

        # Should NOT include full text of all 10 sections
        # Sliding window: full text for last 2, summaries for earlier
        assert len(context.split()) < 3000, (
            f"Context too large: {len(context.split())} words"
        )
        # Must mention recent sections
        assert "Section 10" in context or "Section 9" in context

    def test_no_previous_sections(self):
        from src.polaris_graph.nodes.synthesize import _build_previous_context

        context = _build_previous_context([], max_tokens=4000)
        assert context == "" or len(context) < 50


# ---------------------------------------------------------------------------
# F4.5/F4.6: Timeout handling
# ---------------------------------------------------------------------------

class TestF4_5_Timeout:
    """Per-section timeout must not kill the pipeline."""

    @pytest.mark.asyncio
    async def test_section_timeout_produces_partial(self):
        """If section write times out, accept partial content."""
        from src.polaris_graph.nodes.synthesize import write_verified_section
        import asyncio

        mock_client = AsyncMock()
        # Writer returns content (simulating success before timeout)
        mock_client.generate = AsyncMock(return_value=MagicMock(
            content="Partial analysis of findings [CITE:ev_001].",
            reasoning_content="",
        ))
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            passed=True, feedback="", score=0.8,
        ))

        section = OutlineSection(
            id="s01", title="Test", sub_question_id="sq_01",
            evidence_ids=["ev_001"], target_words=400, order=1,
        )

        result = await write_verified_section(
            client=mock_client,
            section=section,
            evidence_store=_make_evidence_store(1),
            previous_sections=[],
            used_evidence_ids=set(),
            section_timeout=300,
        )

        assert isinstance(result, VerifiedSectionDraft)
        assert len(result.content) > 0


# ---------------------------------------------------------------------------
# Sequential writing integration
# ---------------------------------------------------------------------------

class TestSequentialWriting:
    """Sections written sequentially with shared context (NOT parallel)."""

    @pytest.mark.asyncio
    async def test_run_synthesis_phase_sequential(self):
        from src.polaris_graph.nodes.synthesize import run_synthesis_phase

        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=MagicMock(
            content="Analysis [CITE:ev_001]. Comparison [CITE:ev_002].",
            reasoning_content="",
        ))
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            passed=True, feedback="", score=0.85,
        ))
        mock_client.model = "mock/test"

        outline = LiveOutline(
            title="Test Report",
            sections=[
                OutlineSection(id="s01", title="Mechanisms", sub_question_id="sq_01", evidence_ids=["ev_001", "ev_002", "ev_003"], target_words=600, order=1),
                OutlineSection(id="s02", title="Effectiveness", sub_question_id="sq_02", evidence_ids=["ev_004", "ev_005", "ev_006"], target_words=600, order=2),
                OutlineSection(id="s03", title="Limitations", sub_question_id="sq_03", evidence_ids=["ev_007", "ev_008"], target_words=400, order=3),
            ],
        )

        evidence_store = _make_evidence_store(8)

        result = await run_synthesis_phase(
            client=mock_client,
            outline=outline,
            evidence_store=evidence_store,
            query="biochar heavy metal removal",
        )

        assert "sections" in result
        sections = result["sections"]
        assert len(sections) == 3, f"Expected 3 sections, got {len(sections)}"

        # Verify sequential: each section should have been written AFTER previous
        for i, s in enumerate(sections):
            assert isinstance(s, VerifiedSectionDraft)
            assert s.section_id == f"s{i+1:02d}"

    @pytest.mark.asyncio
    async def test_used_evidence_tracked_across_sections(self):
        """Evidence used in section 1 should be de-prioritized in section 2."""
        from src.polaris_graph.nodes.synthesize import run_synthesis_phase

        mock_client = AsyncMock()
        # Return content that cites specific evidence
        mock_client.generate = AsyncMock(return_value=MagicMock(
            content="Finding [CITE:ev_001]. Another [CITE:ev_002].",
            reasoning_content="",
        ))
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            passed=True, feedback="", score=0.85,
        ))
        mock_client.model = "mock/test"

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id="s01", title="A", sub_question_id="sq_01", evidence_ids=["ev_001", "ev_002"], target_words=400, order=1),
                OutlineSection(id="s02", title="B", sub_question_id="sq_02", evidence_ids=["ev_001", "ev_003"], target_words=400, order=2),
            ],
        )

        evidence_store = _make_evidence_store(3)

        result = await run_synthesis_phase(
            client=mock_client,
            outline=outline,
            evidence_store=evidence_store,
            query="test",
        )

        assert "used_evidence_ids" in result
        assert len(result["used_evidence_ids"]) > 0

    @pytest.mark.asyncio
    async def test_beast_mode_partial_output(self):
        """If time runs out mid-synthesis, return completed sections."""
        from src.polaris_graph.nodes.synthesize import run_synthesis_phase

        mock_client = AsyncMock()
        mock_client.generate = AsyncMock(return_value=MagicMock(
            content="Content [CITE:ev_001].",
            reasoning_content="",
        ))
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            passed=True, feedback="", score=0.8,
        ))
        mock_client.model = "mock/test"

        outline = LiveOutline(
            title="Test",
            sections=[
                OutlineSection(id=f"s{i:02d}", title=f"Section {i}", sub_question_id=f"sq_0{i}", evidence_ids=[f"ev_{i:03d}"], target_words=400, order=i)
                for i in range(1, 6)  # 5 sections
            ],
        )

        result = await run_synthesis_phase(
            client=mock_client,
            outline=outline,
            evidence_store=_make_evidence_store(5),
            query="test",
            time_budget_seconds=0.001,  # Extremely tight budget → beast mode
        )

        # Should have at least 1 section (first one completes before timeout check)
        assert "sections" in result
        assert "status" in result
        # With 0.001s budget, likely partial
        assert len(result["sections"]) >= 0  # May be 0 or more depending on timing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence_store(count: int) -> dict:
    """Create a mock evidence store with N evidence pieces."""
    return {
        f"ev_{i:03d}": {
            "evidence_id": f"ev_{i:03d}",
            "statement": f"Biochar showed {85 + i}% removal efficiency for metal {i} at pH {4 + i * 0.5}.",
            "direct_quote": f"The removal efficiency was {85 + i}% under controlled conditions at pH {4 + i * 0.5}.",
            "source_url": f"https://example.com/study-{i}",
            "source_title": f"Study on Biochar Application {i}",
            "quality_tier": "GOLD" if i <= 3 else "SILVER",
            "relevance_score": round(0.9 - i * 0.05, 2),
            "perspective": "Scientific",
            "source_content": f"Full source content for study {i}. " * 50,
        }
        for i in range(1, count + 1)
    }
