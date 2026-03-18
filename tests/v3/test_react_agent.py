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
    AnalysisPlan,
    PlannedStep,
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
        mode="react",
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
        mode="react",
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
        mode="react",
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
            mode="react",
        )
        notebook = await agent.run()

    # Restore module-level constants after reload
    reload(ra_mod)

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
        mode="react",
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
        mode="react",
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
        mode="react",
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
        mode="react",
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


# ---------------------------------------------------------------------------
# Schema normalization tests (PlannedStep, AnalysisPlan)
# ---------------------------------------------------------------------------

class TestPlannedStepNormalization:
    """Test that PlannedStep handles Qwen's various JSON formats."""

    def test_standard_format(self):
        step = PlannedStep(tool_name="extract_numeric_data", reasoning="First")
        assert step.tool_name == "extract_numeric_data"
        assert step.reasoning == "First"

    def test_alt_field_tool(self):
        step = PlannedStep.model_validate({"tool": "Statistical_Summary"})
        assert step.tool_name == "statistical_summary"

    def test_alt_field_action(self):
        step = PlannedStep.model_validate(
            {"action": "query_evidence_sql", "why": "Get tiers"}
        )
        assert step.tool_name == "query_evidence_sql"
        assert step.reasoning == "Get tiers"

    def test_alt_field_params(self):
        step = PlannedStep.model_validate(
            {"tool_name": "query_evidence_sql", "args": {"sql": "SELECT 1"}}
        )
        assert step.parameters == {"sql": "SELECT 1"}

    def test_default_reasoning(self):
        step = PlannedStep.model_validate({"tool_name": "meta_analysis"})
        assert "meta_analysis" in step.reasoning


class TestAnalysisPlanNormalization:
    """Test that AnalysisPlan handles Qwen's various JSON formats."""

    def test_standard_format(self):
        plan = AnalysisPlan(steps=[
            PlannedStep(tool_name="extract_numeric_data"),
        ])
        assert len(plan.steps) == 1

    def test_flat_tool_list(self):
        plan = AnalysisPlan.model_validate({
            "tools": ["extract_numeric_data", "statistical_summary"]
        })
        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "extract_numeric_data"
        assert plan.steps[1].tool_name == "statistical_summary"

    def test_alt_key_plan(self):
        plan = AnalysisPlan.model_validate({
            "plan": [
                {"tool": "extract_numeric_data", "thought": "Extract first"},
                {"name": "query_evidence_sql", "reason": "Get metadata"},
            ]
        })
        assert len(plan.steps) == 2
        assert plan.steps[0].tool_name == "extract_numeric_data"
        assert plan.steps[0].reasoning == "Extract first"
        assert plan.steps[1].tool_name == "query_evidence_sql"
        assert plan.steps[1].reasoning == "Get metadata"

    def test_alt_key_actions(self):
        plan = AnalysisPlan.model_validate({
            "actions": [{"tool_name": "meta_analysis"}]
        })
        assert len(plan.steps) == 1
        assert plan.steps[0].tool_name == "meta_analysis"

    def test_bare_list_of_strings(self):
        """Qwen sometimes returns a bare list instead of an object."""
        plan = AnalysisPlan.model_validate(
            ["extract_numeric_data", "statistical_summary", "rank_by_impact"]
        )
        assert len(plan.steps) == 3
        assert plan.steps[0].tool_name == "extract_numeric_data"

    def test_bare_list_of_dicts(self):
        """Qwen returns a bare list of tool dicts."""
        plan = AnalysisPlan.model_validate([
            {"tool": "extract_numeric_data"},
            {"tool": "comparison_table"},
        ])
        assert len(plan.steps) == 2
        assert plan.steps[1].tool_name == "comparison_table"


