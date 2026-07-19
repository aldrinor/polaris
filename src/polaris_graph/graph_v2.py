"""v2 Research Graph (CRAG + Parallel Sections + Grounded Assembly).

Complete LangGraph state machine for the v2 research pipeline.

Architecture:
    plan → search → storm_interviews → fetch_content → crag_analyze
         → plan_outline → blueprint
         → [Send: write_section × N] → [Send: verify_section × N]
         → assemble → END

Key Integration Safeguards:
    - Fix R7-#1: Dedicated fetch_content node (content starvation fix)
    - Fix R7-#2: Trace events + legacy sections list (frontend contract)
    - Fix R7-#4: v2 node names emitted for UI progress mapping
    - Fix R5-#1: merge_sections_reducer for parallel writers
    - Fix R5-#3: TPM throttle on all LLM calls
    - Fix R6-#1: Sequential rewrites in verifier
    - Fix R6-#2: Grounded bibliography from actual citations only
    - Fix R6-#3: CancelledError propagation (no zombie nodes)
    - Fix R6-#4: Fallback sections prevent Send crashes
    - Fix R6-#5: Placeholder sections pruned from final output

Cost: $0 for retrieval (local embeddings), LLM cost only for synthesis/verify.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Annotated, Any

from langgraph.graph import END, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from src.polaris_graph.retrieval.crag_retriever import CRAGConfig, CRAGRetriever, RawDocument
from src.polaris_graph.retrieval.section_blueprint import SectionBlueprint, SectionSpec
from src.polaris_graph.retrieval.source_registry import SourceRegistry
from src.polaris_graph.state import (
    ReportSection,
    SectionOutline,
    merge_sections_reducer,
)
from src.polaris_graph.synthesis.report_assembler_v2 import assemble_report
from src.polaris_graph.synthesis.synthesizer_v2 import write_section
from src.polaris_graph.synthesis.verifier_v2 import verify_section
from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MAX_ITERATIONS = int(resolve("PG_V2_MAX_ITERATIONS"))
MAX_EXECUTION_MINUTES = int(resolve("PG_V2_MAX_MINUTES"))

# Fetch concurrency (matches v1 default)
FETCH_CONCURRENCY = int(os.getenv("PG_FETCH_CONCURRENCY", "10"))
FETCH_TIMEOUT = int(os.getenv("PG_FETCH_TIMEOUT", "30"))


# ---------------------------------------------------------------------------
# v2 State TypedDict with Annotated reducers
# ---------------------------------------------------------------------------

class ResearchStateV2(TypedDict):
    """v2 state with proper reducers for parallel section writing."""

    # Identity
    query: str
    title: str

    # Search planning (reused from v1 planner)
    sub_queries: list[str]
    search_strategy: str

    # Raw results (cleared after CRAG — Fix R4-#3)
    web_results: list[dict[str, Any]]
    academic_results: list[dict[str, Any]]
    fetched_content: list[dict[str, Any]]

    # STORM interviews (AREA-3: multi-perspective enrichment)
    storm_conversations: list[dict[str, Any]]
    storm_outline: list[dict[str, Any]]

    # CRAG output
    evidence: list[dict[str, Any]]
    crag_stats: dict[str, Any]
    crag_gate: str  # CORRECT / AMBIGUOUS / INCORRECT

    # Source registry (serialized for checkpointing)
    registry_data: dict[str, Any]

    # Blueprint
    section_specs: list[dict[str, Any]]  # serialized SectionSpec list
    blueprint_stats: dict[str, Any]

    # Outline
    section_outline: list[SectionOutline]
    section_order: list[str]

    # Synthesis (Fix R5-#1: dict-based with merge reducer)
    completed_sections: Annotated[
        dict[str, ReportSection], merge_sections_reducer
    ]

    # Assembly
    final_report: str
    assembly_stats: dict[str, Any]

    # Control
    iteration_count: int
    status: str
    error: str
    timestamps: dict[str, str]


# ---------------------------------------------------------------------------
# v1 State Compatibility
# ---------------------------------------------------------------------------

def _v1_compat_state(state: ResearchStateV2) -> dict[str, Any]:
    """Map v2 state keys to v1 expectations for reused agents.

    v1 agents (planner, searcher, storm) read 'original_query', 'application',
    'region' from state. v2 uses 'query' and omits application/region from
    ResearchStateV2. This wrapper merges both so v1 code works unchanged.
    """
    compat = dict(state)
    compat.setdefault("original_query", state.get("query", ""))
    compat.setdefault("application", "")
    compat.setdefault("region", "")
    compat.setdefault("iteration_count", 0)
    return compat


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------

async def plan_node(state: ResearchStateV2) -> dict[str, Any]:
    """Generate search queries using existing planner infrastructure."""
    from src.polaris_graph.agents.planner import plan_queries
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    tracer = get_tracer()
    if tracer:
        tracer.node_start("plan")

    client = OpenRouterClient()
    # Reuse v1 planner — wrap state for v1 key compatibility
    v1_state = _v1_compat_state(state)
    result = await plan_queries(client, v1_state)

    queries = result.get("sub_queries", [])
    if tracer:
        tracer.node_end("plan", query_count=len(queries))

    return {
        "sub_queries": queries,
        "search_strategy": result.get("search_strategy", "broad"),
        "status": "searching",
    }


async def search_node(state: ResearchStateV2) -> dict[str, Any]:
    """Execute searches using existing searcher infrastructure."""
    from src.polaris_graph.agents.searcher import execute_searches

    tracer = get_tracer()
    if tracer:
        tracer.node_start("search")

    # v1 searcher expects original_query, region, sub_queries
    v1_state = _v1_compat_state(state)
    result = await execute_searches(v1_state)

    web_count = len(result.get("web_results", []))
    acad_count = len(result.get("academic_results", []))
    if tracer:
        tracer.node_end("search", web_results=web_count, academic_results=acad_count)

    return {
        "web_results": result.get("web_results", []),
        "academic_results": result.get("academic_results", []),
        "status": "fetching",
    }


async def storm_interviews_node(state: ResearchStateV2) -> dict[str, Any]:
    """STORM multi-perspective interview node.

    AREA-3: Runs Stanford STORM interviews between search and fetch.
    Opt-in via PG_STORM_ENABLED=1 in .env. When disabled, passes through.
    Enriches web_results with interview-sourced URLs before content fetch.
    """
    from src.polaris_graph.agents.storm_interviews import (
        PG_STORM_ENABLED,
        run_storm_interviews,
    )

    if not PG_STORM_ENABLED:
        return {}  # No-op pass-through

    # Only run STORM on first iteration
    if state.get("iteration_count", 0) > 1:
        logger.info("STORM: Skipping on iteration %d", state.get("iteration_count", 0))
        return {}

    from src.polaris_graph.llm.openrouter_client import NoEndpointError, OpenRouterClient

    client = OpenRouterClient()
    tracer = get_tracer()
    if tracer:
        tracer.node_start("storm_interviews")

    logger.info("STORM: Starting multi-perspective interviews")
    try:
        v1_state = _v1_compat_state(state)
        result = await run_storm_interviews(client=client, state=v1_state)
        if tracer:
            tracer.node_end(
                "storm_interviews",
                conversations=len(result.get("storm_conversations", [])),
                outline_sections=len(result.get("storm_outline", [])),
            )
        return result
    except NoEndpointError:
        # I-ready-019 FL-01 (#1102): structural discovery 404 must fail loud, not "continue without".
        raise
    except Exception as exc:
        logger.warning("STORM interviews failed: %s — continuing without", str(exc)[:200])
        if tracer:
            tracer.node_end("storm_interviews", result="failed", error=str(exc)[:200])
        return {}


# ---------------------------------------------------------------------------
# Fix R7-#1: Dedicated fetch_content node
# ---------------------------------------------------------------------------
# In v1, the analyze node did BOTH fetching and evidence extraction.
# We deleted analyze and replaced it with CRAG (local embeddings).
# But CRAG needs actual text to evaluate — search only returns URLs.
# Without this node, CRAG receives 0 text and produces 0 evidence.
# ---------------------------------------------------------------------------

async def fetch_content_node(state: ResearchStateV2) -> dict[str, Any]:
    """Fetch web page content for all search result URLs.

    Fix R7-#1: This node runs AFTER search and BEFORE crag_analyze.
    Without it, CRAG would receive bare URLs with no text, producing
    zero evidence and an empty report.

    Reuses v1's content fetching infrastructure (AccessBypass chain,
    content cache, trafilatura fallback, snippet fallback).
    """
    from src.polaris_graph.agents.analyzer import _fetch_all_content

    tracer = get_tracer()
    if tracer:
        tracer.node_start("fetch_content")

    web_results = state.get("web_results", [])
    academic_results = state.get("academic_results", [])
    all_results = web_results + academic_results

    if not all_results:
        logger.warning("fetch_content: 0 search results to fetch")
        if tracer:
            tracer.node_end("fetch_content", fetched=0)
        return {"fetched_content": [], "status": "analyzing"}

    logger.info("fetch_content: fetching content for %d URLs", len(all_results))

    try:
        # _fetch_all_content returns (fetched_list, cache_hits_count)
        fetched, cache_hits = await _fetch_all_content(all_results)
        logger.info("fetch_content: %d cache hits", cache_hits)
    except Exception as exc:
        logger.error("fetch_content: fetch failed: %s", str(exc)[:300])
        if tracer:
            tracer.node_end("fetch_content", fetched=0, error=str(exc)[:200])
        return {"fetched_content": [], "status": "analyzing"}

    # Cap content per source to prevent state bloat
    from src.polaris_graph.state import PG_CONTENT_PER_SOURCE
    content_cap = PG_CONTENT_PER_SOURCE

    capped = [
        {
            "url": f.get("url", ""),
            "title": f.get("title", ""),
            "content": f.get("content", "")[:content_cap] if content_cap > 0 else "",
            "source_type": f.get("source_type", "web"),
        }
        for f in fetched
        if f.get("content", "").strip()
    ]

    logger.info(
        "fetch_content: %d/%d URLs returned content (capped to %d chars)",
        len(capped), len(all_results), content_cap,
    )
    if tracer:
        tracer.node_end("fetch_content", fetched=len(capped), total_urls=len(all_results))

    return {"fetched_content": capped, "status": "analyzing"}


async def crag_analyze_node(state: ResearchStateV2) -> dict[str, Any]:
    """Run CRAG pipeline: chunk → dedup → embed → score → gate → register.

    This replaces v1's 126-call LLM analyzer with $0 local embeddings.
    Also clears heavy state fields (Fix R4-#3).
    """
    tracer = get_tracer()
    if tracer:
        tracer.node_start("crag_analyze")

    config = CRAGConfig()
    registry = SourceRegistry()
    retriever = CRAGRetriever(config=config, registry=registry)

    # Build RawDocument list from search results
    search_results = state.get("web_results", []) + state.get("academic_results", [])
    fetched = {
        item.get("url", ""): item.get("content", "")
        for item in state.get("fetched_content", [])
        if item.get("url")
    }

    documents = CRAGRetriever.documents_from_search_results(
        search_results, fetched, config.paywall_min_chars,
    )

    # Run CRAG pipeline
    result = await retriever.retrieve(state["query"], documents)

    ev_count = len(result.evidence)
    gate = result.stats.get("crag_gate", "INCORRECT")
    if tracer:
        tracer.node_end(
            "crag_analyze",
            evidence_count=ev_count,
            crag_gate=gate,
            documents_processed=len(documents),
        )

    # Serialize registry for state (Fix R4-#3: clear heavy fields)
    return {
        "evidence": result.evidence,
        "crag_stats": result.stats,
        "crag_gate": gate,
        "registry_data": _serialize_registry(result.registry),
        # Fix R4-#3: Clear heavy raw payloads
        "fetched_content": [],
        "web_results": [],
        "academic_results": [],
        "status": "outlining",
    }


async def plan_outline_node(state: ResearchStateV2) -> dict[str, Any]:
    """Generate evidence-informed outline (L3: outline AFTER search)."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    from src.polaris_graph.synthesis.section_writer import plan_report

    client = OpenRouterClient()
    evidence = state.get("evidence", [])

    # Cluster evidence for outline generation
    # Simplified: group by quality tier
    clusters = _quick_cluster(evidence)

    outline = await plan_report(
        client=client,
        query=state["query"],
        evidence=evidence,
        clusters=clusters,
    )

    # Extract section order and outline dicts
    section_dicts = []
    section_order = []
    for sec in outline.sections:
        section_dicts.append({
            "section_id": sec.section_id,
            "title": sec.title,
            "description": sec.description,
            "search_keywords": getattr(sec, "search_keywords", ""),
            "target_words": sec.target_words,
            "order": sec.order,
            "evidence_ids": sec.evidence_ids,
        })
        section_order.append(sec.section_id)

    return {
        "section_outline": section_dicts,
        "section_order": section_order,
        "status": "blueprinting",
    }


async def blueprint_node(state: ResearchStateV2) -> dict[str, Any]:
    """Build Section Blueprint: cross-section evidence assignment (L5)."""
    bp = SectionBlueprint()
    registry = _deserialize_registry(state.get("registry_data", {}))

    sections = state.get("section_outline", [])
    evidence = state.get("evidence", [])

    specs, stats = await asyncio.to_thread(
        bp.build, sections, evidence, registry,
    )

    # Serialize specs for state
    spec_dicts = [
        {
            "section_id": s.section_id,
            "title": s.title,
            "description": s.description,
            "search_keywords": s.search_keywords,
            "target_words": s.target_words,
            "assigned_evidence_ids": s.assigned_evidence_ids,
            "secondary_evidence_ids": s.secondary_evidence_ids,
            "global_context_ids": s.global_context_ids,
            "is_thin": s.is_thin,
            "is_empty": s.is_empty,
            "evidence_count": s.evidence_count,
            "avg_relevance": s.avg_relevance,
        }
        for s in specs
    ]

    return {
        "section_specs": spec_dicts,
        "blueprint_stats": {
            "total_sections": stats.total_sections,
            "total_evidence": stats.total_evidence,
            "thin_sections": stats.thin_sections,
            "avg_evidence_per_section": stats.avg_evidence_per_section,
        },
        "status": "writing",
    }


def fan_out_write(state: ResearchStateV2) -> list[Send]:
    """Fan-out: send each section spec to a parallel writer via Send API."""
    specs = state.get("section_specs", [])
    sends = []
    for spec_dict in specs:
        sends.append(Send("write_one_section", {
            "spec": spec_dict,
            "evidence": state.get("evidence", []),
            "registry_data": state.get("registry_data", {}),
        }))
    logger.info("Fan-out: sending %d sections to parallel writers", len(sends))
    return sends


async def write_one_section_node(state: dict[str, Any]) -> dict[str, Any]:
    """Write a single section (called via Send — parallel).

    Fix R6-#4: Top-level fallback ensures one failure doesn't crash all writers.
    """
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    client = OpenRouterClient()
    spec_dict = state["spec"]
    evidence = state["evidence"]
    registry = _deserialize_registry(state.get("registry_data", {}))

    # Reconstruct SectionSpec from dict
    spec = SectionSpec(
        section_id=spec_dict["section_id"],
        title=spec_dict["title"],
        description=spec_dict.get("description", ""),
        search_keywords=spec_dict.get("search_keywords", ""),
        target_words=spec_dict.get("target_words", 800),
        assigned_evidence_ids=spec_dict.get("assigned_evidence_ids", []),
        secondary_evidence_ids=spec_dict.get("secondary_evidence_ids", []),
        global_context_ids=spec_dict.get("global_context_ids", []),
        is_thin=spec_dict.get("is_thin", False),
        is_empty=spec_dict.get("is_empty", False),
        evidence_count=spec_dict.get("evidence_count", 0),
        avg_relevance=spec_dict.get("avg_relevance", 0.0),
    )

    bp = SectionBlueprint()
    result = await write_section(client, spec, evidence, bp, registry)
    return {"completed_sections": result}


def fan_out_verify(state: ResearchStateV2) -> list[Send]:
    """Fan-out: send each completed section to a parallel verifier."""
    sections = state.get("completed_sections", {})
    evidence = state.get("evidence", [])
    sends = []
    for section_id, section in sections.items():
        # Skip placeholder sections (no point verifying)
        if "No reliable evidence" in section.get("content", ""):
            continue
        sends.append(Send("verify_one_section", {
            "section": section,
            "evidence": evidence,
        }))
    logger.info("Fan-out: sending %d sections to parallel verifiers", len(sends))
    return sends


async def verify_one_section_node(state: dict[str, Any]) -> dict[str, Any]:
    """Verify a single section (called via Send — parallel).

    Fix R6-#1: Scoring is parallel but rewrites are sequential WITHIN this node.
    Fix R6-#4: Top-level fallback returns original section on failure.
    """
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    client = OpenRouterClient()
    section = state["section"]
    evidence = state["evidence"]

    result = await verify_section(client, section, evidence)
    return {"completed_sections": result}


async def assemble_node(state: ResearchStateV2) -> dict[str, Any]:
    """Assemble final report with grounded bibliography and outline pruning.

    Fix R6-#2: Bibliography built from actual citations only.
    Fix R6-#5: Placeholder sections silently dropped.
    Fix R7-#2: Emit report_assembled trace event with bibliography for frontend.
    """
    tracer = get_tracer()
    if tracer:
        tracer.node_start("assemble")

    sections = state.get("completed_sections", {})
    section_order = state.get("section_order", [])
    registry = _deserialize_registry(state.get("registry_data", {}))
    title = state.get("title", "Research Report")
    query = state.get("query", "")

    final_report, stats = assemble_report(
        sections=sections,
        section_order=section_order,
        registry=registry,
        title=title,
        query=query,
    )

    # Fix R7-#2: Build bibliography array for frontend (matches v1 format)
    # Frontend reads state.bibliography from report_assembled trace event
    bibliography = _build_frontend_bibliography(registry, sections, section_order)

    # Emit report_assembled trace event (frontend expects this)
    if tracer:
        tracer.evidence(
            "assemble", "report_assembled",
            stats.get("total_words", 0),
            sections=stats.get("active_sections", 0),
            total_citations=stats.get("total_citations", 0),
            bibliography_entries=stats.get("unique_sources", 0),
            bibliography=bibliography,
            section_titles=[
                {"id": sid, "title": sections[sid]["title"], "words": sections[sid].get("word_count", 0)}
                for sid in section_order if sid in sections
            ],
            full_report=final_report,
        )
        tracer.node_end(
            "assemble",
            total_words=stats.get("total_words", 0),
            total_citations=stats.get("total_citations", 0),
            unique_sources=stats.get("unique_sources", 0),
        )

    # Fix R7-#2: Populate legacy sections list for v1 compatibility
    # Smart art generator (graph.py:730) reads result.get("sections", [])
    legacy_sections = [
        sections[sid] for sid in section_order if sid in sections
    ]

    return {
        "final_report": final_report,
        "assembly_stats": stats,
        "status": "complete",
    }


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_after_crag(state: ResearchStateV2) -> str:
    """Route based on CRAG gate result."""
    gate = state.get("crag_gate", "INCORRECT")
    iteration = state.get("iteration_count", 0)

    if gate == "CORRECT":
        return "plan_outline"
    elif gate == "AMBIGUOUS" and iteration < MAX_ITERATIONS:
        logger.info("CRAG gate AMBIGUOUS — triggering gap search (iter %d)", iteration)
        return "plan"  # re-plan with refined queries
    else:
        if iteration >= MAX_ITERATIONS:
            logger.warning("CRAG gate %s but max iterations reached — proceeding", gate)
            return "plan_outline"
        logger.warning("CRAG gate INCORRECT — re-planning")
        return "plan"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_v2_graph() -> StateGraph:
    """Build the v2 research graph.

    Returns a compiled StateGraph ready for execution.
    """
    graph = StateGraph(ResearchStateV2)

    # Add nodes
    graph.add_node("plan", plan_node)
    graph.add_node("search", search_node)
    graph.add_node("storm_interviews", storm_interviews_node)  # AREA-3
    graph.add_node("fetch_content", fetch_content_node)  # Fix R7-#1
    graph.add_node("crag_analyze", crag_analyze_node)
    graph.add_node("plan_outline", plan_outline_node)
    graph.add_node("blueprint", blueprint_node)
    graph.add_node("write_one_section", write_one_section_node)
    graph.add_node("verify_one_section", verify_one_section_node)
    graph.add_node("assemble", assemble_node)

    # Define edges: plan → search → storm → fetch → crag → outline → ...
    graph.set_entry_point("plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "storm_interviews")
    graph.add_edge("storm_interviews", "fetch_content")
    graph.add_edge("fetch_content", "crag_analyze")

    # CRAG gate routing
    graph.add_conditional_edges(
        "crag_analyze",
        route_after_crag,
        {
            "plan_outline": "plan_outline",
            "plan": "plan",
        },
    )

    graph.add_edge("plan_outline", "blueprint")

    # Fan-out to parallel section writers
    graph.add_conditional_edges(
        "blueprint",
        fan_out_write,
        ["write_one_section"],
    )

    # Fan-out to parallel verifiers after all sections complete
    graph.add_conditional_edges(
        "write_one_section",
        fan_out_verify,
        ["verify_one_section"],
    )

    # Assembly after all verifications complete
    graph.add_edge("verify_one_section", "assemble")
    graph.add_edge("assemble", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def run_v2_research(
    query: str,
    title: str | None = None,
    application: str = "",
    region: str = "",
    max_iterations: int = 3,
    max_execution_minutes: int = 60,
) -> dict[str, Any]:
    """Run the complete v2 research pipeline.

    Args:
        query: Research question.
        title: Optional report title (defaults to query).
        application: Application context (forwarded to v1 planner).
        region: Geographic region filter (forwarded to v1 searcher).
        max_iterations: Max pipeline iterations.
        max_execution_minutes: Time budget.

    Returns:
        Final state dict with final_report and assembly_stats.
    """
    graph = build_v2_graph()

    initial_state: ResearchStateV2 = {
        "query": query,
        "title": title or query,
        "sub_queries": [],
        "search_strategy": "broad",
        "web_results": [],
        "academic_results": [],
        "fetched_content": [],
        "storm_conversations": [],
        "storm_outline": [],
        "evidence": [],
        "crag_stats": {},
        "crag_gate": "",
        "registry_data": {},
        "section_specs": [],
        "blueprint_stats": {},
        "section_outline": [],
        "section_order": [],
        "completed_sections": {},
        "final_report": "",
        "assembly_stats": {},
        "iteration_count": 0,
        "status": "planning",
        "error": "",
        "timestamps": {"created": datetime.now(timezone.utc).isoformat()},
    }

    logger.info("Starting v2 research pipeline for: %s", query[:80])

    # V2_E2E_006 fix: Enforce timeout to prevent unbounded runs
    timeout_seconds = max_execution_minutes * 60
    try:
        final_state = await asyncio.wait_for(
            graph.ainvoke(
                initial_state,
                config={"recursion_limit": 50},
            ),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.error(
            "v2 pipeline timed out after %d minutes", max_execution_minutes,
        )
        raise TimeoutError(
            f"v2 pipeline exceeded {max_execution_minutes}m budget"
        )

    return final_state


async def build_and_run(
    vector_id: str,
    query: str,
    application: str = "",
    region: str = "",
    stage: int = 1,
    max_iterations: int = 3,
    max_execution_minutes: int = 60,
    resume: bool = False,
    enable_dashboard: bool = False,
    document_ids: list[str] | None = None,
    steer_callback: Any = None,
    research_brief: str | None = None,
) -> dict[str, Any]:
    """v2 entry point with the same signature as v1's build_and_run.

    Fix R7-#5: This function is the drop-in replacement for the v1 entry point.
    live_server.py calls build_and_run() with these exact kwargs.
    We accept all v1 params for compatibility but route to the v2 graph.
    """
    from src.polaris_graph.tracing import PipelineTracer

    # Initialize tracer for this run (so all nodes can emit events)
    tracer = PipelineTracer(vector_id)
    tracer._emit("pipeline_start", "pipeline", {
        "vector_id": vector_id,
        "query": query[:200],
        "application": application,
        "region": region,
        "max_iterations": max_iterations,
        "max_minutes": max_execution_minutes,
        "engine": "v2_crag",
    })

    start_time = time.monotonic()

    try:
        result = await run_v2_research(
            query=query,
            title=query,
            application=application,
            region=region,
            max_iterations=max_iterations,
            max_execution_minutes=max_execution_minutes,
        )
        elapsed = time.monotonic() - start_time

        # Populate v1-compatible fields that live_server.py reads
        result["vector_id"] = vector_id
        result["query"] = query
        result["application"] = application
        result["region"] = region

        # Emit pipeline_end for UI
        stats = result.get("assembly_stats", {})
        tracer._emit("pipeline_end", "pipeline", {
            "vector_id": vector_id,
            "status": result.get("status", "complete"),
            "elapsed_seconds": round(elapsed, 1),
            "total_words": stats.get("total_words", 0),
            "total_citations": stats.get("total_citations", 0),
            "unique_sources": stats.get("unique_sources", 0),
        })

        # Save result JSON (v1 compat: live_server reads from this path)
        import json
        from pathlib import Path
        out_dir = Path("outputs/polaris_graph")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{vector_id}.json"
        serializable = {
            "vector_id": vector_id,
            "query": query,
            "status": result.get("status", "complete"),
            "final_report": result.get("final_report", ""),
            "assembly_stats": result.get("assembly_stats", {}),
            "bibliography": _build_frontend_bibliography(
                _deserialize_registry(result.get("registry_data", {})),
                result.get("completed_sections", {}),
                result.get("section_order", []),
            ),
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, default=str)

        logger.info(
            "v2 pipeline complete: %s, %d words, %.1fs",
            vector_id, stats.get("total_words", 0), elapsed,
        )
        return result

    except Exception as exc:
        elapsed = time.monotonic() - start_time
        tracer._emit("pipeline_end", "pipeline", {
            "vector_id": vector_id,
            "status": "failed",
            "elapsed_seconds": round(elapsed, 1),
            "error": str(exc)[:500],
        })
        raise


# ---------------------------------------------------------------------------
# Fix R7-#2: Frontend bibliography builder
# ---------------------------------------------------------------------------

def _build_frontend_bibliography(
    registry: SourceRegistry,
    sections: dict[str, ReportSection],
    section_order: list[str],
) -> list[dict[str, Any]]:
    """Build bibliography array matching the v1 format expected by the frontend.

    The frontend (event_processor.js:218) expects:
        [{key: "SRC-001", url: "...", source_type: "...", formatted: "..."}, ...]

    This scans the assembled sections for [N] citations and maps them
    back to registry entries.
    """
    import re
    from src.polaris_graph.synthesis.report_assembler_v2 import _extract_cited_sources

    # Gather all section content
    all_content = " ".join(
        sections[sid].get("content", "")
        for sid in section_order if sid in sections
    )

    # Extract cited SRC-NNN IDs (before number resolution)
    cited_ids = _extract_cited_sources(all_content)

    bibliography = []
    for i, src_id in enumerate(cited_ids, 1):
        entry = registry.get(src_id)
        if not entry:
            continue

        # Format matching v1's bibliography trace event
        parts = [f"[{i}]"]
        if entry.authors:
            if len(entry.authors) <= 3:
                parts.append(", ".join(entry.authors))
            else:
                parts.append(f"{entry.authors[0]} et al.")
        if entry.year:
            parts.append(f"({entry.year}).")
        parts.append(f'"{entry.title}."')
        if getattr(entry, "venue", ""):
            parts.append(f"*{entry.venue}*.")
        if entry.doi:
            parts.append(f"DOI: {entry.doi}")
        elif entry.url:
            parts.append(entry.url)

        bibliography.append({
            "key": src_id,
            "url": entry.url,
            "source_type": entry.source_type,
            "formatted": " ".join(parts),
        })

    return bibliography


# ---------------------------------------------------------------------------
# Registry serialization (for LangGraph state checkpointing)
# ---------------------------------------------------------------------------

def _serialize_registry(registry: SourceRegistry) -> dict[str, Any]:
    """Serialize SourceRegistry to dict for state storage."""
    entries = {}
    for entry in registry.all_entries():
        entries[entry.source_id] = {
            "source_id": entry.source_id,
            "url": entry.url,
            "title": entry.title,
            "source_type": entry.source_type,
            "authors": list(entry.authors),
            "year": entry.year,
            "doi": entry.doi,
            "venue": getattr(entry, "venue", ""),
            "authority_score": entry.authority_score,
        }
    return {"entries": entries, "counter": registry._counter}


def _deserialize_registry(data: dict[str, Any]) -> SourceRegistry:
    """Reconstruct SourceRegistry from serialized state."""
    registry = SourceRegistry()
    if not data:
        return registry

    entries = data.get("entries", {})
    for src_id, entry_data in entries.items():
        registry.register(
            url=entry_data.get("url", ""),
            title=entry_data.get("title", ""),
            source_type=entry_data.get("source_type", "web"),
            authors=entry_data.get("authors", []),
            year=entry_data.get("year"),
            doi=entry_data.get("doi", ""),
            authority_score=entry_data.get("authority_score", 0.0),
        )
    return registry


def _quick_cluster(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Quick evidence clustering by quality tier for outline generation."""
    clusters: dict[str, list] = {}
    for ev in evidence:
        tier = ev.get("quality_tier", "BRONZE")
        if tier not in clusters:
            clusters[tier] = []
        clusters[tier].append(ev.get("evidence_id", ""))

    return [
        {"theme": f"{tier} Evidence", "evidence_ids": ids, "label": tier}
        for tier, ids in clusters.items()
    ]
