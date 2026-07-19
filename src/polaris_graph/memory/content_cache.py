"""
Persistent URL/content cache backed by SQLite.

Stores fetched page content to avoid re-fetching URLs across runs.
TTL-based expiry (default 7 days).
"""

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

import aiosqlite
from dotenv import load_dotenv
from src.polaris_graph.settings import resolve

load_dotenv()

logger = logging.getLogger(__name__)

CACHE_DIR = Path(resolve("PG_CACHE_DIR"))
CACHE_DB = CACHE_DIR / "pg_content_cache.sqlite"
DEFAULT_TTL_HOURS = int(resolve("PG_CONTENT_CACHE_TTL_HOURS"))  # 7 days

# A1.1: Cap raw HTML storage to prevent SQLite bloat (LAW VI).
_RAW_HTML_MAX_CHARS = int(resolve("PG_RAW_HTML_MAX_CHARS"))  # 500KB


def extract_readability_html(raw_html: str) -> str:
    """A1.1: Extract article-body HTML from raw page HTML using readability-lxml.

    Returns the cleaned article HTML, or empty string if readability-lxml is
    not installed or extraction fails. This is a pure function with no side
    effects -- safe to call from any context.

    Args:
        raw_html: The raw HTTP response body (HTML string).

    Returns:
        Cleaned article-only HTML from readability, or "" on failure.
    """
    if not raw_html or len(raw_html) < 100:
        return ""

    try:
        from readability import Document as ReadabilityDocument

        doc = ReadabilityDocument(raw_html)
        readable = doc.summary() or ""
        return readable
    except ImportError:
        # readability-lxml not installed -- graceful degradation
        logger.debug(
            "[content_cache] A1.1: readability-lxml not installed, "
            "skipping readability extraction"
        )
        return ""
    except Exception as exc:
        logger.debug(
            "[content_cache] A1.1: readability extraction failed: %s",
            str(exc)[:200],
        )
        return ""


async def _ensure_table(db: aiosqlite.Connection) -> None:
    """Create the cache table if it doesn't exist."""
    await db.execute("""
        CREATE TABLE IF NOT EXISTS url_cache (
            url TEXT PRIMARY KEY,
            content TEXT NOT NULL,
            title TEXT DEFAULT '',
            content_length INTEGER DEFAULT 0,
            fetch_method TEXT DEFAULT 'direct',
            fetched_at REAL NOT NULL,
            ttl_hours INTEGER DEFAULT 168,
            raw_html TEXT DEFAULT '',
            readability_html TEXT DEFAULT ''
        )
    """)
    await db.commit()
    # Migration: add HTML columns to existing databases (A1.1)
    try:
        await db.execute(
            "ALTER TABLE url_cache ADD COLUMN raw_html TEXT DEFAULT ''"
        )
        await db.commit()
    except Exception:
        pass  # Column already exists
    try:
        await db.execute(
            "ALTER TABLE url_cache ADD COLUMN readability_html TEXT DEFAULT ''"
        )
        await db.commit()
    except Exception:
        pass  # Column already exists


async def get_cached_content(url: str) -> Optional[dict]:
    """Retrieve cached content for a URL.

    Returns dict with keys: url, content, title, content_length, fetch_method, fetched_at
    Returns None if not cached or expired.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM url_cache WHERE url = ?", (url,)
            )
            row = await cursor.fetchone()
            if row is None:
                return None

            # Check TTL
            fetched_at = row["fetched_at"]
            ttl_hours = row["ttl_hours"] or DEFAULT_TTL_HOURS
            age_hours = (time.time() - fetched_at) / 3600
            if age_hours > ttl_hours:
                logger.debug(
                    "[content_cache] Expired entry for %s (%.1fh > %dh)",
                    url[:60], age_hours, ttl_hours,
                )
                return None

            return {
                "url": row["url"],
                "content": row["content"],
                "title": row["title"],
                "content_length": row["content_length"],
                "fetch_method": row["fetch_method"],
                "fetched_at": row["fetched_at"],
                "raw_html": row["raw_html"] if "raw_html" in row.keys() else "",
                "readability_html": row["readability_html"] if "readability_html" in row.keys() else "",
            }
    except Exception as exc:
        logger.warning(
            "[content_cache] Read failed for %s: %s",
            url[:60], str(exc)[:200],
        )
        return None


async def cache_content(
    url: str,
    content: str,
    title: str = "",
    fetch_method: str = "direct",
    ttl_hours: int = DEFAULT_TTL_HOURS,
    raw_html: str = "",
    readability_html: str = "",
) -> bool:
    """Store fetched content in cache.

    Args:
        url: The source URL.
        content: Plaintext extracted content.
        title: Page title.
        fetch_method: How content was fetched (direct, jina, firecrawl, etc.).
        ttl_hours: Time-to-live in hours.
        raw_html: Original fetched HTML (as-is from HTTP response).
        readability_html: Cleaned HTML via readability algorithm (article body only).

    Returns True on success.
    """
    if not url or not content:
        return False

    # A1.1: Cap raw HTML to prevent SQLite bloat
    if raw_html and len(raw_html) > _RAW_HTML_MAX_CHARS:
        raw_html = raw_html[:_RAW_HTML_MAX_CHARS]
    if readability_html and len(readability_html) > _RAW_HTML_MAX_CHARS:
        readability_html = readability_html[:_RAW_HTML_MAX_CHARS]

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            await db.execute(
                """INSERT OR REPLACE INTO url_cache
                   (url, content, title, content_length, fetch_method, fetched_at,
                    ttl_hours, raw_html, readability_html)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (url, content, title, len(content), fetch_method, time.time(),
                 ttl_hours, raw_html, readability_html),
            )
            await db.commit()
        return True
    except Exception as exc:
        logger.warning(
            "[content_cache] Write failed for %s: %s",
            url[:60], str(exc)[:200],
        )
        return False


async def get_cache_stats() -> dict:
    """Get cache statistics."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            cursor = await db.execute("SELECT COUNT(*) FROM url_cache")
            total = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT SUM(content_length) FROM url_cache"
            )
            total_bytes = (await cursor.fetchone())[0] or 0

            now = time.time()
            cursor = await db.execute(
                "SELECT COUNT(*) FROM url_cache WHERE (? - fetched_at) / 3600.0 > ttl_hours",
                (now,),
            )
            expired = (await cursor.fetchone())[0]

            return {
                "total_entries": total,
                "total_bytes": total_bytes,
                "expired_entries": expired,
                "active_entries": total - expired,
            }
    except Exception as exc:
        logger.warning("[content_cache] Stats failed: %s", str(exc)[:200])
        return {"total_entries": 0, "total_bytes": 0, "expired_entries": 0, "active_entries": 0}


async def purge_expired() -> int:
    """Remove expired entries. Returns count of purged entries."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        async with aiosqlite.connect(str(CACHE_DB)) as db:
            await _ensure_table(db)
            now = time.time()
            cursor = await db.execute(
                "DELETE FROM url_cache WHERE (? - fetched_at) / 3600.0 > ttl_hours",
                (now,),
            )
            await db.commit()
            purged = cursor.rowcount
            if purged > 0:
                logger.info("[content_cache] Purged %d expired entries", purged)
            return purged
    except Exception as exc:
        logger.warning("[content_cache] Purge failed: %s", str(exc)[:200])
        return 0
