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
import datetime
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
            tracer.log_event("evidence", node="scope", data={
                "action": "query_plan",
                "queries": update["search_queries"],
                "sub_questions": len(update["sub_questions"]),
            })
            tracer.node_end("scope")

        return update

    # -----------------------------------------------------------------------
    # Node: v3_search — delegates to v1's execute_searches + analyze_sources
    # -----------------------------------------------------------------------
    async def search_node(state: V3State) -> dict:
        """Phase 2: Delegate to v1 search + analysis (13,860 LOC, 37 quality steps).

        Builds a minimal ResearchState, calls v1's execute_searches() for
        multi-provider parallel search (Serper, S2, OpenAlex, Exa, DDG) with
        query amplification, then analyze_sources() for content fetch +
        evidence extraction + structured data + dedup + tier scoring.
        """
        if tracer:
            tracer.node_start("v3_search")

        from src.polaris_graph.agents.searcher import execute_searches
        from src.polaris_graph.agents.analyzer import analyze_sources

        # Build sub_queries from v3 search_queries (v1 expects list[str])
        search_queries = state.get("search_queries", [])
        sub_queries = []
        for sq in search_queries:
            q_text = sq.get("query", "") if isinstance(sq, dict) else str(sq)
            if q_text and q_text not in sub_queries:
                sub_queries.append(q_text)
        # Also include sub-question text as queries for broader coverage
        for sq in state.get("sub_questions", []):
            q_text = sq.get("question", "") if isinstance(sq, dict) else str(sq)
            if q_text and q_text not in sub_queries:
                sub_queries.append(q_text)

        # Build minimal ResearchState for v1 functions (TypedDict = duck-typed)
        v1_state = {
            "vector_id": state["vector_id"],
            "original_query": state["original_query"],
            "application": state.get("application", ""),
            "region": state.get("region", ""),
            "stage": 1,
            "sub_queries": sub_queries,
            "search_strategy": "broad",
            "perspective_distribution": {},
            "web_results": [],
            "academic_results": [],
            "fetched_content": [],
            "evidence": [],
            "evidence_clusters": [],
            "claims": [],
            "faithfulness_score": 0.0,
            "gaps": [],
            "gap_queries": [],
            "section_outline": [],
            "sections": [],
            "completed_sections": {},
            "bibliography": [],
            "evidence_chain": [],
            "draft_report": "",
            "final_report": "",
            "quality_metrics": None,
            "iteration_count": 0,
            "max_iterations": 1,
            "max_execution_minutes": 60,
            "needs_iteration": False,
            "converged": False,
            "convergence_reason": None,
            "status": "searching",
            "error": None,
            "timestamps": {},
            "llm_usage": {},
            "expansion_passes_used": 0,
            "quality_gate_result": "",
            "trace_summary": {},
            "agentic_search_rounds": 0,
            "agentic_total_queries": 0,
            "agentic_convergence_scores": [],
            "agentic_url_accumulator": [],
            "agentic_perspective_coverage": {},
        }

        # Step 1: Execute searches (all 6 providers, query amplification, etc.)
        try:
            search_result = await execute_searches(v1_state, client)
            v1_state.update(search_result)
            logger.info(
                "[v3 search] v1 execute_searches: %d web, %d academic results",
                len(v1_state.get("web_results", [])),
                len(v1_state.get("academic_results", [])),
            )
        except Exception as exc:
            logger.error("[v3 search] execute_searches failed: %s", str(exc)[:300])

        # Step 2: Analyze sources (fetch + extract + dedup + tier scoring)
        try:
            analyze_result = await analyze_sources(client, v1_state)
            v1_evidence = analyze_result.get("evidence", [])
            logger.info(
                "[v3 search] v1 analyze_sources: %d evidence pieces extracted",
                len(v1_evidence),
            )
        except Exception as exc:
            logger.error("[v3 search] analyze_sources failed: %s", str(exc)[:300])
            v1_evidence = []

        # Step 3: Populate evidence_store and build state update
        existing_ids = set(state.get("evidence_ids", []))
        new_ids = []
        new_meta = dict(state.get("evidence_meta", {}))

        for ev in v1_evidence:
            ev_id = ev.get("evidence_id", "")
            if not ev_id or ev_id in existing_ids:
                continue
            # Store full evidence in side-channel (NOT in LangGraph state)
            evidence_store[ev_id] = dict(ev)
            new_ids.append(ev_id)
            new_meta[ev_id] = {
                "tier": ev.get("quality_tier", "BRONZE"),
                "score": ev.get("relevance_score", 0.0),
                "source_url": ev.get("source_url", ""),
                "source_title": ev.get("source_title", ""),
                "statement": ev.get("statement", ""),
            }

        all_ids = list(state.get("evidence_ids", [])) + new_ids

        # Build reflections from evidence summaries
        reflections = list(state.get("reflections", []))
        by_source: dict[str, list] = {}
        for ev in v1_evidence[:50]:
            url = ev.get("source_url", "unknown")
            by_source.setdefault(url, []).append(ev)
        for url, evs in list(by_source.items())[:10]:
            reflections.append({
                "insight": evs[0].get("statement", "")[:300],
                "sub_question_id": evs[0].get("sub_question_id", ""),
                "evidence_ids": [e.get("evidence_id", "") for e in evs[:3]],
                "confidence": max(e.get("relevance_score", 0.5) for e in evs),
            })

        update = {
            "evidence_ids": all_ids,
            "evidence_meta": new_meta,
            "reflections": reflections,
            "search_rounds_completed": state.get("search_rounds_completed", 0) + 1,
            "convergence_score": min(0.9, len(all_ids) / max(int(os.getenv("PG_V3_MAX_EVIDENCE", "1000")), 1)),
        }

        if tracer:
            tracer.log_event("evidence", node="v3_search", data={
                "action": "accumulated",
                "count": len(all_ids),
                "new": len(new_ids),
                "gold": sum(1 for m in new_meta.values() if m.get("tier") == "GOLD"),
                "silver": sum(1 for m in new_meta.values() if m.get("tier") == "SILVER"),
                "bronze": sum(1 for m in new_meta.values() if m.get("tier") == "BRONZE"),
            })
            tracer.node_end("v3_search")

        return update

    # -----------------------------------------------------------------------
    # Node: v3_storm — multi-perspective STORM interviews
    # -----------------------------------------------------------------------
    async def storm_node(state: V3State) -> dict:
        """Phase 2.5: STORM multi-perspective interviews (Stanford arXiv:2402.14207).

        Delegates to v1's run_storm_interviews() which conducts simulated
        expert interviews with diverse personas, producing enriched evidence
        and a hierarchical outline for deeper perspective coverage.
        """
        if tracer:
            tracer.node_start("v3_storm")

        storm_enabled = os.getenv("PG_STORM_ENABLED", "0") == "1"
        if not storm_enabled:
            logger.info("[v3 storm] STORM disabled (PG_STORM_ENABLED=0)")
            if tracer:
                tracer.node_end("v3_storm")
            return {}

        from src.polaris_graph.agents.storm_interviews import run_storm_interviews

        # Build minimal ResearchState for STORM
        v1_state = {
            "vector_id": state["vector_id"],
            "original_query": state["original_query"],
            "application": state.get("application", ""),
            "region": state.get("region", ""),
            "stage": 1,
            "sub_queries": [
                sq.get("question", "") if isinstance(sq, dict) else str(sq)
                for sq in state.get("sub_questions", [])
            ],
            "web_results": [],
            "academic_results": [],
            "evidence": [],
        }

        # Populate web_results from evidence_store for STORM context
        seen_urls = set()
        for ev_id in state.get("evidence_ids", [])[:50]:
            ev = evidence_store.get(ev_id, {})
            url = ev.get("source_url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                v1_state["web_results"].append({
                    "link": url,
                    "title": ev.get("source_title", ""),
                    "snippet": ev.get("statement", "")[:300],
                })

        try:
            storm_result = await run_storm_interviews(client, v1_state)

            # Extract STORM evidence from interview-sourced results
            storm_web = storm_result.get("web_results", [])
            new_storm_ids = []
            new_meta = dict(state.get("evidence_meta", {}))

            import uuid
            for r in storm_web:
                if r.get("link") not in seen_urls:
                    ev_id = f"ev_{uuid.uuid4().hex[:8]}"
                    evidence_store[ev_id] = {
                        "evidence_id": ev_id,
                        "source_url": r.get("link", ""),
                        "source_title": r.get("title", ""),
                        "statement": r.get("snippet", "")[:500],
                        "direct_quote": "",
                        "quality_tier": "SILVER",
                        "relevance_score": 0.6,
                        "perspective": "STORM",
                        "source_type": "storm_interview",
                    }
                    new_storm_ids.append(ev_id)
                    new_meta[ev_id] = {
                        "tier": "SILVER",
                        "score": 0.6,
                        "source_url": r.get("link", ""),
                    }

            # Extract STORM perspectives for outline enrichment
            storm_perspectives = state.get("perspectives", [])
            storm_outline = storm_result.get("storm_outline", [])
            for section in storm_outline:
                title = section.get("title", "") if isinstance(section, dict) else str(section)
                if title and title not in storm_perspectives:
                    storm_perspectives.append(title)

            all_ids = list(state.get("evidence_ids", [])) + new_storm_ids

            logger.info(
                "[v3 storm] STORM: +%d evidence, %d perspectives",
                len(new_storm_ids), len(storm_perspectives),
            )

            if tracer:
                tracer.log_event("evidence", node="v3_storm", data={
                    "action": "storm_complete",
                    "new_evidence": len(new_storm_ids),
                    "perspectives": len(storm_perspectives),
                    "conversations": len(storm_result.get("storm_conversations", [])),
                })
                tracer.node_end("v3_storm")

            return {
                "evidence_ids": all_ids,
                "evidence_meta": new_meta,
                "perspectives": storm_perspectives,
            }

        except Exception as exc:
            logger.warning("[v3 storm] STORM failed (non-fatal): %s", str(exc)[:300])
            if tracer:
                tracer.node_end("v3_storm")
            return {}

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
            tracer.log_event("evidence", node="v3_outline", data={
                "action": "report_outline",
                "sections": [{"id": s.id, "title": s.title, "evidence": len(s.evidence_ids)} for s in outline.sections],
                "version": outline.version,
                "gaps": len(outline.gaps),
            })
            tracer.node_end("v3_outline")

        return update

    # -----------------------------------------------------------------------
    # Node: v3_analyze — proactive Python analysis of evidence data
    # -----------------------------------------------------------------------
    async def analyze_node(state: V3State) -> dict:
        """Phase 3.5: Proactive data analysis using Python tools.

        Runs BEFORE synthesis. Uses the analysis toolkit and code executor
        to produce statistical summaries, comparison tables, and custom
        analyses. Results are stored in evidence_store for synthesis to embed.

        This is what differentiates POLARIS from Gemini — we don't just
        search-extract-write. We ANALYZE with real Python computation.
        """
        if tracer:
            tracer.node_start("v3_analyze")

        analysis_enabled = os.getenv("PG_V3_ANALYSIS_ENABLED", "1") == "1"
        if not analysis_enabled:
            logger.info("[v3 analyze] Analysis phase disabled")
            if tracer:
                tracer.node_end("v3_analyze")
            return {}

        from src.polaris_graph.tools.analysis_toolkit import (
            statistical_summary,
            build_comparison_table,
            generate_meta_analysis_summary,
            compute_agreement_score,
        )
        from src.polaris_graph.tools.code_executor import (
            generate_and_execute_analysis,
        )

        outline = state.get("outline", {})
        sections = outline.get("sections", []) if isinstance(outline, dict) else []
        query = state["original_query"]

        # Collect ALL structured data points from evidence
        all_data_points = []
        all_statements = []
        for ev_id in state.get("evidence_ids", []):
            ev = evidence_store.get(ev_id, {})
            # Structured data from PG_STRUCTURED_DATA_EXTRACTION
            for dp in ev.get("structured_data", []):
                dp["evidence_id"] = ev_id
                dp["source_url"] = ev.get("source_url", "")
                all_data_points.append(dp)
            # Collect statements for agreement analysis
            stmt = ev.get("statement", "")
            if stmt:
                all_statements.append(stmt)

        analysis_results = []
        charts_generated = 0

        # --- Tool 1: Statistical summary across all numeric data ---
        if all_data_points:
            try:
                stats = statistical_summary(all_data_points)
                if stats.get("markdown_table"):
                    analysis_results.append({
                        "type": "statistical_summary",
                        "title": "Statistical Summary Across Studies",
                        "markdown": stats["markdown_table"],
                        "insights": stats.get("insights", []),
                        "statistics": stats.get("statistics", {}),
                    })
                    logger.info(
                        "[v3 analyze] Statistical summary: n=%d, mean=%.2f, CI=[%.2f, %.2f]",
                        stats["statistics"].get("n", 0),
                        stats["statistics"].get("mean", 0),
                        stats["statistics"].get("ci_95_lower", 0),
                        stats["statistics"].get("ci_95_upper", 0),
                    )
            except Exception as exc:
                logger.warning("[v3 analyze] Statistical summary failed: %s", str(exc)[:200])

        # --- Tool 2: Comparison table across studies ---
        if all_data_points and len(set(dp.get("source_url", "") for dp in all_data_points)) >= 2:
            try:
                table_md = build_comparison_table(all_data_points)
                if table_md and len(table_md) > 50:
                    analysis_results.append({
                        "type": "comparison_table",
                        "title": "Cross-Study Comparison",
                        "markdown": table_md,
                    })
                    logger.info("[v3 analyze] Comparison table: %d chars", len(table_md))
            except Exception as exc:
                logger.warning("[v3 analyze] Comparison table failed: %s", str(exc)[:200])

        # --- Tool 3: Meta-analysis summary ---
        if all_data_points and len(all_data_points) >= 3:
            try:
                meta_md = generate_meta_analysis_summary(all_data_points)
                if meta_md and len(meta_md) > 50:
                    analysis_results.append({
                        "type": "meta_analysis",
                        "title": "Meta-Analysis Summary",
                        "markdown": meta_md,
                    })
                    logger.info("[v3 analyze] Meta-analysis generated: %d chars", len(meta_md))
            except Exception as exc:
                logger.warning("[v3 analyze] Meta-analysis failed: %s", str(exc)[:200])

        # --- Tool 4: Source agreement analysis ---
        if len(all_statements) >= 3:
            try:
                agreement = compute_agreement_score(all_statements[:50])
                analysis_results.append({
                    "type": "agreement_analysis",
                    "title": "Source Agreement Analysis",
                    "markdown": (
                        f"**Source Agreement:** {agreement.get('consensus_strength', 'unknown')} "
                        f"(score: {agreement.get('agreement_score', 0):.2f})\n\n"
                        f"Based on pairwise comparison of {len(all_statements[:50])} evidence statements."
                    ),
                    "agreement_score": agreement.get("agreement_score", 0),
                })
            except Exception as exc:
                logger.warning("[v3 analyze] Agreement analysis failed: %s", str(exc)[:200])

        # --- Tool 5: LLM-driven custom analysis (code executor) ---
        code_exec_enabled = os.getenv("PG_V3_CODE_EXEC_ENABLED", "1") == "1"
        if code_exec_enabled and all_data_points and client:
            try:
                custom_result = await asyncio.wait_for(
                    generate_and_execute_analysis(
                        client=client,
                        evidence_data=all_data_points[:30],
                        analysis_question=(
                            f"Analyze the key patterns and relationships in this research data about: {query}. "
                            "Compute correlations, identify trends, and create a visualization."
                        ),
                        research_context=query,
                    ),
                    timeout=90,
                )
                if custom_result.get("success"):
                    result_data = custom_result.get("result", {})
                    if result_data:
                        analysis_results.append({
                            "type": "custom_analysis",
                            "title": "Computational Analysis",
                            "markdown": result_data.get("summary", str(result_data)[:1000]),
                        })
                    for chart in custom_result.get("charts", []):
                        charts_generated += 1
                        analysis_results.append({
                            "type": "chart",
                            "title": chart.get("title", "Analysis Chart"),
                            "image_base64": chart.get("image_base64", ""),
                        })
                    logger.info(
                        "[v3 analyze] Custom analysis: success, %d charts, %.1fs",
                        len(custom_result.get("charts", [])),
                        custom_result.get("execution_time_seconds", 0),
                    )
                else:
                    logger.warning(
                        "[v3 analyze] Custom analysis failed: %s",
                        custom_result.get("error", "unknown")[:200],
                    )
            except Exception as exc:
                logger.warning("[v3 analyze] Code executor failed: %s", str(exc)[:200])

        # Store analysis results in evidence_store for synthesis to find
        if analysis_results:
            import uuid
            for result in analysis_results:
                analysis_id = f"analysis_{uuid.uuid4().hex[:8]}"
                evidence_store[analysis_id] = {
                    "evidence_id": analysis_id,
                    "type": "analysis",
                    "analysis_type": result["type"],
                    "title": result.get("title", ""),
                    "markdown": result.get("markdown", ""),
                    "image_base64": result.get("image_base64", ""),
                    "insights": result.get("insights", []),
                    "statistics": result.get("statistics", {}),
                }

        logger.info(
            "[v3 analyze] Analysis phase complete: %d results, %d charts, %d data points processed",
            len(analysis_results), charts_generated, len(all_data_points),
        )

        if tracer:
            tracer.log_event("evidence", node="v3_analyze", data={
                "action": "analysis_complete",
                "results_count": len(analysis_results),
                "charts_generated": charts_generated,
                "data_points_processed": len(all_data_points),
                "statements_analyzed": len(all_statements),
                "analysis_types": [r["type"] for r in analysis_results],
            })
            tracer.node_end("v3_analyze")

        return {}  # Analysis stored in evidence_store side-channel

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
                tracer.log_event("llm_call", node="v3_write_section", data={
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
            tracer.log_event("evidence", node="v3_assemble", data={
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
    graph.add_node("v3_storm", storm_node)
    graph.add_node("v3_outline", outline_node)
    graph.add_node("v3_analyze", analyze_node)
    graph.add_node("v3_write_section", synthesize_node)
    graph.add_node("v3_assemble", assemble_node)

    # Edges: scope → search → storm → outline → [gap_check] → analyze → synthesize → assemble
    graph.add_edge(START, "scope")
    graph.add_edge("scope", "v3_search")
    graph.add_edge("v3_search", "v3_storm")
    graph.add_edge("v3_storm", "v3_outline")
    graph.add_conditional_edges(
        "v3_outline",
        _should_search_gaps,
        {
            "v3_search": "v3_search",
            "v3_write_section": "v3_analyze",
        },
    )
    graph.add_edge("v3_analyze", "v3_write_section")
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
    started_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Initialize tracer
    tracer = None
    try:
        from src.polaris_graph.tracing import PipelineTracer
        tracer = PipelineTracer(vector_id)
        tracer.log_event("pipeline_start", data={
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
            "started": started_at,
            "completed": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
        tracer.log_event("pipeline_end", data={
            "status": output["status"],
            "total_words": output.get("quality_metrics", {}).get("word_count", 0),
            "total_citations": output.get("quality_metrics", {}).get("citation_count", 0),
            "faithfulness_score": output.get("quality_metrics", {}).get("faithfulness_pct", 0),
            "total_cost_usd": getattr(getattr(client, '_usage_tracker', None), 'total_cost', 0),
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


# Note: Old _real_searcher/_real_fetcher/_make_real_extractor stubs removed.
# Search now delegates directly to v1's execute_searches + analyze_sources
# inside the search_node closure (13,860 LOC, 37 quality steps).
