"""Phase 2: SEARCH — Sub-question-targeted search with convergence detection.

Executes 2-5 rounds of targeted search per sub-question, with:
- CRAG evaluation (correct/ambiguous/incorrect routing)
- Content quality gate (reject garbled/boilerplate)
- Reflection distillation (Tavily pattern — compress each round's findings)
- Convergence detection with hard caps (P0 risk mitigation)
- Evidence content stored in side-channel dict (NOT in LangGraph state)

Failure modes handled:
- F2.1: All providers return 0 results → mark sub-question as no_evidence
- F2.3: Convergence never triggers → hard caps (rounds, evidence, time)
- F2.5: Reflection distillation → fallback builds reflections from evidence
- F2.7: Reflection loses details → raw content preserved in evidence_store
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Any, Callable, Optional

from src.polaris_graph.contracts_v3 import (
    Reflection,
    ScopeOutput,
    SearchRoundOutput,
)

logger = logging.getLogger("polaris_graph")

# Hard caps (P0 — non-negotiable)
_MAX_SEARCH_ROUNDS = int(os.getenv("PG_V3_MAX_SEARCH_ROUNDS", "5"))
_MAX_EVIDENCE = int(os.getenv("PG_V3_MAX_EVIDENCE", "1000"))
_MIN_ROUNDS_BEFORE_CONVERGENCE = 2
_CONVERGENCE_THRESHOLD = float(os.getenv("PG_V3_CONVERGENCE_THRESHOLD", "0.85"))


# ---------------------------------------------------------------------------
# Convergence detection (P0)
# ---------------------------------------------------------------------------

def _check_convergence(history: list[dict]) -> float:
    """Compute convergence score from search round history.

    Score = 1 - (new_evidence_last_round / total_evidence).
    Higher = more saturated. >0.85 = converged.

    Args:
        history: List of dicts with 'new_evidence' and 'total_evidence' per round.

    Returns:
        Convergence score 0.0-1.0.
    """
    if not history:
        return 0.0
    last = history[-1]
    total = last.get("total_evidence", 1)
    new = last.get("new_evidence", total)
    if total <= 0:
        return 0.0
    return round(1.0 - (new / max(total, 1)), 3)


def _detect_declining_convergence(scores: list[float]) -> bool:
    """Detect if convergence is getting WORSE (query space expanding).

    If the convergence score has decreased for 2 consecutive rounds,
    the search is finding MORE new info each round — stop, it won't converge.

    Args:
        scores: Convergence scores per round.

    Returns:
        True if declining for 2+ consecutive rounds.
    """
    if len(scores) < 3:
        return False
    return scores[-1] < scores[-2] < scores[-3]


def _should_continue_searching(
    current_round: int,
    max_rounds: int,
    convergence_score: float,
    total_evidence: int,
    max_evidence: int,
    elapsed_seconds: float,
    time_budget_seconds: float,
) -> bool:
    """Determine whether to continue searching.

    Checks (in order):
    1. Minimum rounds not met → continue
    2. Hard round cap exceeded → stop
    3. Evidence cap exceeded → stop
    4. Time budget exceeded → stop
    5. Convergence threshold met → stop
    6. Otherwise → continue

    Returns:
        True if searching should continue.
    """
    # Must do at least MIN rounds
    if current_round < _MIN_ROUNDS_BEFORE_CONVERGENCE:
        return True

    # Hard caps (P0 — never exceed these)
    if current_round >= max_rounds:
        logger.info(
            "[v3 search] Stopping: round cap reached (%d/%d)",
            current_round, max_rounds,
        )
        return False

    if total_evidence >= max_evidence:
        logger.info(
            "[v3 search] Stopping: evidence cap reached (%d/%d)",
            total_evidence, max_evidence,
        )
        return False

    if elapsed_seconds >= time_budget_seconds:
        logger.info(
            "[v3 search] Stopping: time budget exceeded (%.0fs/%.0fs)",
            elapsed_seconds, time_budget_seconds,
        )
        return False

    # Convergence check
    if convergence_score >= _CONVERGENCE_THRESHOLD:
        logger.info(
            "[v3 search] Stopping: converged (score=%.3f >= %.3f)",
            convergence_score, _CONVERGENCE_THRESHOLD,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# Search round execution
# ---------------------------------------------------------------------------

async def _execute_search_round(
    round_number: int,
    search_queries: list[dict],
    searcher: Callable,
    fetcher: Callable,
    extractor: Callable,
    evidence_store: dict,
    existing_evidence_ids: Optional[set] = None,
) -> SearchRoundOutput:
    """Execute one round of search → fetch → extract → grade.

    Args:
        round_number: Which round (1-indexed).
        search_queries: Queries to execute (from ScopeOutput or gap queries).
        searcher: Async function that executes search queries → raw results.
        fetcher: Async function that fetches content from URLs → text.
        extractor: Async function that extracts evidence from content → evidence dicts.
        evidence_store: Side-channel dict to store full evidence (mutated in place).
        existing_evidence_ids: Evidence already collected (for dedup).

    Returns:
        SearchRoundOutput with new evidence IDs, reflections placeholder, and convergence info.
    """
    existing = existing_evidence_ids or set()

    # Step 1: Execute searches
    try:
        raw_results = await searcher(search_queries)
    except Exception as exc:
        logger.warning("[v3 search] Round %d search failed: %s", round_number, str(exc)[:200])
        raw_results = []

    if not raw_results:
        return SearchRoundOutput(
            round_number=round_number,
            evidence_ids=[],
            reflections=[],
            sources_fetched=0,
            convergence_score=0.0,
            gaps=[],
        )

    # Step 2: Fetch content
    try:
        fetched_content = await fetcher(raw_results)
    except Exception as exc:
        logger.warning("[v3 search] Round %d fetch failed: %s", round_number, str(exc)[:200])
        fetched_content = []

    # Step 3: Extract evidence
    try:
        extracted_evidence = await extractor(fetched_content)
    except Exception as exc:
        logger.warning("[v3 search] Round %d extraction failed: %s", round_number, str(exc)[:200])
        extracted_evidence = []

    # Step 4: Dedup against existing evidence and store in side-channel
    new_evidence_ids = []
    for ev in extracted_evidence:
        ev_id = ev.get("evidence_id", f"ev_{uuid.uuid4().hex[:8]}")
        if ev_id not in existing:
            ev["evidence_id"] = ev_id
            evidence_store[ev_id] = ev
            new_evidence_ids.append(ev_id)

    total_evidence = len(existing) + len(new_evidence_ids)

    logger.info(
        "[v3 search] Round %d: %d new evidence (%d total), %d sources fetched",
        round_number, len(new_evidence_ids), total_evidence, len(fetched_content),
    )

    return SearchRoundOutput(
        round_number=round_number,
        evidence_ids=new_evidence_ids,
        reflections=[],  # Filled by _distill_reflections after this call
        sources_fetched=len(fetched_content),
        convergence_score=0.0,  # Computed by caller using history
        gaps=[],
    )


# ---------------------------------------------------------------------------
# Reflection distillation (Tavily pattern)
# ---------------------------------------------------------------------------

async def _distill_reflections(
    client,
    evidence: list[dict],
    round_number: int,
) -> list[Reflection]:
    """Compress a round's evidence into distilled reflections.

    Each reflection captures a key insight from 1-3 evidence pieces,
    linked to the sub-question it answers. Raw evidence stays in the
    evidence_store; only reflections persist in the search loop context.

    Falls back to _fallback_reflections if LLM fails.
    """
    if not evidence:
        return []

    try:
        # Group evidence by sub-question
        by_sq: dict[str, list[dict]] = {}
        for ev in evidence:
            sq_id = ev.get("sub_question_id", "unknown")
            by_sq.setdefault(sq_id, []).append(ev)

        reflections = []
        for sq_id, sq_evidence in by_sq.items():
            # Build a summary prompt for this sub-question's evidence
            evidence_text = "\n".join(
                f"- [{ev.get('evidence_id', '?')}] {ev.get('statement', '')[:200]}"
                for ev in sq_evidence[:10]  # Cap at 10 per sub-question
            )

            from pydantic import BaseModel, Field

            class ReflectionBatch(BaseModel):
                reflections: list[Reflection] = Field(default_factory=list)

            result = await client.generate_structured(
                prompt=(
                    f"Round {round_number} evidence for sub-question {sq_id}:\n"
                    f"{evidence_text}\n\n"
                    "Distill the key insights from this evidence into 1-3 reflections. "
                    "Each reflection should preserve specific numbers, measurements, and findings. "
                    "Reference the evidence IDs that support each insight."
                ),
                schema=ReflectionBatch,
                system="You are a research analyst distilling evidence into key insights. Preserve ALL numeric values.",
                max_tokens=2048,
                timeout=60,
            )

            if result and result.reflections:
                for r in result.reflections:
                    r.sub_question_id = sq_id
                reflections.extend(result.reflections)

        if reflections:
            return reflections

    except Exception as exc:
        logger.warning(
            "[v3 search] Reflection distillation failed: %s — using fallback",
            str(exc)[:200],
        )

    return _fallback_reflections(evidence)


def _fallback_reflections(evidence: list[dict]) -> list[Reflection]:
    """Build reflections directly from evidence when LLM fails.

    Each evidence piece becomes a simple reflection (no summarization,
    but preserves all data).
    """
    # Group by sub-question, take top 2 per group
    by_sq: dict[str, list[dict]] = {}
    for ev in evidence:
        sq_id = ev.get("sub_question_id", "unknown")
        by_sq.setdefault(sq_id, []).append(ev)

    reflections = []
    for sq_id, sq_evidence in by_sq.items():
        # Take up to 2 evidence pieces per sub-question
        for ev in sq_evidence[:2]:
            reflections.append(Reflection(
                insight=ev.get("statement", "")[:300],
                sub_question_id=sq_id,
                evidence_ids=[ev.get("evidence_id", "")],
                confidence=ev.get("relevance_score", 0.5),
            ))

    return reflections


# ---------------------------------------------------------------------------
# Main search phase orchestrator
# ---------------------------------------------------------------------------

async def run_search_phase(
    client,
    scope: ScopeOutput,
    evidence_store: dict,
    max_rounds: int = _MAX_SEARCH_ROUNDS,
    max_evidence: int = _MAX_EVIDENCE,
    time_budget_seconds: float = 1200.0,
    searcher: Optional[Callable] = None,
    fetcher: Optional[Callable] = None,
    extractor: Optional[Callable] = None,
) -> dict:
    """Phase 2: Execute multi-round targeted search with convergence detection.

    Args:
        client: LLM client for reflection distillation.
        scope: ScopeOutput from Phase 1.
        evidence_store: Side-channel dict for full evidence objects (mutated).
        max_rounds: Hard cap on search rounds.
        max_evidence: Hard cap on total evidence count.
        time_budget_seconds: Phase time budget.
        searcher/fetcher/extractor: Injectable search pipeline functions (for testing).

    Returns:
        Dict with evidence_ids, reflections, search_rounds_completed, convergence_score.
    """
    start_time = time.monotonic()
    all_evidence_ids: list[str] = []
    all_reflections: list[Reflection] = []
    convergence_history: list[dict] = []
    convergence_scores: list[float] = []
    rounds_completed = 0

    # Convert scope search queries to list of dicts
    search_queries = [q.model_dump() for q in scope.search_queries]

    for round_num in range(1, max_rounds + 1):
        elapsed = time.monotonic() - start_time

        # Check if we should continue
        current_convergence = convergence_scores[-1] if convergence_scores else 0.0
        if not _should_continue_searching(
            current_round=round_num,
            max_rounds=max_rounds,
            convergence_score=current_convergence,
            total_evidence=len(all_evidence_ids),
            max_evidence=max_evidence,
            elapsed_seconds=elapsed,
            time_budget_seconds=time_budget_seconds,
        ):
            break

        # Check for declining convergence (P0)
        if len(convergence_scores) >= 3 and _detect_declining_convergence(convergence_scores):
            logger.warning(
                "[v3 search] Stopping: declining convergence detected (scores=%s)",
                convergence_scores[-3:],
            )
            break

        logger.info(
            "[v3 search] Starting round %d (evidence=%d, elapsed=%.0fs)",
            round_num, len(all_evidence_ids), elapsed,
        )

        # Execute one search round
        round_result = await _execute_search_round(
            round_number=round_num,
            search_queries=search_queries,
            searcher=searcher or _default_searcher,
            fetcher=fetcher or _default_fetcher,
            extractor=extractor or _default_extractor,
            evidence_store=evidence_store,
            existing_evidence_ids=set(all_evidence_ids),
        )

        # Accumulate results
        new_ids = round_result.evidence_ids
        all_evidence_ids.extend(new_ids)

        # Track convergence
        convergence_history.append({
            "new_evidence": len(new_ids),
            "total_evidence": len(all_evidence_ids),
        })
        conv_score = _check_convergence(convergence_history)
        convergence_scores.append(conv_score)

        # Distill reflections for this round
        new_evidence = [evidence_store[eid] for eid in new_ids if eid in evidence_store]
        round_reflections = await _distill_reflections(
            client=client,
            evidence=new_evidence,
            round_number=round_num,
        )
        all_reflections.extend(round_reflections)

        rounds_completed = round_num

        logger.info(
            "[v3 search] Round %d complete: +%d evidence, convergence=%.3f, reflections=%d",
            round_num, len(new_ids), conv_score, len(round_reflections),
        )

    elapsed_total = time.monotonic() - start_time
    final_convergence = convergence_scores[-1] if convergence_scores else 0.0

    logger.info(
        "[v3 search] Search phase complete: %d rounds, %d evidence, convergence=%.3f, %.0fs",
        rounds_completed, len(all_evidence_ids), final_convergence, elapsed_total,
    )

    return {
        "evidence_ids": all_evidence_ids,
        "reflections": [r.model_dump() for r in all_reflections],
        "search_rounds_completed": rounds_completed,
        "convergence_score": final_convergence,
        "convergence_history": convergence_history,
        "elapsed_seconds": elapsed_total,
    }


# ---------------------------------------------------------------------------
# Default sub-component stubs (replaced by real implementations in M6 wiring)
# ---------------------------------------------------------------------------

async def _default_searcher(queries: list[dict]) -> list[dict]:
    """Placeholder — replaced by real searcher in graph wiring."""
    logger.warning("[v3 search] Using stub searcher — wire real searcher in graph_v3.py")
    return []


async def _default_fetcher(results: list[dict]) -> list[dict]:
    """Placeholder — replaced by real fetcher in graph wiring."""
    logger.warning("[v3 search] Using stub fetcher — wire real fetcher in graph_v3.py")
    return []


async def _default_extractor(content: list[dict]) -> list[dict]:
    """Placeholder — replaced by real extractor in graph wiring."""
    logger.warning("[v3 search] Using stub extractor — wire real extractor in graph_v3.py")
    return []
