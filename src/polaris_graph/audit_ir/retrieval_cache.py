"""M-D7 (Phase D): Retrieval cache — bootstrap.

Per FINAL_PLAN M-D7 + Phase D milestones plan: aggressive
caching of source-fetch responses (CrossRef / Unpaywall /
PubMed / canonical-URL fetches). Reuses the M-21 SQLite
workspace substrate — one DB file per workspace, one extra
table for cached fetches.

Phase 1 ships **per-workspace cache + explicit eviction API**.
Phase 2 (system-wide cache + empirical ≥80% time-saved
acceptance test) is deferred.

## Why per-workspace (not global) for phase 1

Global cache adds auth/isolation complexity that doesn't belong
in a perf milestone. M-21 already establishes the per-workspace
SQLite substrate — extending it with one more table is the
narrowest cut. M-D7 phase 2 can promote to global once the
isolation contract is designed (likely with M-D13 collaboration
work).

## Cache key strategy

For academic sources, key on the persistent identifier:
  - DOI (lowercased, prefix-stripped)
  - PMID (digits only)

For web-fetched URLs, normalize via the same helper M-16 uses
for run-diff URL canonicalization (`run_diff._normalize_url`):
  - lowercase netloc, strip `www.`
  - drop tracking params (utm_*, fbclid, etc.)
  - sort remaining params, drop fragment + trailing slash
  - drop scheme (http/https treated identically)

This means `?utm_source=x&id=1` and `?id=1` hit the same cache
entry, and `https://Example.COM/` and `http://example.com`
match.

## Eviction API (NOT pure TTL)

Per advisor + Codex round-1 reasoning: pure TTL is
insufficient. Stale cached sources become a faithfulness
liability when the underlying source is retracted or
superseded. We expose:

  - `evict(workspace_id, cache_key)` — remove one entry
  - `evict_by_url(workspace_id, source_url)` — convenience
    wrapper (canonicalizes the URL first)
  - `evict_older_than(workspace_id, max_age_seconds)` — bulk
    age-based eviction (the TTL primitive)
  - `evict_all(workspace_id)` — workspace-wide flush

This shape lets M-D10 (citation freshness monitoring) hook in
later: when M-D10's daemon detects a retracted DOI, it calls
`evict_by_url(workspace_id, doi_url)` to invalidate the cache.

## Coupling to M-21

Same DB file, same isolation contract. The cache table is
independent of the memory table — they don't share rows or
foreign keys. A workspace can have memory entries without
cache entries and vice versa.

## What's pinned in M-D11

The cache content version is NOT in `ModelPin.retrieval_source_versions`
because the cache is workspace-scoped and the pin is run-scoped.
A workspace's cache state is captured at run time by the
workspace's existing audit trail (M-23 review queue records),
not by the model pin. Phase 2 may add a `cache_revision`
counter if replay needs bit-exact cache state.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RetrievalCacheError(Exception):
    """Raised on schema/state violations."""


class RetrievalCacheStateError(RetrievalCacheError):
    """Raised when the store's connection is closed / unusable."""


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CacheEntry:
    """One cached source-fetch response.

    `cache_key` is the canonicalized identifier (see
    `make_cache_key`). `payload` is the response body bytes —
    SQLite BLOB. `content_type` and `payload_sha256` let
    consumers verify integrity without re-fetching.

    `fetched_at` is the timestamp of the underlying fetch (for
    age-based eviction). `last_hit_at` updates on every read,
    enabling LRU-style bulk eviction in phase 2.
    """

    cache_key: str
    workspace_id: str
    source_url: str
    payload: bytes
    content_type: str
    payload_sha256: str
    fetched_at: float
    last_hit_at: float | None
    fetch_status_code: int


