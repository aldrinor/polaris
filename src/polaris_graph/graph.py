"""
polaris graph — LangGraph workflow.

9-node graph:
1. plan: Generate 50 sub-queries
2. search: Execute web + academic + Exa searches
3. storm_interviews: AREA-3 multi-perspective STORM research (opt-in)
4. analyze: Fetch content, extract atomic facts
5. verify: Verify ALL claims against evidence
6. deepen_evidence: Citation chasing + mechanism search (opt-in, PG_EVIDENCE_DEEPENER=1)
7. evaluate: Gap analysis, decide whether to iterate
8. synthesize: Cluster → outline → sections → citations → report
9. search_gaps: FIX-307 targeted gap search (bypasses planner)
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
from dotenv import load_dotenv
from langgraph.graph import END, StateGraph

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.state import ResearchState, create_initial_state
from src.polaris_graph.tracing import PipelineTracer, get_tracer

load_dotenv()

logger = logging.getLogger(__name__)

# Output directory
OUTPUT_DIR = Path(os.getenv("PG_OUTPUT_DIR", "outputs/polaris_graph"))


def build_graph() -> StateGraph:
    """Build the polaris graph LangGraph workflow."""
    from src.polaris_graph.agents.planner import plan_queries
    from src.polaris_graph.agents.searcher import execute_searches
    from src.polaris_graph.agents.analyzer import analyze_sources
    from src.polaris_graph.agents.verifier import verify_claims
    from src.polaris_graph.agents.synthesizer import (
        analyze_gaps,
        synthesize_report,
    )
    from src.polaris_graph.agents.evidence_deepener import deepen_evidence

    # Create shared client (will be set in state via closure)
    # FIX-QM10: _snapshot stores accumulated state for timeout recovery.
    # When asyncio.wait_for() cancels ainvoke(), the LangGraph internal state
    # is lost. Each node shadows its key results here so synthesize_report
    # can run with real evidence even after a timeout.
    client_holder: dict[str, Any] = {"_snapshot": {}}

    async def _plan(state: ResearchState) -> dict:
        """Plan node: generate sub-queries."""
        from src.polaris_graph.state import PG_AGENTIC_SEARCH_ENABLED

        client = client_holder["client"]
        tracer = get_tracer()
        if tracer:
            tracer.node_start("plan", iteration=state.get("iteration_count", 0))
        state["timestamps"]["plan_start"] = _now()

        # Agentic loop: use seed planner on first iteration
        if PG_AGENTIC_SEARCH_ENABLED and state.get("iteration_count", 0) == 0:
            from src.polaris_graph.agents.planner import plan_seed_queries
            result = await plan_seed_queries(client, state)
        else:
            result = await plan_queries(client, state)
        result["iteration_count"] = state.get("iteration_count", 0) + 1
        result["timestamps"] = {
            **state.get("timestamps", {}),
            "plan_end": _now(),
        }
        if tracer:
            tracer.node_end("plan", query_count=len(result.get("sub_queries", [])),
                search_strategy=result.get("search_strategy", ""),
                perspective_coverage=result.get("perspective_distribution", {}))

        # MEM-2b: Query session feedback for best strategies
        feedback_enabled = os.getenv("PG_SESSION_FEEDBACK_ENABLED", "0") == "1"
        if feedback_enabled:
            try:
                from src.polaris_graph.memory.session_feedback import get_best_strategies
                best = await get_best_strategies(min_evidence=3)
                if best:
                    logger.info(
                        "[polaris graph] MEM-2b: Top strategies from memory: %s",
                        [(s["query_text"][:50], s["composite_score"]) for s in best[:3]],
                    )
                    result["memory_best_strategies"] = best[:10]
            except Exception as exc:
                logger.debug("[polaris graph] MEM-2b: strategy query failed: %s", str(exc)[:200])

        # MEM-3b: Query LTM for relevant prior knowledge
        ltm_enabled = os.getenv("PG_CROSS_VECTOR_LTM_ENABLED", "0") == "1"
        if ltm_enabled:
            try:
                from src.polaris_graph.memory.cross_vector import query_ltm
                prior = query_ltm(query=state["original_query"], max_results=10)
                if prior:
                    logger.info("[polaris graph] MEM-3b: Found %d prior knowledge from LTM", len(prior))
                    result["memory_ltm_prior_count"] = len(prior)
                    # Sprint 1B: Pass actual prior knowledge to planner
                    result["memory_ltm_priors"] = prior
            except Exception as exc:
                logger.debug("[polaris graph] MEM-3b: LTM query failed: %s", str(exc)[:200])

        return result

    async def _search(state: ResearchState) -> dict:
        """Search node: execute all searches."""
        client = client_holder["client"]
        tracer = get_tracer()
        if tracer:
            tracer.node_start("search", query_count=len(state.get("sub_queries", [])))
        state["timestamps"]["search_start"] = _now()
        result = await execute_searches(state, client=client)
        result["timestamps"] = {
            **state.get("timestamps", {}),
            "search_end": _now(),
        }
        if tracer:
            tracer.node_end(
                "search",
                web_results=len(result.get("web_results", [])),
                academic_results=len(result.get("academic_results", [])),
            )
        return result

    async def _storm_interviews(state: ResearchState) -> dict:
        """STORM interview node: multi-perspective research enrichment.

        AREA-3: Runs Stanford STORM interviews between search and analyze.
        Opt-in via PG_STORM_ENABLED=1 in .env. When disabled, passes through.
        """
        from src.polaris_graph.agents.storm_interviews import (
            PG_STORM_ENABLED,
            run_storm_interviews,
        )

        if not PG_STORM_ENABLED:
            return {}  # No-op pass-through

        # Only run STORM on first iteration (interviews don't need to repeat)
        if state.get("iteration_count", 0) > 1:
            logger.info("[polaris graph] STORM: Skipping on iteration %d", state.get("iteration_count", 0))
            return {}

        client = client_holder["client"]
        tracer = get_tracer()
        if tracer:
            tracer.node_start("storm_interviews")

        logger.info("[polaris graph] STORM: Starting multi-perspective interviews")
        try:
            result = await run_storm_interviews(
                client=client,
                state=state,
            )
            if tracer:
                tracer.node_end(
                    "storm_interviews",
                    conversations=len(result.get("storm_conversations", [])),
                    outline_sections=len(result.get("storm_outline", [])),
                )
            return result
        except Exception as exc:
            logger.warning(
                "[polaris graph] STORM interviews failed: %s — continuing without",
                str(exc)[:200],
            )
            if tracer:
                tracer.node_end("storm_interviews", result="failed", error=str(exc)[:200])
            return {}

    async def _analyze(state: ResearchState) -> dict:
        """Analyze node: fetch and extract evidence."""
        client = client_holder["client"]
        tracer = get_tracer()
        if tracer:
            tracer.node_start(
                "analyze",
                sources_to_analyze=len(state.get("web_results", [])) + len(state.get("academic_results", [])),
            )
        state["timestamps"]["analyze_start"] = _now()

        # Progressive snapshot callback — saves evidence as each batch completes
        # so timeout recovery can access partial results (FIX-QM10b)
        def _on_evidence_progress(evidence_so_far: list, fetched_so_far: list) -> None:
            from src.polaris_graph.state import PG_CONTENT_PER_SOURCE
            client_holder["_snapshot"]["evidence"] = list(evidence_so_far)
            content_cap = PG_CONTENT_PER_SOURCE  # FIX-CAP1: align with analyzer
            client_holder["_snapshot"]["fetched_content"] = [
                {
                    "url": f.get("url", ""),
                    "title": f.get("title", ""),
                    "content": f.get("content", "")[:content_cap] if content_cap > 0 else "",
                }
                for f in fetched_so_far
            ]

        # DEEP-FIX: Merge deepened_papers into academic_results BEFORE
        # analyze_sources() runs. Without this, the search node overwrites
        # academic_results on iteration 2, wiping out deepened papers.
        # By merging here, we guarantee the analyzer processes them.
        deepened = state.get("deepened_papers", [])
        if deepened:
            existing_academic = list(state.get("academic_results", []))
            existing_urls = {r.get("url", "") for r in existing_academic}
            new_from_deepen = [
                p for p in deepened
                if p.get("url", "") and p.get("url", "") not in existing_urls
            ]
            if new_from_deepen:
                state["academic_results"] = existing_academic + new_from_deepen
                logger.info(
                    "[polaris graph] DEEP-FIX: Injected %d deepened papers "
                    "into academic_results for analysis (%d total)",
                    len(new_from_deepen),
                    len(state["academic_results"]),
                )

                # FIX-B5: Inject deepener's full_text into the SQLite
                # content cache so the analyzer's _fetch_all_content()
                # finds it via get_cached_content() and skips re-fetching.
                # State["fetched_content"] doesn't work — analyzer reads
                # from SQLite cache, not state.
                try:
                    from src.polaris_graph.memory.content_cache import cache_content
                    _cached_count = 0
                    for paper in new_from_deepen:
                        ft = paper.get("full_text", "")
                        purl = paper.get("url", "")
                        if ft and purl and len(ft) > 500:
                            await cache_content(
                                url=purl,
                                content=ft[:25000],
                                title=paper.get("title", ""),
                                fetch_method="deepener",
                            )
                            _cached_count += 1
                    if _cached_count:
                        logger.info(
                            "[polaris graph] FIX-B5: Cached %d deepened paper "
                            "full texts in content_cache SQLite",
                            _cached_count,
                        )
                except Exception as _cache_exc:
                    logger.debug(
                        "[polaris graph] FIX-B5: Content caching failed: %s",
                        str(_cache_exc)[:200],
                    )

        result = await analyze_sources(
            client, state, on_evidence_progress=_on_evidence_progress,
        )
        # FIX-300: ACCUMULATE evidence across iterations (not replace)
        existing_evidence = list(state.get("evidence", []))
        new_evidence = result.get("evidence", [])
        existing_ids = {e.get("evidence_id") for e in existing_evidence}
        unique_new = [e for e in new_evidence if e.get("evidence_id") not in existing_ids]
        result["evidence"] = existing_evidence + unique_new
        if existing_evidence:
            logger.info(
                "[polaris graph] FIX-300: Accumulated evidence: %d existing + %d new = %d total",
                len(existing_evidence),
                len(unique_new),
                len(result["evidence"]),
            )

        # RC-1: ACCUMULATE fetched_content across iterations (not replace).
        # Without this, content from earlier iterations is lost and verifier
        # sees empty url_content_map for those sources.
        existing_fetched = list(state.get("fetched_content", []))
        new_fetched = result.get("fetched_content", [])
        if existing_fetched and new_fetched:
            existing_urls = {f.get("url") for f in existing_fetched}
            unique_fetched = [f for f in new_fetched if f.get("url") not in existing_urls]
            result["fetched_content"] = existing_fetched + unique_fetched
            logger.info(
                "[polaris graph] RC-1: Accumulated fetched_content: "
                "%d existing + %d new = %d total",
                len(existing_fetched),
                len(unique_fetched),
                len(result["fetched_content"]),
            )

        # GEMINI-ARCH: ACCUMULATE structured_data across iterations (not replace).
        # Without this, structured data from earlier iterations is lost and
        # synthesizer sees empty structured_data for chart/table generation.
        existing_sd = list(state.get("structured_data", []))
        new_sd = result.get("structured_data", [])
        if existing_sd and new_sd:
            # Dedup by source_url + value to avoid exact duplicates
            existing_sd_keys = {
                (d.get("source_url", ""), d.get("value", ""), d.get("entity", ""))
                for d in existing_sd
            }
            unique_sd = [
                d for d in new_sd
                if (d.get("source_url", ""), d.get("value", ""), d.get("entity", ""))
                not in existing_sd_keys
            ]
            result["structured_data"] = existing_sd + unique_sd
            logger.info(
                "[polaris graph] GEMINI-ARCH: Accumulated structured_data: "
                "%d existing + %d new = %d total",
                len(existing_sd),
                len(unique_sd),
                len(result["structured_data"]),
            )
        elif existing_sd and not new_sd:
            # Preserve existing structured data even if this iteration found none
            result["structured_data"] = existing_sd

        # IMP-4: Cross-iteration MinHash dedup on the combined pool
        if existing_evidence and unique_new:
            result["evidence"] = _cross_iteration_dedup(result["evidence"])

        # FIX-RC5a: Cap accumulated evidence to prevent unbounded growth.
        # Sort by quality tier (GOLD > SILVER > BRONZE) then relevance DESC.
        # FIX-P5: Reserve 20% of evidence slots for academic sources.
        pg_max_ev_verify = int(os.getenv("PG_MAX_EVIDENCE_FOR_VERIFY", "1500"))
        if len(result["evidence"]) > pg_max_ev_verify:
            tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
            _sort_key = lambda e: (
                tier_order.get(e.get("quality_tier", "BRONZE"), 2),
                -e.get("relevance_score", 0.0),
            )
            # FIX-P5: Split into academic vs non-academic pools
            _academic_ev = sorted(
                [e for e in result["evidence"] if e.get("source_type") == "academic"],
                key=_sort_key,
            )
            _non_academic_ev = sorted(
                [e for e in result["evidence"] if e.get("source_type") != "academic"],
                key=_sort_key,
            )
            _academic_reserve = max(1, int(pg_max_ev_verify * 0.20))
            _academic_slice = _academic_ev[:_academic_reserve]
            _remaining_slots = pg_max_ev_verify - len(_academic_slice)
            _non_academic_slice = _non_academic_ev[:_remaining_slots]
            trimmed = len(result["evidence"]) - pg_max_ev_verify
            result["evidence"] = _academic_slice + _non_academic_slice
            logger.info(
                "[polaris graph] FIX-RC5a+P5: Capped evidence at %d "
                "(removed %d lowest quality, reserved %d academic slots, got %d)",
                pg_max_ev_verify,
                trimmed,
                _academic_reserve,
                len(_academic_slice),
            )

        # MEM-2: Record source-level feedback for session learning
        feedback_enabled = os.getenv("PG_SESSION_FEEDBACK_ENABLED", "0") == "1"
        if feedback_enabled and unique_new:
            try:
                from src.polaris_graph.memory.session_feedback import record_feedback
                from collections import Counter
                session_id = state.get("vector_id", "unknown")
                source_evidence_counts = Counter(e.get("source_url", "") for e in unique_new)
                source_relevances: dict[str, list[float]] = {}
                for e in unique_new:
                    url = e.get("source_url", "")
                    source_relevances.setdefault(url, []).append(e.get("relevance_score", 0.0))
                fb_count = 0
                for url, count in source_evidence_counts.items():
                    if not url:
                        continue
                    rels = source_relevances.get(url, [0.0])
                    avg_rel = sum(rels) / max(len(rels), 1)
                    await record_feedback(
                        session_id=session_id, vector_id=session_id,
                        query_text=state.get("original_query", ""),
                        search_type="combined", source_url=url,
                        evidence_count=count, avg_relevance=round(avg_rel, 4),
                        faithfulness_contribution=0.0,
                    )
                    fb_count += 1
                if fb_count:
                    logger.info("[polaris graph] MEM-2: Recorded feedback for %d sources", fb_count)
            except Exception as exc:
                logger.debug("[polaris graph] MEM-2: feedback record failed: %s", str(exc)[:200])

        result["timestamps"] = {
            **state.get("timestamps", {}),
            "analyze_end": _now(),
        }
        if tracer:
            tracer.node_end(
                "analyze",
                evidence_count=len(result.get("evidence", [])),
            )
        # FIX-QM10: Shadow evidence and fetched_content for timeout recovery
        client_holder["_snapshot"]["evidence"] = result.get("evidence", [])
        client_holder["_snapshot"]["fetched_content"] = result.get("fetched_content", [])
        return result

    async def _verify(state: ResearchState) -> dict:
        """Verify node: verify all claims.

        FIX-RC1: Only verify NEW evidence (not previously verified).
        Keeps existing verification results from previous iterations.
        This prevents re-verifying 3000+ evidence each iteration when
        only ~600 are new — eliminates batch explosion and timeouts.
        """
        client = client_holder["client"]
        tracer = get_tracer()
        if tracer:
            tracer.node_start("verify", evidence_count=len(state.get("evidence", [])))
        state["timestamps"]["verify_start"] = _now()

        # FIX-RC1: Identify already-verified evidence from previous iterations.
        # CRITICAL: Exclude api_error claims — those evidence pieces were NOT
        # actually verified (timeout/network failure). They MUST be re-verified
        # on the next iteration. Only SUCCESSFULLY verified claims count.
        existing_claims = list(state.get("claims", []))
        successfully_verified_ids = {
            c.get("claim_id") for c in existing_claims
            if c.get("verification_method") != "api_error"
        }
        # Strip api_error claims from existing — they'll be re-verified
        api_error_claims = [
            c for c in existing_claims
            if c.get("verification_method") == "api_error"
        ]
        existing_claims_clean = [
            c for c in existing_claims
            if c.get("verification_method") != "api_error"
        ]
        if api_error_claims:
            logger.info(
                "[polaris graph] FIX-RC1: Removing %d api_error claims from "
                "existing pool — their evidence will be re-verified",
                len(api_error_claims),
            )
            existing_claims = existing_claims_clean

        all_evidence = state.get("evidence", [])
        new_evidence = [
            e for e in all_evidence
            if e.get("evidence_id") not in successfully_verified_ids
        ]

        if new_evidence:
            # FIX-PRE-V: Pre-verification relevance gate — filter out low-relevance
            # evidence BEFORE verification to save cost and time.
            # FIX-RISK-FILTER: never drop risk-axis evidence at this gate when the
            # query is about risks/adverse; it is already rare and has been
            # explicitly retained by the analyzer's risk-axis override.
            verify_relevance_gate = float(os.getenv("PG_VERIFY_RELEVANCE_GATE", "0"))
            query_l_risk = (state.get("query", "") or "").lower()
            risk_query_preverify = any(
                kw in query_l_risk
                for kw in (
                    "risk", "adverse", "harm", "safety", "side effect",
                    "side-effect", "contraindicat", "toxic", "downside",
                )
            )
            if verify_relevance_gate > 0:
                pre_filter_count = len(new_evidence)
                kept = []
                dropped_risk = 0
                for e in new_evidence:
                    rel = e.get("relevance_score", 0.5)
                    if rel >= verify_relevance_gate:
                        kept.append(e)
                    elif risk_query_preverify and (
                        e.get("risk_axis_retained") is True
                        or (e.get("fact_category", "") or "").lower() in
                        ("risk", "adverse_event", "contraindication", "safety")
                    ):
                        # Keep risk-axis evidence through the gate.
                        kept.append(e)
                    else:
                        dropped_risk += 0
                new_evidence = kept
                removed = pre_filter_count - len(new_evidence)
                if removed > 0:
                    logger.info(
                        "[polaris graph] FIX-PRE-V: Pre-verification gate removed "
                        "%d/%d evidence with relevance < %.2f (risk-axis retained)",
                        removed, pre_filter_count, verify_relevance_gate,
                    )

            # Create a modified state with only new evidence for verification
            verify_state = dict(state)
            verify_state["evidence"] = new_evidence
            result = await verify_claims(client, verify_state)

            # Merge: keep existing claims + add newly verified claims
            new_claims = result.get("claims", [])
            new_claim_ids = {c.get("claim_id") for c in new_claims}
            # Deduplicate: only add truly new claims
            unique_new = [
                c for c in new_claims
                if c.get("claim_id") not in successfully_verified_ids
            ]
            result["claims"] = existing_claims + unique_new

            # Recalculate faithfulness on the FULL claim set
            all_claims = result["claims"]
            verified_for_score = [
                c for c in all_claims
                if c.get("verification_method") != "api_error"
            ]
            faithful = sum(
                1 for c in verified_for_score if c.get("is_faithful") is True
            )
            total_verified = len(verified_for_score)
            total_all = len(all_claims)
            api_errors = total_all - total_verified
            result["faithfulness_score"] = round(
                faithful / max(total_verified, 1), 4
            )
            logger.info(
                "[polaris graph] FIX-RC1: Verified %d NEW evidence "
                "(skipped %d already verified). Combined: %d/%d faithful "
                "(%.1f%%), honest: %d/%d (%.1f%%), %d api_error",
                len(new_evidence),
                len(successfully_verified_ids),
                faithful,
                total_verified,
                faithful / max(total_verified, 1) * 100,
                faithful,
                total_all,
                faithful / max(total_all, 1) * 100,
                api_errors,
            )
        else:
            logger.info(
                "[polaris graph] FIX-RC1: No new evidence to verify, "
                "keeping %d existing claims",
                len(existing_claims),
            )
            result = {
                "claims": existing_claims,
                "faithfulness_score": state.get("faithfulness_score", -1.0),
            }

        result["timestamps"] = {
            **state.get("timestamps", {}),
            "verify_end": _now(),
        }
        if tracer:
            tracer.node_end(
                "verify",
                claims_count=len(result.get("claims", [])),
                faithfulness=result.get("faithfulness_score", -1),
            )
        # SOTA-12: Cross-reference scoring (embedding cosine similarity)
        try:
            from src.polaris_graph.agents.cross_reference import (
                compute_cross_references,
            )
            cross_ref_enabled = os.getenv("PG_CROSS_REF_ENABLED", "0") == "1"
            if cross_ref_enabled:
                evidence_for_xref = state.get("evidence", [])
                xref_groups = compute_cross_references(evidence_for_xref)
                if xref_groups:
                    result["cross_reference_groups"] = xref_groups
                    # Boost confidence of corroborated evidence
                    xref_ids = set()
                    for grp in xref_groups:
                        xref_ids.update(grp.get("evidence_ids", []))
                    for claim in result.get("claims", []):
                        if claim.get("evidence_id") in xref_ids:
                            claim["cross_referenced"] = True
                    logger.info(
                        "[polaris graph] SOTA-12: %d cross-ref groups found, "
                        "%d evidence pieces corroborated",
                        len(xref_groups), len(xref_ids),
                    )
                    # OBS-TRACE: Emission 18 — Cross-reference groups
                    if tracer:
                        tracer.evidence("verify", "cross_reference_groups", len(xref_groups),
                            corroborated=len(xref_ids),
                            groups=[{"evidence_ids": g.get("evidence_ids", [])[:5],
                                     "similarity": round(g.get("similarity", 0), 3)}
                                    for g in xref_groups[:10]])
            else:
                logger.info("[polaris graph] SOTA-12: Cross-reference DISABLED")
        except Exception as exc:
            logger.warning(
                "[polaris graph] SOTA-12: Cross-reference failed (non-fatal): %s",
                str(exc)[:200],
            )

        # FIX-051: Map NLI verification scores back to evidence pieces.
        # claim_id == evidence_id (nli_verifier.py:727-729). This makes Signal 5
        # (Factual Grounding, 20% of tier composite) active on iteration 2+.
        cross_weight = float(os.getenv("PG_NLI_CROSS_SOURCE_WEIGHT", "0.6"))
        evidence_for_enrich = state.get("evidence", [])
        claims_for_mapping = result.get("claims", [])
        enriched_count = _map_nli_scores_to_evidence(
            evidence_for_enrich, claims_for_mapping, cross_weight,
        )
        if enriched_count > 0:
            logger.info(
                "[polaris graph] FIX-051: Mapped nli_self_check_score to %d/%d "
                "evidence pieces (Signal 5 now active for re-tier)",
                enriched_count,
                len(evidence_for_enrich),
            )

        # FIX-059-N: Propagate faithfulness from claims to evidence records.
        # After claim verification, individual evidence records need is_faithful
        # and avg_faithfulness for downstream synthesis (e.g., section writers
        # can prioritize faithful evidence, quality metrics compute correctly).
        _claim_map = {
            c.get("claim_id"): c for c in result.get("claims", [])
            if c.get("claim_id")
        }
        _faith_enriched = 0
        for _ev in state.get("evidence", []):
            _eid = _ev.get("evidence_id", "")
            _claim = _claim_map.get(_eid)
            if _claim:
                _ev["is_faithful"] = _claim.get("is_faithful", False)
                _ev["nli_score"] = _claim.get("nli_score")
                _ev["avg_faithfulness"] = 1.0 if _claim.get("is_faithful") else 0.0
                _faith_enriched += 1
        if _faith_enriched > 0:
            logger.info(
                "[polaris graph] FIX-059-N: Propagated faithfulness to %d/%d "
                "evidence records from verified claims",
                _faith_enriched,
                len(state.get("evidence", [])),
            )

        # D1 (post-PG_TEST_092 audit 2026-04-14, REVERTED after stress test):
        # Initially added _assign_quality_tiers(evidence) here so sig_grounding
        # would use real NLI scores instead of the frozen 0.3 default. Offline
        # stress test on PG_TEST_092 fixture showed this inflates the GOLD
        # count from 47 -> 113 (27% -> 66%), because the GOLD threshold 0.65
        # was calibrated assuming sig_grounding=0.3. Promoting 66 SILVER
        # pieces to GOLD in bulk is worse than leaving 4 borderline pieces
        # over-tiered. Proper fix is to recalibrate thresholds (future wave)
        # or use a tier-specific signal weight. Not blocking this run.

        # FIX-051b: Return enriched evidence so LangGraph persists mutations.
        # LangGraph only merges keys present in the returned dict into state.
        # Without this, in-place mutations to state["evidence"] are silently lost.
        result["evidence"] = state.get("evidence", [])

        # FIX-QM10: Shadow claims and faithfulness for timeout recovery
        client_holder["_snapshot"]["claims"] = result.get("claims", [])
        client_holder["_snapshot"]["faithfulness_score"] = result.get("faithfulness_score", -1.0)
        return result

    async def _deepen(state: ResearchState) -> dict:
        """Deepen evidence node: chase citations, find primary studies.

        Runs between verify and evaluate. Feature-flagged via PG_EVIDENCE_DEEPENER.
        Only runs on first iteration (like STORM).

        When new papers are found:
        1. Adds them as additional academic_results for re-analysis
        2. The next iteration (plan→search→analyze→verify) will process them
        3. OR, if we're about to synthesize, they get analyzed inline
        """
        from src.polaris_graph.agents.evidence_deepener import (
            PG_EVIDENCE_DEEPENER,
        )

        if not PG_EVIDENCE_DEEPENER:
            return {}

        # Only run on first iteration
        if state.get("iteration_count", 0) > 1:
            logger.info(
                "[polaris graph] DEEPEN: Skipping on iteration %d",
                state.get("iteration_count", 0),
            )
            return {}

        client = client_holder["client"]
        tracer = get_tracer()
        state["timestamps"]["deepen_start"] = _now()

        logger.info(
            "[polaris graph] DEEPEN: Starting evidence deepening "
            "(%d evidence in pool)",
            len(state.get("evidence", [])),
        )

        try:
            result = await deepen_evidence(client, state)
        except Exception as exc:
            logger.warning(
                "[polaris graph] DEEPEN: Failed (non-fatal): %s — continuing",
                str(exc)[:300],
            )
            return {"deepener_stats": {"error": str(exc)[:300]}}

        deepened_papers = result.get("deepened_papers", [])
        deepener_stats = result.get("deepener_stats", {})

        if deepened_papers:
            # Store in deepened_papers state key. The _analyze node's
            # DEEP-FIX reads this and merges into academic_results
            # BEFORE calling analyze_sources(). This avoids two bugs:
            #   1. search node overwrites academic_results on iteration 2
            #   2. evaluate overwrites needs_iteration with its own decision
            # The deepened_papers persist in state across iterations,
            # and _analyze picks them up whenever it next runs.
            logger.info(
                "[polaris graph] DEEPEN: Found %d new papers — "
                "stored in deepened_papers for analyze to process",
                len(deepened_papers),
            )

        result["deepened_papers"] = deepened_papers
        result["deepener_stats"] = deepener_stats
        result["timestamps"] = {
            **state.get("timestamps", {}),
            "deepen_end": _now(),
        }

        # Shadow for timeout recovery
        if deepened_papers:
            client_holder["_snapshot"]["deepened_papers"] = deepened_papers

        return result

    async def _evaluate(state: ResearchState) -> dict:
        """Evaluate node: gap analysis and iteration decision."""
        client = client_holder["client"]
        tracer = get_tracer()
        if tracer:
            tracer.node_start("evaluate", iteration=state.get("iteration_count", 0))
        result = await analyze_gaps(client, state)
        # FIX-H15: Validate that analyze_gaps returned needs_iteration
        if "needs_iteration" not in result:
            logger.error(
                "[polaris graph] FIX-H15: analyze_gaps() did not return "
                "'needs_iteration'. Setting False as safe fallback."
            )
            result["needs_iteration"] = False

        # DEEP-FIX-2: Force iteration when deepened_papers exist but
        # haven't been processed yet. Without this, the LLM gap analysis
        # might say "looks good" and skip to synthesize, wasting all the
        # papers the deepener found.
        deepened = state.get("deepened_papers", [])
        iteration = state.get("iteration_count", 0)
        if deepened and iteration <= 1 and not result.get("needs_iteration"):
            logger.info(
                "[polaris graph] DEEP-FIX-2: Forcing iteration to process "
                "%d deepened papers (evaluate said no gaps, overriding)",
                len(deepened),
            )
            result["needs_iteration"] = True

        if tracer:
            tracer.node_end(
                "evaluate",
                needs_iteration=result.get("needs_iteration", False),
                gap_count=len(result.get("gaps", [])),
                evidence_delta=len(state.get("evidence", [])) - len(state.get("claims", [])),
                faithfulness=state.get("faithfulness_score", 0.0),
            )
        # OBS-ITER: Emit full iteration decision rationale
        if tracer:
            tracer.iteration_decision(
                iteration=state.get("iteration_count", 0),
                decision="iterate" if result.get("needs_iteration", False) else "synthesize",
                rationale={
                    "needs_iteration": result.get("needs_iteration", False),
                    "faithfulness_score": state.get("faithfulness_score", 0.0),
                    "evidence_count": len(state.get("evidence", [])),
                    "gap_count": len(result.get("gaps", [])),
                    "gaps": [g[:200] if isinstance(g, str) else str(g)[:200] for g in result.get("gaps", [])[:5]],
                },
            )
        # D2: Drain steering directives and inject as priority gap queries
        steer_cb = client_holder.get("steer_callback")
        if steer_cb:
            directives = steer_cb()
            if directives:
                logger.info(
                    "[polaris graph] D2 Steering: %d directives received",
                    len(directives),
                )
                existing_gaps = result.get("gap_queries", [])
                result["gap_queries"] = directives + existing_gaps
                result["needs_iteration"] = True

        # FIX-QM10: Shadow filtered evidence (FIX-QM7 may remove unfaithful items)
        if "evidence" in result:
            client_holder["_snapshot"]["evidence"] = result["evidence"]

        # MEM-1b: Perspective gap detection from evidence hierarchy
        hierarchy_read_enabled = os.getenv("PG_EVIDENCE_HIERARCHY_READ_ENABLED", "0") == "1"
        if hierarchy_read_enabled:
            try:
                from src.polaris_graph.memory.evidence_hierarchy import get_by_perspective
                from src.polaris_graph.state import STORM_PERSPECTIVES
                vector_id = state.get("vector_id", "unknown")
                perspective_counts = {}
                for p in STORM_PERSPECTIVES:
                    p_evidence = await get_by_perspective(vector_id, p)
                    perspective_counts[p] = len(p_evidence)
                missing = [p for p, c in perspective_counts.items() if c == 0]
                if missing:
                    logger.info("[polaris graph] MEM-1b: Missing perspectives: %s", missing)
                    result["memory_perspective_gaps"] = missing
                    for mp in missing[:3]:
                        result.setdefault("gap_queries", []).append(
                            f"{state['original_query']} {mp.lower().replace('_', ' ')} perspective"
                        )
            except Exception as exc:
                logger.debug("[polaris graph] MEM-1b: perspective gap query failed: %s", str(exc)[:200])

        # FIX-ENTROPY: Compute perspective_entropy from evidence perspective tags.
        # This field was declared in state.py but never populated — always 0.0.
        try:
            import math
            from collections import Counter as _Counter
            _ev = state.get("evidence", [])
            _persp_counts = _Counter(
                e.get("perspective", "Scientific") for e in _ev if e.get("perspective")
            )
            _total = sum(_persp_counts.values())
            if _total > 0 and len(_persp_counts) > 1:
                _probs = [c / _total for c in _persp_counts.values()]
                _entropy = -sum(p * math.log2(p) for p in _probs if p > 0)
                _max_entropy = math.log2(len(_persp_counts))
                _norm_entropy = round(_entropy / _max_entropy, 3) if _max_entropy > 0 else 0.0
            else:
                _norm_entropy = 0.0
            result["perspective_entropy"] = _norm_entropy
            logger.info(
                "[polaris graph] FIX-ENTROPY: perspective_entropy=%.3f "
                "(%d evidence, %d perspectives: %s)",
                _norm_entropy, _total, len(_persp_counts),
                dict(_persp_counts),
            )
        except Exception as _ent_exc:
            logger.debug("[polaris graph] FIX-ENTROPY failed: %s", str(_ent_exc)[:200])

        return result

    async def _synthesize(state: ResearchState) -> dict:
        """Synthesize node: full report generation.

        FIX-QG2-PURE: After synthesis, if quality gate fails, compute
        gap queries HERE (not in the router) and include them in the
        returned state dict. LangGraph merges this into state before
        the router sees it.
        """
        client = client_holder["client"]
        tracer = get_tracer()
        if tracer:
            tracer.node_start("synthesize", evidence_count=len(state.get("evidence", [])))
        state["timestamps"]["synthesize_start"] = _now()

        # PL: Wiki-based synthesis (Karpathy LLM Wiki pattern)
        wiki_enabled = os.getenv("PG_WIKI_ENABLED", "0") == "1"
        if wiki_enabled:
            from src.polaris_graph.wiki.wiki_builder import (
                build_wiki,
                generate_outline_for_wiki,
            )
            from src.polaris_graph.wiki.wiki_composer import compose_from_wiki

            logger.info("[polaris graph] Wiki synthesis enabled")

            # Generate outline if not already in state (it's normally
            # created inside synthesize_report, which we're replacing)
            outline = state.get("section_outline", [])
            if not outline:
                logger.info("[polaris graph] No outline in state — generating for wiki")
                outline = await generate_outline_for_wiki(
                    client, state["original_query"], state.get("evidence", []),
                )

            wiki_result = build_wiki(
                evidence=state.get("evidence", []),
                outline=outline,
                query=state["original_query"],
                vector_id=state.get("vector_id", "unknown"),
            )
            result = await compose_from_wiki(
                client, wiki_result, state["original_query"], outline,
            )
        else:
            result = await synthesize_report(client, state)
        # FIX-QG2-STALE: Always clear gap_queries from previous iterations.
        # Without this, old gap_queries persist in state and could confuse
        # the router if quality oscillates between iterations.
        result.setdefault("gap_queries", [])
        result["timestamps"] = {
            **state.get("timestamps", {}),
            "synthesize_end": _now(),
            "completed": _now(),
        }
        # Attach LLM usage
        result["llm_usage"] = client.usage.summary()
        # OBS-2: Attach trace summary to state
        if tracer:
            qm = result.get("quality_metrics", {})
            tracer.node_end(
                "synthesize",
                total_words=qm.get("total_words", 0),
                total_citations=qm.get("total_citations", 0),
                unique_sources=qm.get("unique_sources", 0),
            )
            result["trace_summary"] = tracer.summary()

        # FIX-QG2-PURE: Pre-compute gap queries for the router.
        # If quality gate failed and word count is below minimum,
        # generate gap queries so _should_finalize() can route to search_gaps
        # without mutating state (routing functions must be pure).
        quality_gate = result.get("quality_gate_result", "passed")
        if quality_gate == "below_minimum":
            qm = result.get("quality_metrics", {})
            total_words = qm.get("total_words", 0)
            min_words = int(os.getenv("PG_MIN_TOTAL_WORDS", "10000"))
            sections = result.get("sections", [])
            if total_words < min_words and sections:
                sorted_sections = sorted(sections, key=lambda s: s.get("word_count", 0))
                thin_count = max(1, len(sorted_sections) // 3)
                thin_titles = [
                    s.get("title", "unknown") for s in sorted_sections[:thin_count]
                ]
                query = state.get("original_query", "")
                gap_queries = [
                    f"{query} — detailed analysis of {title}"
                    for title in thin_titles
                ]
                result["gap_queries"] = gap_queries
                logger.info(
                    "[polaris graph] FIX-QG2-PURE: Computed %d gap queries "
                    "for thin sections: %s (words=%d/%d)",
                    len(gap_queries),
                    ", ".join(thin_titles[:3]),
                    total_words, min_words,
                )

        # MEM-3: Promote verified evidence to LTM-Global
        ltm_enabled = os.getenv("PG_CROSS_VECTOR_LTM_ENABLED", "0") == "1"
        if ltm_enabled:
            try:
                from src.polaris_graph.memory.cross_vector import promote_to_ltm
                promoted = promote_to_ltm(
                    evidence_pieces=state.get("evidence", []),
                    vector_id=state.get("vector_id", "unknown"),
                )
                logger.info("[polaris graph] MEM-3: Promoted %d evidence to LTM-Global", promoted)
            except Exception as ltm_exc:
                logger.warning("[polaris graph] MEM-3: LTM promotion failed: %s", str(ltm_exc)[:200])

        # A5: Smart art diagram generation (Mermaid.js)
        smart_art_enabled = os.getenv("PG_SMART_ART_ENABLED", "1") == "1"
        if smart_art_enabled and result.get("sections") and result.get("final_report"):
            try:
                from src.polaris_graph.synthesis.smart_art_generator import SmartArtGenerator
                sa_gen = SmartArtGenerator()
                sections_for_art = [
                    {
                        "section_id": s.get("section_id", ""),
                        "title": s.get("title", ""),
                        "content": s.get("content", ""),
                        "evidence_ids": s.get("evidence_ids", []),
                    }
                    for s in result.get("sections", [])
                    if s.get("content", "").strip()
                ]
                evidence_for_art = [
                    {
                        "evidence_id": e.get("evidence_id", ""),
                        "statement": e.get("statement", ""),
                    }
                    for e in state.get("evidence", [])
                ]
                diagrams = await sa_gen.generate_smart_art_for_report(
                    sections=sections_for_art,
                    evidence=evidence_for_art,
                    llm_client=client,
                )
                result["smart_art_diagrams"] = diagrams
                if diagrams:
                    logger.info(
                        "[polaris graph] A5: Generated %d smart art diagrams for sections: %s",
                        len(diagrams),
                        list(diagrams.keys()),
                    )
            except Exception as sa_exc:
                logger.warning(
                    "[polaris graph] A5: Smart art generation failed (non-blocking): %s",
                    str(sa_exc)[:200],
                )
                result["smart_art_diagrams"] = {}
        else:
            result.setdefault("smart_art_diagrams", {})

        return result

    async def _search_gaps(state: ResearchState) -> dict:
        """FIX-307: Search using gap-specific queries without re-planning."""
        gap_queries = state.get("gap_queries", [])
        # FIX-C10: Guard against empty gap queries causing state contamination
        if not gap_queries:
            logger.warning(
                "[polaris graph] FIX-C10: Gap queries empty — skipping gap search"
            )
            return {
                "status": "no_gaps",
                "iteration_count": state.get("iteration_count", 0) + 1,
            }
        tracer = get_tracer()
        if tracer:
            tracer.node_start("search_gaps", gap_query_count=len(gap_queries))
        logger.info(
            "[polaris graph] FIX-307: Gap-targeted search with %d queries "
            "(bypassing planner)",
            len(gap_queries),
        )
        if tracer:
            tracer.node_end("search_gaps", gap_query_count=len(gap_queries))
        # FIX-C10: Use gap_queries key instead of overwriting sub_queries
        # to prevent state contamination of the original query set
        return {
            "sub_queries": gap_queries,
            "gap_queries": [],  # Clear gap queries after consumption
            "status": "searching",
            "iteration_count": state.get("iteration_count", 0) + 1,
        }

    def _should_iterate(state: ResearchState) -> str:
        """Routing: iterate or synthesize.

        FIX-H15: Fail loudly if needs_iteration is missing from state.
        The old code defaulted to False (skip iteration) which masked
        LangGraph state-drop bugs and prevented gap analysis from ever running.

        Phase 1C FAST-EXIT: When faithfulness, evidence count, AND unique
        sources all exceed competitive thresholds, skip iteration immediately
        regardless of gap analysis. Prevents over-iteration when quality is
        already sufficient for competitive scoring.

        FIX-LOOP: Break positive feedback loop — if faithfulness is already
        high enough and we have sufficient evidence, skip iteration even if
        gap analysis says to continue. This prevents the vicious cycle where
        each iteration adds evidence, re-verification creates more timeouts,
        and faithfulness keeps dropping.
        """
        # FIX-H15: Require explicit needs_iteration — never default to False
        if "needs_iteration" not in state:
            logger.error(
                "[polaris graph] FIX-H15: CRITICAL — 'needs_iteration' missing from state. "
                "LangGraph may have dropped it during node execution. "
                "Defaulting to synthesize but logging as pipeline defect."
            )
            return "synthesize"

        # Phase 1C FAST-EXIT: Skip iteration when all three quality signals
        # exceed competitive thresholds. This is stricter than FIX-LOOP
        # (which only checks faithfulness + evidence count) but triggers
        # earlier because it also requires source diversity.
        faithfulness = state.get("faithfulness_score", 0.0)
        evidence_list = state.get("evidence", [])
        evidence_count = len(evidence_list)

        fast_exit_faith = float(os.getenv("PG_FAST_EXIT_FAITHFULNESS", "0.85"))
        fast_exit_evidence = int(os.getenv("PG_FAST_EXIT_EVIDENCE_COUNT", "200"))
        fast_exit_sources = int(os.getenv("PG_FAST_EXIT_UNIQUE_SOURCES", "15"))

        # Compute unique sources from evidence source URLs
        unique_source_urls = {
            e.get("source_url", "")
            for e in evidence_list
            if e.get("source_url")
        }
        unique_sources = len(unique_source_urls)

        if (
            faithfulness >= fast_exit_faith
            and evidence_count >= fast_exit_evidence
            and unique_sources >= fast_exit_sources
        ):
            logger.info(
                "[polaris graph] Phase 1C FAST-EXIT: Quality already sufficient — "
                "faithfulness=%.1f%% (>= %.0f%%), evidence=%d (>= %d), "
                "unique_sources=%d (>= %d). Skipping iteration, proceeding "
                "to synthesis.",
                faithfulness * 100,
                fast_exit_faith * 100,
                evidence_count,
                fast_exit_evidence,
                unique_sources,
                fast_exit_sources,
            )
            _fast_tracer = get_tracer()
            if _fast_tracer:
                _fast_tracer.iteration_decision(
                    iteration=state.get("iteration_count", 0),
                    decision="synthesize",
                    rationale={
                        "reason": "Phase 1C fast-exit",
                        "faithfulness": faithfulness,
                        "faith_threshold": fast_exit_faith,
                        "evidence_count": evidence_count,
                        "evidence_threshold": fast_exit_evidence,
                        "unique_sources": unique_sources,
                        "sources_threshold": fast_exit_sources,
                    },
                )
            return "synthesize"

        # FIX-LOOP: Break positive feedback loop when quality is sufficient
        faith_threshold = float(os.getenv("PG_FAITH_ITERATE_THRESHOLD", "0.75"))
        faith_min_evidence = int(os.getenv("PG_FAITH_MIN_EVIDENCE_FOR_SKIP", "500"))

        if faithfulness >= faith_threshold and evidence_count >= faith_min_evidence:
            logger.info(
                "[polaris graph] FIX-LOOP: Faithfulness %.1f%% >= %.0f%% threshold "
                "with %d evidence >= %d minimum — skipping iteration, "
                "proceeding to synthesis",
                faithfulness * 100,
                faith_threshold * 100,
                evidence_count,
                faith_min_evidence,
            )
            # OBS-ITER: Log routing decision
            _iter_tracer = get_tracer()
            if _iter_tracer:
                _iter_tracer.iteration_decision(
                    iteration=state.get("iteration_count", 0),
                    decision="synthesize",
                    rationale={
                        "reason": "FIX-LOOP skip",
                        "faithfulness": faithfulness,
                        "threshold": faith_threshold,
                        "evidence_count": evidence_count,
                        "min_evidence": faith_min_evidence,
                    },
                )
            return "synthesize"

        needs_iter = state["needs_iteration"]
        if needs_iter is True:
            iteration = state.get("iteration_count", 0)
            max_iter = state.get("max_iterations", 3)
            if iteration < max_iter:
                # FIX-307: Route to gap search if gap_queries available
                if state.get("gap_queries"):
                    logger.info(
                        "[polaris graph] FIX-307: Routing to gap search "
                        "(%d gap queries, iteration %d/%d)",
                        len(state["gap_queries"]),
                        iteration,
                        max_iter,
                    )
                    return "search_gaps"
                logger.info(
                    "[polaris graph] Iterating: %d/%d",
                    iteration,
                    max_iter,
                )
                return "plan"
            else:
                logger.info(
                    "[polaris graph] FIX-H15: needs_iteration=True but "
                    "at max iterations (%d/%d) — proceeding to synthesize",
                    iteration, max_iter,
                )
        return "synthesize"

    def _should_finalize(state: ResearchState) -> str:
        """FIX-QG2: Route after synthesis — finalize or iterate on quality deficit.

        When quality gate fails (below_minimum) and iterations remain,
        route back to search_gaps for more evidence, then re-synthesize.

        FIX-QG2-PURE: This is a LangGraph routing function (conditional edge).
        It must be PURE — only read state and return an edge name string.
        Gap query generation has been moved to the _synthesize() node's
        return dict to avoid state mutation in the router.
        """
        quality_gate = state.get("quality_gate_result", "passed")
        converged = state.get("converged", True)
        iteration = state.get("iteration_count", 0)
        max_iter = state.get("max_iterations", 3)

        if converged or quality_gate != "below_minimum":
            logger.info(
                "[polaris graph] FIX-QG2: Synthesis converged "
                "(gate=%s, iter=%d) — finalizing",
                quality_gate, iteration,
            )
            return "end"

        if iteration >= max_iter:
            logger.warning(
                "[polaris graph] FIX-QG2: Quality gate=%s but at max "
                "iterations (%d/%d) — finalizing with best effort",
                quality_gate, iteration, max_iter,
            )
            return "end"

        # FIX-QG2-PURE: Check if _synthesize() already generated gap queries
        # (gap queries are computed in the synthesize node, not here)
        gap_queries = state.get("gap_queries", [])
        if gap_queries:
            logger.info(
                "[polaris graph] FIX-QG2: Quality gate below_minimum, "
                "%d gap queries available — routing to search_gaps "
                "(iter %d/%d)",
                len(gap_queries), iteration, max_iter,
            )
            return "search_gaps"

        logger.info(
            "[polaris graph] FIX-QG2: Quality gate=%s but no "
            "actionable deficit — finalizing",
            quality_gate,
        )
        return "end"

    # Build graph
    graph = StateGraph(ResearchState)

    graph.add_node("plan", _plan)
    graph.add_node("search", _search)
    graph.add_node("storm_interviews", _storm_interviews)  # AREA-3
    graph.add_node("analyze", _analyze)
    graph.add_node("verify", _verify)
    graph.add_node("deepen_evidence", _deepen)  # Evidence deepening loop
    graph.add_node("evaluate", _evaluate)
    graph.add_node("synthesize", _synthesize)
    graph.add_node("search_gaps", _search_gaps)  # FIX-307

    # Edges
    graph.set_entry_point("plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "storm_interviews")  # AREA-3: STORM between search and analyze
    graph.add_edge("storm_interviews", "analyze")
    graph.add_edge("analyze", "verify")
    graph.add_edge("verify", "deepen_evidence")  # Deepen between verify and evaluate
    graph.add_edge("deepen_evidence", "evaluate")
    graph.add_conditional_edges(
        "evaluate",
        _should_iterate,
        {
            "plan": "plan",
            "synthesize": "synthesize",
            "search_gaps": "search_gaps",  # FIX-307
        },
    )
    # FIX-307: Gap search feeds into the normal search → analyze → verify chain
    graph.add_edge("search_gaps", "search")

    # FIX-QG2: Conditional edge from synthesize — route back to search_gaps
    # when quality gate fails and iterations remain, otherwise END.
    graph.add_conditional_edges(
        "synthesize",
        _should_finalize,
        {
            "end": END,
            "search_gaps": "search_gaps",
        },
    )

    # Store client holder reference for the closure
    graph._pg_client_holder = client_holder  # type: ignore[attr-defined]

    return graph


async def build_and_run(
    vector_id: str,
    query: str,
    application: str,
    region: str,
    stage: int = 1,
    max_iterations: int = 3,
    max_execution_minutes: int = int(os.getenv("PG_MAX_EXECUTION_MINUTES", "60")),
    resume: bool = False,
    enable_dashboard: bool = True,
    document_ids: list[str] | None = None,
    steer_callback: Any = None,
    research_brief: str | None = None,
) -> ResearchState:
    """
    Build the graph, initialize state, and run the full pipeline.

    This is the main entry point for polaris graph.

    AREA-7: Uses astream() for real-time progress updates via Rich dashboard.
    AREA-8: Uses SQLite checkpointer for crash recovery and resume.
    """
    budget_limit = float(os.getenv("PG_BUDGET_GUARD_USD", "150.0"))

    logger.info(
        "[polaris graph] Starting research: vector=%s, query='%s', "
        "resume=%s, budget=$%.2f",
        vector_id,
        query[:80],
        resume,
        budget_limit,
    )

    # Create state
    state = create_initial_state(
        vector_id=vector_id,
        query=query,
        application=application,
        region=region,
        stage=stage,
        max_iterations=max_iterations,
        max_execution_minutes=max_execution_minutes,
    )

    # Campaign Control Center: inject research brief into state
    if research_brief and research_brief.strip():
        state["research_brief"] = research_brief.strip()[:2000]
        logger.info(
            "[polaris graph] Research brief injected: %d chars",
            len(state["research_brief"]),
        )

    # G3: Load uploaded documents into pipeline state as GOLD sources
    if document_ids:
        try:
            from src.polaris_graph.document_ingester import DocumentIngester
            from src.polaris_graph.memory.local_document_rag import LocalDocumentRAG

            ingester = DocumentIngester()
            rag = LocalDocumentRAG(vector_id)
            uploaded_docs = []

            for doc_id in document_ids:
                doc = ingester.get_document(doc_id)
                if doc is None:
                    logger.warning(
                        "[polaris graph] G3: Document not found: %s — skipping",
                        doc_id,
                    )
                    continue

                content = doc.get("content", "")
                metadata = doc.get("metadata", {})
                filename = metadata.get("filename", f"{doc_id}.txt")

                # Ingest into session-scoped RAG for semantic search during analysis
                chunk_count = await rag.ingest_document(
                    doc_id=doc_id,
                    content=content,
                    metadata={"filename": filename},
                )

                uploaded_docs.append({
                    "doc_id": doc_id,
                    "filename": filename,
                    "content_preview": content[:500],
                    "chunk_count": chunk_count,
                    "content": content,  # Full content for analyzer chunking
                })

                logger.info(
                    "[polaris graph] G3: Loaded document %s (%s) — %d chunks",
                    doc_id, filename, chunk_count,
                )

            if uploaded_docs:
                state["uploaded_documents"] = uploaded_docs
                logger.info(
                    "[polaris graph] G3: %d documents loaded (%d total chunks) as GOLD sources",
                    len(uploaded_docs),
                    sum(d["chunk_count"] for d in uploaded_docs),
                )
        except Exception as exc:
            logger.warning(
                "[polaris graph] G3: Failed to load uploaded documents: %s — "
                "continuing without document context",
                str(exc)[:300],
            )

    # OBS-2: Initialize pipeline tracer
    tracer = PipelineTracer(vector_id)
    logger.info("[polaris graph] OBS-2: Pipeline tracer initialized — %s", tracer._path)

    # WAVE-1.1: Pipeline start event — full query, no truncation
    tracer._emit("pipeline_start", "pipeline", {
        "vector_id": vector_id,
        "query": query,
        "application": application,
        "region": region,
        "max_iterations": max_iterations,
        "max_execution_minutes": max_execution_minutes,
        "resume": resume,
        "budget_usd": budget_limit,
    })

    # FIX-C7: Reset per-vector Exa budget tracking
    from src.polaris_graph.agents.searcher import reset_exa_budget
    reset_exa_budget()

    # Build graph
    graph = build_graph()

    # AREA-8: Setup checkpointer (async context manager)
    checkpoint_enabled = os.getenv("PG_CHECKPOINT_ENABLED", "0") == "1"
    checkpoint_cm = None
    thread_id = None
    if checkpoint_enabled:
        try:
            from src.polaris_graph.checkpoint_manager import get_checkpointer, get_thread_id
            checkpoint_cm = get_checkpointer()
            thread_id = get_thread_id(vector_id)
        except Exception as exc:
            logger.warning(
                "[polaris graph] AREA-8: Checkpointing unavailable: %s — "
                "continuing without checkpoint",
                str(exc)[:200],
            )
    else:
        logger.info("[polaris graph] AREA-8: Checkpointing disabled (PG_CHECKPOINT_ENABLED=0)")

    # Helper to enter optional async context manager
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _optional_checkpoint():
        if checkpoint_cm is not None:
            try:
                async with checkpoint_cm as saver:
                    logger.info(
                        "[polaris graph] AREA-8: Checkpointing enabled (thread=%s)",
                        thread_id,
                    )
                    yield saver
            except Exception as exc:
                logger.warning(
                    "[polaris graph] AREA-8: Checkpoint context failed: %s — "
                    "continuing without checkpoint",
                    str(exc)[:200],
                )
                yield None
        else:
            yield None

    # Create and inject client (FIX-F2: pass session_id for cost ledger tagging)
    # W3.12: Wire PG_BUDGET_GUARD_USD through to client so cost guard actually fires.
    # PG_LOOPBACK_MODE=1: route every LLM call to disk for human-in-the-loop testing.
    if os.getenv("PG_LOOPBACK_MODE", "0") == "1":
        from src.polaris_graph.llm.loopback_client import LoopbackLLMClient
        _client_cls = LoopbackLLMClient
        logger.warning(
            "[polaris graph] PG_LOOPBACK_MODE=1 — using LoopbackLLMClient. "
            "Pipeline will write prompts to loopback/pending/ and BLOCK until "
            "responses appear in loopback/responses/. ZERO OpenRouter cost."
        )
    else:
        _client_cls = OpenRouterClient
    async with _client_cls(session_id=vector_id, budget_usd=budget_limit) as client:
        graph._pg_client_holder["client"] = client  # type: ignore[attr-defined]
        # D2: Store steer callback for live steering
        graph._pg_client_holder["steer_callback"] = steer_callback  # type: ignore[attr-defined]

        # FIX-QM11: Validate reasoning tokens before expensive pipeline run
        reasoning_ok = await client.validate_reasoning()
        if not reasoning_ok:
            logger.error(
                "[polaris graph] FIX-QM11: Reasoning validation FAILED. "
                "Model is NOT producing chain-of-thought reasoning. "
                "Check OPENROUTER_PROVIDER_ORDER and reasoning config."
            )

        async with _optional_checkpoint() as checkpointer:
            # Compile with optional checkpointer
            compile_kwargs = {}
            if checkpointer:
                compile_kwargs["checkpointer"] = checkpointer

            # A2: Parse interrupt_before/interrupt_after for checkpoint snapshots.
            # When PG_AUTO_RESUME=1 (default), interrupts create checkpoint
            # snapshots but execution auto-resumes — no manual intervention needed.
            _interrupt_before_raw = os.getenv("PG_INTERRUPT_BEFORE", "")
            _interrupt_after_raw = os.getenv("PG_INTERRUPT_AFTER", "")
            if checkpointer and _interrupt_before_raw:
                _interrupt_nodes = [
                    n.strip() for n in _interrupt_before_raw.split(",") if n.strip()
                ]
                if _interrupt_nodes:
                    compile_kwargs["interrupt_before"] = _interrupt_nodes
                    logger.info(
                        "[polaris graph] A2: interrupt_before=%s",
                        _interrupt_nodes,
                    )
            if checkpointer and _interrupt_after_raw:
                _interrupt_nodes_after = [
                    n.strip() for n in _interrupt_after_raw.split(",") if n.strip()
                ]
                if _interrupt_nodes_after:
                    compile_kwargs["interrupt_after"] = _interrupt_nodes_after
                    logger.info(
                        "[polaris graph] A2: interrupt_after=%s",
                        _interrupt_nodes_after,
                    )

            app = graph.compile(**compile_kwargs)

            # Build run config
            run_config: dict[str, Any] = {"recursion_limit": 100}
            if thread_id:
                run_config["configurable"] = {"thread_id": thread_id}

            # AREA-8: Resume from checkpoint if requested and available
            run_input = state  # Default: fresh start with initial state
            if resume and checkpointer and thread_id:
                try:
                    from src.polaris_graph.checkpoint_manager import has_checkpoint as _has_cp
                    has_cp = await _has_cp(vector_id)
                    if has_cp:
                        run_input = None  # LangGraph resumes from checkpoint when input is None
                        logger.info(
                            "[polaris graph] AREA-8: RESUMING from checkpoint "
                            "(thread=%s) — skipping completed nodes",
                            thread_id,
                        )
                    else:
                        logger.info(
                            "[polaris graph] AREA-8: No checkpoint found for %s "
                            "— starting fresh",
                            vector_id,
                        )
                except Exception as exc:
                    logger.warning(
                        "[polaris graph] AREA-8: Checkpoint check failed: %s "
                        "— starting fresh",
                        str(exc)[:200],
                    )

            start_time = time.monotonic()
            result = dict(state)  # Start with initial state as fallback

            # AREA-7: Dashboard setup
            dashboard = None
            if enable_dashboard:
                try:
                    from src.polaris_graph.dashboard import PipelineDashboard
                    dashboard = PipelineDashboard(
                        vector_id=vector_id, budget=budget_limit
                    )
                except Exception as exc:
                    logger.warning(
                        "[polaris graph] AREA-7: Dashboard unavailable: %s",
                        str(exc)[:200],
                    )

            try:
                # AREA-7: Use astream() for real-time updates with dashboard
                # AREA-8: run_input is None when resuming from checkpoint
                if dashboard:
                    with dashboard:
                        result = await _run_with_stream(
                            app, run_input, run_config, max_execution_minutes,
                            dashboard, graph, client,
                        )
                else:
                    result = await _run_with_stream(
                        app, run_input, run_config, max_execution_minutes,
                        None, graph, client,
                    )
            except Exception as exc:
                elapsed = time.monotonic() - start_time
                logger.error(
                    "[polaris graph] Pipeline failed after %.1fs: %s",
                    elapsed,
                    str(exc)[:300],
                )
                result = dict(state)
                result["status"] = "failed"
                result["error"] = str(exc)[:1000]
                result["llm_usage"] = client.usage.summary()
                # Emit pipeline_end event for UI timer/progress
                try:
                    tracer._emit("pipeline_end", "pipeline", {
                        "vector_id": vector_id,
                        "status": "failed",
                        "elapsed_seconds": round(elapsed, 1),
                        "error": str(exc)[:500],
                    })
                except Exception:
                    pass
                return result

            elapsed = time.monotonic() - start_time

    # Log final stats
    logger.info(
        "[polaris graph] Pipeline complete in %.1fs. Status: %s",
        elapsed,
        result.get("status", "unknown"),
    )

    if result.get("quality_metrics"):
        qm = result["quality_metrics"]
        # S6/D2: faithfulness_score lives at top-level state, not inside
        # quality_metrics dict. Previous code read qm.get() which returned 0
        # when only top-level had the value, showing "faithfulness=0.0%" in
        # logs while actual state.faithfulness_score = 1.0.
        faith = qm.get("faithfulness_score")
        if faith is None:
            faith = result.get("faithfulness_score", 0)
        cov = qm.get("coverage_score")
        if cov is None:
            cov = result.get("coverage_score", 0)
        logger.info(
            "[polaris graph] Quality: %d words, %d citations, %d sources, "
            "faithfulness=%.1f%%, coverage=%.1f%%",
            qm.get("total_words", 0),
            qm.get("total_citations", 0),
            qm.get("unique_sources", 0),
            max(faith or 0, 0) * 100,
            (cov or 0) * 100,
        )

    if result.get("llm_usage"):
        usage = result["llm_usage"]
        logger.info(
            "[polaris graph] LLM usage: %d calls, $%.4f total, "
            "$%.4f remaining",
            usage.get("total_calls", 0),
            usage.get("total_cost_usd", 0),
            usage.get("budget_remaining_usd", 0),
        )

    # Emit pipeline_end event for UI timer/progress
    try:
        qm = result.get("quality_metrics", {})
        usage = result.get("llm_usage", {})
        tracer._emit("pipeline_end", "pipeline", {
            "vector_id": vector_id,
            "status": result.get("status", "completed"),
            "elapsed_seconds": round(elapsed, 1),
            "total_words": qm.get("total_words", 0),
            "total_citations": qm.get("total_citations", 0),
            "unique_sources": qm.get("unique_sources", 0),
            "faithfulness_score": max(qm.get("faithfulness_score", 0), 0),
            "total_cost_usd": usage.get("total_cost_usd", 0),
        })
    except Exception:
        pass

    # Save output
    _save_output(result, vector_id)

    return result


async def _run_with_stream(
    app,
    state,  # ResearchState or None (None = resume from checkpoint)
    run_config: dict,
    max_execution_minutes: int,
    dashboard,
    graph,
    client,
) -> dict:
    """Run the compiled graph using astream() with optional dashboard updates.

    AREA-7: Yields real-time node updates to the dashboard.
    Falls back to ainvoke() if astream() is not available.
    """
    start_time = time.monotonic()
    warned_timeout = False

    # A2: PG_AUTO_RESUME — when True, auto-resume through interrupt points
    _pg_auto_resume = os.getenv("PG_AUTO_RESUME", "1") == "1"
    _pg_max_auto_resumes = int(os.getenv("PG_MAX_AUTO_RESUMES", "20"))

    try:
        # AREA-7: astream with updates mode — yields state changes per-node
        # AREA-8: When state is None, LangGraph resumes from checkpoint
        result = dict(state) if state is not None else {}
        _current_input = state  # First call uses initial state; resumes use None
        _auto_resume_count = 0
        _hard_stopped = False
        _last_resource_log = 0.0

        while True:
            _stream_yielded_events = False
            async for event in app.astream(
                _current_input,
                run_config,
                stream_mode="updates",
            ):
                _stream_yielded_events = True
                # astream(mode="updates") yields {node_name: state_update_dict}
                if isinstance(event, dict):
                    for node_name, node_output in event.items():
                        if isinstance(node_output, dict):
                            # Merge node output into accumulated result
                            result.update(node_output)
                            logger.info(
                                "[polaris graph] AREA-7: Node '%s' completed "
                                "(%d keys updated)",
                                node_name,
                                len(node_output),
                            )

                    # Update dashboard if available
                    if dashboard:
                        try:
                            dashboard.update_from_event(event)
                        except Exception as dash_exc:
                            logger.debug(
                                "[polaris graph] Dashboard update failed: %s",
                                str(dash_exc)[:100],
                            )

                # FIX-TIMEOUT-V2 / W3.12: Two-tier timeout — warning at 1x, hard stop at Nx.
                # With RC-1 (incremental verify), evidence caps, and per-node timeouts,
                # the pipeline should complete naturally. The global timeout is now a
                # safety net, not the primary completion mechanism.
                # Multiplier is env-controlled so operators can tighten to 1.0 for strict caps.
                elapsed = time.monotonic() - start_time
                _hard_stop_mult = max(1.0, float(os.getenv("PG_HARD_STOP_MULTIPLIER", "2.0")))
                warning_threshold = max_execution_minutes * 60
                hard_stop_threshold = max_execution_minutes * 60 * _hard_stop_mult

                if elapsed > warning_threshold and not warned_timeout:
                    warned_timeout = True
                    logger.warning(
                        "[polaris graph] FIX-TIMEOUT-V2: Exceeded %dm budget "
                        "(%.1fs elapsed) — pipeline still running. "
                        "Hard stop at %.0fm (multiplier=%.1fx).",
                        max_execution_minutes,
                        elapsed,
                        max_execution_minutes * _hard_stop_mult,
                        _hard_stop_mult,
                    )

                # FIX-5: Periodic resource monitoring (every 5 min).
                # Logs memory/handle usage for future crash investigations.
                if elapsed - _last_resource_log >= 300:
                    _last_resource_log = elapsed
                    try:
                        proc = psutil.Process()
                        mem = proc.memory_info()
                        sys_mem = psutil.virtual_memory()
                        logger.info(
                            "[polaris graph] FIX-5: Resource snapshot at %.0fm: "
                            "RSS=%.0fMB, VMS=%.0fMB, sys_avail=%.1fGB (%.1f%%), "
                            "handles=%d",
                            elapsed / 60,
                            mem.rss / (1024 * 1024),
                            mem.vms / (1024 * 1024),
                            sys_mem.available / (1024**3),
                            sys_mem.percent,
                            proc.num_handles() if hasattr(proc, "num_handles") else -1,
                        )
                    except Exception as _res_exc:
                        logger.debug(
                            "[polaris graph] FIX-5: Resource check failed: %s",
                            str(_res_exc)[:100],
                        )

                if elapsed > hard_stop_threshold:
                    _hard_stop_minutes = max_execution_minutes * _hard_stop_mult
                    logger.error(
                        "[polaris graph] FIX-TIMEOUT-V2: Hard stop at %.0fm "
                        "(%.1fx budget, %.1fs elapsed) — forcing synthesis",
                        _hard_stop_minutes,
                        _hard_stop_mult,
                        elapsed,
                    )
                    # FIX-TIMEOUT: Synthesize from accumulated evidence instead of
                    # returning empty result. The result dict has accumulated state
                    # from all completed nodes via result.update(node_output).
                    accumulated_evidence = result.get("evidence", [])
                    if accumulated_evidence and not result.get("final_report"):
                        logger.info(
                            "[polaris graph] FIX-TIMEOUT-V2: Synthesizing from %d "
                            "accumulated evidence pieces",
                            len(accumulated_evidence),
                        )
                        result["status"] = "timeout_synthesizing"
                        result["error"] = (
                            f"Hard stop after {_hard_stop_minutes:.0f}min "
                            f"({_hard_stop_mult:.1f}x budget)"
                        )
                        synth_result = await _wiki_or_legacy_synthesize(
                            client, result,
                        )
                        result.update(synth_result)
                        result["status"] = "timeout_synthesized"
                    else:
                        result["status"] = "timeout_synthesized"
                        result["error"] = (
                            f"Hard stop after {_hard_stop_minutes:.0f}min "
                            f"({_hard_stop_mult:.1f}x budget)"
                        )
                    _hard_stopped = True
                    break

            # A2: Check if the graph paused at an interrupt point.
            # When interrupt_before/interrupt_after is set, astream() returns
            # after processing up to the interrupt. If PG_AUTO_RESUME is enabled,
            # we automatically continue by passing None as input.
            # FIX-2: Skip auto-resume when hard stop has fired — prevents
            # pipeline from running indefinitely past the 2x budget cap.
            if _hard_stopped:
                logger.info(
                    "[polaris graph] FIX-2: Skipping auto-resume — hard stop active "
                    "(elapsed %.1fs, %d resumes so far)",
                    time.monotonic() - start_time, _auto_resume_count,
                )
                break

            if _pg_auto_resume and _stream_yielded_events:
                # Check if graph is at an interrupt (not __end__)
                try:
                    current_state = await app.aget_state(run_config)
                    next_nodes = current_state.next if current_state else ()
                    if next_nodes:
                        _auto_resume_count += 1
                        if _auto_resume_count > _pg_max_auto_resumes:
                            logger.warning(
                                "[polaris graph] A2: Max auto-resumes (%d) reached "
                                "— stopping at node '%s'",
                                _pg_max_auto_resumes,
                                next_nodes[0],
                            )
                            break
                        logger.info(
                            "[polaris graph] A2: Auto-resuming through interrupt "
                            "at node '%s' (resume #%d)",
                            next_nodes[0],
                            _auto_resume_count,
                        )
                        _current_input = None  # Resume from checkpoint
                        continue  # Re-enter the while loop
                except Exception as resume_exc:
                    logger.debug(
                        "[polaris graph] A2: State check after stream: %s",
                        str(resume_exc)[:200],
                    )

            # No interrupt or auto-resume disabled — exit the while loop
            break

        # Ensure we have LLM usage
        if "llm_usage" not in result or not result["llm_usage"]:
            result["llm_usage"] = client.usage.summary()

        return result

    except Exception as exc:
        # Fall back to accumulated state from _snapshot
        elapsed = time.monotonic() - start_time
        logger.error(
            "[polaris graph] astream() failed after %.1fs: %s — "
            "attempting recovery from snapshot",
            elapsed, str(exc)[:300],
        )
        snapshot = graph._pg_client_holder.get("_snapshot", {})  # type: ignore[attr-defined]
        snapshot_evidence = snapshot.get("evidence", [])
        # FIX-RESUME: Use result dict (accumulated node outputs) instead of
        # state, because state is None when resuming from checkpoint.
        synth_state = result if result else {}
        if snapshot_evidence:
            logger.info(
                "[polaris graph] Recovered %d evidence from snapshot",
                len(snapshot_evidence),
            )
            synth_state["evidence"] = snapshot_evidence
            synth_state["claims"] = snapshot.get("claims", [])
            synth_state["faithfulness_score"] = snapshot.get(
                "faithfulness_score", -1.0
            )
            synth_state["fetched_content"] = snapshot.get(
                "fetched_content", []
            )
            synth_state["status"] = "timeout_synthesizing"
            synth_state["error"] = f"astream failed: {str(exc)[:200]}"

            # FIX-043A: MERGE synthesis result into accumulated state (not replace).
            synth_result = await _wiki_or_legacy_synthesize(
                client, synth_state,
            )
            synth_state.update(synth_result)
            synth_state["llm_usage"] = client.usage.summary()
            synth_state["status"] = "timeout_synthesized"
            return synth_state
        elif synth_state.get("evidence"):
            # No snapshot but result has accumulated evidence
            logger.info(
                "[polaris graph] Using %d accumulated evidence for synthesis",
                len(synth_state["evidence"]),
            )
            synth_state["status"] = "timeout_synthesizing"
            synth_state["error"] = f"astream failed: {str(exc)[:200]}"

            synth_result = await _wiki_or_legacy_synthesize(
                client, synth_state,
            )
            synth_state.update(synth_result)
            synth_state["llm_usage"] = client.usage.summary()
            synth_state["status"] = "timeout_synthesized"
            return synth_state
        else:
            raise


async def _wiki_or_legacy_synthesize(client: Any, state_dict: dict) -> dict:
    """Route to wiki or legacy synthesis based on PG_WIKI_ENABLED flag.

    Handles outline generation for wiki path (outline is normally created
    inside synthesize_report, which wiki replaces).
    """
    if os.getenv("PG_WIKI_ENABLED", "0") == "1":
        from src.polaris_graph.wiki.wiki_builder import (
            build_wiki,
            generate_outline_for_wiki,
        )
        from src.polaris_graph.wiki.wiki_composer import compose_from_wiki

        # Phase 2: Deep crawl expansion (optional, runs before wiki build)
        if os.getenv("PG_DEEP_CRAWL_ENABLED", "0") == "1":
            try:
                from src.polaris_graph.wiki.wiki_crawl import deep_crawl
                logger.info("[polaris graph] Deep crawl enabled — expanding source pool")
                new_content = await deep_crawl(
                    fetched_content=state_dict.get("fetched_content", []),
                    web_results=state_dict.get("web_results", []),
                    academic_results=state_dict.get("academic_results", []),
                    query=state_dict.get("original_query", ""),
                    vector_id=state_dict.get("vector_id", "unknown"),
                )
                if new_content:
                    existing = state_dict.get("fetched_content", [])
                    state_dict["fetched_content"] = existing + new_content
                    logger.info(
                        "[polaris graph] Deep crawl: %d new sources added (%d total)",
                        len(new_content), len(state_dict["fetched_content"]),
                    )
            except Exception as exc:
                logger.warning("[polaris graph] Deep crawl failed: %s", str(exc)[:100])

        outline = state_dict.get("section_outline", [])
        if not outline:
            outline = await generate_outline_for_wiki(
                client, state_dict.get("original_query", ""),
                state_dict.get("evidence", []),
            )

        wiki_r = build_wiki(
            evidence=state_dict.get("evidence", []),
            outline=outline,
            query=state_dict.get("original_query", ""),
            vector_id=state_dict.get("vector_id", "unknown"),
        )
        return await compose_from_wiki(
            client, wiki_r, state_dict.get("original_query", ""), outline,
        )
    else:
        from src.polaris_graph.agents.synthesizer import synthesize_report
        return await synthesize_report(client, state_dict)


def _cross_iteration_dedup(evidence: list) -> list:
    """IMP-4: Deduplicate evidence across iterations using MinHash.

    Within-iteration dedup runs in analyzer.py. This handles duplicates
    that arise when the same fact is extracted from different sources
    across separate iterations.

    Controlled by PG_EVIDENCE_DEDUP_ENABLED env var (same kill switch
    as within-iteration dedup).
    """
    from src.polaris_graph.state import (
        PG_EVIDENCE_DEDUP_ENABLED,
        PG_EVIDENCE_DEDUP_THRESHOLD,
    )

    if not PG_EVIDENCE_DEDUP_ENABLED or len(evidence) <= 1:
        return evidence

    try:
        from src.utils.content_deduplicator import ContentDeduplicator

        dedup = ContentDeduplicator()
        items = [
            {"content": e.get("statement", ""), **e}
            for e in evidence
        ]
        result = dedup.deduplicate(items, content_key="content")

        if result.unique_count < len(evidence):
            logger.info(
                "[polaris graph] IMP-4: Cross-iteration dedup: %d -> %d "
                "(%d exact, %d near-duplicates removed)",
                len(evidence),
                result.unique_count,
                result.exact_duplicates,
                result.near_duplicates,
            )

        # Remove the temporary "content" key
        deduped = []
        for item in result.unique_items:
            item.pop("content", None)
            deduped.append(item)

        return deduped

    except ImportError:
        logger.warning(
            "[polaris graph] IMP-4: ContentDeduplicator not available — "
            "skipping cross-iteration dedup"
        )
        return evidence
    except Exception as exc:
        logger.warning(
            "[polaris graph] IMP-4: Cross-iteration dedup failed: %s — skipping",
            str(exc)[:200],
        )
        return evidence


def _save_output(state: ResearchState, vector_id: str):
    """Save pipeline output to disk."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Save full state
    state_path = OUTPUT_DIR / f"{vector_id}.json"

    # FIX-043B: Reconcile claims with evidence before save (defense-in-depth).
    # If FIX-043A in analyze_gaps() missed orphaned claims, catch them here.
    evidence_id_set = {e.get("evidence_id") for e in state.get("evidence", [])}
    raw_claims = state.get("claims", [])
    if raw_claims and evidence_id_set:
        clean_claims = [
            c for c in raw_claims
            if any(
                eid in evidence_id_set
                for eid in c.get("evidence_ids", [])
            )
            or not c.get("evidence_ids")
        ]
        orphaned = len(raw_claims) - len(clean_claims)
        if orphaned > 0:
            logger.warning(
                "[polaris graph] FIX-043B: Reconciled %d orphaned claims "
                "at save (%d->%d)",
                orphaned, len(raw_claims), len(clean_claims),
            )
            state["claims"] = clean_claims
            verified = [
                c for c in clean_claims
                if c.get("verification_method") != "api_error"
            ]
            faithful = sum(
                1 for c in verified if c.get("is_faithful")
            )
            state["faithfulness_score"] = round(
                faithful / max(len(verified), 1), 4
            )

    # SF-19: Make state serializable — log non-serializable keys
    serializable = {}
    for key, value in state.items():
        try:
            json.dumps(value)
            serializable[key] = value
        except (TypeError, ValueError):
            logger.warning(
                "[polaris graph] Non-serializable state key '%s' (%s) — "
                "converting to str",
                key,
                type(value).__name__,
            )
            serializable[key] = str(value)

    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)

    # Save report as markdown
    if state.get("final_report"):
        report_path = OUTPUT_DIR / f"{vector_id}_report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(state["final_report"])

        logger.info(
            "[polaris graph] Output saved: %s (%d bytes), %s",
            state_path,
            state_path.stat().st_size,
            report_path,
        )


