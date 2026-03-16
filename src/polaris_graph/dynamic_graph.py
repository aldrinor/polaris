"""
Dynamic graph builder — creates LangGraph StateGraph from PipelineDefinition.

Amendment A4: Two-tier hierarchy with MacroStages as sub-graphs.
Each MacroStage becomes a compiled sub-graph node in the main graph.
State pruning between macro transitions (A8.1).

This module bridges PipelineDefinition (config) and LangGraph (execution).
The standard graph.py build_graph() remains for the default pipeline.
dynamic_graph.py is used when a custom pipeline is selected.
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Callable, Awaitable, Optional

from langgraph.graph import END, StateGraph

from src.polaris_graph.pipeline_definition import (
    MacroStage,
    PipelineDefinition,
    PipelineStage,
    StageType,
)
from src.polaris_graph.state import ResearchState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage type → async handler registry
# ---------------------------------------------------------------------------

# Maps stage_type to the actual async function that processes the state.
# These are lazy-loaded from graph.py's closured node functions.
# For custom pipelines, we import the underlying agent functions directly.

def _get_stage_handler(stage: PipelineStage, client_holder: dict) -> Callable:
    """Return the async handler function for a given stage type.

    Each handler takes (state: ResearchState) and returns a dict of state updates.
    """
    stage_type = stage.stage_type.value
    config = stage.config

    if stage_type == "plan":
        async def _handle_plan(state: ResearchState) -> dict:
            from src.polaris_graph.agents.planner import plan_queries, plan_seed_queries
            from src.polaris_graph.state import PG_AGENTIC_SEARCH_ENABLED
            client = client_holder["client"]
            if PG_AGENTIC_SEARCH_ENABLED and state.get("iteration_count", 0) == 0:
                return await plan_seed_queries(client, state)
            return await plan_queries(client, state)
        return _handle_plan

    elif stage_type == "search":
        async def _handle_search(state: ResearchState) -> dict:
            from src.polaris_graph.agents.searcher import execute_searches
            client = client_holder["client"]
            return await execute_searches(state, client=client)
        return _handle_search

    elif stage_type == "storm_interviews":
        async def _handle_storm(state: ResearchState) -> dict:
            from src.polaris_graph.agents.storm_interviews import (
                PG_STORM_ENABLED, run_storm_interviews,
            )
            if not PG_STORM_ENABLED:
                return {}
            if state.get("iteration_count", 0) > 1:
                return {}
            client = client_holder["client"]
            try:
                return await run_storm_interviews(client=client, state=state)
            except Exception as exc:
                logger.warning("[dynamic_graph] STORM failed: %s", str(exc)[:200])
                return {}
        return _handle_storm

    elif stage_type == "analyze":
        async def _handle_analyze(state: ResearchState) -> dict:
            from src.polaris_graph.agents.analyzer import analyze_sources
            client = client_holder["client"]
            return await analyze_sources(client, state)
        return _handle_analyze

    elif stage_type == "verify":
        async def _handle_verify(state: ResearchState) -> dict:
            from src.polaris_graph.agents.verifier import verify_claims
            client = client_holder["client"]
            return await verify_claims(client, state)
        return _handle_verify

    elif stage_type == "evaluate":
        async def _handle_evaluate(state: ResearchState) -> dict:
            # Evaluate uses the _evaluate logic from graph.py
            # For custom pipelines, we provide a simplified evaluation
            from src.polaris_graph.agents.synthesizer import analyze_gaps
            client = client_holder["client"]
            return await analyze_gaps(client, state)
        return _handle_evaluate

    elif stage_type == "synthesize":
        async def _handle_synthesize(state: ResearchState) -> dict:
            from src.polaris_graph.agents.synthesizer import synthesize_report
            client = client_holder["client"]
            return await synthesize_report(client, state)
        return _handle_synthesize

    elif stage_type == "search_gaps":
        async def _handle_search_gaps(state: ResearchState) -> dict:
            from src.polaris_graph.agents.synthesizer import analyze_gaps
            client = client_holder["client"]
            gap_result = await analyze_gaps(client, state)
            return gap_result
        return _handle_search_gaps

    elif stage_type == "custom_llm":
        async def _handle_custom_llm(state: ResearchState) -> dict:
            """Custom LLM call — uses prompt from stage config."""
            client = client_holder["client"]
            prompt = config.get("prompt", "Analyze the following research state.")
            system_prompt = config.get("system_prompt", "You are a research assistant.")
            result = await client.generate(
                prompt=prompt.format(**{k: str(v)[:500] for k, v in state.items() if isinstance(v, str)}),
                system_prompt=system_prompt,
                max_tokens=config.get("max_tokens", 4096),
            )
            output_key = config.get("output_key", "custom_llm_output")
            return {output_key: result}
        return _handle_custom_llm

    elif stage_type == "filter":
        async def _handle_filter(state: ResearchState) -> dict:
            """Filter stage — passes through (filtering is done in analyze/verify)."""
            return {}
        return _handle_filter

    elif stage_type == "merge":
        async def _handle_merge(state: ResearchState) -> dict:
            """Merge stage — passes through (merging is done in synthesize)."""
            return {}
        return _handle_merge

    else:
        async def _handle_unknown(state: ResearchState) -> dict:
            logger.warning("[dynamic_graph] Unknown stage type: %s", stage_type)
            return {}
        return _handle_unknown


# ---------------------------------------------------------------------------
# State pruning (A8.1)
# ---------------------------------------------------------------------------

def _state_size_kb(state: dict) -> int:
    """Estimate state size in KB."""
    try:
        import json
        return len(json.dumps(state, default=str).encode("utf-8")) // 1024
    except Exception:
        return 0


def prune_state(state: ResearchState, completed_macro: str) -> dict:
    """Drop heavy transient data from state after a MacroStage completes.

    A8.1: Prevents state bloat in 175-node pipelines with uploaded documents.
    """
    pruned = dict(state)

    if completed_macro == "collection":
        # Drop raw source content — evidence pieces already extracted
        pruned["raw_source_contents"] = {}
        logger.debug(
            "[state_prune] Pruned raw_source_contents after '%s'",
            completed_macro,
        )

    elif completed_macro == "analysis":
        # Drop intermediate clustering data
        pruned.pop("cluster_assignments", None)

    elif completed_macro == "verification":
        # Truncate verbose reasoning to save state space
        for claim in pruned.get("claims", []):
            reasoning = claim.get("reasoning", "")
            if len(reasoning) > 300:
                claim["reasoning"] = reasoning[:300] + "..."

    before_kb = _state_size_kb(state)
    after_kb = _state_size_kb(pruned)
    if before_kb > after_kb:
        logger.info(
            "[state_prune] Pruned state after '%s': %d KB -> %d KB (-%d KB)",
            completed_macro, before_kb, after_kb, before_kb - after_kb,
        )

    return pruned


# ---------------------------------------------------------------------------
# Sub-graph builder for a single MacroStage
# ---------------------------------------------------------------------------

def _build_macro_subgraph(
    macro: MacroStage,
    client_holder: dict,
) -> StateGraph:
    """Build a LangGraph StateGraph for a single MacroStage's internal stages."""
    subgraph = StateGraph(ResearchState)

    # Add nodes
    for stage in macro.stages:
        handler = _get_stage_handler(stage, client_holder)
        subgraph.add_node(stage.stage_id, handler)

    # Wire edges based on depends_on
    entry_stages = macro.get_entry_stages()

    if len(entry_stages) == 1:
        subgraph.set_entry_point(entry_stages[0].stage_id)
    else:
        # Multiple entry points — add a dummy entry node that fans out
        async def _noop(state: ResearchState) -> dict:
            return {}
        subgraph.add_node("__entry__", _noop)
        subgraph.set_entry_point("__entry__")
        for entry in entry_stages:
            subgraph.add_edge("__entry__", entry.stage_id)

    # Build dependency edges
    stage_map = {s.stage_id: s for s in macro.stages}
    for stage in macro.stages:
        if stage.depends_on:
            for dep_id in stage.depends_on:
                subgraph.add_edge(dep_id, stage.stage_id)

    # Exit stages → END
    exit_stages = macro.get_exit_stages()
    for exit_stage in exit_stages:
        subgraph.add_edge(exit_stage.stage_id, END)

    return subgraph


