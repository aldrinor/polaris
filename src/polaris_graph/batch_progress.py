"""FIX-V10: Mid-node batch progress persistence.

SQLite-based persistence for batch results within long-running LangGraph nodes.
LangGraph only checkpoints between nodes — if a 3-hour verify node crashes at
batch 200/260, all completed batch results are lost. This module saves each
batch result to SQLite as it completes, enabling recovery on restart.

Usage:
    progress = BatchProgress("verify", thread_id="pg_abc123")
    completed = progress.load_completed_batches()
    # Skip already-completed batches...
    progress.save_batch_result(batch_idx, result_data)
    progress.clear()  # After node completes successfully
"""

import json
import logging
import os
import sqlite3
import time
from typing import Any

logger = logging.getLogger(__name__)

PG_BATCH_PROGRESS_DIR = os.getenv("PG_BATCH_PROGRESS_DIR", "state")


class BatchProgress:
    """Persist batch results within a LangGraph node for crash recovery."""

    def __init__(self, node_name: str, thread_id: str = "default"):
        self._node_name = node_name
        self._thread_id = thread_id
        db_path = os.path.join(PG_BATCH_PROGRESS_DIR, "pg_batch_progress.sqlite")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS batch_results ("
            "  node_name TEXT NOT NULL,"
            "  thread_id TEXT NOT NULL,"
            "  batch_idx INTEGER NOT NULL,"
            "  result_json TEXT NOT NULL,"
            "  created_at REAL NOT NULL,"
            "  PRIMARY KEY (node_name, thread_id, batch_idx)"
            ")"
        )
        self._conn.commit()

    def save_batch_result(self, batch_idx: int, result: Any) -> None:
        """Save a completed batch result."""
        self._conn.execute(
            "INSERT OR REPLACE INTO batch_results "
            "(node_name, thread_id, batch_idx, result_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (self._node_name, self._thread_id, batch_idx,
             json.dumps(result, default=str), time.time()),
        )
        self._conn.commit()

    def load_completed_batches(self) -> dict[int, Any]:
        """Load all completed batch results for this node/thread.

        Returns: dict mapping batch_idx -> result data.
        """
        cursor = self._conn.execute(
            "SELECT batch_idx, result_json FROM batch_results "
            "WHERE node_name = ? AND thread_id = ? ORDER BY batch_idx",
            (self._node_name, self._thread_id),
        )
        results = {}
        for row in cursor.fetchall():
            try:
                results[row[0]] = json.loads(row[1])
            except json.JSONDecodeError:
                logger.warning(
                    "[polaris graph] FIX-V10: Corrupt batch result at idx=%d, skipping",
                    row[0],
                )
        if results:
            logger.info(
                "[polaris graph] FIX-V10: Loaded %d completed batch results "
                "for %s/%s",
                len(results), self._node_name, self._thread_id,
            )
        return results

    def clear(self) -> None:
        """Clear all batch results for this node/thread (after successful completion)."""
        self._conn.execute(
            "DELETE FROM batch_results WHERE node_name = ? AND thread_id = ?",
            (self._node_name, self._thread_id),
        )
        self._conn.commit()
        logger.info(
            "[polaris graph] FIX-V10: Cleared batch progress for %s/%s",
            self._node_name, self._thread_id,
        )

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