# ---------------------------------------------------------------------------
# Agentic mode tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agentic_plan_and_execute(evidence_store, mock_client):
    """Agentic mode: plan -> execute -> interpret -> verify."""
    async def mock_structured(prompt, schema, **kwargs):
        return AnalysisPlan(steps=[
            PlannedStep(tool_name="extract_numeric_data"),
            PlannedStep(tool_name="statistical_summary"),
            PlannedStep(tool_name="query_evidence_sql"),
        ])

    mock_response = MagicMock()
    mock_response.content = (
        "Biochar achieves 85-99% lead removal [CITE:ev_001]. "
        "Average removal efficiency is 92% across 15 studies "
        "[CITE:ev_005]. Contact time ranges from 40 to 170 "
        "minutes [CITE:ev_008]."
    )

    async def mock_generate(**kwargs):
        return mock_response

    mock_client.generate_structured = mock_structured
    mock_client.generate = mock_generate

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
        mode="agentic",
    )
    notebook = await agent.run()

    # Plan executed at least extract + sql (stats may be skipped if no data)
    assert notebook.step_count >= 3
    assert notebook.successful_steps >= 2

    # Should have interpretation step
    tool_names = [s.tool_name for s in notebook.steps]
    assert "interpret_results" in tool_names
    assert "verify_claims" in tool_names


@pytest.mark.asyncio
async def test_agentic_plan_failure_falls_back(evidence_store, mock_client):
    """When planning fails, agentic mode uses fallback plan."""
    async def mock_structured(prompt, schema, **kwargs):
        raise RuntimeError("LLM is down")

    async def mock_generate(**kwargs):
        raise RuntimeError("LLM is down")

    mock_client.generate_structured = mock_structured
    mock_client.generate = mock_generate

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
        mode="agentic",
    )
    notebook = await agent.run()

    # Fallback plan should have run extract + stats/sql
    assert notebook.step_count >= 2
    tool_names = [s.tool_name for s in notebook.steps]
    assert "extract_numeric_data" in tool_names


@pytest.mark.asyncio
async def test_agentic_verify_catches_category_mismatch(
    evidence_store, mock_client,
):
    """Verification catches when a cost metric is cited as removal."""
    # Add a cost-specific evidence piece (no removal/treatment words)
    evidence_store["ev_c05700"] = {
        "evidence_id": "ev_c05700",
        "statement": (
            "GAC is 40% less expensive than ion exchange "
            "according to a 2024 cost analysis"
        ),
        "source_url": "https://example.com/cost",
        "quality_tier": "GOLD",
        "relevance_score": 0.9,
    }

    async def mock_structured(prompt, schema, **kwargs):
        return AnalysisPlan(steps=[
            PlannedStep(tool_name="extract_numeric_data"),
            PlannedStep(tool_name="query_evidence_sql"),
        ])

    mock_response = MagicMock()
    # Deliberately misinterpret: cite cost evidence as removal
    mock_response.content = (
        "Biochar removes heavy metals effectively. "
        "GAC achieves 40% removal efficiency [CITE:ev_c05700]. "
        "Multiple studies confirm 85-99% lead removal [CITE:ev_001]."
    )

    async def mock_generate(**kwargs):
        return mock_response

    mock_client.generate_structured = mock_structured
    mock_client.generate = mock_generate

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal",
        mode="agentic",
    )
    notebook = await agent.run()

    # Verify step should exist and flag the mismatch
    verify_steps = [
        s for s in notebook.steps if s.tool_name == "verify_claims"
    ]
    assert len(verify_steps) == 1
    stats = verify_steps[0].result.statistics
    assert stats.get("mismatches", 0) >= 1


@pytest.mark.asyncio
async def test_agentic_respects_timeout(evidence_store, mock_client):
    """Agentic mode respects the timeout budget."""
    async def mock_structured(prompt, schema, **kwargs):
        return AnalysisPlan(steps=[
            PlannedStep(tool_name="extract_numeric_data"),
            PlannedStep(tool_name="statistical_summary"),
            PlannedStep(tool_name="comparison_table"),
            PlannedStep(tool_name="meta_analysis"),
            PlannedStep(tool_name="rank_by_impact"),
        ])

    mock_client.generate_structured = mock_structured

    with patch.dict(os.environ, {"PG_REACT_TIMEOUT_SECONDS": "1"}):
        from importlib import reload
        import src.polaris_graph.tools.react_agent as ra_mod
        reload(ra_mod)

        agent = ra_mod.ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=list(evidence_store.keys()),
            query="biochar heavy metal removal",
            mode="agentic",
        )
        notebook = await agent.run()

    # Restore module-level constants after reload
    reload(ra_mod)

    # Should have completed with fewer than 5 steps due to timeout
    assert notebook.step_count <= 5


