"""
L0/L1/L2 evidence hierarchy backed by SQLite (OpenViking-inspired).

Stores evidence at three levels of detail:
  L0 (100 tokens): One-sentence claim summary for quick scanning.
  L1 (500 tokens): Claim + context + quality for medium-depth review.
  L2 (full JSON):  Complete evidence piece for synthesis/verification.

DB path: state/pg_evidence_hierarchy.sqlite
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
CACHE_DB = CACHE_DIR / "pg_evidence_hierarchy.sqlite"


async def _ensure_table(db: aiosqlite.Connection) -> None:
    """Create the evidence_memory table if it doesn't exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS evidence_memory (
            evidence_id TEXT PRIMARY KEY,
            vector_id TEXT NOT NULL,
            cluster_id TEXT DEFAULT '',
            l0_summary TEXT DEFAULT '',
            l1_overview TEXT DEFAULT '',
            l2_full TEXT DEFAULT '{}',
            perspective TEXT DEFAULT '',
            quality_tier TEXT DEFAULT 'BRONZE',
            relevance_score REAL DEFAULT 0.0,
            created_at REAL NOT NULL
        )
    """)
    # TIER-3 Stage 4: Add section_assignments column (safe migration)
    try:
        await db.execute(
            "ALTER TABLE evidence_memory ADD COLUMN section_assignments TEXT DEFAULT ''"
        )
    except Exception:
        pass  # Column already exists
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_evidence_vector
            ON evidence_memory (vector_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_evidence_vector_cluster
            ON evidence_memory (vector_id, cluster_id)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_evidence_perspective
            ON evidence_memory (vector_id, perspective)
    """)
    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_evidence_tier
            ON evidence_memory (vector_id, quality_tier)
    """)
    await db.commit()


async def store_evidence(
    evidence_id: str,
    vector_id: str,
    cluster_id: str,
    l0_summary: str,
    l1_overview: str,
    l2_json: dict,
    perspective: str,
    quality_tier: str,
    relevance_score: float,
) -> bool:
    """Store evidence at all three hierarchy levels.

    Args:
        evidence_id: Unique evidence identifier (e.g., ev_abc123).
        vector_id: Parent vector identifier.
        cluster_id: Cluster this evidence belongs to.
        l0_summary: One-sentence claim (~100 tokens).
        l1_overview: Claim + context + quality (~500 tokens).
        l2_json: Full evidence piece as a dict.
        perspective: STORM perspective tag (e.g., 'public_health_expert').
        quality_tier: GOLD / SILVER / BRONZE.
        relevance_score: Float 0.0-1.0.

    Returns:
        True on success.
    """
    if not evidence_id or not vector_id:
        return False

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        l2_text = json.dumps(l2_json, ensure_ascii=False)
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            await db.execute(
                """INSERT OR REPLACE INTO evidence_memory
                   (evidence_id, vector_id, cluster_id, l0_summary, l1_overview,
                    l2_full, perspective, quality_tier, relevance_score, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    evidence_id,
                    vector_id,
                    cluster_id or "",
                    l0_summary or "",
                    l1_overview or "",
                    l2_text,
                    perspective or "",
                    quality_tier or "BRONZE",
                    relevance_score,
                    time.time(),
                ),
            )
            await db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] Write failed for %s: %s",
            evidence_id[:60], str(exc)[:200],
        )
        return False


async def get_l0_summaries(vector_id: str) -> list[dict]:
    """Get L0-level summaries for quick overview of all evidence in a vector.

    Returns list of dicts with keys:
        evidence_id, l0_summary, perspective, quality_tier
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT evidence_id, l0_summary, perspective, quality_tier
                   FROM evidence_memory
                   WHERE vector_id = ?
                   ORDER BY relevance_score DESC""",
                (vector_id,),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "evidence_id": row["evidence_id"],
                    "l0_summary": row["l0_summary"],
                    "perspective": row["perspective"],
                    "quality_tier": row["quality_tier"],
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] L0 read failed for %s: %s",
            vector_id[:60], str(exc)[:200],
        )
        return []


