"""
Session outcome feedback backed by SQLite.

Records which search strategies (query text, search type, source URL)
produce the best evidence, enabling the pipeline to learn over time
which approaches yield the highest relevance and faithfulness.

DB path: state/pg_session_feedback.sqlite
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiosqlite
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

CACHE_DIR = Path(os.getenv("PG_CACHE_DIR", "state"))
CACHE_DB = CACHE_DIR / "pg_session_feedback.sqlite"


async def _ensure_table(db: aiosqlite.Connection) -> None:
    """Create the session_feedback table if it doesn't exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS session_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            vector_id TEXT NOT NULL,
            query_text TEXT NOT NULL,
            search_type TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            evidence_count INTEGER DEFAULT 0,
            avg_relevance REAL DEFAULT 0.0,
            faithfulness_contribution REAL DEFAULT 0.0,
            created_at REAL NOT NULL
        )
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_session
            ON session_feedback (session_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_search_type
            ON session_feedback (search_type)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_feedback_source
            ON session_feedback (source_url)
    """)
    await db.commit()


async def record_feedback(
    session_id: str,
    vector_id: str,
    query_text: str,
    search_type: str,
    source_url: str,
    evidence_count: int,
    avg_relevance: float,
    faithfulness_contribution: float,
) -> bool:
    """Record feedback for a single search action.

    Args:
        session_id: Pipeline run / session identifier.
        vector_id: The vector being researched.
        query_text: The search query that was executed.
        search_type: Provider name (serper, s2, exa, ddg).
        source_url: URL of the source that produced evidence.
        evidence_count: Number of evidence pieces from this source.
        avg_relevance: Average relevance score of produced evidence.
        faithfulness_contribution: Faithfulness contribution (0.0-1.0).

    Returns:
        True on success.
    """
    if not session_id or not vector_id or not query_text:
        return False

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            await db.execute(
                """INSERT INTO session_feedback
                   (session_id, vector_id, query_text, search_type, source_url,
                    evidence_count, avg_relevance, faithfulness_contribution, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    vector_id,
                    query_text,
                    search_type or "",
                    source_url or "",
                    evidence_count,
                    avg_relevance,
                    faithfulness_contribution,
                    time.time(),
                ),
            )
            await db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "[session_feedback] Write failed for session %s: %s",
            session_id[:40], str(exc)[:200],
        )
        return False


