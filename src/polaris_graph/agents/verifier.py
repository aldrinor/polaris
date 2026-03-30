"""
Evidence verifier agent for polaris graph.

Verifies ALL claims against evidence — no sampling.
Uses reason() mode for deep analysis of each claim.
"""

import asyncio
import copy
import logging
import math
import os
import time
from typing import Any

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.schemas import VerificationBatch
from src.polaris_graph.state import (
    EvidencePiece,
    ResearchState,
    VerifiedClaim,
    MIN_CLAIM_CONFIDENCE,
    PG_VERIFY_BATCH_SIZE,
    PG_VERIFY_CONCURRENCY,
    PG_VERIFY_GATHER_TIMEOUT,
    PG_VERIFIER_CONTENT_CAP,
)

logger = logging.getLogger(__name__)


def _normalize_url(u: str) -> str:
    """Normalize URL for consistent lookup (www vs non-www, trailing slash, protocol)."""
    u = u.strip().rstrip("/")
    if u.startswith("http://"):
        u = "https://" + u[7:]
    # Remove www. prefix for matching
    u = u.replace("://www.", "://")
    return u.lower()


VERIFICATION_SYSTEM = """You are a rigorous research claim verifier. Your job is to check
whether extracted claims are faithfully supported by their source material.

For each claim, determine:
1. SUPPORTED: The claim is directly stated in or clearly entailed by the source material.
2. PARTIALLY_SUPPORTED: The claim is related but goes beyond what the source explicitly states.
3. NOT_SUPPORTED: The claim has no basis in the source material.

Rules:
- Apply strict entailment: the source must directly support the claim, not merely discuss the topic.
- When source content is provided, verify the claim AGAINST THE ACTUAL TEXT. Check that specific numbers, dates, names, and causal claims appear in the source content.
- A claim that adds specificity not present in the source (e.g., exact numbers, dates, or causation) that cannot be verified from the provided content/quote is PARTIALLY_SUPPORTED.
- If no source content is provided, mark the claim as NOT_SUPPORTED. Title-only context is insufficient for faithful attribution. If a direct quote IS provided but no full source content, the claim can be PARTIALLY_SUPPORTED at most.
- If the source document is about a completely different field or topic than the research question, mark claims as NOT_SUPPORTED regardless of superficial text matches. A paper about tick genetics is NOT relevant to water filtration even if both mention "contamination".
- If the research question is provided, assess whether the SOURCE is on-topic FIRST. Off-topic sources cannot support on-topic claims.
- Do NOT include reasoning in the JSON output — think deeply before responding but only output the verdict and confidence.

Output format example:
{"verifications": [{"claim": "E. coli was detected in 30% of tested filters", "verdict": "SUPPORTED", "confidence": 0.85, "supporting_evidence": ["ev_abc123"]}, {"claim": "WHO recommends annual filter replacement", "verdict": "PARTIALLY_SUPPORTED", "confidence": 0.6, "supporting_evidence": ["ev_def456"]}], "overall_faithfulness": 0.75}"""