# ---------------------------------------------------------------------------
# Main graph builder
# ---------------------------------------------------------------------------

def build_dynamic_graph(
    pipeline: PipelineDefinition,
    client_holder: Optional[dict] = None,
) -> StateGraph:
    """Build a LangGraph StateGraph dynamically from a PipelineDefinition.

    Each MacroStage becomes a node in the main graph. Internally, each
    macro-stage is a compiled sub-graph.

    Args:
        pipeline: The pipeline definition to build from.
        client_holder: Dict with 'client' key holding the LLM client.
            If None, creates a holder that must be populated before execution.

    Returns:
        Compiled-ready StateGraph (call .compile() on it).
    """
    if client_holder is None:
        client_holder = {"_snapshot": {}}

    main_graph = StateGraph(ResearchState)
    execution_order = pipeline.get_execution_order()

    logger.info(
        "[dynamic_graph] Building graph from pipeline '%s': %d macros, %d total nodes, "
        "execution order: %s",
        pipeline.name, len(pipeline.macro_stages), pipeline.total_nodes,
        execution_order,
    )

    # Build and add sub-graph nodes for each macro-stage
    for macro_id in execution_order:
        macro = pipeline.get_macro(macro_id)
        if not macro:
            raise ValueError(f"Macro '{macro_id}' not found in pipeline definition")

        if macro.stage_count == 1:
            # Single-stage macro — no sub-graph overhead, use handler directly
            handler = _get_stage_handler(macro.stages[0], client_holder)

            # Wrap with state pruning
            async def _wrapped(state: ResearchState, _h=handler, _mid=macro_id) -> dict:
                result = await _h(state)
                pruned_updates = prune_state({**state, **result}, _mid)
                # Only return keys that changed
                diff = {}
                for k, v in pruned_updates.items():
                    if k in result or v != state.get(k):
                        diff[k] = v
                return result  # Let LangGraph merge, pruning is advisory
            main_graph.add_node(macro_id, _wrapped)
        else:
            # Multi-stage macro — build sub-graph
            subgraph = _build_macro_subgraph(macro, client_holder)
            compiled_sub = subgraph.compile()

            # Wrap compiled sub-graph as a node with state pruning
            async def _run_subgraph(
                state: ResearchState,
                _sub=compiled_sub,
                _mid=macro_id,
            ) -> dict:
                try:
                    result = await _sub.ainvoke(dict(state))
                    pruned = prune_state(result, _mid)
                    return pruned
                except Exception as exc:
                    logger.error(
                        "[dynamic_graph] MacroStage '%s' failed: %s",
                        _mid, str(exc)[:300],
                    )
                    raise
            main_graph.add_node(macro_id, _run_subgraph)

    # Wire macro-level edges based on execution order
    if execution_order:
        main_graph.set_entry_point(execution_order[0])

        for i in range(len(execution_order) - 1):
            main_graph.add_edge(execution_order[i], execution_order[i + 1])

        # Last macro → END
        main_graph.add_edge(execution_order[-1], END)

    # Store client holder reference
    main_graph._pg_client_holder = client_holder  # type: ignore[attr-defined]

    logger.info(
        "[dynamic_graph] Graph built successfully: %d macro-nodes, %d total stages",
        len(execution_order), pipeline.total_nodes,
    )

    return main_graph


