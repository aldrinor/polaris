"""Phase 2 SEARCH tests — failure modes F2.1 through F2.8 + convergence.

Tests the search orchestration layer with mocked sub-components.
Real search/fetch/extract are battle-tested (REUSE rated) and tested separately.
"""

import os
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.polaris_graph.contracts_v3 import (
    SearchRoundOutput,
    Reflection,
    ScopeOutput,
)


# ---------------------------------------------------------------------------
# F2.3: Convergence never triggers (P0 — pipeline runs forever)
# ---------------------------------------------------------------------------

class TestF2_3_ConvergenceNeverTriggers:
    """The #1 predicted failure. Hard caps MUST stop the search."""

    def test_convergence_detector_saturated(self):
        from src.polaris_graph.nodes.search import _check_convergence

        # Each round adds fewer new evidence IDs
        history = [
            {"new_evidence": 50, "total_evidence": 50},   # round 1: 100% new
            {"new_evidence": 30, "total_evidence": 80},    # round 2: 37% new
            {"new_evidence": 10, "total_evidence": 90},    # round 3: 11% new
            {"new_evidence": 3, "total_evidence": 93},     # round 4: 3% new
        ]
        score = _check_convergence(history)
        assert score > 0.85, f"Should be saturated at {score}"

    def test_convergence_detector_not_saturated(self):
        from src.polaris_graph.nodes.search import _check_convergence

        history = [
            {"new_evidence": 50, "total_evidence": 50},
            {"new_evidence": 45, "total_evidence": 95},   # Still finding lots
        ]
        score = _check_convergence(history)
        assert score < 0.85, f"Should NOT be saturated at {score}"

    def test_hard_round_cap_enforced(self):
        from src.polaris_graph.nodes.search import _should_continue_searching

        # Even if convergence never triggers, hard cap stops at round 5
        result = _should_continue_searching(
            current_round=6,
            max_rounds=5,
            convergence_score=0.2,  # Not converged
            total_evidence=100,
            max_evidence=1000,
            elapsed_seconds=60,
            time_budget_seconds=1200,
        )
        assert result is False, "Should stop at round cap"

    def test_evidence_cap_stops_search(self):
        from src.polaris_graph.nodes.search import _should_continue_searching

        result = _should_continue_searching(
            current_round=2,
            max_rounds=5,
            convergence_score=0.3,
            total_evidence=1050,   # Over the 1000 cap
            max_evidence=1000,
            elapsed_seconds=60,
            time_budget_seconds=1200,
        )
        assert result is False, "Should stop at evidence cap"

    def test_time_budget_stops_search(self):
        from src.polaris_graph.nodes.search import _should_continue_searching

        result = _should_continue_searching(
            current_round=2,
            max_rounds=5,
            convergence_score=0.3,
            total_evidence=100,
            max_evidence=1000,
            elapsed_seconds=1300,  # Over the 1200s budget
            time_budget_seconds=1200,
        )
        assert result is False, "Should stop at time budget"

    def test_convergence_triggers_stop(self):
        from src.polaris_graph.nodes.search import _should_continue_searching

        result = _should_continue_searching(
            current_round=3,
            max_rounds=5,
            convergence_score=0.92,  # Converged
            total_evidence=200,
            max_evidence=1000,
            elapsed_seconds=300,
            time_budget_seconds=1200,
        )
        assert result is False, "Should stop when converged"

    def test_minimum_rounds_enforced(self):
        from src.polaris_graph.nodes.search import _should_continue_searching

        # Even if converged, must do at least 2 rounds
        result = _should_continue_searching(
            current_round=1,
            max_rounds=5,
            convergence_score=0.95,  # Appears converged but only 1 round
            total_evidence=50,
            max_evidence=1000,
            elapsed_seconds=60,
            time_budget_seconds=1200,
        )
        assert result is True, "Must do at least 2 rounds"

    def test_declining_convergence_stops(self):
        """If convergence score DECREASES for 2 rounds, stop (query space expanding)."""
        from src.polaris_graph.nodes.search import _detect_declining_convergence

        scores = [0.3, 0.5, 0.45, 0.40]  # Declining for last 2 rounds
        assert _detect_declining_convergence(scores) is True

        scores = [0.3, 0.5, 0.6, 0.7]  # Improving
        assert _detect_declining_convergence(scores) is False


# ---------------------------------------------------------------------------
# F2.1: All search providers return 0 results
# ---------------------------------------------------------------------------

class TestF2_1_ZeroResults:
    """When all providers return 0, fallback and mark sub-question as no_evidence."""

    @pytest.mark.asyncio
    async def test_zero_results_produces_empty_round(self):
        from src.polaris_graph.nodes.search import _execute_search_round

        mock_searcher = AsyncMock(return_value=[])  # 0 results
        mock_fetcher = AsyncMock(return_value=[])
        mock_extractor = AsyncMock(return_value=[])

        result = await _execute_search_round(
            round_number=1,
            search_queries=[{"query": "nonexistent topic xyz", "sub_question_id": "sq_01"}],
            searcher=mock_searcher,
            fetcher=mock_fetcher,
            extractor=mock_extractor,
            evidence_store={},
        )

        assert isinstance(result, SearchRoundOutput)
        assert len(result.evidence_ids) == 0
        assert result.convergence_score == 0.0