async def verify_claims(
    client: OpenRouterClient,
    state: ResearchState,
) -> dict:
    """
    Verify ALL evidence claims. No sampling.

    Returns state update with claims and faithfulness_score.
    """
    evidence = state.get("evidence", [])

    if not evidence:
        logger.error("[polaris graph] ZERO evidence — cannot verify. Halting verification.")
        return {
            "claims": [],
            "faithfulness_score": -1.0,  # Sentinel: not computed (distinct from "all unfaithful")
            "status": "failed",
            "error": "Zero evidence to verify",
        }

    # Group evidence by source for efficient verification
    source_groups = _group_by_source(evidence)

    logger.info(
        "[polaris graph] Verifying %d evidence pieces across %d sources",
        len(evidence),
        len(source_groups),
    )

    # IMP-1 + TIER-3 Stage 1: Build URL→content lookup.
    # Primary source: source_content_store (SQLite, deduped by URL).
    # Fallback: fetched_content from state (legacy path).
    url_content_map: dict[str, str] = {}

    # TIER-3: Try content store first (preferred — avoids state bloat)
    try:
        from src.polaris_graph.memory.source_content_store import (
            get_content_batch as _get_batch,
            PG_SOURCE_CONTENT_STORE_ENABLED as _store_enabled,
        )
        if _store_enabled:
            _all_urls = list({
                ev.get("source_url", "") for ev in evidence if ev.get("source_url")
            })
            if _all_urls:
                url_content_map = await _get_batch(_all_urls)
    except Exception as _store_exc:
        logger.debug(
            "[polaris graph] TIER-3: Content store read failed, using fetched_content: %s",
            str(_store_exc)[:200],
        )

    # Fallback: fetched_content from state (legacy path, still works if store empty)
    if not url_content_map:
        fetched_content = state.get("fetched_content", [])
        for fc in fetched_content:
            url = fc.get("url", "")
            content = fc.get("content", "")
            if url and content:
                url_content_map[_normalize_url(url)] = content
                url_content_map[url] = content

    if url_content_map:
        logger.info(
            "[polaris graph] IMP-1: %d sources have content for verification "
            "(avg %.0f chars)",
            len(url_content_map),
            sum(len(v) for v in url_content_map.values()) / max(len(url_content_map), 1),
        )

    # FIX-040: Bind original_query BEFORE NLI block (was at line 204, causing
    # UnboundLocalError when NLI path executed before LLM fallback path).
    original_query = state.get("original_query", "")

    # ARCH-1: If NLI model is enabled, use MiniCheck-7B for primary verification.
    # Only send disputed claims (ambiguous NLI scores) to LLM for second opinion.
    # NOTE: Use os.getenv() directly (NOT imported constant) so the recursion
    # guard at line ~127 actually works — imported constants are bound at import
    # time and won't reflect os.environ changes.
    from src.polaris_graph.agents.nli_verifier import (
        verify_evidence_nli, get_disputed_claims,
    )
    # FIX-059-B: NLI faithfulness threshold for merge point (LLM second opinion).
    _nli_faith_threshold_merge = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))
    nli_enabled = os.getenv("PG_NLI_ENABLED", "0") == "1"
    if nli_enabled:
        logger.info(
            "[polaris graph] ARCH-1: Using NLI model for primary verification "
            "(%d evidence)", len(evidence),
        )
    else:
        logger.info(
            "[polaris graph] ARCH-1: NLI model DISABLED (PG_NLI_ENABLED=0). "
            "Using LLM-only verification for %d evidence.", len(evidence),
        )
    if nli_enabled:
        # FIX-048-K1: Try to get pre-computed embeddings from analyze step
        # for cross-source verification (avoids re-embedding).
        statement_embeddings = None
        try:
            _embed_enabled = os.getenv("PG_CROSS_SOURCE_ENABLED", "1") == "1"
            if _embed_enabled:
                from src.utils.embedding_service import embed_texts
                statements = [e.get("statement", "") for e in evidence]
                if statements:
                    import numpy as _np
                    statement_embeddings = _np.array(embed_texts(statements))
                    logger.info(
                        "[polaris graph] FIX-048-K1: Computed %d statement embeddings "
                        "for cross-source verification",
                        len(statements),
                    )
        except Exception as _emb_exc:
            logger.debug(
                "[polaris graph] FIX-048-K1: Embedding computation failed (non-fatal): %s",
                str(_emb_exc)[:100],
            )

        nli_results = await verify_evidence_nli(
            evidence, url_content_map, original_query,
            all_evidence=evidence,
            statement_embeddings=statement_embeddings,
        )
        if nli_results:
            # NLI succeeded — find disputed claims for LLM review
            disputed = get_disputed_claims(nli_results)
            if disputed:
                logger.info(
                    "[polaris graph] ARCH-1: %d disputed claims (NLI score 0.3-0.7) "
                    "— sending to LLM for second opinion",
                    len(disputed),
                )
                # NLI-1: Use standalone _llm_second_opinion() instead of
                # recursive verify_claims() call. Deep copies evidence,
                # per-batch error isolation, partial results on failure.
                # NLI-4: Skip BRONZE title_only claims (low-value evidence)
                disputed_ids = {d["claim_id"] for d in disputed}
                disputed_evidence = [
                    e for e in evidence
                    if e.get("evidence_id") in disputed_ids
                ]
                # NLI-4: Filter out BRONZE tier title_only claims
                nli_4_filtered = []
                nli_4_skipped = 0
                for ev_item in disputed_evidence:
                    tier = ev_item.get("quality_tier", "")
                    basis_for_item = ""
                    for nr in nli_results:
                        if nr.get("claim_id") == ev_item.get("evidence_id"):
                            basis_for_item = nr.get("verification_basis", "")
                            break
                    if tier == "BRONZE" and basis_for_item == "title_only":
                        nli_4_skipped += 1
                    else:
                        nli_4_filtered.append(ev_item)
                if nli_4_skipped:
                    logger.info(
                        "[polaris graph] NLI-4: Skipped %d BRONZE title_only "
                        "claims from LLM second opinion",
                        nli_4_skipped,
                    )
                if nli_4_filtered:
                    llm_claims = await _llm_second_opinion(
                        client, nli_4_filtered, url_content_map, original_query,
                    )
                    if llm_claims:
                        for i, r in enumerate(nli_results):
                            if r["claim_id"] in llm_claims:
                                llm_claim = llm_claims[r["claim_id"]]
                                # FIX-051h: Preserve original NLI metadata through
                                # LLM second opinion. The LLM replaces the verdict
                                # but the original nli_score and cross_source_score
                                # must survive for _map_nli_scores_to_evidence().
                                llm_claim["nli_score"] = r.get("nli_score")
                                llm_claim["cross_source_score"] = r.get("cross_source_score")
                                # FIX-060-B: Preserve NLI-based confidence through LLM second opinion.
                                # LLM overwrites verdict but must NOT inflate confidence.
                                _orig_nli = r.get("nli_score")
                                if _orig_nli is not None and _orig_nli > 0:
                                    llm_claim["confidence"] = _orig_nli
                                nli_results[i] = llm_claim
                                # FIX-059-B: Enforce NLI threshold on LLM second opinion.
                                # LLM may say SUPPORTED but NLI score was below threshold.
                                _merged_nli = llm_claim.get("nli_score")
                                if (
                                    _merged_nli is not None
                                    and _merged_nli < _nli_faith_threshold_merge
                                    and llm_claim.get("is_faithful")
                                ):
                                    llm_claim["is_faithful"] = False
                                    logger.debug(
                                        "[polaris graph] FIX-059-B: NLI threshold "
                                        "override at merge: claim %s nli=%.3f < %.2f",
                                        r.get("claim_id", "?"),
                                        _merged_nli,
                                        _nli_faith_threshold_merge,
                                    )

            # Calculate faithfulness
            verified_for_score = [
                c for c in nli_results
                if c.get("verification_method") != "api_error"
            ]
            faithful_count = sum(1 for c in verified_for_score if c.get("is_faithful"))
            total = len(verified_for_score)
            faithfulness = faithful_count / max(total, 1)
            logger.info(
                "[polaris graph] ARCH-1: NLI verification: %d/%d faithful (%.1f%%)",
                faithful_count, total, faithfulness * 100,
            )
            # OBS-TRACE: Emit verification traces BEFORE returning (NLI path)
            _nli_tracer = get_tracer()
            if _nli_tracer:
                _nli_api_errors = sum(
                    1 for c in nli_results
                    if c.get("verification_method") == "api_error"
                )
                top_claims = sorted(
                    [c for c in nli_results if c.get("nli_score") is not None],
                    key=lambda c: c.get("nli_score", 0), reverse=True
                )[:20]
                _basis_dist: dict[str, int] = {}
                for c in nli_results:
                    b = c.get("verification_basis", "unknown")
                    _basis_dist[b] = _basis_dist.get(b, 0) + 1
                _nli_tracer.evidence("verify", "nli_verification_detail", len(nli_results),
                    faithful_count=faithful_count,
                    faithfulness_pct=round(faithfulness * 100, 1),
                    disputed_count=sum(1 for c in nli_results if not c.get("is_faithful")),
                    api_error_count=_nli_api_errors,
                    basis_distribution=_basis_dist,
                    claims_detail=[{"id": c.get("claim_id", "")[:20],
                                    "nli_score": round(c.get("nli_score", 0), 3),
                                    "cross_source_score": round(c.get("cross_source_score") or 0, 3) if c.get("cross_source_score") is not None else None,
                                    "is_faithful": c.get("is_faithful"),
                                    "statement": c.get("statement", "")[:150]}
                                   for c in top_claims])
                _nli_tracer.evidence("verify", "verification_context", len(nli_results),
                    claims=[{
                        "evidence_id": c.get("evidence_id", "")[:20],
                        "verdict": c.get("verdict", ""),
                        "confidence": round(c.get("confidence", 0), 3),
                        "is_faithful": c.get("is_faithful"),
                        "basis": c.get("verification_basis", ""),
                        "nli_score": round(c.get("nli_score", 0) or 0, 3),
                        "cross_source_score": round(c.get("cross_source_score") or 0, 3) if c.get("cross_source_score") is not None else None,
                        "source_url": c.get("source_url", ""),
                        "statement": c.get("statement", ""),
                        "direct_quote": c.get("direct_quote", ""),
                    } for c in nli_results])
            # FIX-3: NLI faithfulness floor — when NLI model can't handle
            # domain-specific content (e.g., chemistry, materials science), it
            # defaults to NOT_SUPPORTED for everything. Fall back to LLM-only
            # verification which understands the domain better than flan-t5-large.
            _nli_floor = float(os.getenv("PG_NLI_FAITHFULNESS_FLOOR", "0.15"))
            if faithfulness < _nli_floor:
                logger.warning(
                    "[polaris graph] FIX-3: NLI faithfulness %.1f%% below %.0f%% "
                    "floor — falling back to LLM verification (%d evidence). "
                    "FIX-B2: Preserving per-claim NLI scores for downstream use.",
                    faithfulness * 100, _nli_floor * 100, len(evidence),
                )
                # FIX-B2: Preserve per-claim NLI scores on evidence even when
                # overall NLI faithfulness is below floor. Old behavior discarded
                # ALL NLI metadata, leaving LLM rubber-stamp as only signal.
                # New: keep nli_score on each evidence piece so the LLM verifier
                # can use it as a skepticism signal (cross-check its own verdict).
                for _nli_claim in nli_results:
                    _nli_eid = _nli_claim.get("claim_id", "")
                    _nli_sc = _nli_claim.get("nli_score")
                    if _nli_eid and _nli_sc is not None:
                        for _ev in evidence:
                            if _ev.get("evidence_id") == _nli_eid:
                                _ev["nli_self_check_score"] = _nli_sc
                                break
                # Fall through to LLM-only verification below
            else:
                return {
                    "claims": nli_results,
                    "faithfulness_score": round(faithfulness, 4),
                    "status": "synthesizing",
                }
        else:
            logger.warning(
                "[polaris graph] ARCH-1: NLI model returned empty results — "
                "falling back to LLM verification",
            )

    # FIX-QM10: Run verification batches CONCURRENTLY (not sequentially).
    # With batch_size=10 and 1000+ evidence, sequential processing takes 8+ hours.
    # Concurrent processing with semaphore matches the analyzer's approach.
    all_verified: list[VerifiedClaim] = []
    failed_batches: list[list[EvidencePiece]] = []
    batch_size = PG_VERIFY_BATCH_SIZE
    concurrency = PG_VERIFY_CONCURRENCY
    sem = asyncio.Semaphore(concurrency)

    evidence_list = list(evidence)
    batches = [
        evidence_list[i : i + batch_size]
        for i in range(0, len(evidence_list), batch_size)
    ]

    # original_query already bound above (FIX-040), used by NLI + LLM batch

    async def _run_batch(batch: list[EvidencePiece]) -> tuple[list, bool]:
        async with sem:
            verified = await _verify_batch(client, batch, url_content_map, original_query)
            # FIX-C3: Check for "api_error" too (verifier returns "api_error",
            # not "failed", when API calls fail)
            is_all_failed = bool(verified) and all(
                c.get("verification_method") in ("failed", "api_error")
                for c in verified
            )
            return verified, is_all_failed

    # FIX-V1: Use asyncio.wait() instead of asyncio.wait_for(asyncio.gather(...))
    # so that completed results are preserved even when some batches time out.
    # FIX-RC2: Auto-scale gather timeout based on batch count and concurrency.
    # With 767 batches at 30 concurrency and 300s/call, the old 3600s was too short.
    base_timeout = PG_VERIFY_GATHER_TIMEOUT
    per_call_timeout_est = int(os.getenv("PG_VERIFY_PER_CALL_TIMEOUT", "300"))
    estimated_time = (len(batches) / max(concurrency, 1)) * per_call_timeout_est
    gather_timeout = max(base_timeout, int(estimated_time * 1.5))  # 50% safety margin
    if gather_timeout > base_timeout:
        logger.info(
            "[polaris graph] FIX-RC2: Auto-scaled gather_timeout: %d batches / %d concurrency "
            "* %ds/call * 1.5 = %ds (base=%ds)",
            len(batches), concurrency, per_call_timeout_est,
            gather_timeout, base_timeout,
        )

    # Create tasks and track task-to-batch mapping
    tasks = []
    task_to_batch_idx: dict[asyncio.Task, int] = {}
    for idx, b in enumerate(batches):
        task = asyncio.create_task(_run_batch(b))
        tasks.append(task)
        task_to_batch_idx[task] = idx

    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=gather_timeout)

        # Cancel pending (timed-out) tasks
        for task in pending:
            task.cancel()

        # Process completed tasks
        for task in done:
            batch_idx = task_to_batch_idx[task]
            exc = task.exception()
            if exc is not None:
                logger.warning(
                    "[polaris graph] Verification batch %d failed with exception: %s",
                    batch_idx, str(exc)[:200],
                )
                failed_batches.append(batches[batch_idx])
            else:
                verified, is_all_failed = task.result()
                if is_all_failed:
                    failed_batches.append(batches[batch_idx])
                else:
                    all_verified.extend(verified)
                    # FIX-H3: Even when batch is marked is_all_failed, preserve
                    # any successfully verified claims from partial results.
                    # Previously, the entire batch was discarded and retried,
                    # losing valid verifications within the batch.
                if is_all_failed and verified:
                    successful_partial = [
                        c for c in verified
                        if c.get("verification_method") not in ("failed", "api_error")
                    ]
                    if successful_partial:
                        all_verified.extend(successful_partial)
                        logger.info(
                            "[polaris graph] FIX-H3: Preserved %d successful "
                            "verifications from partially failed batch %d",
                            len(successful_partial), batch_idx,
                        )

        # FIX-V1: Create api_error placeholders for pending (timed-out) batches
        if pending:
            logger.error(
                "[polaris graph] FIX-V1: %d/%d verification batches timed out after %ds "
                "— creating api_error placeholders",
                len(pending),
                len(tasks),
                gather_timeout,
            )
            for task in pending:
                batch_idx = task_to_batch_idx[task]
                timed_out_batch = batches[batch_idx]
                for j, ev in enumerate(timed_out_batch):
                    all_verified.append(
                        VerifiedClaim(
                            claim_id=ev.get("evidence_id", f"api_error_{batch_idx}_{j}"),
                            statement=ev.get("statement", ""),
                            evidence_ids=[ev.get("evidence_id", "")],
                            confidence=0.0,
                            verification_method="api_error",
                            is_faithful=None,
                            section_id=None,
                            reasoning="FIX-V1: Gather timed out — not verified",
                            verification_basis="none",
                            verification_type="api_error",
                            nli_score=None,
                            cross_source_score=None,
                            verdict="NO_VERDICT",  # FIX-B4
                            source_url=ev.get("source_url", ""),  # FIX-B5
                            direct_quote=ev.get("direct_quote", ""),  # FIX-B5
                        )
                    )

    # Retry failed batches with consecutive timeout cap (FIX-V7)
    retry_cap = int(os.getenv("PG_VERIFY_RETRY_CAP", "3"))
    if failed_batches:
        logger.info(
            "[polaris graph] Retrying %d failed verification batches "
            "(%d evidence pieces), consecutive timeout cap=%d",
            len(failed_batches),
            sum(len(b) for b in failed_batches),
            retry_cap,
        )
        await asyncio.sleep(5)  # Brief pause before retries
        # FIX-HANG-2: Add per-batch timeout to retry loop (prevents infinite hang)
        retry_timeout = 600  # 10 min per batch — generous but bounded
        consecutive_timeouts = 0
        for batch in failed_batches:
            # FIX-V7: Stop retrying after N consecutive timeouts
            if consecutive_timeouts >= retry_cap:
                logger.warning(
                    "[polaris graph] FIX-V7: %d consecutive timeouts reached cap=%d "
                    "— creating api_error placeholders for remaining %d batches",
                    consecutive_timeouts,
                    retry_cap,
                    len(failed_batches) - failed_batches.index(batch),
                )
                # Create api_error placeholders for all remaining batches
                remaining_idx = failed_batches.index(batch)
                for remaining_batch in failed_batches[remaining_idx:]:
                    for j, ev in enumerate(remaining_batch):
                        all_verified.append(
                            VerifiedClaim(
                                claim_id=ev.get("evidence_id", f"api_error_cap_{j}"),
                                statement=ev.get("statement", ""),
                                evidence_ids=[ev.get("evidence_id", "")],
                                confidence=0.0,
                                verification_method="api_error",
                                is_faithful=None,
                                section_id=None,
                                reasoning="FIX-V7: Retry cap reached — not verified",
                                verification_basis="none",
                                verification_type="api_error",
                                nli_score=None,
                                cross_source_score=None,
                                verdict="NO_VERDICT",  # FIX-B4
                                source_url=ev.get("source_url", ""),  # FIX-B5
                                direct_quote=ev.get("direct_quote", ""),  # FIX-B5
                            )
                        )
                break

            try:
                verified = await asyncio.wait_for(
                    _verify_batch(client, batch, url_content_map),
                    timeout=retry_timeout,
                )
                all_verified.extend(verified)
                consecutive_timeouts = 0  # Reset on success
            except asyncio.TimeoutError:
                consecutive_timeouts += 1
                logger.error(
                    "[polaris graph] FIX-V7: Retry batch timed out after %ds "
                    "(%d/%d consecutive) — skipping %d evidence pieces",
                    retry_timeout,
                    consecutive_timeouts,
                    retry_cap,
                    len(batch),
                )
                # FIX-V3: Create api_error placeholders for timed-out retry batches
                for j, ev in enumerate(batch):
                    all_verified.append(
                        VerifiedClaim(
                            claim_id=ev.get("evidence_id", f"api_error_retry_{j}"),
                            statement=ev.get("statement", ""),
                            evidence_ids=[ev.get("evidence_id", "")],
                            confidence=0.0,
                            verification_method="api_error",
                            is_faithful=None,
                            section_id=None,
                            reasoning="FIX-V3: Retry timed out — not verified",
                            verification_basis="none",
                            verification_type="api_error",
                            nli_score=None,
                            cross_source_score=None,
                            verdict="NO_VERDICT",  # FIX-B4
                            source_url=ev.get("source_url", ""),  # FIX-B5
                            direct_quote=ev.get("direct_quote", ""),  # FIX-B5
                        )
                    )

    # FIX-045G: Individual retry for api_error claims.
    # Batch failures often have transient causes (rate limits, timeouts).
    # Retry each api_error claim individually for better recovery.
    api_error_claims = [
        c for c in all_verified
        if c.get("verification_method") == "api_error"
    ]
    max_individual_retries = int(os.getenv("PG_MAX_INDIVIDUAL_RETRIES", "20"))
    if api_error_claims and len(api_error_claims) <= max_individual_retries:
        logger.info(
            "[polaris graph] FIX-045G: Retrying %d api_error claims individually",
            len(api_error_claims),
        )
        # Build evidence_id → evidence lookup for individual retry
        evidence_by_id = {e.get("evidence_id", ""): e for e in evidence}
        recovered_count = 0

        for err_claim in api_error_claims:
            eid = err_claim.get("claim_id", "")
            ev = evidence_by_id.get(eid)
            if not ev:
                continue
            try:
                individual_result = await _verify_batch(
                    client, [ev], url_content_map, original_query,
                )
                if individual_result and individual_result[0].get("verification_method") != "api_error":
                    # Replace the api_error claim with the verified result
                    idx = all_verified.index(err_claim)
                    all_verified[idx] = individual_result[0]
                    recovered_count += 1
            except Exception as ind_exc:
                logger.debug(
                    "[polaris graph] FIX-045G: Individual retry failed for %s: %s",
                    eid, str(ind_exc)[:100],
                )

        if recovered_count > 0:
            logger.info(
                "[polaris graph] FIX-045G: Recovered %d/%d api_error claims "
                "via individual retry",
                recovered_count, len(api_error_claims),
            )
    elif api_error_claims:
        logger.info(
            "[polaris graph] FIX-045G: Skipping individual retry for %d api_error "
            "claims (exceeds cap=%d)",
            len(api_error_claims), max_individual_retries,
        )

    # FIX-060-G: Detect systemic empty batch rate from V4 placeholders.
    _v4_error_count = sum(
        1 for c in all_verified
        if c.get("verification_method") == "api_error"
        and "FIX-V4" in c.get("reasoning", "")
    )
    _total_claims = len(all_verified)
    _empty_batch_rate = _v4_error_count / max(_total_claims, 1)
    if _v4_error_count > 0:
        logger.warning(
            "[polaris graph] FIX-060-G: %d/%d claims from empty batches "
            "(V4 rate=%.1f%%)",
            _v4_error_count, _total_claims, _empty_batch_rate * 100,
        )
    if _empty_batch_rate > 0.20:
        logger.error(
            "[polaris graph] FIX-060-G: CASE_4 ALERT - empty batch rate "
            "%.1f%% exceeds 20%%. LLM verification output systemically broken.",
            _empty_batch_rate * 100,
        )

    # FIX-S2: Apply triangulation confidence boost for cross-source corroboration
    corroboration = _triangulate_claims(evidence)

    # BUG-B17: Populate cross_source_score from triangulation data.
    # Score = min(1.0, corroborating_sources / 3.0) — 3+ sources = 1.0.
    for claim in all_verified:
        primary_eid = claim["evidence_ids"][0] if claim.get("evidence_ids") else ""
        count = corroboration.get(primary_eid, 1)  # Default 1 = only self
        claim["cross_source_score"] = round(min(1.0, count / 3.0), 3)

    boosted_count = 0
    for claim in all_verified:
        eid = claim.get("claim_id", "")
        source_count = corroboration.get(eid, 1)
        # FIX-V5: Only boost SUPPORTED claims — don't reward unverified/failed claims
        # FIX-060-C: Only boost claims below 0.70 (still uncertain). Cap at 0.85
        # to leave headroom for truly exceptional evidence.
        if source_count > 1 and claim.get("is_faithful") is True and claim.get("confidence", 0) < 0.70:
            boost = min(math.log2(source_count) * 0.05, 0.15)
            claim["confidence"] = min(0.85, claim["confidence"] + boost)
            boosted_count += 1
    if boosted_count > 0:
        logger.info(
            "[polaris graph] FIX-S2: Triangulation boosted confidence for %d/%d "
            "claims (multi-source corroboration)",
            boosted_count,
            len(all_verified),
        )

    # Calculate faithfulness — exclude api_error claims from denominator
    # so transient failures don't deflate the score
    verified_for_score = [
        c for c in all_verified
        if c.get("verification_method") != "api_error"
    ]
    api_error_count = len(all_verified) - len(verified_for_score)

    if verified_for_score:
        # FIX-F1 + FIX-F2: Strict binary faithfulness weighted by verification basis.
        # Only SUPPORTED counts as faithful (PARTIALLY_SUPPORTED = not faithful).
        # Claims verified against full content get full weight; quote_only gets 0.7;
        # title_only gets 0.0 (FIX-060-F: title-only = NOT_SUPPORTED, zero weight).
        content_verified = [
            c for c in verified_for_score
            if c.get("verification_basis") == "content" and c.get("is_faithful")
        ]
        quote_verified = [
            c for c in verified_for_score
            if c.get("verification_basis") == "quote_only" and c.get("is_faithful")
        ]
        title_verified = [
            c for c in verified_for_score
            if c.get("verification_basis") == "title_only" and c.get("is_faithful")
        ]
        weighted_faithful = (
            len(content_verified)
            + 0.7 * len(quote_verified)
            + 0.0 * len(title_verified)  # FIX-060-F alignment: title-only = NOT_SUPPORTED, weight 0
        )
        faithfulness = weighted_faithful / len(verified_for_score)

        # FIX-F2: Log verification basis distribution
        logger.info(
            "[polaris graph] Verification basis: %d content, %d quote_only, %d title_only",
            len([c for c in verified_for_score if c.get("verification_basis") == "content"]),
            len([c for c in verified_for_score if c.get("verification_basis") == "quote_only"]),
            len([c for c in verified_for_score if c.get("verification_basis") == "title_only"]),
        )
    elif all_verified:
        # All claims were api_error — can't compute faithfulness
        faithfulness = -1.0  # Sentinel: not computed
    else:
        faithfulness = 0.0

    # FIX-060-F alignment: Exclude title_only from count (weight = 0.0).
    # Without this, title_only is_faithful=True inflates faithful_count while
    # contributing zero to the weighted faithfulness — making honest_faithfulness
    # more lenient than primary, inverting its purpose.
    faithful_count = sum(
        1 for c in verified_for_score
        if c.get("is_faithful") and c.get("verification_basis") != "title_only"
    )
    logger.info(
        "[polaris graph] Verification complete: %d/%d faithful (%.1f%%), "
        "%d api_error excluded",
        faithful_count,
        len(verified_for_score),
        faithfulness * 100 if faithfulness >= 0 else 0,
        api_error_count,
    )

    # FIX-MP3: Log HONEST faithfulness (including api_error in denominator)
    # This metric shows the true % of evidence that was positively verified,
    # not the optimistic metric that excludes unverified evidence.
    if all_verified:
        honest_faithfulness = faithful_count / len(all_verified)
        logger.info(
            "[polaris graph] FIX-MP3: Honest faithfulness: %d/%d (%.1f%%) "
            "— includes %d api_error claims in denominator",
            faithful_count,
            len(all_verified),
            honest_faithfulness * 100,
            api_error_count,
        )


    # OBS-TRACE: Emission 8 — NLI verification summary
    tracer = get_tracer()
    if tracer:
        top_claims = sorted(
            [c for c in all_verified if c.get("nli_score") is not None],
            key=lambda c: c.get("nli_score", 0), reverse=True
        )[:20]
        # Basis distribution
        _basis_dist: dict[str, int] = {}
        for c in all_verified:
            b = c.get("verification_basis", "unknown")
            _basis_dist[b] = _basis_dist.get(b, 0) + 1
        tracer.evidence("verify", "nli_verification_detail", len(all_verified),
            faithful_count=sum(1 for c in all_verified if c.get("is_faithful")),
            faithfulness_pct=round(sum(1 for c in all_verified if c.get("is_faithful")) / max(len(all_verified), 1) * 100, 1),
            disputed_count=sum(1 for c in all_verified if not c.get("is_faithful")),
            api_error_count=api_error_count,
            basis_distribution=_basis_dist,
            claims_detail=[{"id": c.get("claim_id", "")[:20],
                            "nli_score": round(c.get("nli_score", 0), 3),
                            "cross_source_score": round(c.get("cross_source_score") or 0, 3) if c.get("cross_source_score") is not None else None,
                            "is_faithful": c.get("is_faithful"),
                            "statement": c.get("statement", "")[:150]}
                           for c in top_claims])

        # WAVE-4.1: Per-claim verification context (ALL claims, no cap)
        tracer.evidence("verify", "verification_context", len(all_verified),
            claims=[{
                "evidence_id": c.get("evidence_id", "")[:20],
                "verdict": c.get("verdict", ""),
                "confidence": round(c.get("confidence", 0), 3),
                "is_faithful": c.get("is_faithful"),
                "basis": c.get("verification_basis", ""),
                "nli_score": round(c.get("nli_score", 0) or 0, 3),
                "cross_source_score": round(c.get("cross_source_score") or 0, 3) if c.get("cross_source_score") is not None else None,
                "source_url": c.get("source_url", ""),
                "statement": c.get("statement", ""),
                "direct_quote": c.get("direct_quote", ""),
            } for c in all_verified])
    return {
        "claims": all_verified,
        "faithfulness_score": round(faithfulness, 4),
        "status": "synthesizing",
    }


