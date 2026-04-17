"""OpenAlex API client for source canonicalization and authority scoring.

PATCH-D (SOTA adoption plan). Source: api.openalex.org /works endpoint.
Free public API, no key required. Polite-pool header gives 10× rate
limit by providing an email.

Two operations:

1. canonicalize(url, doi, title) -> OpenAlexWork | None
   Returns the canonical OpenAlex work ID, source type, and
   publication type. Used for bibliography dedup across revisions
   (same work at publisher + PMC + institutional-repo collapses to one
   work_id) and for authority-tier gating.

2. OpenAlexWork.authority_tier() -> str
   Maps (type, source.type, is_retracted) to our internal tier:

     GOLD:    type in {article, review} AND source.type == journal AND
              NOT is_retracted
     SILVER:  type == preprint OR source.type == repository (preprints,
              institutional repos — legitimate but unreviewed)
     BRONZE:  type in {book-chapter, book, dataset, editorial, letter,
              other} (grey literature, non-primary)
     BLOCKED: is_retracted OR type == erratum

Closes the PG_LB_SA_01 defect where Motley Rice law-firm pages, Medium
blog posts, thegutpunch.com, Fella Health telehealth, NHS JS high-school
journal, and a ResearchSquare preprint were all tiered SILVER alongside
SELECT trial data.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

OPENALEX_BASE = "https://api.openalex.org"
POLITE_EMAIL = os.getenv("OPENALEX_EMAIL", "")
CACHE_DB = Path(os.getenv("OPENALEX_CACHE_DB", "cache/openalex.sqlite"))
TIMEOUT = float(os.getenv("OPENALEX_TIMEOUT", "10"))
ENABLED = os.getenv("PG_OPENALEX_ENABLED", "1") == "1"


@dataclass
class OpenAlexWork:
    """Subset of OpenAlex work fields we need for authority + dedup."""
    work_id: str            # canonical: https://openalex.org/W...
    doi: str                # https://doi.org/10... or ''
    title: str
    type: str               # 'article', 'preprint', 'book-chapter', ...
    source_type: str        # 'journal', 'repository', ...
    source_name: str        # 'Nature Medicine', etc.
    publication_year: int
    is_retracted: bool

    def authority_tier(self) -> str:
        if self.is_retracted or self.type == "erratum":
            return "BLOCKED"
        if self.type in {"article", "review"} and self.source_type == "journal":
            return "GOLD"
        if self.type == "preprint" or self.source_type == "repository":
            return "SILVER"
        return "BRONZE"


def _cache_init() -> None:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS works ("
            " key TEXT PRIMARY KEY,"
            " work_id TEXT,"
            " doi TEXT,"
            " title TEXT,"
            " type TEXT,"
            " source_type TEXT,"
            " source_name TEXT,"
            " publication_year INTEGER,"
            " is_retracted INTEGER,"
            " fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,"
            " miss INTEGER DEFAULT 0)"
        )
        conn.commit()
    finally:
        conn.close()


def _cache_get(key: str) -> tuple[Optional[OpenAlexWork], bool]:
    """Return (work, is_miss_record). is_miss_record=True means we've
    previously looked this up and OpenAlex had no match — don't re-query."""
    if not CACHE_DB.exists():
        return None, False
    conn = sqlite3.connect(CACHE_DB)
    try:
        row = conn.execute(
            "SELECT work_id, doi, title, type, source_type, source_name,"
            " publication_year, is_retracted, miss FROM works WHERE key = ?",
            (key,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None, False
    if row[8]:
        return None, True
    return OpenAlexWork(
        work_id=row[0], doi=row[1] or "", title=row[2] or "",
        type=row[3] or "other", source_type=row[4] or "",
        source_name=row[5] or "", publication_year=row[6] or 0,
        is_retracted=bool(row[7]),
    ), False


def _cache_put(key: str, w: Optional[OpenAlexWork]) -> None:
    conn = sqlite3.connect(CACHE_DB)
    try:
        if w is None:
            conn.execute(
                "INSERT OR REPLACE INTO works "
                "(key, work_id, doi, title, type, source_type, source_name,"
                " publication_year, is_retracted, miss)"
                " VALUES (?, '', '', '', '', '', '', 0, 0, 1)",
                (key,),
            )
        else:
            conn.execute(
                "INSERT OR REPLACE INTO works "
                "(key, work_id, doi, title, type, source_type, source_name,"
                " publication_year, is_retracted, miss)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (key, w.work_id, w.doi, w.title, w.type, w.source_type,
                 w.source_name, w.publication_year, int(w.is_retracted)),
            )
        conn.commit()
    finally:
        conn.close()


async def _fetch_work(params: dict) -> Optional[dict]:
    import httpx
    headers = {
        "User-Agent": f"POLARIS/1.0 (mailto:{POLITE_EMAIL})"
    } if POLITE_EMAIL else {"User-Agent": "POLARIS/1.0"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as c:
            r = await c.get(f"{OPENALEX_BASE}/works", params=params, headers=headers)
            if r.status_code != 200:
                return None
            data = r.json()
            results = data.get("results", [])
            return results[0] if results else None
    except Exception as exc:
        logger.debug("OpenAlex fetch failed: %s", str(exc)[:200])
        return None


def _parse_work(data: dict) -> OpenAlexWork:
    primary = data.get("primary_location") or {}
    source = primary.get("source") or {}
    return OpenAlexWork(
        work_id=data.get("id", ""),
        doi=data.get("doi", "") or "",
        title=data.get("title", "") or "",
        type=data.get("type", "other") or "other",
        source_type=source.get("type", "") or "",
        source_name=source.get("display_name", "") or "",
        publication_year=data.get("publication_year", 0) or 0,
        is_retracted=bool(data.get("is_retracted", False)),
    )


def _fetch_work_sync(params: dict) -> Optional[dict]:
    """Synchronous variant of _fetch_work for callers that aren't async."""
    import httpx
    headers = {
        "User-Agent": f"POLARIS/1.0 (mailto:{POLITE_EMAIL})"
    } if POLITE_EMAIL else {"User-Agent": "POLARIS/1.0"}
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            r = c.get(f"{OPENALEX_BASE}/works", params=params, headers=headers)
            if r.status_code != 200:
                return None
            data = r.json()
            results = data.get("results", [])
            return results[0] if results else None
    except Exception as exc:
        logger.debug("OpenAlex sync fetch failed: %s", str(exc)[:200])
        return None


def canonicalize_sync(
    url: str = "",
    doi: str = "",
    title: str = "",
) -> Optional[OpenAlexWork]:
    """Sync variant of canonicalize() for use inside _build_bibliography.

    Same semantics as canonicalize() but uses a blocking HTTP client so
    callers already inside an event loop don't have to juggle nest_asyncio.
    """
    if not ENABLED:
        return None
    _cache_init()

    if doi:
        doi_clean = doi.lower().strip()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if doi_clean.startswith(prefix):
                doi_clean = doi_clean[len(prefix):]
        doi_clean = doi_clean.rstrip("/")
        key = f"doi:{doi_clean}"
        hit, is_miss = _cache_get(key)
        if is_miss:
            return None
        if hit:
            return hit
        data = _fetch_work_sync({"filter": f"doi:{doi_clean}"})
        if data:
            w = _parse_work(data)
            _cache_put(key, w)
            return w
        _cache_put(key, None)

    if title:
        key = f"title:{title.lower().strip()[:200]}"
        hit, is_miss = _cache_get(key)
        if is_miss:
            return None
        if hit:
            return hit
        data = _fetch_work_sync({"search": title[:300], "per_page": 1})
        if data:
            w = _parse_work(data)
            _cache_put(key, w)
            return w
        _cache_put(key, None)

    return None


async def canonicalize(
    url: str = "",
    doi: str = "",
    title: str = "",
) -> Optional[OpenAlexWork]:
    """Look up a work by DOI first, fall back to title search.

    Results are cached per lookup-key (SQLite). A miss is also cached
    to avoid repeated failed lookups within a session.
    """
    if not ENABLED:
        return None
    _cache_init()

    if doi:
        doi_clean = doi.lower().strip()
        # Strip common prefixes
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if doi_clean.startswith(prefix):
                doi_clean = doi_clean[len(prefix):]
        doi_clean = doi_clean.rstrip("/")
        key = f"doi:{doi_clean}"
        hit, is_miss = _cache_get(key)
        if is_miss:
            return None
        if hit:
            return hit
        data = await _fetch_work({"filter": f"doi:{doi_clean}"})
        if data:
            w = _parse_work(data)
            _cache_put(key, w)
            return w
        _cache_put(key, None)  # remember the miss

    if title:
        key = f"title:{title.lower().strip()[:200]}"
        hit, is_miss = _cache_get(key)
        if is_miss:
            return None
        if hit:
            return hit
        data = await _fetch_work({"search": title[:300], "per_page": 1})
        if data:
            w = _parse_work(data)
            _cache_put(key, w)
            return w
        _cache_put(key, None)

    return None