def cache_entry_to_dict(entry: CacheEntry) -> dict[str, Any]:
    """JSON-safe dict (without the binary payload)."""
    return {
        "cache_key": entry.cache_key,
        "workspace_id": entry.workspace_id,
        "source_url": entry.source_url,
        "content_type": entry.content_type,
        "payload_sha256": entry.payload_sha256,
        "payload_size_bytes": len(entry.payload),
        "fetched_at": entry.fetched_at,
        "last_hit_at": entry.last_hit_at,
        "fetch_status_code": entry.fetch_status_code,
    }


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS retrieval_cache (
    cache_key TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    source_url TEXT NOT NULL,
    payload BLOB NOT NULL,
    content_type TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    fetched_at REAL NOT NULL,
    last_hit_at REAL,
    fetch_status_code INTEGER NOT NULL,
    PRIMARY KEY (workspace_id, cache_key)
);

-- Fast workspace-scoped age scans for evict_older_than().
CREATE INDEX IF NOT EXISTS idx_retrieval_cache_ws_fetched
    ON retrieval_cache(workspace_id, fetched_at);

-- Fast LRU scans (phase 2 will use this).
CREATE INDEX IF NOT EXISTS idx_retrieval_cache_ws_hit
    ON retrieval_cache(workspace_id, last_hit_at);
"""


# ---------------------------------------------------------------------------
# Cache key construction
# ---------------------------------------------------------------------------


_DOI_PREFIX_RE = re.compile(
    r"^(?:https?://)?(?:dx\.)?doi\.org/", re.IGNORECASE
)
_PMID_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?(?:ncbi\.nlm\.nih\.gov/pubmed/|pubmed\.ncbi\.nlm\.nih\.gov/)(\d+)/?$",
    re.IGNORECASE,
)
# DOI shape per Crossref + ANSI/NISO Z39.84-2010:
#   prefix: 10.<registrant 4-9 digits, optional dotted sub-prefixes>
#   suffix: any non-whitespace 1+ chars
# We additionally exclude `/`/`?`/`#`/whitespace from the suffix
# because those almost always indicate URL decoration we want to
# strip (or, in the `/` case, structural decoration we keep — see
# below).
_DOI_FULL_RE = re.compile(
    r"^10\.[0-9]{4,9}(?:\.[0-9]+)*/[^\s?#]+$"
)


def _canonicalize_doi(raw: str) -> str | None:
    """Normalize a DOI string. Returns the bare DOI (e.g.
    "10.1000/foo.bar") or None if input doesn't look like one.

    Strips:
      - URL prefix (`https://doi.org/`, `dx.doi.org/`)
      - `doi:` scheme prefix
      - URL fragment (`#frag`)
      - URL query string (`?utm_source=x`)
      - trailing `/`
    Lower-cases the entire DOI (DOIs are
    case-insensitive per the standard).
    """
    if not raw:
        return None
    text = raw.strip().lower()
    text = _DOI_PREFIX_RE.sub("", text)
    if text.startswith("doi:"):
        text = text[4:]
    # Drop fragment first, then query.
    text = text.split("#", 1)[0]
    text = text.split("?", 1)[0]
    text = text.rstrip("/")
    if not text.startswith("10."):
        return None
    # Reject anything with whitespace.
    if any(c.isspace() for c in text):
        return None
    # Strict shape match — rejects `10.123/foo` (registrant must
    # be 4-9 digits) and other near-DOI strings like
    # `10.x` URL paths that happen to start with the prefix.
    if not _DOI_FULL_RE.match(text):
        return None
    return text


def _canonicalize_pmid(raw: str) -> str | None:
    """Normalize a PMID. Accepts URL forms and bare digits.
    Returns digits-only string or None."""
    if not raw:
        return None
    text = raw.strip()
    if text.isdigit():
        return text
    m = _PMID_RE.match(text)
    if m:
        return m.group(1)
    return None


def _normalize_web_url(url: str) -> str:
    """Reuse the M-16 URL canonicalizer. Importing lazily so
    this module's import surface stays tight."""
    from src.polaris_graph.audit_ir.run_diff import _normalize_url
    return _normalize_url(url)


