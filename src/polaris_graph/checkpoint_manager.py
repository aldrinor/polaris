"""
Checkpoint manager for polaris graph pipeline.

Uses langgraph-checkpoint-sqlite for state persistence across crashes/restarts.
Each vector gets its own thread_id for independent resume capability.

Amendment A2 (Pipeline Traceback and Rewind):
- list_checkpoints(): Enumerate all saved checkpoints for a vector.
- get_checkpoint_state(): Retrieve full state snapshot at a specific checkpoint.
- rewind_to_checkpoint(): Resume pipeline from a specific checkpoint with optional state patch.
"""

import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Feature flag — checkpointing must be explicitly enabled
PG_CHECKPOINT_ENABLED = os.getenv("PG_CHECKPOINT_ENABLED", "0") == "1"

# Checkpoint storage location
CHECKPOINT_DIR = Path(os.getenv("PG_CHECKPOINT_DIR", "state"))
CHECKPOINT_DB = CHECKPOINT_DIR / "pg_checkpoints.sqlite"

# A2: Maximum number of checkpoints to return from list_checkpoints
PG_CHECKPOINT_LIST_LIMIT = int(os.getenv("PG_CHECKPOINT_LIST_LIMIT", "50"))


def get_checkpointer():
    """Get or create the SQLite checkpointer.

    Returns a SqliteSaver instance backed by CHECKPOINT_DB.
    Creates the directory if it doesn't exist.
    """
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    checkpointer = AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB))
    logger.info(
        "[polaris graph] Checkpoint manager: using %s",
        CHECKPOINT_DB,
    )
    return checkpointer


def get_thread_id(vector_id: str) -> str:
    """Generate a consistent thread ID for a vector."""
    return f"pg_{vector_id}"


async def has_checkpoint(vector_id: str) -> bool:
    """Check if a checkpoint exists for the given vector."""
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    if not CHECKPOINT_DB.exists():
        return False

    thread_id = get_thread_id(vector_id)
    try:
        async with AsyncSqliteSaver.from_conn_string(str(CHECKPOINT_DB)) as saver:
            config = {"configurable": {"thread_id": thread_id}}
            checkpoint = await saver.aget(config)
            return checkpoint is not None
    except Exception as exc:
        logger.warning(
            "[polaris graph] Checkpoint check failed for %s: %s",
            vector_id, str(exc)[:200],
        )
        return False


async def clear_checkpoint(vector_id: str) -> bool:
    """Clear checkpoint for a specific vector.

    Returns True if successfully cleared, False otherwise.
    """
    import aiosqlite

    if not CHECKPOINT_DB.exists():
        return True

    thread_id = get_thread_id(vector_id)
    try:
        async with aiosqlite.connect(str(CHECKPOINT_DB)) as db:
            await db.execute(
                "DELETE FROM checkpoints WHERE thread_id = ?",
                (thread_id,),
            )
            await db.execute(
                "DELETE FROM writes WHERE thread_id = ?",
                (thread_id,),
            )
            await db.commit()
        logger.info(
            "[polaris graph] Cleared checkpoint for %s (thread=%s)",
            vector_id, thread_id,
        )
        return True
    except Exception as exc:
        logger.warning(
            "[polaris graph] Failed to clear checkpoint for %s: %s",
            vector_id, str(exc)[:200],
        )
        return False


# ---------------------------------------------------------------------------
# A2: Pipeline Traceback and Rewind
# ---------------------------------------------------------------------------


def _extract_state_summary(values: dict[str, Any]) -> dict[str, Any]:
    """Extract a lightweight summary from a full state snapshot.

    Pulls out the key metrics that are useful for checkpoint browsing
    without returning the entire (potentially multi-MB) state.
    """
    evidence = values.get("evidence", [])
    evidence_count = len(evidence) if isinstance(evidence, list) else 0

    claims = values.get("claims", [])
    claims_count = len(claims) if isinstance(claims, list) else 0

    sections = values.get("sections", [])
    sections_count = len(sections) if isinstance(sections, list) else 0

    quality_metrics = values.get("quality_metrics")
    faithfulness = None
    if isinstance(quality_metrics, dict):
        faithfulness = quality_metrics.get("faithfulness_pct")
    # Fallback to top-level faithfulness_score
    if faithfulness is None:
        raw_faith = values.get("faithfulness_score")
        if isinstance(raw_faith, (int, float)) and raw_faith >= 0:
            faithfulness = round(raw_faith * 100, 1)

    return {
        "evidence_count": evidence_count,
        "claims_count": claims_count,
        "sections_count": sections_count,
        "iteration": values.get("iteration_count", 0),
        "faithfulness": faithfulness,
        "status": values.get("status", "unknown"),
        "query": str(values.get("original_query", ""))[:200],
        "has_report": bool(values.get("final_report")),
        "word_count": len(values.get("final_report", "").split()) if values.get("final_report") else 0,
    }