def _extract_relevant_context(
    full_content: str,
    direct_quote: str,
    context_chars: int = 5000,
) -> str:
    """FIX-CAP2: Find direct_quote in content and return a surrounding context window.

    Instead of blindly truncating to the first N chars, locates the quote
    in the content and returns a window centered on it. This ensures the
    verifier sees the same text the analyzer extracted from.

    Falls back to first context_chars if quote is not found.
    """
    if not direct_quote or len(direct_quote) < 20:
        return full_content[:context_chars]

    content_lower = full_content.lower()

    # Try progressively shorter prefixes of the quote
    for prefix_len in [len(direct_quote), 80, 50, 30]:
        prefix = direct_quote[:prefix_len].lower()
        idx = content_lower.find(prefix)
        if idx >= 0:
            # Center a window around the found location (25% before, 75% after)
            start = max(0, idx - context_chars // 4)
            end = min(len(full_content), idx + context_chars * 3 // 4)
            return full_content[start:end]

    # Quote not found — fall back to first context_chars
    return full_content[:context_chars]


async def _llm_second_opinion(
    client: OpenRouterClient,
    disputed_evidence: list[EvidencePiece],
    url_content_map: dict[str, str],
    original_query: str,
) -> dict[str, VerifiedClaim]:
    """NLI-1: Standalone LLM second opinion for disputed NLI claims.

    Replaces the fragile recursive verify_claims() call pattern.
    Deep copies evidence to prevent parent state corruption.
    Per-batch error isolation with partial results on failure.

    Returns:
        Dict mapping claim_id to VerifiedClaim. Empty dict on total failure.
    """
    if not disputed_evidence:
        return {}

    batch_size = PG_VERIFY_BATCH_SIZE
    concurrency = PG_VERIFY_CONCURRENCY
    sem = asyncio.Semaphore(concurrency)

    # Deep copy to prevent mutation of parent's evidence
    evidence_copy = copy.deepcopy(disputed_evidence)
    batches = [
        evidence_copy[i: i + batch_size]
        for i in range(0, len(evidence_copy), batch_size)
    ]

    results: dict[str, VerifiedClaim] = {}
    succeeded = 0
    failed = 0

    async def _run_opinion_batch(batch: list[EvidencePiece]) -> list[VerifiedClaim]:
        async with sem:
            return await _verify_batch(client, batch, url_content_map, original_query)

    # Run all batches concurrently with per-batch error isolation
    tasks = [asyncio.create_task(_run_opinion_batch(b)) for b in batches]
    gather_timeout = max(3600, len(batches) * 60)

    if tasks:
        done, pending = await asyncio.wait(tasks, timeout=gather_timeout)

        for task in pending:
            task.cancel()
            failed += 1

        for task in done:
            try:
                batch_claims = task.result()
                for claim in batch_claims:
                    cid = claim.get("claim_id", "")
                    if cid:
                        results[cid] = claim
                        succeeded += 1
            except Exception as exc:
                logger.warning(
                    "[polaris graph] NLI-1: LLM second opinion batch failed: %s",
                    str(exc)[:200],
                )
                failed += 1

    logger.info(
        "[polaris graph] NLI-1: LLM second opinion complete. "
        "%d claims resolved, %d claims succeeded, %d batches failed",
        len(results), succeeded, failed,
    )
    return results


_BASIS_CONFIDENCE_CAP = {
    "content": 0.50,      # LLM had real source text
    "quote_only": 0.30,   # LLM had only the quote
    "title_only": 0.10,   # LLM had only title
    "none": 0.0,
}


def _basis_aware_confidence(llm_confidence: float, basis: str) -> float:
    """FIX-060-A: Cap LLM self-assessed confidence by verification basis.

    LLM self-assesses 0.90-0.95 regardless of evidence quality. This
    caps confidence by what information the LLM actually had available,
    preventing inflated metrics and enabling low-confidence gap search.
    """
    cap = _BASIS_CONFIDENCE_CAP.get(basis, 0.50)
    return min(llm_confidence, cap)


async def _verify_batch(
    client: OpenRouterClient,
    batch: list[EvidencePiece],
    url_content_map: dict[str, str] | None = None,
    research_query: str = "",
) -> list[VerifiedClaim]:
    """Verify a batch of evidence claims.

    IMP-1: When url_content_map is provided, includes actual source content
    (capped at PG_VERIFIER_CONTENT_CAP chars per claim) for real content-based verification.
    FIX-CAP2: Uses smart quote retrieval to find relevant context window.
    FIX-NLI-CASCADE: Includes research query context for topical alignment check.
    """
    content_cap_per_claim = PG_VERIFIER_CONTENT_CAP
    # FIX-STUB: Track which claim indices had their content suppressed
    # so the basis determination loop can correctly label them as quote_only.
    stub_suppressed_indices: set[int] = set()
    claims_text = []
    for i, ev in enumerate(batch, 1):
        quote = ev.get("direct_quote", "")
        quote_line = (
            f'  Direct quote: "{quote[:300]}"'
            if quote
            else "  Direct quote: (not available)"
        )

        # IMP-1 + FIX-CAP2: Include source content excerpt if available.
        # Smart quote retrieval: find the direct_quote in full content and
        # return a context window around it, rather than blindly truncating.
        source_url = ev.get("source_url", "")
        source_content = ""
        if url_content_map and source_url:
            # FIX-URL-NORM: Try normalized URL first, then original
            raw_content = url_content_map.get(source_url, "") or url_content_map.get(_normalize_url(source_url), "")
            if raw_content:
                source_content = _extract_relevant_context(
                    raw_content, ev.get("direct_quote", ""), content_cap_per_claim,
                )

        # FIX-STUB: Detect paywall/stub content — if source content is below
        # the minimum useful threshold, fall back to quote_only verification
        # instead of content verification against HTML boilerplate.
        min_useful_content = int(os.getenv("PG_MIN_USEFUL_CONTENT", "500"))
        content_block = ""
        if source_content and len(source_content) >= min_useful_content:
            content_block = (
                f"  Source content excerpt:\n"
                f"  ---\n"
                f"  {source_content}\n"
                f"  ---\n"
            )
        elif source_content:
            # FIX-STUB: Content too short (paywall/stub) — don't include it
            logger.debug(
                "[polaris graph] FIX-STUB: Source content too short (%d < %d chars) "
                "for %s — falling back to quote_only",
                len(source_content),
                min_useful_content,
                source_url[:80],
            )
            source_content = ""  # Clear so basis becomes quote_only
            stub_suppressed_indices.add(i - 1)  # 0-indexed for results loop

        claims_text.append(
            f"Claim {i}: {ev.get('statement', '')}\n"
            f"  Source: {ev.get('source_title', '')} ({source_url})\n"
            f"{quote_line}\n"
            f"  Fact category: {ev.get('fact_category', '')}\n"
            f"{content_block}"
        )

    has_content = any(
        url_content_map and (
            url_content_map.get(ev.get("source_url", ""))
            or url_content_map.get(_normalize_url(ev.get("source_url", "")))
        )
        for ev in batch
    ) if url_content_map else False

    # ARCH-4: Balanced prompting (Gemini 3 pattern) — verify AND try to disprove
    balanced_enabled = os.getenv("PG_BALANCED_PROMPTING", "0") == "1"
    logger.debug(
        "[polaris graph] ARCH-4: Balanced prompting %s, has_content=%s",
        "ENABLED" if balanced_enabled else "DISABLED", has_content,
    )
    if has_content:
        if balanced_enabled:
            verify_instruction = (
                "For each claim, perform BALANCED verification:\n"
                "1. SUPPORT: Find specific text in the source that supports this claim. Quote it exactly.\n"
                "2. CONTRADICT: Try to find text that contradicts, limits, or weakens this claim.\n"
                "3. VERDICT: Based on both analyses:\n"
                "   - SUPPORTED: Supporting text found, no contradicting text.\n"
                "   - PARTIALLY_SUPPORTED: Some support, but the claim adds specificity or scope "
                "not present in the source.\n"
                "   - NOT_SUPPORTED: No supporting text, or the source discusses the topic but "
                "does not make this specific claim.\n"
                "Check that specific numbers, dates, names, and causal claims appear EXACTLY "
                "in the source text."
            )
        else:
            verify_instruction = (
                "For each claim, verify it against the actual source content provided. "
                "Check that specific numbers, dates, names, and causal claims appear in the source text."
            )
    else:
        verify_instruction = (
            "For each claim, assess whether it is plausibly supported by the cited source. "
            "If no direct quote is available, use the source title and URL as context."
        )

    query_context = (
        f"\nResearch question: {research_query}\n"
        if research_query else ""
    )
    prompt = f"""Verify each of the following {len(batch)} claims.
Each claim was extracted from its cited source by an AI system.
{query_context}
{chr(10).join(claims_text)}

{verify_instruction}"""

    # Retry up to 3 times for transient errors (network, rate limit)

    # FIX-059-B: NLI faithfulness threshold. A claim is faithful only if
    # NLI score (when available) meets this minimum. Prevents LLM verdicts
    # from overriding low NLI scores (e.g., NLI=0.526 + LLM="SUPPORTED").
    _nli_faith_threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))

    last_exc = None
    for attempt in range(3):
        try:
            # AREA-1: Use generate_structured() with reasoning ON for deep thinking.
            # Reasoning happens in reasoning_content (not duplicated in JSON output
            # since we removed reasoning field from ClaimVerification schema).
            # FIX-MP1: Configurable per-call timeout (was hardcoded 120s, caused
            # 70+ batch timeouts in PG_TEST_033 with batch_size=10 + 3000 chars/claim)
            per_call_timeout = int(os.getenv("PG_VERIFY_PER_CALL_TIMEOUT", "300"))
            parsed = await client.generate_structured(
                prompt=prompt,
                schema=VerificationBatch,
                system=VERIFICATION_SYSTEM,
                max_tokens=8192,
                timeout=per_call_timeout,
                reasoning_enabled=True,
            )

            # OBS-5: Count verdicts for tracing
            supported_count = 0
            partial_count_obs = 0
            not_supported_count = 0

            verified: list[VerifiedClaim] = []
            for i, verification in enumerate(parsed.verifications):
                if i >= len(batch):
                    break

                ev = batch[i]

                # FIX-F1: PARTIALLY_SUPPORTED no longer counts as faithful
                # (aligns with RAGAS methodology - strict binary)
                # FIX-059-B: Enforce NLI threshold on faithfulness verdict.
                # A claim is faithful only if LLM says SUPPORTED AND NLI score
                # (when available on the evidence) meets the threshold.
                # FIX-B2: Read NLI score from EITHER field — nli_score (set by
                # normal NLI path) or nli_self_check_score (preserved by FIX-B2
                # when NLI floor triggers full discard).
                # Use `is not None` instead of `or` — 0.0 is a valid NLI score
                # (completely unsupported), not falsy.
                _ev_nli_raw = ev.get("nli_score")
                _ev_nli = _ev_nli_raw if _ev_nli_raw is not None else ev.get("nli_self_check_score")
                is_faithful = verification.verdict == "SUPPORTED"
                if is_faithful and _ev_nli is not None and _ev_nli < _nli_faith_threshold:
                    is_faithful = False
                    logger.debug(
                        "[polaris graph] FIX-059-B: NLI threshold override: "
                        "claim %d verdict=SUPPORTED but nli_score=%.3f < %.2f",
                        i + 1, _ev_nli, _nli_faith_threshold,
                    )
                method = (
                    "partial" if verification.verdict == "PARTIALLY_SUPPORTED"
                    else "not_supported" if verification.verdict == "NOT_SUPPORTED"
                    else "atomic"
                )
                # FIX-P1: NLI-based verdict override. When NLI score is available,
                # override LLM verdict to reflect actual evidence quality:
                # - NLI >= 0.75: SUPPORTED (keep LLM verdict)
                # - NLI 0.50-0.75: PARTIALLY_SUPPORTED (borderline)
                # - NLI < 0.50: NOT_SUPPORTED (insufficient evidence)
                if _ev_nli is not None and verification.verdict == "SUPPORTED":
                    if _ev_nli < 0.50:
                        method = "not_supported"
                        is_faithful = False
                        logger.debug(
                            "[polaris graph] FIX-P1: NLI override to NOT_SUPPORTED: "
                            "claim %d nli=%.3f < 0.50", i + 1, _ev_nli,
                        )
                    elif _ev_nli < _nli_faith_threshold:
                        method = "partial"
                        # is_faithful already False from FIX-059-B block above
                        logger.debug(
                            "[polaris graph] FIX-P1: NLI override to PARTIAL: "
                            "claim %d nli=%.3f < %.2f", i + 1, _ev_nli, _nli_faith_threshold,
                        )

                # FIX-B2: Determine verification basis
                # FIX-STUB: If content was suppressed for this claim (paywall/stub),
                # override basis to quote_only regardless of url_content_map
                source_url = ev.get("source_url", "")
                source_content = ""
                if url_content_map and source_url:
                    # FIX-URL-NORM: Try normalized URL first, then original
                    source_content = url_content_map.get(source_url, "") or url_content_map.get(_normalize_url(source_url), "")
                has_content = bool(source_content) and i not in stub_suppressed_indices
                has_quote = bool(ev.get("direct_quote", ""))
                if has_content:
                    basis = "content"
                elif has_quote:
                    basis = "quote_only"
                else:
                    basis = "title_only"
                    # FIX-H9: Warn when verification has no content or quote.
                    # Title-only verification is unreliable — insufficient basis.
                    logger.debug(
                        "[polaris graph] FIX-H9: Insufficient verification basis for "
                        "claim %d from %s — title_only (no content, no quote)",
                        i + 1, source_url[:80],
                    )
                    is_faithful = False  # Cannot verify without evidence

                # OBS-5: Track verdict counts
                if verification.verdict == "SUPPORTED":
                    supported_count += 1
                elif verification.verdict == "PARTIALLY_SUPPORTED":
                    partial_count_obs += 1
                else:
                    not_supported_count += 1

                logger.debug(
                    "[polaris graph] Claim %d: verdict=%s, conf=%.2f, faithful=%s, "
                    "method=%s, basis=%s",
                    i + 1,
                    verification.verdict,
                    verification.confidence,
                    is_faithful,
                    method,
                    basis,
                )

                # FIX-047-K4: Mark self-referential verification.
                primary_eid = ev.get("evidence_id", f"claim_{i}")
                verified.append(
                    VerifiedClaim(
                        claim_id=primary_eid,
                        statement=verification.claim or ev.get("statement", ""),
                        evidence_ids=[primary_eid],
                        # FIX-059-B: Use NLI score as confidence when available.
                        # LLM always self-assesses 0.90-0.95 which inflates metrics.
                        # FIX-060-A: When NLI unavailable, cap LLM confidence by basis.
                        confidence=_ev_nli if _ev_nli and _ev_nli > 0 else _basis_aware_confidence(verification.confidence, basis),
                        verification_method=method,
                        is_faithful=is_faithful,
                        section_id=None,
                        reasoning=f"verdict={verification.verdict} basis={basis}",
                        verification_basis=basis,
                        verification_type="extraction_self_check",
                        nli_score=_ev_nli,
                        cross_source_score=None,
                        verdict=verification.verdict,  # FIX-B4: Human-readable verdict
                        source_url=source_url,  # FIX-B5: Source URL verified against
                        direct_quote=ev.get("direct_quote", ""),  # FIX-B5: Evidence quote
                    )
                )

            # OBS-5: Trace verification batch
            tracer = get_tracer()
            if tracer:
                tracer.llm_call(
                    "verify", "verification_batch",
                    batch_size=len(batch),
                    supported=supported_count,
                    partial=partial_count_obs,
                    not_supported=not_supported_count,
                    claims=[{
                        "id": c.get("claim_id", "")[:20],
                        "verdict": {"atomic": "SUPPORTED", "partial": "PARTIAL", "not_supported": "NOT_SUPPORTED"}.get(c.get("verification_method", ""), c.get("verification_method", "")),
                        "confidence": round(c.get("confidence", 0), 3),
                        "faithful": c.get("is_faithful"),
                        "statement": c.get("statement", "")[:150],
                    } for c in verified[:10]],
                )

            # FIX-V4: Detect index mismatch — LLM returned fewer verifications
            if len(parsed.verifications) < len(batch):
                missing_count = len(batch) - len(parsed.verifications)
                logger.warning(
                    "[polaris graph] FIX-V4: LLM returned %d verifications for "
                    "%d claims — creating api_error placeholders for %d unmatched",
                    len(parsed.verifications),
                    len(batch),
                    missing_count,
                )
                for idx in range(len(parsed.verifications), len(batch)):
                    ev = batch[idx]
                    verified.append(
                        VerifiedClaim(
                            claim_id=ev.get("evidence_id", f"api_error_partial_{idx}"),
                            statement=ev.get("statement", ""),
                            evidence_ids=[ev.get("evidence_id", "")],
                            confidence=0.0,
                            verification_method="api_error",
                            is_faithful=None,
                            section_id=None,
                            reasoning="FIX-V4: LLM returned fewer verifications than claims",
                            verification_basis="none",
                            verification_type="api_error",
                            nli_score=None,
                            cross_source_score=None,
                            verdict="NO_VERDICT",  # FIX-B4
                            source_url=ev.get("source_url", ""),  # FIX-B5
                            direct_quote=ev.get("direct_quote", ""),  # FIX-B5
                        )
                    )

            return verified

        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                wait = 2 ** (attempt + 1)  # 2s, 4s
                logger.warning(
                    "[polaris graph] Verification batch attempt %d failed: %s, "
                    "retrying in %ds",
                    attempt + 1,
                    str(exc)[:100],
                    wait,
                )
                await asyncio.sleep(wait)

    logger.error(
        "[polaris graph] Verification batch failed after 3 attempts: %s",
        str(last_exc)[:200],
    )
    # FIX-SD5: Proper sentinel — excluded from faithfulness calc
    # api_error claims with is_faithful=None are excluded from faithfulness calculation
    # by the caller (verification_method="api_error" filter).
    return [
        VerifiedClaim(
            claim_id=ev.get("evidence_id", f"claim_{i}"),
            statement=ev.get("statement", ""),
            evidence_ids=[ev.get("evidence_id", "")],
            confidence=0.0,
            verification_method="api_error",
            is_faithful=None,  # FIX-SD5: Proper sentinel — excluded from faithfulness calc
            section_id=None,
            reasoning="API error — verification could not be performed",
            verification_basis="none",
            verification_type="api_error",
            nli_score=None,
            cross_source_score=None,
            verdict="NO_VERDICT",  # FIX-B4
            source_url=ev.get("source_url", ""),  # FIX-B5
            direct_quote=ev.get("direct_quote", ""),  # FIX-B5
        )
        for i, ev in enumerate(batch)
    ]