def _map_nli_scores_to_evidence(
    evidence: list[dict],
    claims: list[dict],
    cross_weight: float = 0.6,
) -> int:
    """FIX-051: Map NLI verification scores from claims back to evidence pieces.

    Enriches evidence in-place with ``nli_self_check_score`` using the
    claim_id == evidence_id mapping (nli_verifier.py:727-729).

    Args:
        evidence: List of evidence dicts (mutated in-place).
        claims: List of verified claim dicts with nli_score/cross_source_score.
        cross_weight: Weight for cross-source score in blend (0.0-1.0).

    Returns:
        Number of evidence pieces enriched.
    """
    self_weight = 1.0 - cross_weight
    claim_scores: dict[str, float] = {}
    for c in claims:
        cid = c.get("claim_id")
        if not cid:
            continue
        nli = c.get("nli_score")
        if nli is None:
            continue
        cross = c.get("cross_source_score")
        faithful = c.get("is_faithful")
        # Blend self-check with cross-source when available
        if cross is not None:
            score = self_weight * float(nli) + cross_weight * float(cross)
        else:
            score = float(nli)
        # Penalty for unfaithful evidence
        if faithful is False:
            score = min(score, 0.3)
        claim_scores[cid] = round(score, 4)

    enriched_count = 0
    for ev in evidence:
        eid = ev.get("evidence_id")
        if eid in claim_scores:
            ev["nli_self_check_score"] = claim_scores[eid]
            enriched_count += 1
    return enriched_count