# ---------------------------------------------------------------------------
# Pipeline runner — high-level API for executing a custom pipeline
# ---------------------------------------------------------------------------

async def run_custom_pipeline(
    pipeline: PipelineDefinition,
    vector_id: str,
    query: str,
    application: str = "general",
    region: str = "GLOBAL",
) -> dict:
    """Execute a custom pipeline definition end-to-end.

    Creates an LLM client, builds the dynamic graph, applies config
    overrides, and runs the pipeline.

    Returns the final state dict.
    """
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.state import create_initial_state

    # Apply config overrides from pipeline definition
    for key, value in pipeline.config_overrides.items():
        os.environ[key] = str(value)
        logger.info("[dynamic_graph] Config override: %s=%s", key, value)

    # Create LLM client
    client = OpenRouterClient()
    client_holder = {"client": client, "_snapshot": {}}

    # Build graph
    graph = build_dynamic_graph(pipeline, client_holder)
    app = graph.compile()

    # Create initial state
    initial_state = create_initial_state(
        vector_id=vector_id,
        query=query,
        application=application,
        region=region,
    )
    initial_state["pipeline_id"] = pipeline.pipeline_id
    initial_state["pipeline_name"] = pipeline.name

    logger.info(
        "[dynamic_graph] Running pipeline '%s' for vector '%s': query='%s'",
        pipeline.name, vector_id, query[:100],
    )

    # Execute
    start = time.time()
    try:
        final_state = await app.ainvoke(initial_state)
        elapsed = time.time() - start
        logger.info(
            "[dynamic_graph] Pipeline '%s' completed in %.1f min. "
            "Evidence: %d, Claims: %d",
            pipeline.name, elapsed / 60,
            len(final_state.get("evidence", [])),
            len(final_state.get("claims", [])),
        )
        return final_state
    except Exception as exc:
        elapsed = time.time() - start
        logger.error(
            "[dynamic_graph] Pipeline '%s' failed after %.1f min: %s",
            pipeline.name, elapsed / 60, str(exc)[:300],
        )
        raise
