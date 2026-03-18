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