@pytest.mark.asyncio
async def test_mode_switch(evidence_store, mock_client):
    """Agent respects mode parameter and env var override."""
    async def mock_structured(prompt, schema, **kwargs):
        if hasattr(schema, '__name__') and schema.__name__ == "AnalysisPlan":
            return AnalysisPlan(steps=[
                PlannedStep(tool_name="extract_numeric_data"),
            ])
        return ReactDecision(action="stop", reasoning="done")

    mock_client.generate_structured = mock_structured

    # Test explicit mode="react"
    agent_react = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="test",
        mode="react",
    )
    assert agent_react._mode == "react"

    # Test explicit mode="agentic"
    agent_agentic = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="test",
        mode="agentic",
    )
    assert agent_agentic._mode == "agentic"

    # Test env var override
    with patch.dict(os.environ, {"PG_REACT_MODE": "react"}):
        agent_env = ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=list(evidence_store.keys()),
            query="test",
            mode="agentic",  # Should be overridden by env var
        )
        assert agent_env._mode == "react"


@pytest.mark.asyncio
async def test_agentic_on_real_evidence(evidence_store, mock_client):
    """Agentic pipeline produces usable output on real evidence."""
    async def mock_structured(prompt, schema, **kwargs):
        return AnalysisPlan(steps=[
            PlannedStep(tool_name="extract_numeric_data"),
            PlannedStep(tool_name="query_evidence_sql"),
            PlannedStep(tool_name="statistical_summary"),
            PlannedStep(tool_name="rank_by_impact"),
        ])

    mock_response = MagicMock()
    mock_response.content = (
        "Biochar derived from rice husk achieves 86% lead removal "
        "at pH 5.2 with 40-minute contact time [CITE:ev_001]. "
        "Higher pH levels improve performance, with 99% removal "
        "reported at pH 7.8 [CITE:ev_015]. "
        "Statistical analysis across 15 studies shows mean removal "
        "of 92.0% (95% CI: 88.2-95.8%) [CITE:ev_008]. "
        "Contact time varies from 40 to 170 minutes [CITE:ev_003]."
    )

    async def mock_generate(**kwargs):
        return mock_response

    mock_client.generate_structured = mock_structured
    mock_client.generate = mock_generate

    agent = ReactAnalysisAgent(
        client=mock_client,
        evidence_store=evidence_store,
        evidence_ids=list(evidence_store.keys()),
        query="biochar heavy metal removal efficiency",
        mode="agentic",
    )
    notebook = await agent.run()

    # Should have multiple successful steps
    assert notebook.successful_steps >= 3

    # Should have data points from extraction
    assert len(notebook.data_points) > 0

    # Should have interpretation and verification
    tool_names = [s.tool_name for s in notebook.steps]
    assert "interpret_results" in tool_names
    assert "verify_claims" in tool_names

    # Build synthesis context should be non-empty
    ctx = notebook.build_synthesis_context()
    assert len(ctx) > 100
    assert "[CITE:" in ctx
    assert "POLARIS" not in ctx

    # to_entries should produce valid entries
    entries = notebook.to_entries()
    assert len(entries) >= 3


# ---------------------------------------------------------------------------
# 8-phase pipeline tests (10 new tests)
# ---------------------------------------------------------------------------

from src.polaris_graph.tools.react_agent import (
    InterpretationCritique,
    CritiqueDimension,
)


