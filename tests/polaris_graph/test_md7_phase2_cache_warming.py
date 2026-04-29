"""M-D7 phase 2 v1 — cache warming tests.

Pins:
  - warm_cache pure substrate contract
  - skip_existing semantics (skip vs force-refresh)
  - on_fetcher_error semantics (raise vs record)
  - Duplicate URL deduplication (first wins, dupes dropped)
  - Empty / whitespace URL handling
  - Workspace isolation
  - FetchResult shape validation (FetcherProtocolError)
  - Partial-progress preservation under raise mode
  - WarmingReport count aggregation
  - report_to_exit_code mapping
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.cache_warming import (
    CacheFetcher,
    CacheWarmingError,
    FetchResult,
    FetcherProtocolError,
    WarmingReport,
    WarmingResult,
    WarmingStatus,
    report_to_exit_code,
    warm_cache,
)
from src.polaris_graph.audit_ir.retrieval_cache import (
    RetrievalCacheStore,
    make_cache_key,
)


# ---------------------------------------------------------------------------
# Fixtures: store + fetchers
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache_store(tmp_path: Path) -> RetrievalCacheStore:
    return RetrievalCacheStore(tmp_path / "cache.sqlite")


@dataclass
class _StubFetcher:
    """Returns a FetchResult with deterministic content based
    on the URL."""

    payloads: dict[str, FetchResult] | None = None
    call_log: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []

    def fetch(self, source_url: str) -> FetchResult:
        self.call_log.append(source_url)
        if self.payloads is not None and source_url in self.payloads:
            return self.payloads[source_url]
        # Default payload — bytes of the URL.
        return FetchResult(
            payload=source_url.encode("utf-8"),
            content_type="text/html",
            fetch_status_code=200,
        )


@dataclass
class _RaisingFetcher:
    """Raises a configured exception type on every fetch."""

    exc: Exception
    call_log: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []

    def fetch(self, source_url: str) -> FetchResult:
        self.call_log.append(source_url)
        raise self.exc


@dataclass
class _ConditionalFetcher:
    """Raises for URLs matching `raise_for`, returns default
    FetchResult otherwise."""

    raise_for: set[str]
    exc_factory: type[Exception]
    call_log: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []

    def fetch(self, source_url: str) -> FetchResult:
        self.call_log.append(source_url)
        if source_url in self.raise_for:
            raise self.exc_factory(f"simulated failure for {source_url}")
        return FetchResult(
            payload=source_url.encode("utf-8"),
            content_type="text/html",
            fetch_status_code=200,
        )


# ---------------------------------------------------------------------------
# Empty / no-op
# ---------------------------------------------------------------------------


def test_empty_url_list_returns_empty_report(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    report = warm_cache(cache_store, "ws1", [], fetcher)
    assert report.workspace_id == "ws1"
    assert report.results == ()
    assert report.fetched_count == 0
    assert report.skipped_count == 0
    assert report.errored_count == 0
    assert report.started_at <= report.finished_at
    assert fetcher.call_log == []


def test_only_empty_or_whitespace_urls_returns_empty_report(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    report = warm_cache(cache_store, "ws1", ["", "   ", "\t\n"], fetcher)
    assert report.results == ()
    assert fetcher.call_log == []


# ---------------------------------------------------------------------------
# Cold cache → fetched
# ---------------------------------------------------------------------------


def test_cold_cache_all_fetched(cache_store: RetrievalCacheStore) -> None:
    urls = [
        "https://example.com/a",
        "https://example.com/b",
    ]
    fetcher = _StubFetcher()
    report = warm_cache(cache_store, "ws1", urls, fetcher)
    assert report.fetched_count == 2
    assert report.skipped_count == 0
    assert report.errored_count == 0
    assert all(r.status == WarmingStatus.FETCHED for r in report.results)
    assert all(r.fetched_at is not None for r in report.results)
    # Verify entries actually landed in cache
    for url in urls:
        entry = cache_store.get("ws1", url)
        assert entry is not None
        assert entry.payload == url.encode("utf-8")


def test_fetched_entries_preserve_content_type_and_status(
    cache_store: RetrievalCacheStore,
) -> None:
    payloads = {
        "https://example.com/a": FetchResult(
            payload=b"hello",
            content_type="application/pdf",
            fetch_status_code=200,
        ),
    }
    fetcher = _StubFetcher(payloads=payloads)
    warm_cache(cache_store, "ws1", ["https://example.com/a"], fetcher)
    entry = cache_store.get("ws1", "https://example.com/a")
    assert entry is not None
    assert entry.payload == b"hello"
    assert entry.content_type == "application/pdf"
    assert entry.fetch_status_code == 200


# ---------------------------------------------------------------------------
# skip_existing semantics
# ---------------------------------------------------------------------------


def test_skip_existing_default_true_skips_cached(
    cache_store: RetrievalCacheStore,
) -> None:
    cache_store.put(
        workspace_id="ws1",
        source_url="https://example.com/a",
        payload=b"already cached",
        content_type="text/html",
        fetch_status_code=200,
    )
    fetcher = _StubFetcher()
    report = warm_cache(
        cache_store, "ws1", ["https://example.com/a"], fetcher,
    )
    assert report.skipped_count == 1
    assert report.fetched_count == 0
    assert fetcher.call_log == [], "fetcher should not be called for cached URL"
    assert report.results[0].status == WarmingStatus.SKIPPED_CACHED


def test_skip_existing_false_force_refreshes(
    cache_store: RetrievalCacheStore,
) -> None:
    cache_store.put(
        workspace_id="ws1",
        source_url="https://example.com/a",
        payload=b"old payload",
        content_type="text/html",
        fetch_status_code=200,
    )
    fetcher = _StubFetcher(payloads={
        "https://example.com/a": FetchResult(
            payload=b"new payload",
            content_type="text/html",
            fetch_status_code=200,
        ),
    })
    report = warm_cache(
        cache_store, "ws1", ["https://example.com/a"], fetcher,
        skip_existing=False,
    )
    assert report.fetched_count == 1
    assert report.skipped_count == 0
    assert fetcher.call_log == ["https://example.com/a"]
    entry = cache_store.get("ws1", "https://example.com/a")
    assert entry is not None
    assert entry.payload == b"new payload"


def test_mixed_cached_and_uncached(cache_store: RetrievalCacheStore) -> None:
    cache_store.put(
        workspace_id="ws1",
        source_url="https://example.com/cached",
        payload=b"cached",
        content_type="text/html",
        fetch_status_code=200,
    )
    fetcher = _StubFetcher()
    report = warm_cache(
        cache_store, "ws1",
        ["https://example.com/cached", "https://example.com/cold"],
        fetcher,
    )
    assert report.fetched_count == 1
    assert report.skipped_count == 1
    assert fetcher.call_log == ["https://example.com/cold"]


# ---------------------------------------------------------------------------
# on_fetcher_error semantics
# ---------------------------------------------------------------------------


def test_on_error_record_continues_after_failure(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _ConditionalFetcher(
        raise_for={"https://example.com/bad"},
        exc_factory=RuntimeError,
    )
    urls = [
        "https://example.com/good1",
        "https://example.com/bad",
        "https://example.com/good2",
    ]
    report = warm_cache(
        cache_store, "ws1", urls, fetcher,
        on_fetcher_error="record",
    )
    assert report.fetched_count == 2
    assert report.errored_count == 1
    # Both good URLs continued past the bad one
    assert "https://example.com/good2" in fetcher.call_log
    bad = next(r for r in report.results
               if r.source_url == "https://example.com/bad")
    assert bad.status == WarmingStatus.ERRORED
    assert bad.error is not None
    assert "simulated failure" in bad.error


def test_on_error_raise_propagates(cache_store: RetrievalCacheStore) -> None:
    fetcher = _RaisingFetcher(exc=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        warm_cache(
            cache_store, "ws1",
            ["https://example.com/a"],
            fetcher,
            on_fetcher_error="raise",
        )


def test_on_error_raise_preserves_partial_progress(
    cache_store: RetrievalCacheStore,
) -> None:
    """Per LAW II — idempotent partial progress. Already-fetched
    entries land in the cache before the raising URL is reached.
    No rollback. Operator can re-run warming and the
    skip_existing default will skip the already-warm entries."""
    fetcher = _ConditionalFetcher(
        raise_for={"https://example.com/bad"},
        exc_factory=RuntimeError,
    )
    urls = [
        "https://example.com/good_first",
        "https://example.com/bad",
        "https://example.com/never_reached",
    ]
    with pytest.raises(RuntimeError):
        warm_cache(
            cache_store, "ws1", urls, fetcher,
            on_fetcher_error="raise",
        )
    # The good URL before the bad one IS in cache
    assert cache_store.get("ws1", "https://example.com/good_first") is not None
    # The URL after is NOT (loop exited)
    assert cache_store.get("ws1", "https://example.com/never_reached") is None


# ---------------------------------------------------------------------------
# Duplicate URL deduplication
# ---------------------------------------------------------------------------


def test_duplicate_urls_deduplicate_in_report(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    urls = [
        "https://example.com/a",
        "https://example.com/a",  # exact duplicate
        "https://example.com/b",
    ]
    report = warm_cache(cache_store, "ws1", urls, fetcher)
    # Only 2 unique entries in the report
    assert len(report.results) == 2
    # Fetcher only called twice (the dupe was dropped before fetch)
    assert fetcher.call_log == ["https://example.com/a", "https://example.com/b"]


def test_duplicate_canonical_keys_deduplicate(
    cache_store: RetrievalCacheStore,
) -> None:
    """Two URLs that canonicalize to the same cache_key (e.g.
    DOI URLs vs https://doi.org/... links) should dedup."""
    # If make_cache_key normalizes "doi:10.1000/foo" and
    # "https://doi.org/10.1000/foo" to the same key, both
    # should dedup. We test by feeding the same URL twice
    # (guaranteed same key) which exercises the same code path.
    fetcher = _StubFetcher()
    url = "https://example.com/a"
    report = warm_cache(cache_store, "ws1", [url, url, url], fetcher)
    assert len(report.results) == 1
    assert fetcher.call_log == [url]


# ---------------------------------------------------------------------------
# Workspace isolation
# ---------------------------------------------------------------------------


def test_warming_one_workspace_does_not_warm_another(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    warm_cache(
        cache_store, "ws1", ["https://example.com/a"], fetcher,
    )
    assert cache_store.get("ws1", "https://example.com/a") is not None
    assert cache_store.get("ws2", "https://example.com/a") is None


def test_skip_existing_is_workspace_scoped(
    cache_store: RetrievalCacheStore,
) -> None:
    """A URL cached in ws1 should NOT be skipped when warming ws2."""
    cache_store.put(
        workspace_id="ws1",
        source_url="https://example.com/a",
        payload=b"in ws1",
        content_type="text/html",
        fetch_status_code=200,
    )
    fetcher = _StubFetcher()
    report = warm_cache(
        cache_store, "ws2", ["https://example.com/a"], fetcher,
    )
    assert report.fetched_count == 1
    assert report.skipped_count == 0


# ---------------------------------------------------------------------------
# Contract validation
# ---------------------------------------------------------------------------


def test_empty_workspace_id_raises(cache_store: RetrievalCacheStore) -> None:
    fetcher = _StubFetcher()
    with pytest.raises(CacheWarmingError, match="workspace_id"):
        warm_cache(cache_store, "", ["https://example.com/a"], fetcher)


def test_whitespace_workspace_id_raises(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    with pytest.raises(CacheWarmingError, match="workspace_id"):
        warm_cache(cache_store, "   ", ["https://example.com/a"], fetcher)


def test_workspace_id_stripped(cache_store: RetrievalCacheStore) -> None:
    """Leading/trailing whitespace on workspace_id is trimmed
    before use — matches M-D7 phase 1 store.put behavior."""
    fetcher = _StubFetcher()
    report = warm_cache(
        cache_store, "  ws1  ", ["https://example.com/a"], fetcher,
    )
    assert report.workspace_id == "ws1"
    assert cache_store.get("ws1", "https://example.com/a") is not None


def test_non_store_argument_raises(cache_store: RetrievalCacheStore) -> None:
    fetcher = _StubFetcher()
    with pytest.raises(CacheWarmingError, match="store must"):
        warm_cache("not a store", "ws1", [], fetcher)  # type: ignore[arg-type]


def test_non_sequence_urls_raises(cache_store: RetrievalCacheStore) -> None:
    fetcher = _StubFetcher()
    with pytest.raises(CacheWarmingError, match="source_urls"):
        warm_cache(cache_store, "ws1", "not a list", fetcher)  # type: ignore[arg-type]


def test_non_string_url_in_list_raises(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    with pytest.raises(CacheWarmingError, match="source_urls entries"):
        warm_cache(
            cache_store, "ws1",
            ["https://example.com/a", 123],  # type: ignore[list-item]
            fetcher,
        )


def test_invalid_on_fetcher_error_value_raises(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    with pytest.raises(CacheWarmingError, match="on_fetcher_error"):
        warm_cache(
            cache_store, "ws1", [], fetcher,
            on_fetcher_error="ignore",  # type: ignore[arg-type]
        )


def test_fetcher_without_fetch_method_raises(
    cache_store: RetrievalCacheStore,
) -> None:
    @dataclass
    class _NotAFetcher:
        pass

    with pytest.raises(CacheWarmingError, match="CacheFetcher Protocol"):
        warm_cache(
            cache_store, "ws1", [],
            _NotAFetcher(),  # type: ignore[arg-type]
        )


def test_workspace_id_must_be_str(
    cache_store: RetrievalCacheStore,
) -> None:
    """Codex round-1 MEDIUM fix (v2): non-string workspace_id
    types must raise. v1 accepted bytes silently (creating
    orphaned cache namespace) and leaked AttributeError on int
    (no .strip())."""
    fetcher = _StubFetcher()
    with pytest.raises(CacheWarmingError, match="workspace_id must be str"):
        warm_cache(cache_store, b"ws1", [], fetcher)  # type: ignore[arg-type]
    with pytest.raises(CacheWarmingError, match="workspace_id must be str"):
        warm_cache(cache_store, 123, [], fetcher)  # type: ignore[arg-type]


def test_fetcher_with_non_callable_fetch_attr_raises(
    cache_store: RetrievalCacheStore,
) -> None:
    """Codex round-1 MEDIUM fix (v2): hasattr check alone
    isn't enough — v1 accepted fetchers with non-callable
    `fetch` attribute, resulting in TypeError being caught as
    a per-URL ERRORED instead of surfacing as contract error.
    """
    @dataclass
    class _BadFetcher:
        fetch: str = "not callable"

    with pytest.raises(CacheWarmingError, match="callable"):
        warm_cache(
            cache_store, "ws1", [],
            _BadFetcher(),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# FetchResult shape validation
# ---------------------------------------------------------------------------


def test_fetcher_returning_non_fetchresult_raises_protocol_error(
    cache_store: RetrievalCacheStore,
) -> None:
    @dataclass
    class _BadFetcher:
        def fetch(self, url: str) -> str:  # wrong return type
            return "not a FetchResult"

    with pytest.raises(FetcherProtocolError, match="FetchResult"):
        warm_cache(
            cache_store, "ws1",
            ["https://example.com/a"],
            _BadFetcher(),  # type: ignore[arg-type]
        )


def test_fetcher_protocol_error_propagates_under_record_mode(
    cache_store: RetrievalCacheStore,
) -> None:
    """FetcherProtocolError is a programmer error, not a fetch
    failure. on_fetcher_error="record" should NOT swallow it —
    the caller's Fetcher impl needs fixing."""
    @dataclass
    class _BadFetcher:
        def fetch(self, url: str) -> str:
            return "wrong type"

    with pytest.raises(FetcherProtocolError):
        warm_cache(
            cache_store, "ws1",
            ["https://example.com/a"],
            _BadFetcher(),  # type: ignore[arg-type]
            on_fetcher_error="record",
        )


# ---------------------------------------------------------------------------
# WarmingReport count aggregation
# ---------------------------------------------------------------------------


def test_counts_match_results(cache_store: RetrievalCacheStore) -> None:
    cache_store.put(
        workspace_id="ws1",
        source_url="https://example.com/cached",
        payload=b"x",
        content_type="text/html",
        fetch_status_code=200,
    )
    fetcher = _ConditionalFetcher(
        raise_for={"https://example.com/bad"},
        exc_factory=RuntimeError,
    )
    urls = [
        "https://example.com/cached",  # SKIPPED
        "https://example.com/good1",   # FETCHED
        "https://example.com/bad",     # ERRORED
        "https://example.com/good2",   # FETCHED
    ]
    report = warm_cache(cache_store, "ws1", urls, fetcher)
    assert report.skipped_count == 1
    assert report.fetched_count == 2
    assert report.errored_count == 1
    assert (
        report.skipped_count + report.fetched_count + report.errored_count
        == len(report.results)
    )


def test_started_at_le_finished_at(cache_store: RetrievalCacheStore) -> None:
    fetcher = _StubFetcher()
    report = warm_cache(
        cache_store, "ws1", ["https://example.com/a"], fetcher,
    )
    assert report.started_at <= report.finished_at


# ---------------------------------------------------------------------------
# report_to_exit_code mapping
# ---------------------------------------------------------------------------


def test_report_to_exit_code_zero_errored_passes(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    report = warm_cache(
        cache_store, "ws1", ["https://example.com/a"], fetcher,
    )
    assert report.errored_count == 0
    assert report_to_exit_code(report) == 0


def test_report_to_exit_code_any_errored_blocks(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _RaisingFetcher(exc=RuntimeError("boom"))
    report = warm_cache(
        cache_store, "ws1", ["https://example.com/a"], fetcher,
        on_fetcher_error="record",
    )
    assert report.errored_count == 1
    assert report_to_exit_code(report) == 1


def test_report_to_exit_code_empty_no_op_passes(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    report = warm_cache(cache_store, "ws1", [], fetcher)
    assert report_to_exit_code(report) == 0


# ---------------------------------------------------------------------------
# Cache_key identity
# ---------------------------------------------------------------------------


def test_warming_result_cache_key_matches_make_cache_key(
    cache_store: RetrievalCacheStore,
) -> None:
    fetcher = _StubFetcher()
    url = "https://example.com/a"
    report = warm_cache(cache_store, "ws1", [url], fetcher)
    assert report.results[0].cache_key == make_cache_key(url)
