"""M-D7 phase 2 v1 (Phase D): Cache warming substrate.

M-D7 phase 1 (`retrieval_cache.py`, commit 74b8962) shipped the
per-workspace SQLite retrieval cache with DOI/PMID/URL
canonicalization + a 4-method eviction API.

Phase 2 v1 layers **cache warming** on top: given a list of
source URLs, populate the cache from a pluggable Fetcher
Protocol BEFORE the user asks. Pure substrate — no live HTTP,
no DB queries beyond the M-D7 phase 1 surface. The Fetcher is
the seam: caller code wires up the actual HTTP / Crossref /
Semantic Scholar client.

## Why this milestone matters

Cold-cache pipelines pay first-query latency on every fetch.
For predictable workloads (e.g. a recurring overnight audit
that re-fetches the same N regulatory sources, or a batch
warming step before a known live-audit window opens), warming
the cache amortizes the fetch cost outside the user-facing
request path.

Phase 2 v1 ships the substrate. Phase 2 v2 (deferred) may add:
  - Concurrent warming via thread / asyncio Fetcher variants
  - Auto-warming heuristics (warm what was hit recently in
    other workspaces, warm based on a static "always-fresh"
    list, etc.)
  - Integration with M-D10 freshness monitor (auto-warm on
    eviction trigger so the next fetch is never cold)

## What v1 ships

  - `CacheFetcher` Protocol — pluggable fetcher contract
  - `FetchResult` dataclass — payload + metadata
  - `WarmingStatus` enum: FETCHED | SKIPPED_CACHED | ERRORED
  - `WarmingResult` dataclass — one entry per source URL
  - `WarmingReport` dataclass — full warming output
  - `warm_cache(store, workspace_id, source_urls, fetcher, *,
    skip_existing, on_fetcher_error)` — pure substrate

## Substrate boundary

Imports `retrieval_cache.RetrievalCacheStore` +
`retrieval_cache.make_cache_key` + stdlib only. Does not
import any HTTP client. Does not perform DB queries beyond
the M-D7 phase 1 API surface (store.get + store.put).

See `docs/md7_phase2_threat_model.md` for boundaries.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Protocol, Sequence

from src.polaris_graph.audit_ir.retrieval_cache import (
    RetrievalCacheError,
    RetrievalCacheStore,
    make_cache_key,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class CacheWarmingError(ValueError):
    """Raised on contract violations — empty workspace_id, bad
    fetcher Protocol, invalid on_fetcher_error sentinel, etc."""


class FetcherProtocolError(CacheWarmingError):
    """A Fetcher returned something other than a FetchResult.
    Caller-side bug — surface loudly per LAW II."""


# ---------------------------------------------------------------------------
# Fetcher Protocol + result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FetchResult:
    """One fetch's output — payload + metadata.

    `payload` is raw bytes (HTML, PDF, JSON, etc.) — caller's
    responsibility to encode/decode. `content_type` is the
    HTTP-style MIME string. `fetch_status_code` is the HTTP-
    style status (200 OK, 404, 429, etc.).
    """

    payload: bytes
    content_type: str
    fetch_status_code: int


class CacheFetcher(Protocol):
    """Pluggable fetcher contract.

    Implementers MUST:
      - Return a `FetchResult` on success
      - Raise an exception on failure (do NOT return a
        FetchResult with a non-2xx status to signal failure
        — that's a *successful fetch of an error page*, which
        IS what callers want cached for retry-suppression)
      - Be safe to call concurrently if the warming caller
        opts into concurrency (phase 2 v2)

    Implementers MUST NOT:
      - Mutate the cache directly
      - Block indefinitely (caller should wrap with timeout
        if their fetch backend doesn't enforce one)
    """

    def fetch(self, source_url: str) -> FetchResult:
        ...


# ---------------------------------------------------------------------------
# Warming result types
# ---------------------------------------------------------------------------


class WarmingStatus(str, Enum):
    """Per-URL warming outcome.

    FETCHED: cache miss → fetcher invoked → payload stored.
    SKIPPED_CACHED: cache hit + skip_existing=True → no fetch.
    ERRORED: fetcher raised → entry NOT stored, error string
       captured in WarmingResult.error.
    """

    FETCHED = "fetched"
    SKIPPED_CACHED = "skipped_cached"
    ERRORED = "errored"


@dataclass(frozen=True)
class WarmingResult:
    """One source_url's outcome.

    `cache_key` is the canonicalized key (matches
    `make_cache_key(source_url)`).
    `error` is None unless `status == ERRORED`, in which case
    it carries the str(exception) of the fetcher's raised
    error. The exception type is NOT preserved — callers
    wanting structured errors should use a custom Fetcher that
    catches its own exceptions and converts to typed
    payloads.
    `fetched_at` is None unless `status == FETCHED`.
    """

    source_url: str
    cache_key: str
    status: WarmingStatus
    error: str | None = None
    fetched_at: float | None = None


@dataclass(frozen=True)
class WarmingReport:
    """Full warming output.

    `workspace_id` echoes the warming call's argument.
    `started_at` / `finished_at` are UNIX epoch floats; the
    duration is `finished_at - started_at`.
    `results` is one entry per UNIQUE input source_url
    (duplicates collapse to the same cache_key — first wins,
    subsequent dupes are dropped from the report).
    `fetched_count` / `skipped_count` / `errored_count` are
    convenience aggregates over `results`.
    """

    workspace_id: str
    started_at: float
    finished_at: float
    results: tuple[WarmingResult, ...] = field(default_factory=tuple)
    fetched_count: int = 0
    skipped_count: int = 0
    errored_count: int = 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_VALID_ON_ERROR: tuple[str, ...] = ("raise", "record")


def warm_cache(
    store: RetrievalCacheStore,
    workspace_id: str,
    source_urls: Sequence[str],
    fetcher: CacheFetcher,
    *,
    skip_existing: bool = True,
    on_fetcher_error: Literal["raise", "record"] = "record",
) -> WarmingReport:
    """Warm `store` for `workspace_id` by fetching `source_urls`
    via `fetcher`.

    For each URL:
    1. If `skip_existing` and the URL is already cached, skip
       (status=SKIPPED_CACHED).
    2. Else, call `fetcher.fetch(url)` to get a FetchResult.
       Validate the FetchResult shape, then store via
       `store.put(...)`.
       Status=FETCHED on success.
    3. If the fetcher raises:
       - `on_fetcher_error="record"` → status=ERRORED for this
         URL, continue with the next URL. Other URLs' progress
         is preserved.
       - `on_fetcher_error="raise"` → re-raise the fetcher's
         exception immediately. Already-warmed URLs in this
         call ARE preserved in the cache (idempotent partial
         progress per LAW II — no rollback that would force
         the operator to re-fetch already-warm entries).

    Duplicate source_urls in input collapse to the same
    cache_key. The first occurrence is processed; duplicates
    are dropped from the report (NOT counted in any aggregate).

    Empty source_urls returns a trivially-valid empty report
    (not an error — warming nothing is a no-op).
    """
    if not isinstance(store, RetrievalCacheStore):
        raise CacheWarmingError(
            f"store must be RetrievalCacheStore, got "
            f"{type(store).__name__}"
        )
    # Codex round-1 MEDIUM fix (v2): workspace_id must be str.
    # v1 accepted bytes/int silently — bytes would create an
    # orphaned cache namespace invisible to normal str lookups,
    # and int would leak AttributeError on .strip().
    if not isinstance(workspace_id, str):
        raise CacheWarmingError(
            f"workspace_id must be str, got "
            f"{type(workspace_id).__name__}"
        )
    if not workspace_id or not workspace_id.strip():
        raise CacheWarmingError("workspace_id must be non-empty")
    if not isinstance(source_urls, Sequence) or isinstance(
        source_urls, (str, bytes)
    ):
        raise CacheWarmingError(
            f"source_urls must be a sequence of str, got "
            f"{type(source_urls).__name__}"
        )
    # Codex round-1 MEDIUM fix (v2): fetcher.fetch must be
    # callable. v1 only checked hasattr, accepting fetchers
    # with non-callable `fetch` attribute — the resulting
    # TypeError was caught as ERRORED instead of surfacing as
    # a contract error.
    if (
        fetcher is None
        or not hasattr(fetcher, "fetch")
        or not callable(getattr(fetcher, "fetch"))
    ):
        raise CacheWarmingError(
            "fetcher must implement the CacheFetcher Protocol "
            "(must have a callable `fetch(url) -> FetchResult` method)"
        )
    if on_fetcher_error not in _VALID_ON_ERROR:
        raise CacheWarmingError(
            f"on_fetcher_error must be one of {_VALID_ON_ERROR!r}, "
            f"got {on_fetcher_error!r}"
        )

    ws = workspace_id.strip()
    started_at = time.time()

    # Dedup input by cache_key. First-occurrence wins; track
    # which keys we've already processed.
    seen_keys: set[str] = set()
    results: list[WarmingResult] = []

    for raw_url in source_urls:
        if not isinstance(raw_url, str):
            raise CacheWarmingError(
                f"source_urls entries must be str, got "
                f"{type(raw_url).__name__}"
            )
        url = raw_url.strip()
        if not url:
            # Empty / whitespace URL: skip silently. This
            # matches the M-D7 phase 1 cache_key behavior of
            # rejecting empty input upstream — but here at the
            # warming layer we just skip rather than raise, to
            # let bulk warming continue if one URL in the list
            # is malformed.
            continue
        cache_key = make_cache_key(url)
        if cache_key in seen_keys:
            # Duplicate input URL canonicalizing to the same
            # key — drop from the report.
            continue
        seen_keys.add(cache_key)

        if skip_existing and store.get(ws, url) is not None:
            results.append(
                WarmingResult(
                    source_url=url,
                    cache_key=cache_key,
                    status=WarmingStatus.SKIPPED_CACHED,
                )
            )
            continue

        try:
            fetch_result = fetcher.fetch(url)
        except CacheWarmingError:
            # Re-raise our own contract errors regardless of
            # on_fetcher_error — these are programmer errors,
            # not transient fetch failures.
            raise
        except Exception as exc:  # noqa: BLE001 — intentional broad
            if on_fetcher_error == "raise":
                raise
            results.append(
                WarmingResult(
                    source_url=url,
                    cache_key=cache_key,
                    status=WarmingStatus.ERRORED,
                    error=str(exc),
                )
            )
            continue

        if not isinstance(fetch_result, FetchResult):
            raise FetcherProtocolError(
                f"fetcher.fetch({url!r}) returned "
                f"{type(fetch_result).__name__}, expected FetchResult"
            )

        # Persist via M-D7 phase 1 API.
        try:
            entry = store.put(
                workspace_id=ws,
                source_url=url,
                payload=fetch_result.payload,
                content_type=fetch_result.content_type,
                fetch_status_code=fetch_result.fetch_status_code,
                cache_key=cache_key,
            )
        except RetrievalCacheError:
            # Cache-layer contract error — surface loudly. Don't
            # silently demote to ERRORED, because this means the
            # FetchResult was malformed (e.g. payload not bytes)
            # and the caller's Fetcher impl needs fixing.
            raise

        results.append(
            WarmingResult(
                source_url=url,
                cache_key=cache_key,
                status=WarmingStatus.FETCHED,
                fetched_at=entry.fetched_at,
            )
        )

    finished_at = time.time()
    fetched = sum(1 for r in results if r.status == WarmingStatus.FETCHED)
    skipped = sum(1 for r in results if r.status == WarmingStatus.SKIPPED_CACHED)
    errored = sum(1 for r in results if r.status == WarmingStatus.ERRORED)

    return WarmingReport(
        workspace_id=ws,
        started_at=started_at,
        finished_at=finished_at,
        results=tuple(results),
        fetched_count=fetched,
        skipped_count=skipped,
        errored_count=errored,
    )


def report_to_exit_code(report: WarmingReport) -> int:
    """Map warming outcome to CI exit code.

    Convention: only `errored_count > 0` returns 1 (block).
    `fetched_count == 0 && skipped_count == 0` (warming a
    completely empty / all-malformed list) returns 0 — that's
    a no-op, not a failure.
    """
    return 1 if report.errored_count > 0 else 0