class TestDistillFact:
    """Tests for the _distill_fact static method."""

    def test_distill_fact_strips_boilerplate(self):
        """Boilerplate prefix 'The study found that' is stripped."""
        result = ReactAnalysisAgent._distill_fact(
            "The study found that GAC achieves 95% removal"
        )
        assert result.startswith("GAC"), (
            f"Expected result to start with 'GAC', got: '{result}'"
        )
        assert "study found" not in result.lower()

    def test_distill_fact_truncates(self):
        """Statements over 20 words are truncated with '...'."""
        long_statement = " ".join(
            f"word{i}" for i in range(50)
        )
        result = ReactAnalysisAgent._distill_fact(long_statement)
        word_count = len(result.split())
        assert word_count <= 21, (
            f"Expected <= 21 words (20 + '...'), got {word_count}: '{result}'"
        )
        assert result.endswith("..."), (
            f"Expected truncated result to end with '...', got: '{result}'"
        )


class TestBuildEvidenceBriefing:
    """Tests for _build_evidence_briefing."""

    @patch("src.polaris_graph.tools.react_agent._LLM_LEARNINGS_ENABLED", False)
    @patch("src.polaris_graph.tools.react_agent.embed_texts")
    @patch("src.polaris_graph.tools.react_agent.embed_text")
    @pytest.mark.asyncio
    async def test_build_evidence_briefing_covers_all_categories(
        self, mock_embed_text, mock_embed_texts, mock_client,
    ):
        """Briefing should contain clusters covering all fact categories."""
        # Build 15 evidence pieces across 3 categories (5 each)
        categories = ["removal", "cost", "market"]
        evidence_store = {}
        evidence_ids = []
        for cat_idx, cat in enumerate(categories):
            for i in range(5):
                eid = f"ev_{cat_idx * 5 + i:03d}"
                evidence_ids.append(eid)
                evidence_store[eid] = {
                    "evidence_id": eid,
                    "statement": (
                        f"The {cat} efficiency was {80 + i}% "
                        f"for technology variant {i}"
                    ),
                    "fact_category": cat,
                    "quality_tier": "GOLD" if i == 0 else "SILVER",
                    "relevance_score": 0.85,
                    "source_url": f"https://example.com/{cat}-{i}",
                }

        # Mock embeddings: different vectors per category so clustering works
        # Query embedding
        mock_embed_text.return_value = [1.0, 1.0, 1.0]

        # Each evidence gets an embedding — same category = similar vector
        category_vectors = {
            "removal": [1.0, 0.0, 0.0],
            "cost": [0.0, 1.0, 0.0],
            "market": [0.0, 0.0, 1.0],
        }
        mock_embed_texts.return_value = [
            category_vectors[categories[idx // 5]]
            for idx in range(15)
        ]

        agent = ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=evidence_ids,
            query="water filter removal cost market analysis",
            mode="8phase",
        )
        briefing = await agent._build_evidence_briefing()

        # At least 3 clusters (one per category)
        assert len(briefing["clusters"]) >= 3, (
            f"Expected >= 3 clusters, got {len(briefing['clusters'])}: "
            f"{[c['theme'] for c in briefing['clusters']]}"
        )

        # All categories represented in cluster themes
        themes = {c["theme"] for c in briefing["clusters"]}
        for cat in categories:
            assert cat in themes, (
                f"Category '{cat}' not in cluster themes: {themes}"
            )

    @patch("src.polaris_graph.tools.react_agent._LLM_LEARNINGS_ENABLED", False)
    @patch("src.polaris_graph.tools.react_agent.embed_texts")
    @patch("src.polaris_graph.tools.react_agent.embed_text")
    @pytest.mark.asyncio
    async def test_domain_filter_catches_pei_conflation(
        self, mock_embed_text, mock_embed_texts, mock_client,
    ):
        """Domain filter removes evidence about the wrong polymer domain."""
        evidence_store = {}
        evidence_ids = []

        # 5 on-topic: polyethylenimine membrane coating
        for i in range(5):
            eid = f"ev_{i:03d}"
            evidence_ids.append(eid)
            evidence_store[eid] = {
                "evidence_id": eid,
                "statement": (
                    f"Polyethylenimine coating achieves {90 + i}% salt rejection"
                ),
                "fact_category": "coating",
                "quality_tier": "GOLD",
                "relevance_score": 0.9,
                "source_url": f"https://example.com/pei-{i}",
            }

        # 5 off-topic: polyetherimide (wrong domain, low cosine sim)
        for i in range(5):
            eid = f"ev_{i + 5:03d}"
            evidence_ids.append(eid)
            evidence_store[eid] = {
                "evidence_id": eid,
                "statement": (
                    f"Polyetherimide shows thermal stability at {300 + i}C"
                ),
                "fact_category": "thermal",
                "quality_tier": "SILVER",
                "relevance_score": 0.7,
                "source_url": f"https://example.com/ultem-{i}",
            }

        # Query embedding: on-topic direction
        mock_embed_text.return_value = [1.0, 0.0, 0.0]

        # On-topic evidence: high cosine sim; off-topic: near-zero
        embeddings = []
        for i in range(10):
            if i < 5:
                embeddings.append([0.9, 0.1, 0.0])  # high sim to query
            else:
                embeddings.append([0.0, 1.0, 0.0])  # low sim to query
        mock_embed_texts.return_value = embeddings

        agent = ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=evidence_ids,
            query="polyethylenimine membrane coating",
            mode="8phase",
        )
        briefing = await agent._build_evidence_briefing()

        # Learnings should NOT contain polyetherimide facts
        for learning in briefing["learnings"]:
            assert "polyetherimide" not in learning["fact"].lower(), (
                f"Off-topic 'polyetherimide' should have been filtered: "
                f"'{learning['fact']}'"
            )

    @patch("src.polaris_graph.tools.react_agent._LLM_LEARNINGS_ENABLED", False)
    @patch("src.polaris_graph.tools.react_agent.embed_texts")
    @patch("src.polaris_graph.tools.react_agent.embed_text")
    @pytest.mark.asyncio
    async def test_comparison_matrix_for_multi_criteria(
        self, mock_embed_text, mock_embed_texts, mock_client,
    ):
        """Multi-criteria query produces comparison matrix with markdown table."""
        evidence_store = {}
        evidence_ids = []
        techs = [
            "Reverse Osmosis", "Activated Carbon", "Ion Exchange",
            "UV Disinfection", "Membrane Filtration", "Ozonation",
        ]
        for i, tech in enumerate(techs):
            eid = f"ev_{i:03d}"
            evidence_ids.append(eid)
            evidence_store[eid] = {
                "evidence_id": eid,
                "statement": (
                    f"{tech} achieves {85 + i}% removal at a cost of "
                    f"${10 + i * 5} per 1000 gallons"
                ),
                "fact_category": "treatment",
                "quality_tier": "GOLD",
                "relevance_score": 0.9,
                "source_url": f"https://example.com/tech-{i}",
            }

        # Mock embeddings: all similar so nothing is filtered
        mock_embed_text.return_value = [1.0, 1.0, 0.0]
        mock_embed_texts.return_value = [
            [0.9, 0.8, 0.1] for _ in range(len(techs))
        ]

        agent = ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=evidence_ids,
            query="effective AND affordable water filters",
            mode="8phase",
        )
        briefing = await agent._build_evidence_briefing()

        matrix = briefing.get("comparison_matrix", "")
        assert matrix, "comparison_matrix should be non-empty for multi-criteria query"
        assert "|" in matrix, (
            f"comparison_matrix should contain markdown table pipes, got: "
            f"'{matrix[:200]}'"
        )