def make_cache_key(source_url: str) -> str:
    """Build a stable cache key from a source URL or identifier.

    Tries DOI first (most stable), then PMID, then falls back to
    canonicalized web URL. Returns a string with a discriminator
    prefix so different identifier kinds never collide.

    Raises RetrievalCacheError on empty input.
    """
    if not source_url or not source_url.strip():
        raise RetrievalCacheError("source_url must be non-empty")
    text = source_url.strip()

    doi = _canonicalize_doi(text)
    if doi is not None:
        return f"doi:{doi}"

    pmid = _canonicalize_pmid(text)
    if pmid is not None:
        return f"pmid:{pmid}"

    normalized = _normalize_web_url(text)
    if not normalized:
        raise RetrievalCacheError(
            f"could not canonicalize source_url: {source_url!r}"
        )
    return f"url:{normalized}"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class RetrievalCacheStore:
    """SQLite-backed retrieval cache, per-workspace isolated.

    Pattern matches M-21 `WorkspaceMemoryStore`: per-call
    connections, WAL journal, isolation_level=None for explicit
    transaction control. Cross-workspace isolation: every read +
    write requires a workspace_id. Same DB file as
    workspace_memory; one extra table.
    """

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self._db_path, isolation_level=None, timeout=30.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    # -- writes --

    def put(
        self,
        *,
        workspace_id: str,
        source_url: str,
        payload: bytes,
        content_type: str,
        fetch_status_code: int,
        fetched_at: float | None = None,
        cache_key: str | None = None,
    ) -> CacheEntry:
        """Insert or replace a cache entry. Returns the persisted
        entry record.

        Replaces on (workspace_id, cache_key) collision — refetch
        of the same source overwrites the stale payload.
        """
        if not workspace_id or not workspace_id.strip():
            raise RetrievalCacheError("workspace_id must be non-empty")
        if not isinstance(payload, bytes):
            raise RetrievalCacheError(
                f"payload must be bytes, got {type(payload).__name__}"
            )
        if not isinstance(fetch_status_code, int):
            raise RetrievalCacheError(
                "fetch_status_code must be int"
            )

        key = cache_key if cache_key is not None else make_cache_key(source_url)
        ws = workspace_id.strip()
        ts = fetched_at if fetched_at is not None else time.time()
        sha = hashlib.sha256(payload).hexdigest()
        ctype = content_type.strip() if content_type else ""

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO retrieval_cache
                    (cache_key, workspace_id, source_url, payload,
                     content_type, payload_sha256, fetched_at,
                     last_hit_at, fetch_status_code)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (key, ws, source_url, payload, ctype, sha, ts,
                 fetch_status_code),
            )

        return CacheEntry(
            cache_key=key,
            workspace_id=ws,
            source_url=source_url,
            payload=payload,
            content_type=ctype,
            payload_sha256=sha,
            fetched_at=ts,
            last_hit_at=None,
            fetch_status_code=fetch_status_code,
        )

    # -- reads --

    def get(
        self, workspace_id: str, source_url: str
    ) -> CacheEntry | None:
        """Fetch by workspace + source URL. Returns None on miss.

        Updates `last_hit_at` on hit (write-through, single
        UPDATE per read — kept cheap by the workspace-scoped
        index).
        """
        if not workspace_id or not workspace_id.strip():
            raise RetrievalCacheError("workspace_id must be non-empty")
        key = make_cache_key(source_url)
        return self._get_by_key(workspace_id.strip(), key)

    def _get_by_key(
        self, workspace_id: str, cache_key: str
    ) -> CacheEntry | None:
        """Atomic SELECT + UPDATE last_hit_at.

        Wrapped in BEGIN IMMEDIATE to prevent the race where a
        concurrent put()/evict() lands between SELECT and UPDATE
        — without the explicit transaction, the caller could
        receive a stale payload while last_hit_at lands on a
        newer or deleted row. BEGIN IMMEDIATE acquires the write
        lock at the start so no other writer can interleave.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    "SELECT * FROM retrieval_cache "
                    "WHERE workspace_id=? AND cache_key=?",
                    (workspace_id, cache_key),
                )
                row = cur.fetchone()
                if row is None:
                    conn.execute("COMMIT")
                    return None

                now = time.time()
                conn.execute(
                    "UPDATE retrieval_cache SET last_hit_at=? "
                    "WHERE workspace_id=? AND cache_key=?",
                    (now, workspace_id, cache_key),
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return _row_to_entry(row, last_hit_at_override=now)

    # -- eviction (explicit, not pure TTL) --

    def evict(self, workspace_id: str, cache_key: str) -> bool:
        """Remove one entry. Returns True if a row was deleted."""
        if not workspace_id or not workspace_id.strip():
            raise RetrievalCacheError("workspace_id must be non-empty")
        if not cache_key or not cache_key.strip():
            raise RetrievalCacheError("cache_key must be non-empty")
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM retrieval_cache "
                "WHERE workspace_id=? AND cache_key=?",
                (workspace_id.strip(), cache_key.strip()),
            )
            return cur.rowcount > 0

    def evict_by_url(self, workspace_id: str, source_url: str) -> bool:
        """Convenience: canonicalize the URL then evict.

        This is the API surface M-D10 (citation freshness
        monitoring) will call: when a DOI is detected as
        retracted/superseded, M-D10 invokes
        `evict_by_url(workspace_id, doi_url)` to invalidate the
        cache without needing to know our key format.
        """
        return self.evict(workspace_id, make_cache_key(source_url))

    def evict_older_than(
        self, workspace_id: str, max_age_seconds: float
    ) -> int:
        """Bulk-evict entries older than `max_age_seconds`.
        Returns the number of rows deleted."""
        if not workspace_id or not workspace_id.strip():
            raise RetrievalCacheError("workspace_id must be non-empty")
        if max_age_seconds < 0:
            raise RetrievalCacheError(
                "max_age_seconds must be >=0"
            )
        cutoff = time.time() - max_age_seconds
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM retrieval_cache "
                "WHERE workspace_id=? AND fetched_at < ?",
                (workspace_id.strip(), cutoff),
            )
            return cur.rowcount

    def evict_all(self, workspace_id: str) -> int:
        """Workspace-wide flush. Returns rows deleted."""
        if not workspace_id or not workspace_id.strip():
            raise RetrievalCacheError("workspace_id must be non-empty")
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM retrieval_cache WHERE workspace_id=?",
                (workspace_id.strip(),),
            )
            return cur.rowcount

    # -- introspection --

    def count(self, workspace_id: str) -> int:
        """Total entries in this workspace's cache."""
        if not workspace_id or not workspace_id.strip():
            raise RetrievalCacheError("workspace_id must be non-empty")
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM retrieval_cache "
                "WHERE workspace_id=?",
                (workspace_id.strip(),),
            )
            return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_entry(
    row: sqlite3.Row, *, last_hit_at_override: float | None = None
) -> CacheEntry:
    """sqlite3.Row → CacheEntry. `last_hit_at_override` lets
    `_get_by_key` reflect the just-written hit timestamp without
    a re-SELECT."""
    return CacheEntry(
        cache_key=row["cache_key"],
        workspace_id=row["workspace_id"],
        source_url=row["source_url"],
        payload=bytes(row["payload"]),
        content_type=row["content_type"],
        payload_sha256=row["payload_sha256"],
        fetched_at=row["fetched_at"],
        last_hit_at=(
            last_hit_at_override
            if last_hit_at_override is not None
            else row["last_hit_at"]
        ),
        fetch_status_code=row["fetch_status_code"],
    )