def _triangulate_claims(
    evidence: list[EvidencePiece],
) -> dict[str, int]:
    """FIX-S2: Count how many independent sources support similar claims.

    Uses simple word overlap (Jaccard similarity > 0.4) to group
    evidence pieces making similar statements from different sources.
    Returns a mapping of evidence_id -> corroborating_source_count.

    BUG-092: Caps evidence to PG_MAX_TRIANGULATE_EVIDENCE (default 500)
    to avoid O(n^2) scaling. Sorts by tier+relevance and takes top N.
    """
    # BUG-092: Cap evidence to prevent O(n^2) scaling
    max_evidence = int(os.getenv("PG_MAX_TRIANGULATE_EVIDENCE", "500"))
    if len(evidence) > max_evidence:
        logger.warning(
            "[polaris graph] BUG-092: Capping triangulation from %d to %d evidence",
            len(evidence), max_evidence,
        )
        tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
        evidence = sorted(
            evidence,
            key=lambda e: (
                tier_order.get(e.get("quality_tier", e.get("tier", "BRONZE")), 2),
                -(e.get("relevance_score", 0) or 0),
            ),
        )[:max_evidence]

    corroboration: dict[str, int] = {}
    n = len(evidence)

    for i in range(n):
        stmt_i = set(evidence[i].get("statement", "").lower().split())
        url_i = evidence[i].get("source_url", "")
        if len(stmt_i) < 5:
            continue

        source_count = 1  # Count self
        for j in range(n):
            if i == j:
                continue
            url_j = evidence[j].get("source_url", "")
            if url_j == url_i:
                continue  # Same source doesn't count
            stmt_j = set(evidence[j].get("statement", "").lower().split())
            if len(stmt_j) < 5:
                continue
            intersection = len(stmt_i & stmt_j)
            union = len(stmt_i | stmt_j)
            if union > 0 and intersection / union > 0.4:
                source_count += 1

        eid = evidence[i].get("evidence_id", "")
        corroboration[eid] = source_count

    return corroboration