async def get_l1_overviews(
    vector_id: str,
    cluster_id: Optional[str] = None,
) -> list[dict]:
    """Get L1-level overviews (claim + context + quality).

    Args:
        vector_id: Parent vector identifier.
        cluster_id: Optional cluster filter.

    Returns list of dicts with keys:
        evidence_id, cluster_id, l1_overview, perspective, quality_tier, relevance_score
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row

            if cluster_id is not None:
                cursor = await db.execute(
                    """SELECT evidence_id, cluster_id, l1_overview,
                              perspective, quality_tier, relevance_score
                       FROM evidence_memory
                       WHERE vector_id = ? AND cluster_id = ?
                       ORDER BY relevance_score DESC""",
                    (vector_id, cluster_id),
                )
            else:
                cursor = await db.execute(
                    """SELECT evidence_id, cluster_id, l1_overview,
                              perspective, quality_tier, relevance_score
                       FROM evidence_memory
                       WHERE vector_id = ?
                       ORDER BY relevance_score DESC""",
                    (vector_id,),
                )

            rows = await cursor.fetchall()
            return [
                {
                    "evidence_id": row["evidence_id"],
                    "cluster_id": row["cluster_id"],
                    "l1_overview": row["l1_overview"],
                    "perspective": row["perspective"],
                    "quality_tier": row["quality_tier"],
                    "relevance_score": row["relevance_score"],
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] L1 read failed for %s: %s",
            vector_id[:60], str(exc)[:200],
        )
        return []


async def get_l2_full(evidence_id: str) -> Optional[dict]:
    """Get the full L2 evidence JSON for a single piece.

    Returns the deserialized dict, or None if not found.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT l2_full FROM evidence_memory WHERE evidence_id = ?",
                (evidence_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return None
            return json.loads(row["l2_full"])
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] L2 read failed for %s: %s",
            evidence_id[:60], str(exc)[:200],
        )
        return None


async def get_by_perspective(vector_id: str, perspective: str) -> list[dict]:
    """Get all evidence for a vector filtered by STORM perspective.

    Returns list of dicts with keys:
        evidence_id, cluster_id, l0_summary, l1_overview, quality_tier, relevance_score
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT evidence_id, cluster_id, l0_summary, l1_overview,
                          quality_tier, relevance_score
                   FROM evidence_memory
                   WHERE vector_id = ? AND perspective = ?
                   ORDER BY relevance_score DESC""",
                (vector_id, perspective),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "evidence_id": row["evidence_id"],
                    "cluster_id": row["cluster_id"],
                    "l0_summary": row["l0_summary"],
                    "l1_overview": row["l1_overview"],
                    "quality_tier": row["quality_tier"],
                    "relevance_score": row["relevance_score"],
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] Perspective read failed for %s/%s: %s",
            vector_id[:40], perspective[:20], str(exc)[:200],
        )
        return []


async def get_high_quality(
    vector_id: str,
    min_relevance: float = 0.5,
) -> list[dict]:
    """Get evidence above a relevance threshold for a vector.

    Args:
        vector_id: Parent vector identifier.
        min_relevance: Minimum relevance_score (default 0.5).

    Returns list of dicts with keys:
        evidence_id, cluster_id, l0_summary, l1_overview, perspective,
        quality_tier, relevance_score
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT evidence_id, cluster_id, l0_summary, l1_overview,
                          perspective, quality_tier, relevance_score
                   FROM evidence_memory
                   WHERE vector_id = ? AND relevance_score >= ?
                   ORDER BY relevance_score DESC""",
                (vector_id, min_relevance),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "evidence_id": row["evidence_id"],
                    "cluster_id": row["cluster_id"],
                    "l0_summary": row["l0_summary"],
                    "l1_overview": row["l1_overview"],
                    "perspective": row["perspective"],
                    "quality_tier": row["quality_tier"],
                    "relevance_score": row["relevance_score"],
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] High-quality read failed for %s: %s",
            vector_id[:60], str(exc)[:200],
        )
        return []