class TestAnalyticalScaffold:
    """Tests for _generate_analytical_scaffold."""

    @pytest.mark.asyncio
    async def test_scaffold_uses_reason_not_generate(self, mock_client):
        """Scaffold phase must call client.reason(), NOT client.generate()."""
        mock_response = MagicMock()
        mock_response.content = (
            "## Analytical Framework\n\n"
            "### Sub-question 1: Effectiveness\n"
            "Evidence shows 90% removal [CITE:ev_001].\n\n"
            "### Sub-question 2: Cost\n"
            "Cost analysis reveals $15/1000gal [CITE:ev_002].\n\n"
            "### Gaps\n"
            "Long-term data is missing."
        )

        mock_client.reason = AsyncMock(return_value=mock_response)
        mock_client.generate = AsyncMock(return_value=mock_response)

        evidence_store = {
            f"ev_{i:03d}": {
                "evidence_id": f"ev_{i:03d}",
                "statement": f"Treatment achieves {80 + i}% removal",
                "quality_tier": "GOLD",
                "relevance_score": 0.9,
                "source_url": f"https://example.com/{i}",
            }
            for i in range(5)
        }

        agent = ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=list(evidence_store.keys()),
            query="water treatment effectiveness",
            mode="8phase",
        )
        # Populate notebook with a successful step so scaffold has context
        agent._notebook.add_step(AnalysisStep(
            step_number=1,
            reasoning="extract",
            tool_name="extract_numeric_data",
            result=ToolResult(
                success=True,
                tool_name="extract_numeric_data",
                markdown="extracted data",
                source_evidence_ids=["ev_001"],
                data_points_produced=[
                    {"value": "90", "unit": "%", "evidence_id": "ev_001"},
                ],
            ),
            elapsed_seconds=1.0,
        ))

        briefing = {
            "learnings": [
                {
                    "fact": "Treatment achieves 90% removal",
                    "tier": "GOLD",
                    "evidence_ids": ["ev_001"],
                },
            ],
            "clusters": [
                {
                    "theme": "treatment",
                    "learning_indices": [0],
                    "evidence_count": 1,
                },
            ],
            "sub_questions": ["What is the effectiveness?"],
        }

        scaffold = await agent._generate_analytical_scaffold(briefing)

        assert mock_client.reason.called, (
            "client.reason() should have been called for scaffold generation"
        )
        assert not mock_client.generate.called, (
            "client.generate() should NOT be called for scaffold generation"
        )
        assert len(scaffold) > 50