def _group_by_source(
    evidence: list[EvidencePiece],
) -> dict[str, list[EvidencePiece]]:
    """Group evidence by source URL."""
    groups: dict[str, list[EvidencePiece]] = {}
    for ev in evidence:
        url = ev.get("source_url", "unknown")
        if url not in groups:
            groups[url] = []
        groups[url].append(ev)
    return groups


def link_corroborating_evidence(
    claims: list[VerifiedClaim],
    evidence: list[EvidencePiece],
    cross_reference_groups: list[dict],
    max_per_claim: int = 5,
) -> int:
    """FIX-045H: Enrich claims with corroborating evidence IDs.

    For each claim, finds evidence pieces making similar statements from
    different sources (via cross-reference groups or Jaccard fallback)
    and adds their IDs to the claim's evidence_ids list.

    Args:
        claims: Verified claims to enrich (mutated in place).
        evidence: Full evidence pool for Jaccard fallback.
        cross_reference_groups: Groups from compute_cross_references().
        max_per_claim: Maximum corroborating evidence per claim.

    Returns:
        Number of claims enriched with additional evidence.
    """
    if not claims:
        return 0

    # Use env var only when caller uses the default (5)
    if max_per_claim == 5:
        max_per_claim = int(os.getenv("PG_CORROBORATION_MAX_PER_CLAIM", "5"))
    enriched_count = 0

    # FIX-047-K5: Claim-level similarity threshold for corroboration.
    # T047 audit found 184/231 claims (79.7%) padded with 5 generic evidence IDs
    # that had topic-level match but ZERO claim-level relevance. A claim about
    # "Stratmoor Hills water treatment plant" was "supported" by Astute Analytica
    # market analysis. Now requires statement-level Jaccard similarity >= threshold.
    corr_sim_threshold = float(
        os.getenv("PG_CORROBORATION_SIM_THRESHOLD", "0.15")
    )

    # Build evidence statement lookup for similarity checking
    eid_to_statement_words: dict[str, set[str]] = {}
    eid_to_url: dict[str, str] = {}
    for ev in evidence:
        eid = ev.get("evidence_id", "")
        if eid:
            words = set(ev.get("statement", "").lower().split())
            # Remove very common stopwords to improve similarity signal
            words -= {"the", "a", "an", "is", "are", "was", "were", "of", "in",
                       "to", "for", "and", "or", "that", "this", "with", "on",
                       "by", "from", "as", "at", "be", "it", "has", "have", "had"}
            eid_to_statement_words[eid] = words
            eid_to_url[eid] = ev.get("source_url", "")

    if cross_reference_groups:
        # Build index: evidence_id -> set of all evidence_ids in same group(s)
        eid_to_corroborating: dict[str, set[str]] = {}
        for group in cross_reference_groups:
            group_eids = set(group.get("evidence_ids", []))
            for eid in group_eids:
                if eid not in eid_to_corroborating:
                    eid_to_corroborating[eid] = set()
                eid_to_corroborating[eid].update(group_eids)

        filtered_out = 0
        for claim in claims:
            primary_eid = claim["evidence_ids"][0] if claim.get("evidence_ids") else ""
            if not primary_eid:
                continue
            corroborating = eid_to_corroborating.get(primary_eid, set())
            corroborating = corroborating - {primary_eid}
            if not corroborating:
                continue

            # FIX-047-K5: Filter by statement-level similarity
            primary_words = eid_to_statement_words.get(primary_eid, set())
            primary_url = eid_to_url.get(primary_eid, "")
            if len(primary_words) < 3:
                continue

            scored_corr: list[tuple[float, str]] = []
            for ceid in corroborating:
                # Skip same-source corroboration (not independent)
                if eid_to_url.get(ceid, "") == primary_url:
                    continue
                cand_words = eid_to_statement_words.get(ceid, set())
                if len(cand_words) < 3:
                    filtered_out += 1
                    continue
                intersection = len(primary_words & cand_words)
                union = len(primary_words | cand_words)
                sim = intersection / union if union > 0 else 0.0
                if sim >= corr_sim_threshold:
                    scored_corr.append((sim, ceid))
                else:
                    filtered_out += 1

            if not scored_corr:
                continue
            scored_corr.sort(reverse=True)
            sorted_corr = [eid for _, eid in scored_corr[:max_per_claim]]
            claim["evidence_ids"] = [primary_eid] + sorted_corr
            # FIX-047-K4: Mark as independently corroborated
            claim["verification_type"] = "independent_cross_source"
            enriched_count += 1

        if filtered_out:
            logger.info(
                "[polaris graph] FIX-047-K5: Filtered %d irrelevant corroboration "
                "candidates (Jaccard < %.2f)",
                filtered_out, corr_sim_threshold,
            )
    else:
        # Fallback: Jaccard similarity (same approach as _triangulate_claims
        # but returns actual evidence IDs, not just counts)

        # BUG-092: Cap evidence to prevent O(n^2) scaling in Jaccard fallback
        max_corr_evidence = int(os.getenv("PG_MAX_CORROBORATION_EVIDENCE", "500"))
        if len(evidence) > max_corr_evidence:
            logger.warning(
                "[polaris graph] BUG-092: Capping corroboration evidence from %d to %d",
                len(evidence), max_corr_evidence,
            )
            tier_order = {"GOLD": 0, "SILVER": 1, "BRONZE": 2}
            evidence = sorted(
                evidence,
                key=lambda e: (
                    tier_order.get(e.get("quality_tier", e.get("tier", "BRONZE")), 2),
                    -(e.get("relevance_score", 0) or 0),
                ),
            )[:max_corr_evidence]

        n = len(evidence)
        if n < 2:
            return 0

        word_sets: list[set[str]] = []
        ev_urls: list[str] = []
        ev_ids: list[str] = []
        for ev in evidence:
            words = ev.get("statement", "").lower().split()
            word_sets.append(set(words))
            ev_urls.append(ev.get("source_url", ""))
            ev_ids.append(ev.get("evidence_id", ""))

        eid_to_idx = {eid: i for i, eid in enumerate(ev_ids)}
        jaccard_threshold = float(
            os.getenv("PG_CORROBORATION_JACCARD_THRESHOLD", "0.35")
        )

        for claim in claims:
            primary_eid = claim["evidence_ids"][0] if claim.get("evidence_ids") else ""
            if not primary_eid or primary_eid not in eid_to_idx:
                continue

            i = eid_to_idx[primary_eid]
            if len(word_sets[i]) < 5:
                continue

            candidates: list[tuple[float, str]] = []
            for j in range(n):
                if i == j or ev_urls[j] == ev_urls[i]:
                    continue
                if len(word_sets[j]) < 5:
                    continue
                intersection = len(word_sets[i] & word_sets[j])
                union = len(word_sets[i] | word_sets[j])
                if union > 0 and intersection / union > jaccard_threshold:
                    candidates.append((intersection / union, ev_ids[j]))

            if not candidates:
                continue
            candidates.sort(reverse=True)
            sorted_corr = [eid for _, eid in candidates[:max_per_claim]]
            claim["evidence_ids"] = [primary_eid] + sorted_corr
            enriched_count += 1

    logger.info(
        "[polaris graph] FIX-045H: Enriched %d/%d claims with corroborating "
        "evidence (method=%s, max_per_claim=%d)",
        enriched_count,
        len(claims),
        "cross_reference" if cross_reference_groups else "jaccard_fallback",
        max_per_claim,
    )
    return enriched_count