async def count_by_tier(vector_id: str) -> dict[str, int]:
    """Count evidence pieces grouped by quality tier for a vector.

    Returns dict mapping tier name (GOLD, SILVER, BRONZE) to count.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            cursor = await db.execute(
                """SELECT quality_tier, COUNT(*) as cnt
                   FROM evidence_memory
                   WHERE vector_id = ?
                   GROUP BY quality_tier""",
                (vector_id,),
            )
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] Count failed for %s: %s",
            vector_id[:60], str(exc)[:200],
        )
        return {}


# ---------------------------------------------------------------------------
# TIER-3 Stage 4: Batch getters and section assignment support
# ---------------------------------------------------------------------------


async def get_l1_for_section(
    vector_id: str,
    evidence_ids: list[str],
) -> list[dict]:
    """Batch L1 retrieval for a specific set of evidence IDs.

    More efficient than scanning the full in-memory evidence list.

    Args:
        vector_id: Parent vector identifier.
        evidence_ids: List of evidence_id strings to retrieve.

    Returns:
        List of dicts with keys: evidence_id, l1_overview, quality_tier, relevance_score
    """
    if not evidence_ids:
        return []

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row

            # Process in chunks to avoid SQLite variable limit
            results = []
            chunk_size = 900
            for i in range(0, len(evidence_ids), chunk_size):
                chunk = evidence_ids[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                cursor = await db.execute(
                    f"""SELECT evidence_id, l1_overview, quality_tier, relevance_score
                       FROM evidence_memory
                       WHERE vector_id = ? AND evidence_id IN ({placeholders})
                       ORDER BY relevance_score DESC""",
                    [vector_id] + chunk,
                )
                rows = await cursor.fetchall()
                results.extend([
                    {
                        "evidence_id": row["evidence_id"],
                        "l1_overview": row["l1_overview"],
                        "quality_tier": row["quality_tier"],
                        "relevance_score": row["relevance_score"],
                    }
                    for row in rows
                ])

            return results
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] L1 batch read failed for %s: %s",
            vector_id[:60], str(exc)[:200],
        )
        return []


async def get_l2_batch(evidence_ids: list[str]) -> list[dict]:
    """Batch L2 retrieval for multiple evidence IDs.

    More efficient than calling get_l2_full() per piece.

    Args:
        evidence_ids: List of evidence_id strings.

    Returns:
        List of deserialized L2 dicts.
    """
    if not evidence_ids:
        return []

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)

            results = []
            chunk_size = 900
            for i in range(0, len(evidence_ids), chunk_size):
                chunk = evidence_ids[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                cursor = await db.execute(
                    f"SELECT evidence_id, l2_full FROM evidence_memory WHERE evidence_id IN ({placeholders})",
                    chunk,
                )
                rows = await cursor.fetchall()
                for row in rows:
                    try:
                        l2_dict = json.loads(row[1])
                        results.append(l2_dict)
                    except (json.JSONDecodeError, TypeError):
                        pass

            return results
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] L2 batch read failed: %s",
            str(exc)[:200],
        )
        return []


async def update_section_assignments(
    evidence_id: str,
    section_ids: list[str],
) -> bool:
    """Store evidence-to-section routing result.

    Args:
        evidence_id: Evidence identifier.
        section_ids: List of section IDs this evidence is assigned to.

    Returns:
        True on success.
    """
    if not evidence_id:
        return False

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        assignments_str = ",".join(section_ids)
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            await db.execute(
                "UPDATE evidence_memory SET section_assignments = ? WHERE evidence_id = ?",
                (assignments_str, evidence_id),
            )
            await db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] Section assignment update failed for %s: %s",
            evidence_id[:40], str(exc)[:200],
        )
        return False


async def batch_update_section_assignments(
    assignments: dict[str, list[str]],
) -> int:
    """Batch update section assignments for multiple evidence pieces.

    Args:
        assignments: Dict mapping evidence_id -> list of section_ids.

    Returns:
        Number of successfully updated records.
    """
    if not assignments:
        return 0

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        updated = 0
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            for eid, section_ids in assignments.items():
                assignments_str = ",".join(section_ids)
                await db.execute(
                    "UPDATE evidence_memory SET section_assignments = ? WHERE evidence_id = ?",
                    (assignments_str, eid),
                )
                updated += 1
            await db.commit()
        return updated
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] Batch section assignment failed: %s",
            str(exc)[:200],
        )
        return 0


async def get_evidence_for_section(
    vector_id: str,
    section_id: str,
) -> list[dict]:
    """Get all evidence assigned to a specific section.

    Args:
        vector_id: Parent vector identifier.
        section_id: Section identifier to filter by.

    Returns:
        List of dicts with keys: evidence_id, l1_overview, quality_tier, relevance_score
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            # Use LIKE for comma-separated section_assignments field
            cursor = await db.execute(
                """SELECT evidence_id, l1_overview, quality_tier, relevance_score
                   FROM evidence_memory
                   WHERE vector_id = ? AND (
                       section_assignments = ?
                       OR section_assignments LIKE ?
                       OR section_assignments LIKE ?
                       OR section_assignments LIKE ?
                   )
                   ORDER BY relevance_score DESC""",
                (
                    vector_id,
                    section_id,  # Exact match (single assignment)
                    f"{section_id},%",  # Starts with
                    f"%,{section_id},%",  # Middle
                    f"%,{section_id}",  # Ends with
                ),
            )
            rows = await cursor.fetchall()
            return [
                {
                    "evidence_id": row["evidence_id"],
                    "l1_overview": row["l1_overview"],
                    "quality_tier": row["quality_tier"],
                    "relevance_score": row["relevance_score"],
                }
                for row in rows
            ]
    except Exception as exc:
        logger.warning(
            "[evidence_hierarchy] Section evidence read failed for %s/%s: %s",
            vector_id[:40], section_id[:20], str(exc)[:200],
        )
        return []