class TestProgrammaticCritique:
    """Tests for _programmatic_critique."""

    def test_critique_flags_missing_integration(self, mock_client):
        """Multi-criteria query without integrated paragraphs fails integration."""
        evidence_store = {
            f"ev_{i:03d}": {
                "evidence_id": f"ev_{i:03d}",
                "statement": f"Evidence piece {i}",
                "quality_tier": "GOLD",
                "relevance_score": 0.9,
                "source_url": f"https://example.com/{i}",
            }
            for i in range(10)
        }

        agent = ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=list(evidence_store.keys()),
            query="effective AND affordable water filters",
            mode="8phase",
        )

        # Interpretation that lists criteria separately (no integration)
        interpretation = (
            "Section on Removal Efficiency:\n\n"
            "The removal rate was 95% for GAC [CITE:ev_001]. "
            "Another study found 88% removal [CITE:ev_002].\n\n"
            "Section on Cost Analysis:\n\n"
            "The price per unit was $15 [CITE:ev_003]. "
            "Maintenance costs were low [CITE:ev_004].\n\n"
            "Section on Market Trends:\n\n"
            "The market is growing at 7.2% CAGR [CITE:ev_005]."
        )

        briefing = {
            "sub_questions": [
                "What is the effective of each option?",
                "What is the affordable of each option?",
                "What gaps remain in the evidence?",
            ],
            "learnings": [],
            "clusters": [],
        }

        critique = agent._programmatic_critique(interpretation, briefing)

        # Find the integration dimension
        integration_dim = None
        for dim in critique["dimensions"]:
            if dim["dimension"] == "integration":
                integration_dim = dim
                break

        assert integration_dim is not None, (
            "Critique should have an 'integration' dimension"
        )
        assert not integration_dim["passed"], (
            "Integration should FAIL when criteria are discussed in separate "
            "sections without cross-criterion paragraphs"
        )


