"""Tests for the mock LLM factory itself.

Validates that mock responses produce valid schema instances,
so downstream tests can trust their fixtures.

Tests 0.3 from Milestone 0.
"""

import pytest

from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    ScopeOutput,
)


class TestMockLLMFactory:
    """Validate the mock LLM produces correct schema instances."""

    @pytest.mark.asyncio
    async def test_mock_generates_scope_output(self, mock_llm):
        """Mock LLM returns valid ScopeOutput."""
        result = await mock_llm.generate_structured(
            prompt="Decompose this research query",
            schema=ScopeOutput,
        )
        assert isinstance(result, ScopeOutput)
        assert len(result.sub_questions) >= 3
        assert len(result.perspectives) >= 3
        assert len(result.search_queries) >= 3

    @pytest.mark.asyncio
    async def test_mock_generates_live_outline(self, mock_llm):
        """Mock LLM returns valid LiveOutline."""
        result = await mock_llm.generate_structured(
            prompt="Generate outline",
            schema=LiveOutline,
        )
        assert isinstance(result, LiveOutline)
        assert len(result.sections) >= 1

    @pytest.mark.asyncio
    async def test_mock_tracks_calls(self, mock_llm):
        """Mock LLM records all calls for assertion."""
        await mock_llm.generate_structured(prompt="test", schema=ScopeOutput)
        await mock_llm.generate(prompt="test prose")
        assert len(mock_llm.calls) == 2
        assert mock_llm.calls[0]["method"] == "generate_structured"
        assert mock_llm.calls[0]["schema"] == "ScopeOutput"
        assert mock_llm.calls[1]["method"] == "generate"

    @pytest.mark.asyncio
    async def test_mock_generate_returns_content(self, mock_llm):
        """Mock generate() returns object with content attribute."""
        result = await mock_llm.generate(prompt="write something")
        assert hasattr(result, "content")
        assert len(result.content) > 0

    @pytest.mark.asyncio
    async def test_mock_reason_returns_both_fields(self, mock_llm):
        """Mock reason() returns both content and reasoning_content."""
        result = await mock_llm.reason(prompt="think about this")
        assert hasattr(result, "content")
        assert hasattr(result, "reasoning_content")
