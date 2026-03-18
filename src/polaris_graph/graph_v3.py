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
            tracer.log_event("evidence", node="scope", data={
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
            searcher=_real_searcher,
            fetcher=_real_fetcher,
            extractor=_make_real_extractor(client),
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
            tracer.log_event("evidence", node="v3_search", data={
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
            tracer.log_event("evidence", node="v3_outline", data={
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
        tracer.log_event("pipeline_end", data={
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


# ---------------------------------------------------------------------------
# Real search/fetch/extract adapters (bridge v1 functions to v3 interface)
# ---------------------------------------------------------------------------

async def _real_searcher(queries: list[dict]) -> list[dict]:
    """Execute web + academic searches using v1's search infrastructure.

    Takes v3 SearchQuery dicts, returns v1-style search result dicts.
    """
    results = []
    try:
        from src.agents.search_agent import search_serper, search_s2
        from concurrent.futures import ThreadPoolExecutor
        import asyncio

        executor = ThreadPoolExecutor(max_workers=5)
        loop = asyncio.get_event_loop()

        for q in queries[:20]:  # Cap at 20 queries
            query_text = q.get("query", "") if isinstance(q, dict) else str(q)
            pref = q.get("source_preference", "both") if isinstance(q, dict) else "both"

            if pref in ("web", "both"):
                try:
                    web_results = await loop.run_in_executor(
                        executor, search_serper, query_text, 5
                    )
                    for r in (web_results or []):
                        r["search_query"] = query_text
                        r["sub_question_id"] = q.get("sub_question_id", "")
                        results.append(r)
                except Exception as exc:
                    logger.debug("[v3 searcher] Serper failed for '%s': %s", query_text[:50], str(exc)[:100])

            if pref in ("academic", "both"):
                try:
                    from src.polaris_graph.agents.searcher import _search_openalex
                    academic = await _search_openalex(query_text, max_results=5)
                    for r in (academic or []):
                        r["search_query"] = query_text
                        r["sub_question_id"] = q.get("sub_question_id", "")
                        results.append(r)
                except Exception as exc:
                    logger.debug("[v3 searcher] Academic failed for '%s': %s", query_text[:50], str(exc)[:100])

    except Exception as exc:
        logger.warning("[v3 searcher] Search adapter failed: %s", str(exc)[:200])

    logger.info("[v3 searcher] %d results from %d queries", len(results), len(queries))
    return results


async def _real_fetcher(search_results: list[dict]) -> list[dict]:
    """Fetch content from URLs using v1's access_bypass + Jina + trafilatura.

    Takes search result dicts, returns content dicts with 'url' and 'content'.
    """
    fetched = []
    try:
        import trafilatura
        import aiohttp

        urls = []
        for r in search_results[:30]:  # Cap at 30 URLs
            url = r.get("link") or r.get("url") or r.get("openAccessPdf", {}).get("url", "")
            if url and url not in urls:
                urls.append(url)

        # Try Jina Reader first (best for article extraction)
        jina_key = os.getenv("JINA_API_KEY", "")
        for url in urls[:20]:
            try:
                content = None
                if jina_key:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f"https://r.jina.ai/{url}",
                            headers={"Authorization": f"Bearer {jina_key}", "Accept": "text/markdown"},
                            timeout=aiohttp.ClientTimeout(total=15),
                        ) as resp:
                            if resp.status == 200:
                                content = await resp.text()

                if not content or len(content) < 200:
                    # Fallback to trafilatura
                    downloaded = trafilatura.fetch_url(url)
                    if downloaded:
                        content = trafilatura.extract(downloaded) or ""

                if content and len(content) > 200:
                    # Find matching search result for metadata
                    meta = next((r for r in search_results if (r.get("link") or r.get("url", "")) == url), {})
                    fetched.append({
                        "url": url,
                        "content": content[:25000],  # Cap at 25K chars
                        "title": meta.get("title", ""),
                        "snippet": meta.get("snippet", meta.get("abstract", "")),
                        "sub_question_id": meta.get("sub_question_id", ""),
                    })
            except Exception as exc:
                logger.debug("[v3 fetcher] Failed for %s: %s", url[:60], str(exc)[:100])

    except Exception as exc:
        logger.warning("[v3 fetcher] Fetch adapter failed: %s", str(exc)[:200])

    logger.info("[v3 fetcher] Fetched %d of %d URLs", len(fetched), len(search_results))
    return fetched


def _make_real_extractor(client):
    """Create an extractor closure that uses the LLM client for evidence extraction."""

    async def _real_extractor(fetched_content: list[dict]) -> list[dict]:
        """Extract evidence from fetched content using LLM.

        Takes content dicts, returns evidence piece dicts.
        """
        import uuid
        evidence = []

        for doc in fetched_content[:20]:  # Cap at 20 documents
            content = doc.get("content", "")
            url = doc.get("url", "")
            title = doc.get("title", "")
            sq_id = doc.get("sub_question_id", "")

            if len(content) < 200:
                continue

            try:
                # Use LLM to extract atomic facts
                from src.polaris_graph.schemas import SourceAnalysis
                result = await client.generate_structured(
                    prompt=(
                        f"Source: {title}\nURL: {url}\n\n"
                        f"Content:\n{content[:10000]}\n\n"
                        "Extract 3-8 key findings as atomic facts. Each fact must include "
                        "a specific claim, a direct quote from the source, and relevance score."
                    ),
                    schema=SourceAnalysis,
                    system="Extract verifiable facts from this research source. Include exact numbers and measurements.",
                    max_tokens=4096,
                    timeout=90,
                )

                if result and hasattr(result, 'atomic_facts'):
                    for fact in result.atomic_facts[:8]:
                        ev_id = f"ev_{uuid.uuid4().hex[:8]}"
                        evidence.append({
                            "evidence_id": ev_id,
                            "statement": getattr(fact, 'statement', str(fact))[:500],
                            "direct_quote": getattr(fact, 'direct_quote', '')[:500],
                            "source_url": url,
                            "source_title": title,
                            "source_content": content[:10000],
                            "sub_question_id": sq_id,
                            "quality_tier": "SILVER",
                            "relevance_score": getattr(fact, 'relevance_score', 0.5),
                            "perspective": "Scientific",
                        })
            except Exception as exc:
                logger.debug("[v3 extractor] Failed for %s: %s", url[:60], str(exc)[:100])

        logger.info("[v3 extractor] Extracted %d evidence from %d documents", len(evidence), len(fetched_content))
        return evidence

    return _real_extractor


# Avoid import of MagicMock at module level
from unittest.mock import MagicMock