def _now() -> str:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def run_sync(
    vector_id: str,
    query: str,
    application: str,
    region: str,
    stage: int = 1,
    max_iterations: int = 3,
    max_execution_minutes: int = int(os.getenv("PG_MAX_EXECUTION_MINUTES", "60")),
    resume: bool = False,
    enable_dashboard: bool = True,
) -> ResearchState:
    """Synchronous wrapper for build_and_run."""
    return asyncio.run(
        build_and_run(
            vector_id=vector_id,
            query=query,
            application=application,
            region=region,
            stage=stage,
            max_iterations=max_iterations,
            max_execution_minutes=max_execution_minutes,
            resume=resume,
            enable_dashboard=enable_dashboard,
        )
    )


if __name__ == "__main__":
    import argparse

    # Log to both console and persistent file
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "polaris_graph.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, mode="a", encoding="utf-8"),
        ],
    )

    parser = argparse.ArgumentParser(description="polaris graph research pipeline")
    parser.add_argument("--vector-id", required=True, help="Vector ID")
    parser.add_argument("--query", required=True, help="Research query")
    parser.add_argument("--application", default="general", help="Application domain")
    parser.add_argument("--region", default="GLOBAL", help="Geographic region")
    parser.add_argument("--stage", type=int, default=1, help="Stage number")
    parser.add_argument("--max-iterations", type=int, default=3, help="Max iterations")
    parser.add_argument(
        "--max-minutes", type=int,
        default=int(os.getenv("PG_MAX_EXECUTION_MINUTES", "60")),
        help="Max execution minutes (default: PG_MAX_EXECUTION_MINUTES env or 60)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last checkpoint (AREA-8)",
    )
    parser.add_argument(
        "--no-dashboard", action="store_true",
        help="Disable Rich terminal dashboard (AREA-7)",
    )

    args = parser.parse_args()

    result = run_sync(
        vector_id=args.vector_id,
        query=args.query,
        application=args.application,
        region=args.region,
        stage=args.stage,
        max_iterations=args.max_iterations,
        max_execution_minutes=args.max_minutes,
        resume=args.resume,
        enable_dashboard=not args.no_dashboard,
    )

    # Print summary
    qm = result.get("quality_metrics") or {}
    status = result.get("status", "unknown")
    print(f"\n{'='*60}")
    print(f"polaris graph — {args.vector_id}")
    print(f"{'='*60}")
    print(f"Status: {status}")
    print(f"Words: {qm.get('total_words', 0)}")
    print(f"Sections: {qm.get('total_sections', 0)}")
    print(f"Citations: {qm.get('total_citations', 0)}")
    print(f"Sources: {qm.get('unique_sources', 0)}")
    faithfulness = qm.get('faithfulness_score', 0)
    print(f"Faithfulness: {faithfulness:.1%}" if faithfulness >= 0 else "Faithfulness: N/A (not computed)")
    print(f"Coverage: {qm.get('coverage_score', 0):.1%}")
    usage = result.get("llm_usage", {})
    print(f"LLM calls: {usage.get('total_calls', 0)}")
    print(f"Cost: ${usage.get('total_cost_usd', 0):.4f}")
    print(f"{'='*60}")

    # SF-18: Exit non-zero on pipeline failure
    import sys
    if status == "failed":
        print(f"\nERROR: Pipeline failed — {result.get('error', 'unknown error')}")
        sys.exit(1)