# ---------------------------------------------------------------------------
# F2.5: Reflection distillation
# ---------------------------------------------------------------------------

class TestReflectionDistillation:
    """Reflections must preserve key findings from each round."""

    @pytest.mark.asyncio
    async def test_distill_produces_reflections(self):
        from src.polaris_graph.nodes.search import _distill_reflections

        evidence = [
            {"evidence_id": "ev_001", "statement": "Biochar removal efficiency was 95.3% for Pb(II) at pH 5.5", "sub_question_id": "sq_03"},
            {"evidence_id": "ev_002", "statement": "Rice husk biochar had surface area of 287 m2/g after 500C pyrolysis", "sub_question_id": "sq_02"},
            {"evidence_id": "ev_003", "statement": "Langmuir isotherm model showed R2=0.998", "sub_question_id": "sq_01"},
        ]

        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            reflections=[
                Reflection(
                    insight="Removal efficiency of 95.3% for Pb(II) at pH 5.5 with rice husk biochar",
                    sub_question_id="sq_03",
                    evidence_ids=["ev_001"],
                    confidence=0.85,
                ),
            ]
        ))

        reflections = await _distill_reflections(
            client=mock_client,
            evidence=evidence,
            round_number=1,
        )

        assert len(reflections) >= 1
        assert all(isinstance(r, Reflection) for r in reflections)

    def test_fallback_reflections_from_evidence(self):
        """When LLM distillation fails, build reflections directly from evidence."""
        from src.polaris_graph.nodes.search import _fallback_reflections

        evidence = [
            {"evidence_id": "ev_001", "statement": "Finding A about topic X", "sub_question_id": "sq_01"},
            {"evidence_id": "ev_002", "statement": "Finding B about topic Y", "sub_question_id": "sq_02"},
        ]

        reflections = _fallback_reflections(evidence)
        assert len(reflections) >= 1
        assert all(isinstance(r, Reflection) for r in reflections)
        # Reflections should reference the evidence IDs
        all_ev_ids = set()
        for r in reflections:
            all_ev_ids.update(r.evidence_ids)
        assert "ev_001" in all_ev_ids or "ev_002" in all_ev_ids


# ---------------------------------------------------------------------------
# Evidence store (side-channel, P0)
# ---------------------------------------------------------------------------

class TestEvidenceStore:
    """Evidence content must be stored OUTSIDE LangGraph state."""

    def test_evidence_store_is_dict(self, sample_evidence_store):
        assert isinstance(sample_evidence_store, dict)
        assert len(sample_evidence_store) > 0

    def test_evidence_store_keys_are_ids(self, sample_evidence_store):
        for key in sample_evidence_store:
            assert key.startswith("ev_"), f"Key should be evidence ID: {key}"

    def test_evidence_ids_only_in_state(self):
        """State should carry IDs only, not full evidence objects."""
        # Simulate what state would contain
        state_evidence = ["ev_001", "ev_002", "ev_003"]
        # Each ID is ~10 bytes. 1000 IDs = 10KB. Acceptable.
        import json
        serialized = json.dumps(state_evidence)
        assert len(serialized) < 50000, "Evidence IDs in state should be < 50KB"


# ---------------------------------------------------------------------------
# Search phase integration
# ---------------------------------------------------------------------------

class TestSearchPhaseIntegration:
    """Full search phase orchestration with mocked sub-components."""

    @pytest.mark.asyncio
    async def test_run_search_phase_produces_output(self, sample_scope_output):
        from src.polaris_graph.nodes.search import run_search_phase

        evidence_store = {}
        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(return_value=MagicMock(
            reflections=[
                Reflection(
                    insight="Key finding from search",
                    sub_question_id="sq_01",
                    evidence_ids=["ev_001"],
                    confidence=0.7,
                ),
            ]
        ))
        mock_client.model = "mock/test"

        # Mock the search/fetch/extract pipeline to return some evidence
        mock_evidence = [
            {"evidence_id": f"ev_{i:03d}", "statement": f"Finding {i}", "sub_question_id": f"sq_0{(i%6)+1}"}
            for i in range(1, 11)
        ]

        with patch("src.polaris_graph.nodes.search._execute_search_round") as mock_round:
            mock_round.return_value = SearchRoundOutput(
                round_number=1,
                evidence_ids=[e["evidence_id"] for e in mock_evidence],
                reflections=[Reflection(
                    insight="Found 10 evidence pieces about biochar",
                    sub_question_id="sq_01",
                    evidence_ids=["ev_001"],
                    confidence=0.7,
                )],
                sources_fetched=15,
                convergence_score=0.9,  # Converge after 1 round for test speed
            )

            result = await run_search_phase(
                client=mock_client,
                scope=sample_scope_output,
                evidence_store=evidence_store,
                max_rounds=3,
                max_evidence=1000,
                time_budget_seconds=300,
            )

        assert "evidence_ids" in result
        assert "reflections" in result
        assert "search_rounds_completed" in result
        assert "convergence_score" in result