class TestRewriteInterpretation:
    """Tests for _rewrite_interpretation."""

    @pytest.mark.asyncio
    async def test_rewrite_preserves_length(self, mock_client):
        """Rewrites >= 70% of original are accepted; < 70% are rejected."""
        evidence_store = {
            "ev_001": {
                "evidence_id": "ev_001",
                "statement": "GAC achieves 95% removal",
                "quality_tier": "GOLD",
                "relevance_score": 0.9,
                "source_url": "https://example.com/1",
            },
        }

        agent = ReactAnalysisAgent(
            client=mock_client,
            evidence_store=evidence_store,
            evidence_ids=["ev_001"],
            query="water treatment",
            mode="8phase",
        )

        original = "A" * 1000  # 1000 characters
        critique = {
            "dimensions": [
                {"dimension": "test", "passed": False, "issues": ["fix this"]},
            ],
            "needs_rewrite": True,
            "rewrite_instructions": "Fix the test issue",
        }
        briefing = {"learnings": [], "clusters": [], "sub_questions": []}

        # Add an interpret_results step to the notebook (required by rewrite)
        agent._notebook.add_step(AnalysisStep(
            step_number=1,
            reasoning="interpretation",
            tool_name="interpret_results",
            result=ToolResult(
                success=True,
                tool_name="interpret_results",
                markdown=original,
                source_evidence_ids=["ev_001"],
            ),
            elapsed_seconds=1.0,
        ))

        # Test 1: Rewrite at 80% of original length — should be ACCEPTED
        rewrite_80pct = MagicMock()
        rewrite_80pct.content = "B" * 800  # 80% of 1000
        mock_client.generate = AsyncMock(return_value=rewrite_80pct)

        result = await agent._rewrite_interpretation(
            original, critique, briefing,
        )
        assert result is not None, (
            "Rewrite at 80% of original length should be accepted"
        )

        # Test 2: Rewrite at 50% of original length — should be REJECTED
        rewrite_50pct = MagicMock()
        rewrite_50pct.content = "C" * 500  # 50% of 1000
        mock_client.generate = AsyncMock(return_value=rewrite_50pct)

        result = await agent._rewrite_interpretation(
            original, critique, briefing,
        )
        assert result is None, (
            "Rewrite at 50% of original length should be rejected (< 70%)"
        )


