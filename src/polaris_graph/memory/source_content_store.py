"""
URL-keyed SQLite store for source content deduplication.

Problem: Each evidence dict carries source_content (25K chars). 1000 evidence
from 50 sources = same content duplicated ~20x each = 1.25MB state bloat.

Solution: Store content once per URL. Evidence references content by source_url.

DB path: state/pg_source_content.sqlite (follows PG_CACHE_DIR pattern from
evidence_hierarchy.py).
"""

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
STORE_DB = CACHE_DIR / "pg_source_content.sqlite"

# Feature flag (LAW VI: from env var)
PG_SOURCE_CONTENT_STORE_ENABLED = os.getenv("PG_SOURCE_CONTENT_STORE_ENABLED", "1") == "1"


def _normalize_url(url: str) -> str:
    """Normalize URL for consistent lookup (www vs non-www, trailing slash, protocol)."""
    url = url.strip().rstrip("/")
    if url.startswith("http://"):
        url = "https://" + url[7:]
    url = url.replace("://www.", "://")
    return url.lower()


async def _ensure_table(db: aiosqlite.Connection) -> None:
    """Create the source_content table if it doesn't exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS source_content (
            url TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            title TEXT DEFAULT '',
            content_length INTEGER DEFAULT 0,
            stored_at REAL NOT NULL
        )
    """)
    await db.commit()


async def store_content(url: str, content: str, title: str = "") -> bool:
    """Store source content keyed by normalized URL.

    Idempotent: re-storing the same URL updates the content.

    Args:
        url: Source URL (will be normalized).
        content: Full source content text.
        title: Optional source title for metadata.

    Returns:
        True on success, False on failure.
    """
    if not url or not content:
        return False

    if not PG_SOURCE_CONTENT_STORE_ENABLED:
        return False

    normalized = _normalize_url(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        async with aiosqlite.connect(str(STORE_DB)) as db:
            await _ensure_table(db)
            await db.execute(
                """INSERT OR REPLACE INTO source_content
                   (url, content, title, content_length, stored_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (normalized, content, title or "", len(content), time.time()),
            )
            await db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "[source_content_store] Write failed for %s: %s",
            normalized[:80],
            str(exc)[:200],
        )
        return False


async def get_content(url: str) -> str:
    """Retrieve source content by URL.

    Args:
        url: Source URL (will be normalized).

    Returns:
        Content string, or empty string if not found.
    """
    if not url:
        return ""

    if not PG_SOURCE_CONTENT_STORE_ENABLED:
        return ""

    normalized = _normalize_url(url)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        async with aiosqlite.connect(str(STORE_DB)) as db:
            await _ensure_table(db)
            cursor = await db.execute(
                "SELECT content FROM source_content WHERE url = ?",
                (normalized,),
            )
            row = await cursor.fetchone()
            if row is not None:
                return row[0]

            # Try original URL as fallback (handles edge cases in normalization)
            cursor = await db.execute(
                "SELECT content FROM source_content WHERE url = ?",
                (url.strip(),),
            )
            row = await cursor.fetchone()
            return row[0] if row is not None else ""
    except Exception as exc:
        logger.warning(
            "[source_content_store] Read failed for %s: %s",
            normalized[:80],
            str(exc)[:200],
        )
        return ""


async def get_content_batch(urls: list[str]) -> dict[str, str]:
    """Retrieve content for multiple URLs in a single DB connection.

    Drop-in replacement for the url_content_map construction in verifier.py.

    Args:
        urls: List of source URLs.

    Returns:
        Dict mapping URL -> content string.
    """
    if not urls:
        return {}

    if not PG_SOURCE_CONTENT_STORE_ENABLED:
        return {}

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, str] = {}

    try:
        async with aiosqlite.connect(str(STORE_DB)) as db:
            await _ensure_table(db)

            # Normalize all URLs and build lookup
            norm_to_original: dict[str, list[str]] = {}
            for url in urls:
                if not url:
                    continue
                normalized = _normalize_url(url)
                if normalized not in norm_to_original:
                    norm_to_original[normalized] = []
                norm_to_original[normalized].append(url)

            # Batch query — SQLite IN clause with parameterized placeholders
            normalized_urls = list(norm_to_original.keys())
            if not normalized_urls:
                return {}

            # Process in chunks to avoid SQLite variable limit (999)
            chunk_size = 900
            for i in range(0, len(normalized_urls), chunk_size):
                chunk = normalized_urls[i : i + chunk_size]
                placeholders = ",".join("?" for _ in chunk)
                cursor = await db.execute(
                    f"SELECT url, content FROM source_content WHERE url IN ({placeholders})",
                    chunk,
                )
                rows = await cursor.fetchall()

                for db_url, content in rows:
                    # Map back to all original URL variants
                    originals = norm_to_original.get(db_url, [db_url])
                    for orig in originals:
                        result[orig] = content
                    # Also store normalized form for direct lookups
                    result[db_url] = content

        if result:
            logger.debug(
                "[source_content_store] Batch read: %d/%d URLs found (avg %.0f chars)",
                len(result),
                len(urls),
                sum(len(v) for v in result.values()) / max(len(result), 1),
            )
    except Exception as exc:
        logger.warning(
            "[source_content_store] Batch read failed: %s",
            str(exc)[:200],
        )

    return result


async def get_store_stats() -> dict:
    """Get statistics about the content store.

    Returns:
        Dict with entry_count, total_chars, avg_chars, db_size_mb.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(STORE_DB)) as db:
            await _ensure_table(db)
            cursor = await db.execute(
                "SELECT COUNT(*), COALESCE(SUM(content_length), 0), "
                "COALESCE(AVG(content_length), 0) FROM source_content"
            )
            row = await cursor.fetchone()
            db_size = STORE_DB.stat().st_size / (1024 * 1024) if STORE_DB.exists() else 0
            return {
                "entry_count": row[0],
                "total_chars": row[1],
                "avg_chars": round(row[2]),
                "db_size_mb": round(db_size, 2),
            }
    except Exception as exc:
        logger.warning("[source_content_store] Stats failed: %s", str(exc)[:200])
        return {"entry_count": 0, "total_chars": 0, "avg_chars": 0, "db_size_mb": 0}