async def list_checkpoints(
    vector_id: str,
    app: Any,
) -> list[dict[str, Any]]:
    """List all checkpoints for a vector with state summaries.

    Uses LangGraph's aget_state_history() to enumerate saved checkpoints.
    Returns list of dicts with: checkpoint_id, node (next node scheduled),
    timestamp, evidence_count, iteration, faithfulness.

    Args:
        vector_id: The research vector identifier.
        app: A compiled LangGraph application (CompiledStateGraph) with
             a checkpointer attached.

    Returns:
        List of checkpoint summary dicts, ordered most-recent-first.
        Returns empty list if checkpointing is disabled or no checkpoints exist.
    """
    if not PG_CHECKPOINT_ENABLED:
        logger.info(
            "[polaris graph] A2: list_checkpoints skipped — "
            "PG_CHECKPOINT_ENABLED=0"
        )
        return []

    if not CHECKPOINT_DB.exists():
        logger.debug(
            "[polaris graph] A2: No checkpoint DB at %s", CHECKPOINT_DB
        )
        return []

    thread_id = get_thread_id(vector_id)
    config = {"configurable": {"thread_id": thread_id}}

    checkpoints: list[dict[str, Any]] = []
    try:
        async for snapshot in app.aget_state_history(
            config, limit=PG_CHECKPOINT_LIST_LIMIT
        ):
            # Extract checkpoint_id from the config
            cp_config = snapshot.config or {}
            cp_configurable = cp_config.get("configurable", {})
            checkpoint_id = cp_configurable.get("checkpoint_id", "")

            # next is a tuple of node names scheduled to run next
            next_nodes = snapshot.next if snapshot.next else ()
            node_label = next_nodes[0] if next_nodes else "__end__"

            # State summary
            values = snapshot.values if snapshot.values else {}
            summary = _extract_state_summary(values)

            checkpoints.append({
                "checkpoint_id": checkpoint_id,
                "node": node_label,
                "timestamp": snapshot.created_at or "",
                "evidence_count": summary["evidence_count"],
                "claims_count": summary["claims_count"],
                "sections_count": summary["sections_count"],
                "iteration": summary["iteration"],
                "faithfulness": summary["faithfulness"],
                "status": summary["status"],
                "has_report": summary["has_report"],
                "word_count": summary["word_count"],
                "parent_checkpoint_id": (
                    snapshot.parent_config.get("configurable", {}).get(
                        "checkpoint_id", ""
                    )
                    if snapshot.parent_config
                    else None
                ),
            })

        logger.info(
            "[polaris graph] A2: Listed %d checkpoints for %s",
            len(checkpoints), vector_id,
        )
    except Exception as exc:
        logger.error(
            "[polaris graph] A2: list_checkpoints failed for %s: %s",
            vector_id, str(exc)[:300],
        )

    return checkpoints


async def get_checkpoint_state(
    vector_id: str,
    checkpoint_id: str,
    app: Any,
) -> dict[str, Any]:
    """Get full state snapshot at a specific checkpoint.

    Returns the complete state values at the checkpoint plus metadata
    (checkpoint_id, next node, timestamp, parent checkpoint).

    Args:
        vector_id: The research vector identifier.
        checkpoint_id: The specific checkpoint to retrieve.
        app: A compiled LangGraph application with checkpointer.

    Returns:
        Dict with "metadata" and "state" keys. On error, returns dict
        with "error" key.
    """
    if not PG_CHECKPOINT_ENABLED:
        return {"error": "Checkpointing is disabled (PG_CHECKPOINT_ENABLED=0)"}

    if not CHECKPOINT_DB.exists():
        return {"error": f"No checkpoint database at {CHECKPOINT_DB}"}

    thread_id = get_thread_id(vector_id)
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
        }
    }

    try:
        snapshot = await app.aget_state(config)
        if snapshot is None:
            return {
                "error": (
                    f"No checkpoint found: vector_id={vector_id}, "
                    f"checkpoint_id={checkpoint_id}"
                )
            }

        values = snapshot.values if snapshot.values else {}
        next_nodes = snapshot.next if snapshot.next else ()

        # Serialize state values — handle non-JSON-serializable types
        serialized_state = _serialize_state(values)

        summary = _extract_state_summary(values)

        result: dict[str, Any] = {
            "metadata": {
                "checkpoint_id": checkpoint_id,
                "thread_id": thread_id,
                "vector_id": vector_id,
                "node": next_nodes[0] if next_nodes else "__end__",
                "next_nodes": list(next_nodes),
                "timestamp": snapshot.created_at or "",
                "parent_checkpoint_id": (
                    snapshot.parent_config.get("configurable", {}).get(
                        "checkpoint_id", ""
                    )
                    if snapshot.parent_config
                    else None
                ),
                "summary": summary,
            },
            "state": serialized_state,
        }

        logger.info(
            "[polaris graph] A2: Retrieved checkpoint %s for %s "
            "(node=%s, evidence=%d)",
            checkpoint_id[:12],
            vector_id,
            result["metadata"]["node"],
            summary["evidence_count"],
        )
        return result

    except Exception as exc:
        logger.error(
            "[polaris graph] A2: get_checkpoint_state failed for %s/%s: %s",
            vector_id, checkpoint_id[:12], str(exc)[:300],
        )
        return {"error": f"Failed to retrieve checkpoint: {str(exc)[:500]}"}