_contradiction_model = None
_contradiction_model_lock = asyncio.Lock()


def _get_contradiction_model():
    """FIX-048-K14: Lazy-load cross-encoder/nli-deberta-v3-base for contradiction detection.

    Returns CrossEncoder instance or None if unavailable.
    Model: 184M params, 90.04% MNLI, three-way classification.
    """
    global _contradiction_model
    if _contradiction_model is not None:
        return _contradiction_model

    try:
        from sentence_transformers import CrossEncoder
        model_name = os.getenv(
            "PG_CONTRADICTION_MODEL", "cross-encoder/nli-deberta-v3-base",
        )
        logger.info(
            "[polaris graph] FIX-048-K14: Loading NLI CrossEncoder '%s' "
            "for contradiction detection...",
            model_name,
        )
        t0 = time.time()
        _contradiction_model = CrossEncoder(model_name)
        elapsed = time.time() - t0
        logger.info(
            "[polaris graph] FIX-048-K14: CrossEncoder loaded in %.1fs", elapsed,
        )
        return _contradiction_model
    except ImportError:
        logger.warning(
            "[polaris graph] FIX-048-K14: sentence-transformers CrossEncoder not "
            "available — falling back to keyword heuristic"
        )
        return None
    except Exception as exc:
        logger.error(
            "[polaris graph] FIX-048-K14: CrossEncoder load failed: %s — "
            "falling back to keyword heuristic",
            str(exc)[:200],
        )
        return None