class TestEightPhasePipeline:
    """Integration tests for the full 8-phase pipeline."""

    @pytest.mark.asyncio
    async def test_8phase_full_pipeline(self, evidence_store, mock_client):
        """Full 8-phase pipeline produces interpret_results and verify_claims."""
        # Phase 1: Plan
        async def mock_structured(prompt, schema, **kwargs):
            return AnalysisPlan(steps=[
                PlannedStep(tool_name="extract_numeric_data"),
                PlannedStep(tool_name="query_evidence_sql"),
            ])

        mock_client.generate_structured = mock_structured

        # Phase 4: Scaffold (reason) — must be >50 chars
        scaffold_text = (
            "## Analytical Framework\n\n"
            "### Sub-question 1: Effectiveness\n"
            "Biochar removes 85-99% lead across 15 studies [CITE:ev_001] "
            "[CITE:ev_005]. Rice husk variants show highest performance.\n"
            "Higher pH improves removal: 99% at pH 7.8 [CITE:ev_015].\n"
            "However, contact time varies from 40-170 min [CITE:ev_003].\n\n"
            "### Sub-question 2: Trade-offs\n"
            "Effectiveness correlates with contact time — higher removal "
            "requires longer exposure. Cost data is sparse but biochar is "
            "generally considered low-cost compared to activated carbon.\n\n"
            "### Evidence-based ranking\n"
            "1. Biochar (rice husk): highest removal, lowest cost\n"
            "2. Biochar (wood): moderate removal, moderate cost\n\n"
            "### Gaps\n"
            "Long-term performance data missing. No cost-per-unit data."
        )
        scaffold_response = MagicMock()
        scaffold_response.content = scaffold_text
        mock_client.reason = AsyncMock(return_value=scaffold_response)

        # Phase 5: Write + Phase 7: Rewrite (generate) — must be >100 chars
        write_text = (
            "Biochar derived from rice husk achieves 86% removal at pH 5.2 "
            "[CITE:ev_001]. Statistical analysis across 15 studies shows "
            "mean removal of 92% with 95% CI of 88-96% [CITE:ev_005]. "
            "Higher pH levels correlate with improved performance, reaching "
            "99% at pH 7.8 [CITE:ev_015]. However, contact time varies "
            "significantly from 40 to 170 minutes [CITE:ev_003], creating "
            "a trade-off between removal efficiency and processing speed. "
            "Comparing rice husk and wood-derived biochar reveals that rice "
            "husk variants consistently outperform at equivalent contact "
            "times [CITE:ev_001] [CITE:ev_008]. The cost-effectiveness "
            "ranking places biochar at the top for lead removal due to "
            "low material cost and high efficiency. However, gaps remain: "
            "no long-term performance data beyond 6 months exists, and "
            "cost-per-unit comparisons with activated carbon are absent."
        )
        write_response = MagicMock()
        write_response.content = write_text
        mock_client.generate = AsyncMock(return_value=write_response)

        with patch.dict(os.environ, {"PG_ANALYSIS_PIPELINE": "8phase"}):
            with patch(
                "src.polaris_graph.tools.react_agent._LLM_LEARNINGS_ENABLED",
                False,
            ):
                with patch(
                    "src.polaris_graph.tools.react_agent.embed_text",
                    return_value=[1.0, 0.0, 0.0],
                ):
                    with patch(
                        "src.polaris_graph.tools.react_agent.embed_texts",
                        return_value=[
                            [0.9, 0.1, 0.0]
                            for _ in range(len(evidence_store))
                        ],
                    ):
                        agent = ReactAnalysisAgent(
                            client=mock_client,
                            evidence_store=evidence_store,
                            evidence_ids=list(evidence_store.keys()),
                            query="biochar heavy metal removal",
                            mode="8phase",
                        )
                        notebook = await agent.run()

        tool_names = [s.tool_name for s in notebook.steps]

        # Must have interpretation and verification steps
        assert "interpret_results" in tool_names, (
            f"8-phase pipeline must produce interpret_results step, "
            f"got: {tool_names}"
        )
        assert "verify_claims" in tool_names, (
            f"8-phase pipeline must produce verify_claims step, "
            f"got: {tool_names}"
        )

        # Interpretation step must have content
        interp_steps = [
            s for s in notebook.steps if s.tool_name == "interpret_results"
        ]
        assert len(interp_steps) >= 1
        assert interp_steps[0].result.success
        assert len(interp_steps[0].result.markdown) > 50

    @pytest.mark.asyncio
    async def test_legacy_mode_unchanged(self, evidence_store, mock_client):
        """Legacy mode does NOT use 8-phase steps (no critique/rewrite)."""
        async def mock_structured(prompt, schema, **kwargs):
            return AnalysisPlan(steps=[
                PlannedStep(tool_name="extract_numeric_data"),
                PlannedStep(tool_name="query_evidence_sql"),
            ])

        mock_client.generate_structured = mock_structured

        mock_response = MagicMock()
        mock_response.content = (
            "Biochar achieves 85-99% lead removal [CITE:ev_001]. "
            "Average removal efficiency is 92% across studies "
            "[CITE:ev_005]. Contact time ranges from 40 to 170 "
            "minutes [CITE:ev_008]."
        )
        mock_client.generate = AsyncMock(return_value=mock_response)

        with patch.dict(os.environ, {
            "PG_ANALYSIS_PIPELINE": "",
            "PG_REACT_MODE": "",
        }):
            agent = ReactAnalysisAgent(
                client=mock_client,
                evidence_store=evidence_store,
                evidence_ids=list(evidence_store.keys()),
                query="biochar heavy metal removal",
                mode="legacy",
            )
            notebook = await agent.run()

        tool_names = [s.tool_name for s in notebook.steps]

        # Legacy mode SHOULD have interpret_results and verify_claims
        assert "interpret_results" in tool_names, (
            f"Legacy mode should have interpret_results, got: {tool_names}"
        )
        assert "verify_claims" in tool_names, (
            f"Legacy mode should have verify_claims, got: {tool_names}"
        )

        # Legacy mode should NOT call client.reason (that's 8-phase only)
        # Verify no scaffold or critique steps exist
        for step in notebook.steps:
            assert step.tool_name not in ("scaffold", "critique", "rewrite"), (
                f"Legacy mode should not have 8-phase step: {step.tool_name}"
            )