async def rewind_to_checkpoint(
    vector_id: str,
    checkpoint_id: str,
    app: Any,
    state_patch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resume pipeline from a specific checkpoint, optionally with state modifications.

    Uses LangGraph's aupdate_state() to apply a patch to the checkpoint state,
    then resumes execution from that point. The pipeline will re-execute from
    the next scheduled node at the checkpoint.

    If state_patch is provided, it is merged into the checkpoint state before
    resuming. Common use cases:
    - Adjusting max_iterations to allow more search rounds
    - Clearing gaps to force synthesis
    - Overriding faithfulness_score to skip unnecessary re-verification

    If PG_AUTO_RESUME is disabled, this function only applies the patch and
    returns the updated state without re-executing the pipeline.

    Args:
        vector_id: The research vector identifier.
        checkpoint_id: The checkpoint to rewind to.
        app: A compiled LangGraph application with checkpointer.
        state_patch: Optional dict of state keys to override before resuming.

    Returns:
        Dict with execution result or error. Contains "status", "metadata",
        and optionally "state" with the final pipeline state.
    """
    if not PG_CHECKPOINT_ENABLED:
        return {"error": "Checkpointing is disabled (PG_CHECKPOINT_ENABLED=0)"}

    if not CHECKPOINT_DB.exists():
        return {"error": f"No checkpoint database at {CHECKPOINT_DB}"}

    thread_id = get_thread_id(vector_id)
    config = {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_id": checkpoint_id,
        }
    }

    try:
        # Step 1: Verify the checkpoint exists and get its state
        snapshot = await app.aget_state(config)
        if snapshot is None:
            return {
                "error": (
                    f"No checkpoint found: vector_id={vector_id}, "
                    f"checkpoint_id={checkpoint_id}"
                )
            }

        next_nodes = snapshot.next if snapshot.next else ()
        if not next_nodes:
            return {
                "error": (
                    f"Checkpoint {checkpoint_id[:12]} is at __end__ — "
                    "no next node to resume from. Choose an earlier checkpoint."
                )
            }

        resume_node = next_nodes[0]
        original_summary = _extract_state_summary(
            snapshot.values if snapshot.values else {}
        )

        logger.info(
            "[polaris graph] A2: Rewinding %s to checkpoint %s "
            "(resume_node=%s, evidence=%d, iter=%d)",
            vector_id,
            checkpoint_id[:12],
            resume_node,
            original_summary["evidence_count"],
            original_summary["iteration"],
        )

        # Step 2: Apply state patch if provided
        patched_keys: list[str] = []
        if state_patch:
            # Validate that patch keys are known state fields
            # (log warnings for unknown keys, but still apply them)
            for key in state_patch:
                patched_keys.append(key)

            logger.info(
                "[polaris graph] A2: Applying state patch with %d keys: %s",
                len(state_patch),
                patched_keys,
            )

            # aupdate_state returns a new config pointing to the updated checkpoint
            updated_config = await app.aupdate_state(
                config,
                values=state_patch,
                as_node=resume_node,
            )
            logger.info(
                "[polaris graph] A2: State patch applied. New config: %s",
                updated_config.get("configurable", {}).get(
                    "checkpoint_id", ""
                )[:12],
            )
            # Use the updated config for resumption
            resume_config = updated_config
        else:
            # Resume from the original checkpoint config — use thread_id only
            # so LangGraph picks up from the checkpoint_id's position
            resume_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": checkpoint_id,
                }
            }

        # Step 3: Resume execution
        auto_resume = os.getenv("PG_AUTO_RESUME", "1") == "1"
        if not auto_resume:
            logger.info(
                "[polaris graph] A2: PG_AUTO_RESUME=0 — patch applied but "
                "not resuming execution. Use the pipeline runner to continue."
            )
            # Return the patched state without executing
            patched_snapshot = await app.aget_state(resume_config)
            patched_values = (
                patched_snapshot.values if patched_snapshot else {}
            )
            return {
                "status": "patched_not_resumed",
                "metadata": {
                    "checkpoint_id": checkpoint_id,
                    "vector_id": vector_id,
                    "resume_node": resume_node,
                    "patched_keys": patched_keys,
                    "auto_resume": False,
                },
                "summary": _extract_state_summary(patched_values),
            }

        # Auto-resume: stream execution from the checkpoint
        import time as _time

        max_execution_minutes = int(
            os.getenv("PG_REWIND_MAX_MINUTES", os.getenv("PG_MAX_EXECUTION_MINUTES", "60"))
        )
        timeout_seconds = max_execution_minutes * 60

        logger.info(
            "[polaris graph] A2: Resuming execution from node '%s' "
            "(timeout=%dm)",
            resume_node,
            max_execution_minutes,
        )

        start_time = _time.monotonic()
        result_state: dict[str, Any] = {}

        # Use astream to collect state updates during resumed execution.
        # Pass None as input to resume from checkpoint.
        run_config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 100,
        }

        import asyncio

        try:
            async with asyncio.timeout(timeout_seconds):
                async for event in app.astream(
                    None,
                    run_config,
                    stream_mode="updates",
                ):
                    if isinstance(event, dict):
                        for node_name, node_output in event.items():
                            if isinstance(node_output, dict):
                                result_state.update(node_output)
                                logger.info(
                                    "[polaris graph] A2: Rewind node '%s' "
                                    "completed (%d keys)",
                                    node_name,
                                    len(node_output),
                                )
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning(
                "[polaris graph] A2: Rewind execution timed out after %dm",
                max_execution_minutes,
            )
            result_state["status"] = "rewind_timeout"
            result_state["error"] = (
                f"Rewind timed out after {max_execution_minutes}min"
            )

        elapsed = _time.monotonic() - start_time
        final_summary = _extract_state_summary(result_state)

        logger.info(
            "[polaris graph] A2: Rewind complete in %.1fs. "
            "Status=%s, evidence=%d, faithfulness=%s",
            elapsed,
            result_state.get("status", "unknown"),
            final_summary["evidence_count"],
            final_summary["faithfulness"],
        )

        return {
            "status": result_state.get("status", "rewind_complete"),
            "metadata": {
                "checkpoint_id": checkpoint_id,
                "vector_id": vector_id,
                "resume_node": resume_node,
                "patched_keys": patched_keys,
                "auto_resume": True,
                "elapsed_seconds": round(elapsed, 1),
            },
            "summary": final_summary,
        }

    except Exception as exc:
        logger.error(
            "[polaris graph] A2: rewind_to_checkpoint failed for %s/%s: %s",
            vector_id, checkpoint_id[:12], str(exc)[:500],
        )
        return {
            "error": f"Rewind failed: {str(exc)[:500]}",
            "status": "rewind_failed",
        }


def _serialize_state(values: dict[str, Any]) -> dict[str, Any]:
    """Serialize state values into JSON-safe format.

    Handles Pydantic models, datetime objects, and other non-serializable types
    that may appear in ResearchState.
    """
    import json as _json

    serialized: dict[str, Any] = {}
    for key, value in values.items():
        try:
            # Try direct JSON serialization first (fast path)
            _json.dumps(value)
            serialized[key] = value
        except (TypeError, ValueError, OverflowError):
            # Handle Pydantic models
            if hasattr(value, "model_dump"):
                serialized[key] = value.model_dump()
            elif isinstance(value, list):
                serialized[key] = [
                    item.model_dump() if hasattr(item, "model_dump") else str(item)
                    for item in value
                ]
            elif isinstance(value, dict):
                serialized[key] = {
                    k: v.model_dump() if hasattr(v, "model_dump") else str(v)
                    for k, v in value.items()
                }
            else:
                serialized[key] = str(value)
    return serialized