def detect_contradictions(
    claims: list[VerifiedClaim],
    similarity_threshold: float = 0.3,
    contradiction_threshold: float = 0.7,
) -> list[dict]:
    """FIX-048-K14: Detect contradictory claims using NLI CrossEncoder.

    Replaces Jaccard + keyword heuristic (FIX-047-K14) with proper NLI model
    (cross-encoder/nli-deberta-v3-base, 90.04% MNLI accuracy).

    Approach:
    1. Pre-filter topically related pairs using Jaccard similarity (O(n) -> O(k))
    2. Run CrossEncoder NLI on candidate pairs (three-way: contradiction/entailment/neutral)
    3. Return pairs with contradiction score >= threshold

    Falls back to keyword heuristic if CrossEncoder unavailable.

    Uses env vars:
    - PG_CONTRADICTION_ENABLED (default: 1)
    - PG_CONTRADICTION_SIM_THRESHOLD (default: 0.3) — Jaccard pre-filter
    - PG_CONTRADICTION_NLI_THRESHOLD (default: 0.7) — NLI contradiction score
    - PG_CONTRADICTION_MODEL (default: cross-encoder/nli-deberta-v3-base)
    """
    if os.getenv("PG_CONTRADICTION_ENABLED", "1") != "1":
        return []

    sim_threshold = float(
        os.getenv("PG_CONTRADICTION_SIM_THRESHOLD", str(similarity_threshold))
    )
    nli_threshold = float(
        os.getenv("PG_CONTRADICTION_NLI_THRESHOLD", str(contradiction_threshold))
    )

    if len(claims) < 2:
        return []

    # Step 1: Pre-filter topically related pairs using Jaccard similarity
    stopwords = {"the", "a", "an", "is", "are", "was", "were", "of", "in",
                 "to", "for", "and", "or", "that", "this", "with", "on",
                 "by", "from", "as", "at", "be", "it", "has", "have", "had",
                 "can", "will", "do", "does", "not", "no"}

    claim_words: list[set[str]] = []
    claim_stmts: list[str] = []
    for c in claims:
        stmt = c.get("statement", "").lower()
        words = set(stmt.split()) - stopwords
        claim_words.append(words)
        claim_stmts.append(stmt)

    # Find candidate pairs (Jaccard >= threshold, reduces O(n^2) to manageable set)
    candidate_pairs: list[tuple[int, int, float]] = []  # (i, j, jaccard)
    n = len(claims)
    for i in range(n):
        if len(claim_words[i]) < 3:
            continue
        for j in range(i + 1, n):
            if len(claim_words[j]) < 3:
                continue
            intersection = len(claim_words[i] & claim_words[j])
            union = len(claim_words[i] | claim_words[j])
            if union == 0:
                continue
            sim = intersection / union
            if sim >= sim_threshold:
                candidate_pairs.append((i, j, sim))

    if not candidate_pairs:
        logger.info(
            "[polaris graph] FIX-048-K14: No topically related pairs among "
            "%d claims (sim_threshold=%.2f)",
            n, sim_threshold,
        )
        return []

    # BUG-092: Cap contradiction pairs to prevent O(n^2) NLI calls
    max_pairs = int(os.getenv("PG_MAX_CONTRADICTION_PAIRS", "1000"))
    if len(candidate_pairs) > max_pairs:
        logger.info(
            "[polaris graph] BUG-092: Capping contradiction pairs from %d to %d",
            len(candidate_pairs), max_pairs,
        )
        candidate_pairs.sort(key=lambda x: x[2], reverse=True)
        candidate_pairs = candidate_pairs[:max_pairs]

    logger.info(
        "[polaris graph] FIX-048-K14: Found %d candidate pairs for contradiction "
        "checking (Jaccard >= %.2f)",
        len(candidate_pairs), sim_threshold,
    )

    # Step 2: Try NLI CrossEncoder for proper contradiction detection
    model = _get_contradiction_model()
    if model is not None:
        return _nli_contradiction_detection(
            model, claims, claim_stmts, candidate_pairs, nli_threshold, n,
        )

    # Step 3: Fallback — keyword heuristic (pre-FIX-048 behavior)
    return _keyword_contradiction_fallback(
        claims, claim_words, claim_stmts, candidate_pairs, n,
    )


