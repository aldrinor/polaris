"""
Persistent search result cache backed by SQLite.

Caches search API results (Serper, S2, Exa, DDG) to avoid duplicate queries.
TTL-based expiry (default 24 hours for freshness).
"""

import hashlib
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
CACHE_DB = CACHE_DIR / "pg_search_cache.sqlite"
DEFAULT_TTL_HOURS = int(os.getenv("PG_SEARCH_CACHE_TTL_HOURS", "24"))


def _query_hash(query: str, search_type: str = "") -> str:
    """Generate a consistent hash for a query + type pair."""
    key = f"{search_type}:{query}".lower().strip()
    return hashlib.sha256(key.encode()).hexdigest()[:32]


async def _ensure_table(db: aiosqlite.Connection) -> None:
    """Create the cache table if it doesn't exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS search_cache (
            query_hash TEXT PRIMARY KEY,
            query_text TEXT NOT NULL,
            results_json TEXT NOT NULL,
            search_type TEXT DEFAULT '',
            result_count INTEGER DEFAULT 0,
            cached_at REAL NOT NULL,
            ttl_hours INTEGER DEFAULT 24
        )
    """)
    await db.commit()


async def get_cached_results(
    query: str,
    search_type: str = "",
) -> Optional[list[dict]]:
    """Retrieve cached search results.

    Returns list of result dicts, or None if not cached/expired.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    qhash = _query_hash(query, search_type)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM search_cache WHERE query_hash = ?", (qhash,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            # Check TTL
            cached_at = row["cached_at"]
            ttl_hours = row["ttl_hours"] or DEFAULT_TTL_HOURS
            age_hours = (time.time() - cached_at) / 3600
            if age_hours > ttl_hours:
                return None

            return json.loads(row["results_json"])
    except Exception as exc:
        logger.warning(
            "[search_cache] Read failed for '%s': %s",
            query[:50], str(exc)[:200],
        )
        return None


async def cache_results(
    query: str,
    results: list[dict],
    search_type: str = "",
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> bool:
    """Store search results in cache."""
    if not query or not results:
        return False

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    qhash = _query_hash(query, search_type)
    try:
        results_json = json.dumps(results, ensure_ascii=False)
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            await db.execute(
                """INSERT OR REPLACE INTO search_cache
                   (query_hash, query_text, results_json, search_type,
                    result_count, cached_at, ttl_hours)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (qhash, query, results_json, search_type,
                 len(results), time.time(), ttl_hours),
            )
            await db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "[search_cache] Write failed for '%s': %s",
            query[:50], str(exc)[:200],
        )
        return False


async def get_cache_stats() -> dict:
    """Get cache statistics."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            cursor = await db.execute("SELECT COUNT(*) FROM search_cache")
            total = (await cursor.fetchone())[0]

            cursor = await db.execute("SELECT SUM(result_count) FROM search_cache")
            total_results = (await cursor.fetchone())[0] or 0

            cursor = await db.execute(
                "SELECT search_type, COUNT(*) as cnt FROM search_cache GROUP BY search_type"
            )
            by_type = {row[0]: row[1] for row in await cursor.fetchall()}

            return {
                "total_queries": total,
                "total_results_cached": total_results,
                "by_type": by_type,
            }
    except Exception as exc:
        logger.warning("[search_cache] Stats failed: %s", str(exc)[:200])
        return {"total_queries": 0, "total_results_cached": 0, "by_type": {}}
