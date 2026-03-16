"""ARCH-2: Subgraph decomposition for verification with per-batch checkpointing.

LangGraph only checkpoints at node boundaries. The verify node processes 260+
batches over 3+ hours — a crash loses everything. This module splits verification
into a subgraph where each batch of evidence is a separate node, enabling
per-batch checkpointing.

Usage:
    subgraph = build_verify_subgraph()
    result = await subgraph.ainvoke(batch_state, config={"configurable": {...}})

Note: This is a future-ready module. The current pipeline uses the simpler
FIX-V10 (SQLite batch progress) for crash recovery. This subgraph approach
can be activated when LangGraph's subgraph checkpointing matures.
"""

import asyncio
import logging
import os
from typing import Any, TypedDict

logger = logging.getLogger(__name__)

PG_VERIFY_SUBGRAPH_BATCH = int(os.getenv("PG_VERIFY_SUBGRAPH_BATCH", "100"))
PG_VERIFY_SUBGRAPH_ENABLED = os.getenv("PG_VERIFY_SUBGRAPH_ENABLED", "0") == "1"


class VerifyBatchState(TypedDict):
    """State for a single verification batch within the subgraph."""
    evidence_batch: list[dict]
    batch_index: int
    url_content_map: dict[str, str]
    claims: list[dict]
    query: str


async def verify_with_batched_subgraph(
    evidence: list[dict],
    url_content_map: dict[str, str],
    query: str,
    verify_fn: Any,
    thread_id: str = "default",
) -> list[dict]:
    """Split evidence into batches and verify each with separate checkpointing.

    Args:
        evidence: Full list of evidence to verify.
        url_content_map: URL -> content mapping for verification.
        query: Research query.
        verify_fn: Async function(batch, url_content_map) -> list[VerifiedClaim].
        thread_id: Thread ID for checkpoint namespacing.

    Returns:
        List of all verified claims across all batches.
    """
    if not PG_VERIFY_SUBGRAPH_ENABLED:
        logger.debug("[polaris graph] ARCH-2: Subgraph disabled, using direct verification")
        return []  # Signal caller to use direct verification

    batch_size = PG_VERIFY_SUBGRAPH_BATCH
    all_claims = []

    # Use FIX-V10 batch progress for persistence
    from src.polaris_graph.batch_progress import BatchProgress
    progress = BatchProgress("verify_subgraph", thread_id=thread_id)
    completed = progress.load_completed_batches()

    total_batches = (len(evidence) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        # Skip already-completed batches (crash recovery)
        if batch_idx in completed:
            all_claims.extend(completed[batch_idx])
            continue

        start = batch_idx * batch_size
        end = min(start + batch_size, len(evidence))
        batch = evidence[start:end]

        logger.info(
            "[polaris graph] ARCH-2: Verifying batch %d/%d (%d evidence)",
            batch_idx + 1, total_batches, len(batch),
        )

        try:
            batch_claims = await verify_fn(batch, url_content_map)
            # Persist batch result
            progress.save_batch_result(batch_idx, batch_claims)
            all_claims.extend(batch_claims)
        except Exception as exc:
            logger.error(
                "[polaris graph] ARCH-2: Batch %d failed: %s",
                batch_idx, str(exc)[:200],
            )
            # Create api_error placeholders
            for j, ev in enumerate(batch):
                all_claims.append({
                    "claim_id": ev.get("evidence_id", f"subgraph_error_{batch_idx}_{j}"),
                    "statement": ev.get("statement", ""),
                    "evidence_ids": [ev.get("evidence_id", "")],
                    "confidence": 0.0,
                    "verification_method": "api_error",
                    "is_faithful": None,
                    "section_id": None,
                    "reasoning": f"ARCH-2: Subgraph batch {batch_idx} failed: {str(exc)[:100]}",
                    "verification_basis": "none",
                })

    # Clear progress on successful completion
    progress.clear()
    progress.close()

    logger.info(
        "[polaris graph] ARCH-2: Subgraph verification complete: %d claims "
        "from %d batches (%d recovered from checkpoint)",
        len(all_claims), total_batches, len(completed),
    )

    return all_claims
