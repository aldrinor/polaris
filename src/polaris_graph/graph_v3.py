"""v3 Pipeline Graph — 5-phase deep research with question-driven search.

Graph topology:
    START → scope → v3_search → v3_outline → [gap_check] → v3_write_section → v3_assemble → END
                       ↑                          |
                       └── gap_search ←── "gaps" ──┘

Evidence content stored in side-channel dict (evidence_store), NOT in
LangGraph state. Prevents OOM at >1000 evidence pieces.

All node functions are closures capturing `client` and `evidence_store`.
This follows v1's proven pattern from graph.py.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Callable, Optional

from langgraph.graph import END, START, StateGraph

from src.polaris_graph.state_v3 import V3State, create_v3_state
from src.polaris_graph.contracts_v3 import (
    LiveOutline,
    ScopeOutput,
    V3_NODE_NAMES,
)

logger = logging.getLogger("polaris_graph")

_MAX_GAP_SEARCHES = int(os.getenv("PG_V3_MAX_GAP_SEARCHES", "2"))


# ---------------------------------------------------------------------------
# Conditional edge: should we search for more evidence to fill gaps?
# ---------------------------------------------------------------------------

def _should_search_gaps(state: dict) -> str:
    """Route after outline: search more if gaps exist and cap not reached."""
    gaps = state.get("gaps", [])
    gap_searches_done = state.get("gap_searches_done", 0)
    status = state.get("status", "running")

    if status != "running":
        return "v3_write_section"

    if gaps and gap_searches_done < _MAX_GAP_SEARCHES:
        logger.info(
            "[v3 graph] Outline has %d gaps, gap search %d/%d — routing to search",
            len(gaps), gap_searches_done + 1, _MAX_GAP_SEARCHES,
        )
        return "v3_search"

    return "v3_write_section"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------

def build_v3_graph(
    client=None,
    evidence_store: Optional[dict] = None,
    tracer=None,
):
    """Build the v3 LangGraph StateGraph.

    Args:
        client: OpenRouterClient (or mock). If None, created from env.
        evidence_store: Side-channel dict for evidence content. If None, created.
        tracer: PipelineTracer for JSONL events. If None, events are logged only.

    Returns:
        Compiled LangGraph ready for .invoke() or .astream().
    """
    if evidence_store is None:
        evidence_store = {}

    # -----------------------------------------------------------------------
    # Node: scope
    # -----------------------------------------------------------------------
    async def scope_node(state: V3State) -> dict:
        """Phase 1: Decompose query into sub-questions."""
        if tracer:
            tracer.node_start("scope")

        from src.polaris_graph.nodes.scope import run_scope

        result = await run_scope(
            client=client,
            query=state["original_query"],
            application=state["application"],
            region=state["region"],
            research_brief=state.get("research_brief", ""),
        )

        update = {
            "sub_questions": [sq.model_dump() for sq in result.sub_questions],
            "perspectives": result.perspectives,
            "search_queries": [q.model_dump() for q in result.search_queries],
            "complexity": result.complexity,
        }

        if tracer:
            tracer.emit("evidence", node="scope", data={
                "action": "query_plan",
                "queries": update["search_queries"],
                "sub_questions": len(update["sub_questions"]),
            })
            tracer.node_end("scope")

        return update

    # -----------------------------------------------------------------------
    # Node: v3_search
    # -----------------------------------------------------------------------
    async def search_node(state: V3State) -> dict:
        """Phase 2: Targeted search per sub-question."""
        if tracer:
            tracer.node_start("v3_search")

        from src.polaris_graph.nodes.search import run_search_phase

        scope = ScopeOutput.model_validate({
            "sub_questions": state["sub_questions"],
            "perspectives": state["perspectives"],
            "search_queries": state.get("search_queries", []),
            "complexity": state.get("complexity", "moderate"),
        })

        # Compute time budget (35% of total, configurable)
        search_budget_pct = float(os.getenv("PG_V3_SEARCH_BUDGET_PCT", "35"))
        total_budget = float(os.getenv("PG_V3_TOTAL_BUDGET_SECONDS", "3600"))
        search_budget = total_budget * search_budget_pct / 100

        result = await run_search_phase(
            client=client,
            scope=scope,
            evidence_store=evidence_store,
            time_budget_seconds=search_budget,
        )

        # Merge new evidence IDs with existing
        existing_ids = state.get("evidence_ids", [])
        new_ids = result.get("evidence_ids", [])
        all_ids = existing_ids + [eid for eid in new_ids if eid not in set(existing_ids)]

        # Merge evidence metadata
        existing_meta = dict(state.get("evidence_meta", {}))
        for eid in new_ids:
            if eid in evidence_store and eid not in existing_meta:
                ev = evidence_store[eid]
                existing_meta[eid] = {
                    "tier": ev.get("quality_tier", "BRONZE"),
                    "score": ev.get("relevance_score", 0.0),
                    "source_url": ev.get("source_url", ""),
                }

        update = {
            "evidence_ids": all_ids,
            "evidence_meta": existing_meta,
            "reflections": state.get("reflections", []) + result.get("reflections", []),
            "search_rounds_completed": state.get("search_rounds_completed", 0) + result.get("search_rounds_completed", 0),
            "convergence_score": result.get("convergence_score", 0.0),
        }

        if tracer:
            tracer.emit("evidence", node="v3_search", data={
                "action": "accumulated",
                "count": len(all_ids),
                "new": len(new_ids),
                "gold": sum(1 for m in existing_meta.values() if m.get("tier") == "GOLD"),
                "silver": sum(1 for m in existing_meta.values() if m.get("tier") == "SILVER"),
                "bronze": sum(1 for m in existing_meta.values() if m.get("tier") == "BRONZE"),
            })
            tracer.node_end("v3_search")

        return update

    # -----------------------------------------------------------------------
    # Node: v3_outline
    # -----------------------------------------------------------------------
    async def outline_node(state: V3State) -> dict:
        """Phase 3: Generate or refine the living outline."""
        if tracer:
            tracer.node_start("v3_outline")

        from src.polaris_graph.nodes.outline import (
            generate_outline,
            refine_outline,
            _detect_gaps,
        )
        from src.polaris_graph.contracts_v3 import SubQuestion, Reflection

        sub_questions = [SubQuestion.model_validate(sq) for sq in state["sub_questions"]]
        reflections = [Reflection.model_validate(r) for r in state.get("reflections", [])]

        if state.get("outline_version", 0) == 0:
            # First outline generation
            outline = await generate_outline(
                client=client,
                query=state["original_query"],
                sub_questions=sub_questions,
                reflections=reflections,
                evidence_ids=state["evidence_ids"],
                evidence_meta=state.get("evidence_meta", {}),
            )
        else:
            # Refinement
            current = LiveOutline.model_validate(state["outline"])
            outline = await refine_outline(
                client=client,
                current_outline=current,
                new_reflections=reflections[-10:],  # Last 10 reflections
                evidence_ids=state["evidence_ids"],
                evidence_meta=state.get("evidence_meta", {}),
                query=state["original_query"],
            )

        update = {
            "outline": outline.model_dump(),
            "outline_version": outline.version,
            "gaps": [g.model_dump() for g in outline.gaps],
            "gap_searches_done": state.get("gap_searches_done", 0) + (
                1 if state.get("outline_version", 0) > 0 and state.get("gaps", []) else 0
            ),
        }

        if tracer:
            tracer.emit("evidence", node="v3_outline", data={
                "action": "report_outline",
                "sections": [{"id": s.id, "title": s.title, "evidence": len(s.evidence_ids)} for s in outline.sections],
                "version": outline.version,
                "gaps": len(outline.gaps),
            })
            tracer.node_end("v3_outline")

        return update

    # -----------------------------------------------------------------------
    # Node: v3_write_section
    # -----------------------------------------------------------------------
    async def synthesize_node(state: V3State) -> dict:
        """Phase 4: Sequential section writing with critic."""
        if tracer:
            tracer.node_start("v3_write_section")

        from src.polaris_graph.nodes.synthesize import run_synthesis_phase

        outline = LiveOutline.model_validate(state["outline"])

        synth_budget_pct = float(os.getenv("PG_V3_SYNTH_BUDGET_PCT", "40"))
        total_budget = float(os.getenv("PG_V3_TOTAL_BUDGET_SECONDS", "3600"))
        synth_budget = total_budget * synth_budget_pct / 100

        result = await run_synthesis_phase(
            client=client,
            outline=outline,
            evidence_store=evidence_store,
            query=state["original_query"],
            time_budget_seconds=synth_budget,
        )

        sections = result.get("sections", [])

        if tracer:
            for section in sections:
                tracer.emit("llm_call", node="v3_write_section", data={
                    "action": "section_write",
                    "call_type": "section_write",
                    "section_id": section.section_id,
                    "title": section.title,
                    "content": section.content[:500],
                    "word_count": section.word_count,
                    "evidence_count": len(section.evidence_ids_used),
                })
            tracer.node_end("v3_write_section")

        return {
            "completed_sections": [s.model_dump() for s in sections],
            "used_evidence_ids": list(result.get("used_evidence_ids", set())),
            "status": result.get("status", "completed"),
        }

    # -----------------------------------------------------------------------
    # Node: v3_assemble
    # -----------------------------------------------------------------------
    async def assemble_node(state: V3State) -> dict:
        """Phase 5: Final assembly."""
        if tracer:
            tracer.node_start("v3_assemble")

        from src.polaris_graph.nodes.assemble import run_assemble_phase
        from src.polaris_graph.contracts_v3 import VerifiedSectionDraft

        sections = [
            VerifiedSectionDraft.model_validate(s)
            for s in state.get("completed_sections", [])
        ]

        outline = state.get("outline", {})
        expected = len(outline.get("sections", [])) if outline else None

        result = await run_assemble_phase(
            sections=sections,
            evidence_store=evidence_store,
            query=state["original_query"],
            vector_id=state["vector_id"],
            expected_sections=expected,
        )

        if tracer:
            # CRITICAL: report_assembled triggers frontend completion
            tracer.emit("evidence", node="v3_assemble", data={
                "action": "report_assembled",
                "full_report": result.get("final_report", ""),
                "bibliography": result.get("bibliography", []),
                "section_titles": [s.get("title", "") for s in result.get("sections", [])],
                "count": len(result.get("evidence", [])),
                "total_citations": result.get("quality_metrics", {}).get("citation_count", 0),
            })
            tracer.node_end("v3_assemble")

        return {
            "final_report": result.get("final_report", ""),
            "bibliography": result.get("bibliography", []),
            "quality_metrics": result.get("quality_metrics", {}),
            "status": result.get("status", "completed"),
        }

    # -----------------------------------------------------------------------
    # Build the graph
    # -----------------------------------------------------------------------
    graph = StateGraph(V3State)

    graph.add_node("scope", scope_node)
    graph.add_node("v3_search", search_node)
    graph.add_node("v3_outline", outline_node)
    graph.add_node("v3_write_section", synthesize_node)
    graph.add_node("v3_assemble", assemble_node)

    # Edges
    graph.add_edge(START, "scope")
    graph.add_edge("scope", "v3_search")
    graph.add_edge("v3_search", "v3_outline")
    graph.add_conditional_edges(
        "v3_outline",
        _should_search_gaps,
        {
            "v3_search": "v3_search",
            "v3_write_section": "v3_write_section",
        },
    )
    graph.add_edge("v3_write_section", "v3_assemble")
    graph.add_edge("v3_assemble", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Entry point (v1-compatible signature)
# ---------------------------------------------------------------------------

async def build_and_run_v3(
    vector_id: str,
    query: str,
    application: str = "",
    region: str = "",
    stage: int = 1,
    max_iterations: int = 3,
    max_execution_minutes: int = 60,
    resume: bool = False,
    enable_dashboard: bool = True,
    document_ids: Optional[list[str]] = None,
    steer_callback: Optional[Callable] = None,
    research_brief: str = "",
) -> dict:
    """v3 pipeline entry point. Signature matches v1 for live_server compatibility.

    Returns a dict compatible with V3ResultOutput schema.
    """
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    # Initialize LLM client
    client = OpenRouterClient()

    # Side-channel evidence store (NOT in LangGraph state)
    evidence_store: dict = {}

    # Set total budget
    os.environ["PG_V3_TOTAL_BUDGET_SECONDS"] = str(max_execution_minutes * 60)

    # Initialize tracer
    tracer = None
    try:
        from src.polaris_graph.tracing import PipelineTracer
        tracer = PipelineTracer(vector_id)
        tracer.emit("pipeline_start", data={
            "query": query,
            "application": application,
            "region": region,
            "max_iterations": max_iterations,
            "budget_usd": float(os.getenv("OPENROUTER_BUDGET_USD", "50")),
            "vector_id": vector_id,
            "graph_version": "v3",
        })
    except Exception as exc:
        logger.warning("[v3 graph] Tracer init failed: %s", str(exc)[:100])

    # Build graph
    graph = build_v3_graph(
        client=client,
        evidence_store=evidence_store,
        tracer=tracer,
    )

    # Create initial state
    initial_state = create_v3_state(
        vector_id=vector_id,
        query=query,
        application=application,
        region=region,
        research_brief=research_brief,
    )

    # Document upload injection
    if document_ids:
        try:
            from src.polaris_graph.document_ingester import DocumentIngester
            ingester = DocumentIngester()
            for doc_id in document_ids:
                doc_evidence = ingester.ingest(doc_id)
                for ev in doc_evidence:
                    evidence_store[ev["evidence_id"]] = ev
                    initial_state["evidence_ids"].append(ev["evidence_id"])
        except Exception as exc:
            logger.warning("[v3 graph] Document upload failed: %s", str(exc)[:200])

    # Execute with timeout
    start_time = time.monotonic()
    try:
        result_state = await asyncio.wait_for(
            graph.ainvoke(initial_state),
            timeout=max_execution_minutes * 60 + 30,  # +30s grace
        )
    except asyncio.TimeoutError:
        logger.warning("[v3 graph] Pipeline timed out at %d minutes", max_execution_minutes)
        result_state = initial_state
        result_state["status"] = "partial"
    except Exception as exc:
        logger.error("[v3 graph] Pipeline failed: %s", str(exc)[:500])
        result_state = initial_state
        result_state["status"] = "failed"

    elapsed = time.monotonic() - start_time

    # Build output
    output = {
        "vector_id": vector_id,
        "original_query": query,
        "status": result_state.get("status", "completed"),
        "final_report": result_state.get("final_report", ""),
        "bibliography": result_state.get("bibliography", []),
        "quality_metrics": result_state.get("quality_metrics", {}),
        "sections": result_state.get("completed_sections", []),
        "evidence": list(evidence_store.values()),
        "claims": [],
        "iteration_count": result_state.get("search_rounds_completed", 0),
        "timestamps": {
            "started": "",
            "completed": "",
            "duration_seconds": round(elapsed, 1),
        },
        "trace_summary": {},
        "v3_metadata": {
            "sub_questions": result_state.get("sub_questions", []),
            "outline_version": result_state.get("outline_version", 0),
            "convergence_score": result_state.get("convergence_score", 0.0),
            "gap_searches_done": result_state.get("gap_searches_done", 0),
        },
    }

    # Emit pipeline_end trace event
    if tracer:
        tracer.emit("pipeline_end", data={
            "status": output["status"],
            "total_words": output.get("quality_metrics", {}).get("word_count", 0),
            "total_citations": output.get("quality_metrics", {}).get("citation_count", 0),
            "faithfulness_score": output.get("quality_metrics", {}).get("faithfulness_pct", 0),
            "total_cost_usd": getattr(client, '_usage_tracker', MagicMock()).total_cost if hasattr(client, '_usage_tracker') else 0,
            "elapsed_seconds": round(elapsed, 1),
        })

    # Save output to disk
    output_dir = Path(os.getenv("PG_OUTPUT_DIR", "outputs/polaris_graph"))
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{vector_id}.json"
    try:
        import json
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False, default=str)
        logger.info("[v3 graph] Output saved: %s", output_path)
    except Exception as exc:
        logger.warning("[v3 graph] Failed to save output: %s", str(exc)[:200])

    # Save report markdown
    report_path = output_dir / f"{vector_id}_report.md"
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(output.get("final_report", ""))
        logger.info("[v3 graph] Report saved: %s", report_path)
    except Exception:
        pass

    return output


# Avoid import of MagicMock at module level
from unittest.mock import MagicMock