def _nli_contradiction_detection(
    model,
    claims: list[VerifiedClaim],
    claim_stmts: list[str],
    candidate_pairs: list[tuple[int, int, float]],
    nli_threshold: float,
    total_claims: int,
) -> list[dict]:
    """Run CrossEncoder NLI on candidate pairs for contradiction detection.

    cross-encoder/nli-deberta-v3-base returns 3 scores per pair:
    [contradiction, entailment, neutral]. We use the contradiction score.
    """
    t0 = time.time()

    # Prepare sentence pairs for CrossEncoder
    sentence_pairs = [
        (claim_stmts[i][:512], claim_stmts[j][:512])
        for i, j, _ in candidate_pairs
    ]

    try:
        # CrossEncoder.predict() returns scores for each label
        # For nli-deberta-v3-base: labels = ['contradiction', 'entailment', 'neutral']
        scores = model.predict(
            sentence_pairs,
            apply_softmax=True,
        )
    except Exception as exc:
        logger.warning(
            "[polaris graph] FIX-048-K14: CrossEncoder prediction failed: %s — "
            "falling back to keyword heuristic",
            str(exc)[:200],
        )
        return []

    elapsed = time.time() - t0

    # Extract contradictions above threshold
    contradictions = []
    for pair_idx, (i, j, jaccard) in enumerate(candidate_pairs):
        if pair_idx >= len(scores):
            break

        # scores[pair_idx] = [contradiction_score, entailment_score, neutral_score]
        pair_scores = scores[pair_idx]
        if len(pair_scores) < 3:
            continue

        contradiction_score = float(pair_scores[0])
        entailment_score = float(pair_scores[1])

        if contradiction_score >= nli_threshold:
            contradictions.append({
                "claim_a_id": claims[i].get("claim_id", ""),
                "claim_a_statement": claim_stmts[i][:200],
                "claim_b_id": claims[j].get("claim_id", ""),
                "claim_b_statement": claim_stmts[j][:200],
                "similarity": round(jaccard, 3),
                "contradiction_score": round(contradiction_score, 4),
                "entailment_score": round(entailment_score, 4),
                "reason": f"NLI CrossEncoder: contradiction={contradiction_score:.3f}, "
                          f"entailment={entailment_score:.3f}",
            })

    if contradictions:
        logger.info(
            "[polaris graph] FIX-048-K14: NLI detected %d contradictions among "
            "%d pairs (%d claims) in %.1fs (threshold=%.2f)",
            len(contradictions), len(candidate_pairs), total_claims,
            elapsed, nli_threshold,
        )
    else:
        logger.info(
            "[polaris graph] FIX-048-K14: NLI found no contradictions among "
            "%d pairs (%d claims) in %.1fs (threshold=%.2f)",
            len(candidate_pairs), total_claims, elapsed, nli_threshold,
        )

    return contradictions


def _keyword_contradiction_fallback(
    claims: list[VerifiedClaim],
    claim_words: list[set[str]],
    claim_stmts: list[str],
    candidate_pairs: list[tuple[int, int, float]],
    total_claims: int,
) -> list[dict]:
    """Fallback: keyword-based contradiction detection (pre-FIX-048 behavior).

    Used when CrossEncoder model is unavailable.
    """
    _positive = {"effective", "efficient", "simple", "uniform", "consistent",
                 "cost-effective", "low-cost", "reliable", "successful", "destroys",
                 "destruction", "complete", "adequate", "sufficient"}
    _negative = {"ineffective", "inefficient", "complex", "inconsistent",
                 "variable", "expensive", "costly", "high-cost", "unreliable",
                 "limited", "challenges", "difficult", "inadequate", "insufficient"}
    _negation = {"not", "no", "never", "without", "lacks", "lacking",
                 "limited", "fails", "cannot", "unable"}

    contradictions = []
    for i, j, sim in candidate_pairs:
        words_i = claim_words[i]
        words_j = claim_words[j]

        has_pos_i = bool(words_i & _positive)
        has_neg_i = bool(words_i & _negative)
        has_pos_j = bool(words_j & _positive)
        has_neg_j = bool(words_j & _negative)
        has_negation_i = bool(words_i & _negation)
        has_negation_j = bool(words_j & _negation)

        is_contradiction = False
        reason = ""

        if has_pos_i and has_neg_j:
            is_contradiction = True
            pos_word = (words_i & _positive).pop()
            neg_word = (words_j & _negative).pop()
            reason = f"Keyword: Claim A uses '{pos_word}', Claim B uses '{neg_word}'"
        elif has_neg_i and has_pos_j:
            is_contradiction = True
            neg_word = (words_i & _negative).pop()
            pos_word = (words_j & _positive).pop()
            reason = f"Keyword: Claim A uses '{neg_word}', Claim B uses '{pos_word}'"
        elif has_negation_i != has_negation_j and sim >= 0.4:
            is_contradiction = True
            reason = "Keyword: One claim uses negation, the other doesn't"

        if is_contradiction:
            contradictions.append({
                "claim_a_id": claims[i].get("claim_id", ""),
                "claim_a_statement": claim_stmts[i][:200],
                "claim_b_id": claims[j].get("claim_id", ""),
                "claim_b_statement": claim_stmts[j][:200],
                "similarity": round(sim, 3),
                "reason": reason,
            })

    if contradictions:
        logger.info(
            "[polaris graph] FIX-048-K14: Keyword fallback detected %d "
            "contradictions among %d pairs (%d claims)",
            len(contradictions), len(candidate_pairs), total_claims,
        )
    else:
        logger.info(
            "[polaris graph] FIX-048-K14: No contradictions detected among "
            "%d claims (keyword fallback)",
            total_claims,
        )

    return contradictions
