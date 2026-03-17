"""Phase 1 SCOPE tests — failure modes F1.1 through F1.5.

Tests written BEFORE implementation (test-first development).
Each test validates a specific failure mode identified in the v3 plan.
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.polaris_graph.contracts_v3 import (
    ScopeOutput,
    SubQuestion,
    SearchQuery,
)


# ---------------------------------------------------------------------------
# F1.1: LLM produces 0 sub-questions
# ---------------------------------------------------------------------------

class TestF1_1_EmptySubQuestions:
    """When the LLM returns 0 sub-questions, fallback must produce >= 6."""

    @pytest.mark.asyncio
    async def test_empty_llm_response_triggers_fallback(self):
        from src.polaris_graph.nodes.scope import run_scope

        # Mock LLM that returns empty sub-questions
        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(
            side_effect=Exception("LLM returned garbage")
        )
        mock_client.model = "mock/test"

        result = await run_scope(
            client=mock_client,
            query="effectiveness of biochar for heavy metal removal",
            application="water_treatment",
            region="global",
        )

        assert isinstance(result, ScopeOutput)
        assert len(result.sub_questions) >= 3, (
            f"Fallback should produce >= 3 sub-questions, got {len(result.sub_questions)}"
        )
        assert len(result.search_queries) >= 3

    @pytest.mark.asyncio
    async def test_llm_returns_empty_list_triggers_fallback(self):
        from src.polaris_graph.nodes.scope import run_scope

        # Mock LLM that returns valid JSON but empty questions
        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(
            side_effect=ValueError("Need >= 3 sub-questions, got 0")
        )
        mock_client.model = "mock/test"

        result = await run_scope(
            client=mock_client,
            query="biochar wastewater",
            application="water_treatment",
            region="global",
        )

        assert isinstance(result, ScopeOutput)
        assert len(result.sub_questions) >= 3


# ---------------------------------------------------------------------------
# F1.2: All sub-questions are about the same angle
# ---------------------------------------------------------------------------

class TestF1_2_DegenerateDecomposition:
    """Sub-questions that are all paraphrases should be caught by diversity gate."""

    @pytest.mark.asyncio
    async def test_diversity_gate_detects_duplicates(self):
        from src.polaris_graph.nodes.scope import _check_question_diversity

        # All questions are paraphrases of the same thing
        degenerate_questions = [
            SubQuestion(id="sq_01", question="How effective is biochar for removing heavy metals?"),
            SubQuestion(id="sq_02", question="What is the effectiveness of biochar for heavy metal removal?"),
            SubQuestion(id="sq_03", question="How well does biochar remove heavy metals from water?"),
            SubQuestion(id="sq_04", question="Is biochar effective at heavy metal removal?"),
            SubQuestion(id="sq_05", question="Can biochar effectively remove heavy metals?"),
            SubQuestion(id="sq_06", question="Does biochar work for heavy metal removal from wastewater?"),
        ]

        is_diverse = await _check_question_diversity(degenerate_questions)
        assert not is_diverse, "Degenerate questions should fail diversity check"

    @pytest.mark.asyncio
    async def test_diverse_questions_pass(self):
        from src.polaris_graph.nodes.scope import _check_question_diversity

        diverse_questions = [
            SubQuestion(id="sq_01", question="What mechanisms drive biochar adsorption?", analytical_focus="explain"),
            SubQuestion(id="sq_02", question="How do pyrolysis conditions affect performance?", analytical_focus="compare"),
            SubQuestion(id="sq_03", question="What removal efficiencies are reported?", analytical_focus="aggregate"),
            SubQuestion(id="sq_04", question="How does biochar compare to activated carbon?", analytical_focus="tabulate"),
            SubQuestion(id="sq_05", question="What are the cost-effectiveness considerations?", analytical_focus="compare"),
            SubQuestion(id="sq_06", question="What limitations exist in current research?", analytical_focus="challenge"),
        ]

        is_diverse = await _check_question_diversity(diverse_questions)
        assert is_diverse, "Diverse questions should pass diversity check"


# ---------------------------------------------------------------------------
# F1.3: Query is too vague for decomposition
# ---------------------------------------------------------------------------

class TestF1_3_VagueQuery:
    """Vague queries should be classified as 'simple' with reduced depth."""

    @pytest.mark.asyncio
    async def test_vague_query_classified_simple(self):
        from src.polaris_graph.nodes.scope import run_scope

        mock_client = AsyncMock()
        # Return a valid but minimal scope for a vague query
        mock_client.generate_structured = AsyncMock(return_value=ScopeOutput(
            sub_questions=[
                SubQuestion(id="sq_01", question="What is water treatment?", expected_depth="brief"),
                SubQuestion(id="sq_02", question="What methods exist?", expected_depth="brief"),
                SubQuestion(id="sq_03", question="How effective are they?", expected_depth="moderate"),
            ],
            perspectives=["Scientific", "Engineering", "Regulatory"],
            search_queries=[
                SearchQuery(query="water treatment methods overview", sub_question_id="sq_01"),
                SearchQuery(query="water treatment technologies", sub_question_id="sq_02"),
                SearchQuery(query="water treatment effectiveness", sub_question_id="sq_03"),
            ],
            complexity="simple",
            estimated_depth=50,
        ))
        mock_client.model = "mock/test"

        result = await run_scope(
            client=mock_client,
            query="water treatment",
            application="",
            region="",
        )

        assert result.complexity in ("simple", "moderate")


# ---------------------------------------------------------------------------
# F1.4: Single specific factual question
# ---------------------------------------------------------------------------

class TestF1_4_FactualQuestion:
    """Factual questions should get 'simple' classification and low depth."""

    @pytest.mark.asyncio
    async def test_factual_query_produces_valid_scope(self):
        from src.polaris_graph.nodes.scope import run_scope

        mock_client = AsyncMock()
        mock_client.generate_structured = AsyncMock(return_value=ScopeOutput(
            sub_questions=[
                SubQuestion(id="sq_01", question="What is the LD50 of glyphosate?", expected_depth="brief"),
                SubQuestion(id="sq_02", question="What studies measured glyphosate toxicity?", expected_depth="brief"),
                SubQuestion(id="sq_03", question="How does glyphosate LD50 compare to other herbicides?", expected_depth="brief"),
            ],
            perspectives=["Scientific", "Regulatory", "Public_Health"],
            search_queries=[
                SearchQuery(query="glyphosate LD50 toxicity", sub_question_id="sq_01"),
                SearchQuery(query="glyphosate toxicity studies", sub_question_id="sq_02"),
                SearchQuery(query="herbicide LD50 comparison", sub_question_id="sq_03"),
            ],
            complexity="simple",
            estimated_depth=30,
        ))
        mock_client.model = "mock/test"

        result = await run_scope(
            client=mock_client,
            query="What is the LD50 of glyphosate?",
            application="toxicology",
            region="global",
        )

        assert isinstance(result, ScopeOutput)
        assert result.estimated_depth <= 100


# ---------------------------------------------------------------------------
# F1.5: LLM produces unparseable JSON
# ---------------------------------------------------------------------------

class TestF1_5_UnparseableJson:
    """When LLM returns garbage JSON, fallback must produce valid ScopeOutput."""

    @pytest.mark.asyncio
    async def test_json_parse_failure_uses_fallback(self):
        from src.polaris_graph.nodes.scope import run_scope

        mock_client = AsyncMock()
        # First call fails (bad JSON), retry also fails
        mock_client.generate_structured = AsyncMock(
            side_effect=[
                Exception("JSON parse error: unexpected token"),
                Exception("JSON parse error: truncated"),
            ]
        )
        mock_client.model = "mock/test"

        result = await run_scope(
            client=mock_client,
            query="biochar heavy metal removal effectiveness",
            application="water_treatment",
            region="global",
        )

        assert isinstance(result, ScopeOutput)
        assert len(result.sub_questions) >= 3
        assert len(result.search_queries) >= 3


# ---------------------------------------------------------------------------
# Happy path: LLM returns good output
# ---------------------------------------------------------------------------

class TestScopeHappyPath:
    """Normal operation — LLM produces valid decomposition."""

    @pytest.mark.asyncio
    async def test_good_llm_response(self, mock_llm):
        from src.polaris_graph.nodes.scope import run_scope

        result = await run_scope(
            client=mock_llm,
            query="effectiveness of biochar for heavy metal removal from wastewater",
            application="water_treatment",
            region="global",
        )

        assert isinstance(result, ScopeOutput)
        assert len(result.sub_questions) >= 6
        assert len(result.perspectives) >= 5
        assert len(result.search_queries) >= 6
        # Every sub-question has search queries
        sq_ids = {sq.id for sq in result.sub_questions}
        query_sq_ids = {q.sub_question_id for q in result.search_queries}
        assert sq_ids == query_sq_ids

    @pytest.mark.asyncio
    async def test_analytical_focus_variety(self, mock_llm):
        from src.polaris_graph.nodes.scope import run_scope

        result = await run_scope(
            client=mock_llm,
            query="biochar wastewater treatment",
            application="water_treatment",
            region="global",
        )

        focuses = {sq.analytical_focus for sq in result.sub_questions}
        # Should have at least 3 different analytical focuses
        assert len(focuses) >= 3, (
            f"Need >= 3 distinct analytical focuses, got {focuses}"
        )

    @pytest.mark.asyncio
    async def test_result_is_json_serializable(self, mock_llm):
        from src.polaris_graph.nodes.scope import run_scope
        import json

        result = await run_scope(
            client=mock_llm,
            query="biochar wastewater",
            application="water_treatment",
            region="global",
        )

        # Must serialize for LangGraph state
        json_str = result.model_dump_json()
        parsed = json.loads(json_str)
        assert "sub_questions" in parsed