async def get_best_strategies(
    search_type: Optional[str] = None,
    min_evidence: int = 5,
) -> list[dict]:
    """Get the best-performing query strategies ranked by composite score.

    The composite score is avg_relevance * evidence_count, which rewards
    queries that return both relevant and plentiful evidence.

    Args:
        search_type: Optional filter by provider (serper, s2, exa, etc.).
        min_evidence: Minimum total evidence_count to qualify.

    Returns:
        List of dicts with keys: query_text, search_type, total_evidence,
        avg_relevance, avg_faithfulness, composite_score
        Ordered by composite_score descending.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row

            if search_type is not None:
                cursor = await db.execute(
                    """SELECT
                           query_text,
                           search_type,
                           SUM(evidence_count) as total_evidence,
                           AVG(avg_relevance) as avg_relevance,
                           AVG(faithfulness_contribution) as avg_faithfulness
                       FROM session_feedback
                       WHERE search_type = ?
                       GROUP BY query_text, search_type
                       HAVING SUM(evidence_count) >= ?
                       ORDER BY AVG(avg_relevance) * SUM(evidence_count) DESC
                       LIMIT 50""",
                    (search_type, min_evidence),
                )
            else:
                cursor = await db.execute(
                    """SELECT
                           query_text,
                           search_type,
                           SUM(evidence_count) as total_evidence,
                           AVG(avg_relevance) as avg_relevance,
                           AVG(faithfulness_contribution) as avg_faithfulness
                       FROM session_feedback
                       GROUP BY query_text, search_type
                       HAVING SUM(evidence_count) >= ?
                       ORDER BY AVG(avg_relevance) * SUM(evidence_count) DESC
                       LIMIT 50""",
                    (min_evidence,),
                )

            rows = await cursor.fetchall()
            return [
                {
                    "query_text": row["query_text"],
                    "search_type": row["search_type"],
                    "total_evidence": row["total_evidence"],
                    "avg_relevance": round(row["avg_relevance"], 4),
                    "avg_faithfulness": round(row["avg_faithfulness"], 4),
                    "composite_score": round(
                        row["avg_relevance"] * row["total_evidence"], 4
                    ),
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning(
            "[session_feedback] Best strategies read failed: %s",
            str(exc)[:200],
        )
        return []


async def get_source_performance(min_entries: int = 3) -> list[dict]:
    """Get source URLs ranked by average faithfulness contribution.

    Args:
        min_entries: Minimum feedback entries for a source to qualify.

    Returns:
        List of dicts with keys: source_url, entry_count, total_evidence,
        avg_relevance, avg_faithfulness
        Ordered by avg_faithfulness descending.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT
                       source_url,
                       COUNT(*) as entry_count,
                       SUM(evidence_count) as total_evidence,
                       AVG(avg_relevance) as avg_relevance,
                       AVG(faithfulness_contribution) as avg_faithfulness
                   FROM session_feedback
                   WHERE source_url != ''
                   GROUP BY source_url
                   HAVING COUNT(*) >= ?
                   ORDER BY AVG(faithfulness_contribution) DESC
                   LIMIT 100""",
                (min_entries,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "source_url": row["source_url"],
                    "entry_count": row["entry_count"],
                    "total_evidence": row["total_evidence"],
                    "avg_relevance": round(row["avg_relevance"], 4),
                    "avg_faithfulness": round(row["avg_faithfulness"], 4),
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning(
            "[session_feedback] Source performance read failed: %s",
            str(exc)[:200],
        )
        return []


async def get_session_summary(session_id: str) -> dict:
    """Get an aggregate summary for a single session.

    Returns dict with keys:
        session_id, total_queries, total_evidence, avg_relevance,
        avg_faithfulness, by_search_type (dict mapping type to sub-summary)
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)

            # Overall aggregates
            cursor = await db.execute(
                """SELECT
                       COUNT(*) as total_queries,
                       COALESCE(SUM(evidence_count), 0) as total_evidence,
                       COALESCE(AVG(avg_relevance), 0.0) as avg_relevance,
                       COALESCE(AVG(faithfulness_contribution), 0.0) as avg_faithfulness
                   FROM session_feedback
                   WHERE session_id = ?""",
                (session_id,),
            )
            row = await cursor.fetchone()
            if row is None or row[0] == 0:
                return {
                    "session_id": session_id,
                    "total_queries": 0,
                    "total_evidence": 0,
                    "avg_relevance": 0.0,
                    "avg_faithfulness": 0.0,
                    "by_search_type": {},
                }

            total_queries = row[0]
            total_evidence = row[1]
            avg_relevance = round(row[2], 4)
            avg_faithfulness = round(row[3], 4)

            # Breakdown by search type
            cursor = await db.execute(
                """SELECT
                       search_type,
                       COUNT(*) as queries,
                       SUM(evidence_count) as evidence,
                       AVG(avg_relevance) as relevance,
                       AVG(faithfulness_contribution) as faithfulness
                   FROM session_feedback
                   WHERE session_id = ?
                   GROUP BY search_type""",
                (session_id,),
            )
            type_rows = await cursor.fetchall()
            by_type = {}
            for trow in type_rows:
                by_type[trow[0] or "unknown"] = {
                    "queries": trow[1],
                    "evidence": trow[2],
                    "avg_relevance": round(trow[3], 4),
                    "avg_faithfulness": round(trow[4], 4),
                }

            return {
                "session_id": session_id,
                "total_queries": total_queries,
                "total_evidence": total_evidence,
                "avg_relevance": avg_relevance,
                "avg_faithfulness": avg_faithfulness,
                "by_search_type": by_type,
            }
    except Exception as exc:
        logger.warning(
            "[session_feedback] Session summary failed for %s: %s",
            session_id[:40], str(exc)[:200],
        )
        return {
            "session_id": session_id,
            "total_queries": 0,
            "total_evidence": 0,
            "avg_relevance": 0.0,
            "avg_faithfulness": 0.0,
            "by_search_type": {},
        }
