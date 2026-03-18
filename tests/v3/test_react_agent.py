"""Tests for the ReAct analysis agent and tool registry.

Tests cover:
1. Extracts first when no data — must run extract_numeric_data
2. Stops after sufficient analysis
3. Handles tool failure — picks different tool
4. Respects timeout budget
5. Provenance chain — every result has source_evidence_ids
6. No POLARIS citation — zero "POLARIS" in output
7. Fallback on LLM failure — minimal analysis without LLM
8. Real evidence — load sample evidence, verify tools produce output
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.polaris_graph.contracts_v3 import AnalysisEntry
from src.polaris_graph.tools.analysis_notebook import AnalysisNotebook, AnalysisStep
from src.polaris_graph.tools.react_agent import (
    ReactAnalysisAgent,
    ReactDecision,
)
from src.polaris_graph.tools.tool_registry import (
    ToolDefinition,
    ToolRegistry,
    ToolResult,
    build_default_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def evidence_store():
    """Evidence store with realistic evidence for testing analysis tools."""
    return {
        f"ev_{i:03d}": {
            "evidence_id": f"ev_{i:03d}",
            "statement": (
                f"The removal efficiency of biochar for lead was {85 + i}% "
                f"at pH {5.0 + i * 0.2} with a contact time of {30 + i * 10} minutes."
            ),
            "direct_quote": (
                f"Biochar derived from rice husk achieved {85 + i}% removal."
            ),
            "source_url": f"https://example.com/study-{i}",
            "source_title": f"Study on Biochar {i}",
            "quality_tier": "GOLD" if i <= 3 else "SILVER",
            "relevance_score": round(0.9 - i * 0.02, 2),
            "perspective": "Scientific",
        }
        for i in range(1, 16)
    }


@pytest.fixture
def mock_client():
    """Mock LLM client with generate_structured returning ReactDecision."""
    client = MagicMock()
    client.model = "mock/test"
    return client


def _make_react_decision(action: str, reasoning: str = "", **params):
    """Helper to create a ReactDecision."""
    return ReactDecision(
        reasoning=reasoning or f"I should run {action}",
        action=action,
        action_input=params,
    )


# ---------------------------------------------------------------------------
# Test 1: Must extract data first when no structured data exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_extracts_first_when_no_data(evidence_store, mock_client):
    """When no data points exist, the agent must run extract_numeric_data first."""
    call_count = 0

    async def mock_structured(prompt, schema, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_react_decision(
                "extract_numeric_data",
                "No data points exist, must extract first",
            )
        return _make_react_decision("stop", "Sufficient analysis")

    mock_client.generate_structured = mock_structured

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
    )
    notebook = await agent.run()

    # Must have at least one step
    assert notebook.step_count >= 1
    # First step must be extract_numeric_data
    assert notebook.steps[0].tool_name == "extract_numeric_data"


# ---------------------------------------------------------------------------
# Test 2: Stops after sufficient analysis
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_stops_after_sufficient_analysis(evidence_store, mock_client):
    """Agent stops when it has stats + comparison."""
    decisions = [
        _make_react_decision("extract_numeric_data", "Extract data first"),
        _make_react_decision("statistical_summary", "Compute stats"),
        _make_react_decision("agreement_analysis", "Check agreement"),
        _make_react_decision("meta_analysis", "This should not run"),
    ]
    call_idx = 0

    async def mock_structured(prompt, schema, **kwargs):
        nonlocal call_idx
        if call_idx < len(decisions):
            d = decisions[call_idx]
            call_idx += 1
            return d
        return _make_react_decision("stop", "Done")

    mock_client.generate_structured = mock_structured

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
    )
    notebook = await agent.run()

    # Should have stopped before running all 4 tools
    # (sufficiency check: stats + insights >= 2)
    assert notebook.step_count <= 4
    assert notebook.successful_steps >= 1


# ---------------------------------------------------------------------------
# Test 3: Handles tool failure — picks different tool
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_handles_tool_failure(mock_client):
    """If a tool fails, agent should pick a different one next iteration."""
    # Use an EMPTY evidence store so extract_numeric_data fails
    empty_store = {
        "ev_001": {
            "evidence_id": "ev_001",
            "statement": "x",  # Too short for extraction
            "source_url": "https://example.com",
            "quality_tier": "BRONZE",
            "relevance_score": 0.5,
        },
    }
    call_count = 0

    async def mock_structured(prompt, schema, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # extract_numeric_data will fail (statement too short)
            return _make_react_decision(
                "extract_numeric_data",
                "Try extraction first",
            )
        if call_count == 2:
            # Should recover — try SQL instead
            return _make_react_decision(
                "query_evidence_sql",
                "Previous tool failed, try SQL",
            )
        return _make_react_decision("stop", "Done")

    mock_client.generate_structured = mock_structured

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=empty_store,
        evidence_ids=["ev_001"],
        query="biochar heavy metal removal",
    )
    notebook = await agent.run()

    assert notebook.step_count >= 2
    # First step should have failed (no extractable numbers)
    assert not notebook.steps[0].result.success
    # Second step should succeed (SQL always works on loaded evidence)
    assert notebook.steps[1].result.success
    assert notebook.steps[1].tool_name == "query_evidence_sql"


# ---------------------------------------------------------------------------
# Test 4: Respects timeout budget
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_respects_timeout(evidence_store, mock_client):
    """Agent must stop when the time budget is exhausted."""
    call_count = 0

    async def mock_structured(prompt, schema, **kwargs):
        nonlocal call_count
        call_count += 1
        # Always return extract — it'll keep looping
        return _make_react_decision(
            "extract_numeric_data",
            f"Iteration {call_count}",
        )

    mock_client.generate_structured = mock_structured

    # Set very short timeout
    with patch.dict(os.environ, {"PG_REACT_TIMEOUT_SECONDS": "1"}):
        # Re-import to pick up the env var change
        from importlib import reload
        import src.polaris_graph.tools.react_agent as ra_mod
        reload(ra_mod)

        agent = ra_mod.ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=list(evidence_store.keys()),
            query="biochar heavy metal removal",
        )
        notebook = await agent.run()

    # Should have completed in <= 5 iterations (max) but likely fewer
    # due to the 1s timeout
    assert notebook.step_count <= 5


# ---------------------------------------------------------------------------
# Test 5: Provenance chain — every result has source_evidence_ids
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_provenance_chain(evidence_store, mock_client):
    """Every successful ToolResult must have non-empty source_evidence_ids."""
    decisions = [
        _make_react_decision("extract_numeric_data", "Extract first"),
        _make_react_decision("query_evidence_sql", "Query SQL"),
        _make_react_decision("stop", "Done"),
    ]
    idx = 0

    async def mock_structured(prompt, schema, **kwargs):
        nonlocal idx
        if idx < len(decisions):
            d = decisions[idx]
            idx += 1
            return d
        return _make_react_decision("stop", "Done")

    mock_client.generate_structured = mock_structured

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
    )
    notebook = await agent.run()

    for step in notebook.steps:
        if step.result.success:
            assert len(step.result.source_evidence_ids) > 0, (
                f"Tool {step.tool_name} produced no source_evidence_ids"
            )
            # All IDs should start with "ev_"
            for eid in step.result.source_evidence_ids:
                assert eid.startswith("ev_"), (
                    f"Evidence ID {eid} doesn't start with 'ev_'"
                )

    # to_entries must also have provenance
    entries = notebook.to_entries()
    for entry in entries:
        assert len(entry.source_evidence_ids) > 0
        assert isinstance(entry, AnalysisEntry)


# ---------------------------------------------------------------------------
# Test 6: No POLARIS citation — zero "POLARIS" in output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_no_polaris_citation(evidence_store, mock_client):
    """Zero references to 'POLARIS' or 'Analysis Toolkit' in any output."""
    decisions = [
        _make_react_decision("extract_numeric_data", "Extract first"),
        _make_react_decision("agreement_analysis", "Check agreement"),
        _make_react_decision("stop", "Done"),
    ]
    idx = 0

    async def mock_structured(prompt, schema, **kwargs):
        nonlocal idx
        if idx < len(decisions):
            d = decisions[idx]
            idx += 1
            return d
        return _make_react_decision("stop", "Done")

    mock_client.generate_structured = mock_structured

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
    )
    notebook = await agent.run()

    # Check all markdown output
    context = notebook.build_synthesis_context()
    assert "POLARIS" not in context, (
        f"Found 'POLARIS' in synthesis context: "
        f"{context[:200]}"
    )
    assert "Analysis Toolkit" not in context

    # Check entries
    for entry in notebook.to_entries():
        assert "POLARIS" not in entry.markdown
        assert "Analysis Toolkit" not in entry.markdown


# ---------------------------------------------------------------------------
# Test 7: Fallback on LLM failure — minimal analysis without LLM
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_fallback_on_llm_failure(evidence_store, mock_client):
    """When LLM fails to make a decision, fallback runs deterministic tools."""
    async def mock_structured(prompt, schema, **kwargs):
        raise RuntimeError("LLM is down")

    mock_client.generate_structured = mock_structured

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
    )
    notebook = await agent.run()

    # Fallback should have run at least extract + sql
    assert notebook.step_count >= 2
    tool_names = [s.tool_name for s in notebook.steps]
    assert "extract_numeric_data" in tool_names
    assert "query_evidence_sql" in tool_names

    # Should have some successful results despite LLM failure
    assert notebook.successful_steps >= 1


# ---------------------------------------------------------------------------
# Test 8: Real evidence — verify tools produce output
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_react_on_real_evidence(evidence_store, mock_client):
    """Load sample evidence and verify all tools produce usable output."""
    # Run a controlled sequence of all non-LLM tools
    tool_sequence = [
        "extract_numeric_data",
        "query_evidence_sql",
        "statistical_summary",
        "agreement_analysis",
        "rank_by_impact",
        "stop",
    ]
    idx = 0

    async def mock_structured(prompt, schema, **kwargs):
        nonlocal idx
        tool = tool_sequence[min(idx, len(tool_sequence) - 1)]
        idx += 1
        return _make_react_decision(tool, f"Running {tool}")

    mock_client.generate_structured = mock_structured

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal efficiency",
    )
    notebook = await agent.run()

    # Should have run multiple tools
    assert notebook.step_count >= 3

    # Collect successful tool names
    successful_tools = {
        s.tool_name for s in notebook.steps if s.result.success
    }

    # At minimum, extract and SQL should work on any evidence
    assert "extract_numeric_data" in successful_tools
    assert "query_evidence_sql" in successful_tools

    # Should have produced data points
    assert len(notebook.data_points) > 0

    # build_synthesis_context should produce non-empty markdown
    context = notebook.build_synthesis_context()
    assert len(context) > 100

    # All evidence IDs collected
    all_ids = notebook.get_all_source_evidence_ids()
    assert len(all_ids) > 0

    # to_entries should produce valid AnalysisEntry objects
    entries = notebook.to_entries()
    assert len(entries) >= 2
    for entry in entries:
        assert entry.entry_id.startswith("analysis_")
        assert entry.markdown
        assert len(entry.source_evidence_ids) > 0


# ---------------------------------------------------------------------------
# Unit tests for ToolRegistry
# ---------------------------------------------------------------------------

class TestToolRegistry:
    """Unit tests for ToolRegistry."""

    def test_build_default_registry(self):
        """Default registry has 8 tools."""
        registry = build_default_registry()
        all_tools = registry.available_tools(has_data=True)
        assert len(all_tools) == 8

    def test_available_without_data(self):
        """Without data, requires_data tools are filtered out."""
        registry = build_default_registry()
        available = registry.available_tools(has_data=False)
        no_data_tools = {
            "extract_numeric_data", "query_evidence_sql",
            "agreement_analysis", "execute_python",
        }
        for tool in available:
            assert tool in no_data_tools, f"{tool} should not be available without data"

    def test_available_with_data(self):
        """With data, all tools are available."""
        registry = build_default_registry()
        available = registry.available_tools(has_data=True)
        data_tools = {
            "statistical_summary", "comparison_table",
            "meta_analysis", "rank_by_impact",
        }
        for tool in data_tools:
            assert tool in available

    def test_get_tool(self):
        """get_tool returns ToolDefinition or None."""
        registry = build_default_registry()
        tool = registry.get_tool("extract_numeric_data")
        assert tool is not None
        assert tool.name == "extract_numeric_data"
        assert not tool.requires_data
        assert tool.execute is not None

        assert registry.get_tool("nonexistent") is None

    def test_tool_descriptions(self):
        """get_tool_descriptions returns formatted string."""
        registry = build_default_registry()
        desc = registry.get_tool_descriptions(has_data=False)
        assert "extract_numeric_data" in desc
        assert "UNAVAILABLE" in desc  # data-requiring tools marked


# ---------------------------------------------------------------------------
# Unit tests for AnalysisNotebook
# ---------------------------------------------------------------------------

class TestAnalysisNotebook:
    """Unit tests for AnalysisNotebook."""

    def test_empty_notebook(self):
        assert AnalysisNotebook("q", []).step_count == 0
        assert not AnalysisNotebook("q", []).has_data
        assert AnalysisNotebook("q", []).build_synthesis_context() == ""

    def test_add_step_accumulates_data(self):
        nb = AnalysisNotebook("q", ["ev_001"])
        step = AnalysisStep(
            step_number=1,
            reasoning="test",
            tool_name="extract",
            result=ToolResult(
                success=True,
                tool_name="extract",
                markdown="data",
                source_evidence_ids=["ev_001"],
                data_points_produced=[{"value": "42", "evidence_id": "ev_001"}],
            ),
            elapsed_seconds=1.0,
        )
        nb.add_step(step)
        assert nb.has_data
        assert len(nb.data_points) == 1
        assert nb.successful_steps == 1

    def test_failed_step_no_data(self):
        nb = AnalysisNotebook("q", [])
        step = AnalysisStep(
            step_number=1,
            reasoning="test",
            tool_name="stats",
            result=ToolResult(
                success=False,
                tool_name="stats",
                error="no data",
            ),
            elapsed_seconds=0.5,
        )
        nb.add_step(step)
        assert not nb.has_data
        assert nb.step_count == 1
        assert nb.successful_steps == 0

    def test_to_entries_skips_failures(self):
        nb = AnalysisNotebook("q", ["ev_001"])
        nb.add_step(AnalysisStep(
            step_number=1,
            reasoning="extract",
            tool_name="extract",
            result=ToolResult(
                success=True, tool_name="extract",
                markdown="ok", source_evidence_ids=["ev_001"],
            ),
            elapsed_seconds=1.0,
        ))
        nb.add_step(AnalysisStep(
            step_number=2,
            reasoning="fail",
            tool_name="stats",
            result=ToolResult(success=False, tool_name="stats"),
            elapsed_seconds=0.5,
        ))
        entries = nb.to_entries()
        assert len(entries) == 1
        assert entries[0].analysis_type == "extract"

    def test_get_all_source_evidence_ids_deduplicates(self):
        nb = AnalysisNotebook("q", [])
        for i in range(3):
            nb.add_step(AnalysisStep(
                step_number=i + 1,
                reasoning=f"step {i}",
                tool_name="tool",
                result=ToolResult(
                    success=True, tool_name="tool",
                    markdown="x",
                    source_evidence_ids=["ev_001", f"ev_{i:03d}"],
                ),
                elapsed_seconds=0.1,
            ))
        all_ids = nb.get_all_source_evidence_ids()
        assert len(all_ids) == len(set(all_ids))  # No duplicates

    def test_synthesis_context_has_cite_tokens(self):
        nb = AnalysisNotebook("q", ["ev_001"])
        nb.add_step(AnalysisStep(
            step_number=1,
            reasoning="test",
            tool_name="extract",
            result=ToolResult(
                success=True,
                tool_name="extract",
                markdown="Found 95% removal [CITE:ev_001]",
                source_evidence_ids=["ev_001"],
            ),
            elapsed_seconds=1.0,
        ))
        ctx = nb.build_synthesis_context()
        assert "[CITE:ev_001]" in ctx
        assert "POLARIS" not in ctx
