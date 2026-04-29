"""M-D8 phase 1 v1 — parallel-fetch substrate tests.

Pins:
  - parallel_fetch dispatch correctness on small/empty input
  - Per-backend concurrency limits enforced via semaphore
  - Global max_workers enforced
  - Per-task timeout marks TIMEOUT and continues
  - ERRORED captures str(exc); other tasks proceed
  - FetchResultRecord shape validation (FetcherProtocolError)
  - Duplicate (source_url, backend_id) collapses to first
  - Result order matches input order (not completion order)
  - Counts sum to len(results)
  - Contract validation (negative cases)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

import pytest

from src.polaris_graph.audit_ir.parallel_fetch import (
    DEFAULT_PER_BACKEND_LIMIT,
    FetchOutcome,
    FetchResultRecord,
    FetchTask,
    FetcherProtocolError,
    ParallelFetchError,
    ParallelFetchReport,
    parallel_fetch,
    report_to_exit_code,
)


# ---------------------------------------------------------------------------
# Stub fetchers
# ---------------------------------------------------------------------------


@dataclass
class _StubFetcher:
    """Returns a deterministic payload based on task URL."""

    delay_seconds: float = 0.0
    call_log: list[FetchTask] = None  # type: ignore[assignment]
    call_log_lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []
        if self.call_log_lock is None:
            self.call_log_lock = threading.Lock()

    def fetch(self, task: FetchTask) -> tuple[bytes, str, int]:
        with self.call_log_lock:
            self.call_log.append(task)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return (
            task.source_url.encode("utf-8"),
            "text/html",
            200,
        )


@dataclass
class _RaisingFetcher:
    exc: Exception

    def fetch(self, task: FetchTask) -> tuple[bytes, str, int]:
        raise self.exc


@dataclass
class _ConditionalFetcher:
    raise_for: set[str]
    exc_type: type[Exception]
    call_log: list[str] = None  # type: ignore[assignment]
    call_log_lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.call_log is None:
            self.call_log = []
        if self.call_log_lock is None:
            self.call_log_lock = threading.Lock()

    def fetch(self, task: FetchTask) -> tuple[bytes, str, int]:
        with self.call_log_lock:
            self.call_log.append(task.source_url)
        if task.source_url in self.raise_for:
            raise self.exc_type(f"sim failure {task.source_url}")
        return (b"ok", "text/html", 200)


# ---------------------------------------------------------------------------
# Empty / no-op
# ---------------------------------------------------------------------------


def test_empty_tasks_returns_empty_report() -> None:
    report = parallel_fetch([], _StubFetcher())
    assert report.results == ()
    assert report.success_count == 0
    assert report.errored_count == 0
    assert report.timeout_count == 0
    assert report.started_at <= report.finished_at


# ---------------------------------------------------------------------------
# Single-task smoke
# ---------------------------------------------------------------------------


def test_single_task_succeeds() -> None:
    fetcher = _StubFetcher()
    tasks = [FetchTask("https://example.com/a", "default")]
    report = parallel_fetch(tasks, fetcher)
    assert report.success_count == 1
    assert report.results[0].outcome == FetchOutcome.SUCCESS
    assert report.results[0].payload == b"https://example.com/a"
    assert report.results[0].content_type == "text/html"
    assert report.results[0].fetch_status_code == 200


def test_task_metadata_round_trips() -> None:
    fetcher = _StubFetcher()
    tasks = [
        FetchTask(
            "https://example.com/a", "serper",
            task_metadata={"tier": "regulatory", "trace_id": "abc"},
        ),
    ]
    report = parallel_fetch(tasks, fetcher)
    assert report.results[0].task_metadata["tier"] == "regulatory"
    assert report.results[0].task_metadata["trace_id"] == "abc"


# ---------------------------------------------------------------------------
# Multi-task ordering
# ---------------------------------------------------------------------------


def test_results_preserve_input_order() -> None:
    """Even though tasks complete in arbitrary order under
    concurrency, `results` is in input order."""
    fetcher = _StubFetcher()
    tasks = [
        FetchTask(f"https://example.com/{i}", "default")
        for i in range(10)
    ]
    report = parallel_fetch(tasks, fetcher)
    for i, rec in enumerate(report.results):
        assert rec.source_url == f"https://example.com/{i}"


def test_concurrent_dispatch_observable_via_overlap() -> None:
    """If max_workers>1 and per-backend limit allows it, tasks
    should run concurrently. Detect by total wall time being
    less than serial."""
    fetcher = _StubFetcher(delay_seconds=0.05)
    tasks = [
        FetchTask(f"https://example.com/{i}", f"backend_{i}")
        for i in range(4)
    ]
    t0 = time.time()
    report = parallel_fetch(tasks, fetcher, max_workers=4)
    elapsed = time.time() - t0
    # Serial would be 4 * 0.05 = 0.2s; concurrent should be ~0.05s.
    # Allow 0.15 for thread-startup overhead on CI.
    assert elapsed < 0.15, f"elapsed {elapsed} suggests not concurrent"
    assert report.success_count == 4


# ---------------------------------------------------------------------------
# Per-backend concurrency limits
# ---------------------------------------------------------------------------


def test_per_backend_limit_serializes_same_backend() -> None:
    """semantic_scholar has limit=1; two tasks on same backend
    must serialize even with max_workers=4."""
    fetcher = _StubFetcher(delay_seconds=0.05)
    tasks = [
        FetchTask("https://a.com/1", "semantic_scholar"),
        FetchTask("https://a.com/2", "semantic_scholar"),
    ]
    t0 = time.time()
    report = parallel_fetch(
        tasks, fetcher, max_workers=4,
        per_backend_max_concurrent={"semantic_scholar": 1},
    )
    elapsed = time.time() - t0
    # With limit=1 they serialize: ~2 * 0.05 = 0.1s minimum.
    # Allow generous CI floor; assert it's not concurrent (< 0.1).
    assert elapsed >= 0.09, (
        f"elapsed {elapsed} suggests concurrency violated limit=1"
    )
    assert report.success_count == 2


def test_per_backend_limit_independent_across_backends() -> None:
    """semantic_scholar limit=1 doesn't slow down a serper task."""
    fetcher = _StubFetcher(delay_seconds=0.05)
    tasks = [
        FetchTask("https://ss.com/1", "semantic_scholar"),
        FetchTask("https://serper.com/1", "serper"),
    ]
    t0 = time.time()
    report = parallel_fetch(
        tasks, fetcher, max_workers=4,
        per_backend_max_concurrent={"semantic_scholar": 1, "serper": 10},
    )
    elapsed = time.time() - t0
    # Both run concurrently — ~0.05s.
    assert elapsed < 0.12
    assert report.success_count == 2


def test_default_per_backend_limit_applies_to_unconfigured(
) -> None:
    """A backend not in per_backend_max_concurrent gets
    DEFAULT_PER_BACKEND_LIMIT."""
    assert DEFAULT_PER_BACKEND_LIMIT >= 1
    fetcher = _StubFetcher()
    tasks = [
        FetchTask(f"https://x.com/{i}", "unconfigured")
        for i in range(DEFAULT_PER_BACKEND_LIMIT + 2)
    ]
    # Should complete without deadlock or error.
    report = parallel_fetch(tasks, fetcher, max_workers=8)
    assert report.success_count == len(tasks)


# ---------------------------------------------------------------------------
# Error semantics
# ---------------------------------------------------------------------------


def test_fetcher_exception_marks_errored_and_continues() -> None:
    fetcher = _ConditionalFetcher(
        raise_for={"https://bad.com"},
        exc_type=RuntimeError,
    )
    tasks = [
        FetchTask("https://good.com/1", "default"),
        FetchTask("https://bad.com", "default"),
        FetchTask("https://good.com/2", "default"),
    ]
    report = parallel_fetch(tasks, fetcher, max_workers=4)
    assert report.success_count == 2
    assert report.errored_count == 1
    bad = next(r for r in report.results
               if r.source_url == "https://bad.com")
    assert bad.outcome == FetchOutcome.ERRORED
    assert "sim failure" in bad.error
    assert bad.payload is None


def test_fetcher_exception_does_not_leak_backend_semaphore() -> None:
    """A backend with limit=1 must not deadlock when the first
    task on that backend raises — the semaphore must release."""
    fetcher = _ConditionalFetcher(
        raise_for={"https://first.com"},
        exc_type=RuntimeError,
    )
    tasks = [
        FetchTask("https://first.com", "single_slot"),
        FetchTask("https://second.com", "single_slot"),
    ]
    # If the semaphore leaked, the second task would deadlock.
    report = parallel_fetch(
        tasks, fetcher, max_workers=4,
        per_backend_max_concurrent={"single_slot": 1},
    )
    assert report.success_count == 1
    assert report.errored_count == 1


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_per_task_timeout_marks_timeout() -> None:
    """A task that takes longer than per_task_timeout is marked
    TIMEOUT (best-effort cancel — the worker may finish in the
    background, but the result is recorded as TIMEOUT)."""
    fetcher = _StubFetcher(delay_seconds=0.5)
    tasks = [FetchTask("https://slow.com", "default")]
    report = parallel_fetch(
        tasks, fetcher, max_workers=2,
        per_task_timeout=0.05,
    )
    assert report.timeout_count == 1
    rec = report.results[0]
    assert rec.outcome == FetchOutcome.TIMEOUT
    assert rec.error == "per-task timeout exceeded"


def test_no_timeout_with_none() -> None:
    """per_task_timeout=None disables timeout — slow task
    completes successfully."""
    fetcher = _StubFetcher(delay_seconds=0.05)
    tasks = [FetchTask("https://x.com", "default")]
    report = parallel_fetch(
        tasks, fetcher, max_workers=2,
        per_task_timeout=None,
    )
    assert report.timeout_count == 0
    assert report.success_count == 1


# ---------------------------------------------------------------------------
# Duplicate dedup
# ---------------------------------------------------------------------------


def test_duplicate_url_backend_pair_collapses() -> None:
    fetcher = _StubFetcher()
    tasks = [
        FetchTask("https://a.com", "serper"),
        FetchTask("https://a.com", "serper"),  # duplicate
        FetchTask("https://b.com", "serper"),
    ]
    report = parallel_fetch(tasks, fetcher)
    assert len(report.results) == 2
    assert len(fetcher.call_log) == 2


def test_same_url_different_backend_does_not_dedup() -> None:
    """Same URL on different backends are distinct tasks (e.g.
    you might want to fetch via Serper AND DuckDuckGo to
    cross-check)."""
    fetcher = _StubFetcher()
    tasks = [
        FetchTask("https://a.com", "serper"),
        FetchTask("https://a.com", "duckduckgo"),
    ]
    report = parallel_fetch(tasks, fetcher)
    assert len(report.results) == 2


# ---------------------------------------------------------------------------
# FetchResult shape validation
# ---------------------------------------------------------------------------


def test_fetcher_returning_wrong_shape_raises() -> None:
    @dataclass
    class _BadFetcher:
        def fetch(self, task: FetchTask):
            return "not a tuple"

    with pytest.raises(FetcherProtocolError, match="tuple"):
        parallel_fetch(
            [FetchTask("https://a.com", "default")],
            _BadFetcher(),  # type: ignore[arg-type]
        )


def test_fetcher_returning_wrong_arity_tuple_raises() -> None:
    @dataclass
    class _BadFetcher:
        def fetch(self, task: FetchTask):
            return (b"payload", "text/html")  # missing status code

    with pytest.raises(FetcherProtocolError):
        parallel_fetch(
            [FetchTask("https://a.com", "default")],
            _BadFetcher(),  # type: ignore[arg-type]
        )


def test_fetcher_returning_str_payload_raises() -> None:
    @dataclass
    class _BadFetcher:
        def fetch(self, task: FetchTask):
            return ("not bytes", "text/html", 200)

    with pytest.raises(FetcherProtocolError):
        parallel_fetch(
            [FetchTask("https://a.com", "default")],
            _BadFetcher(),  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Contract validation
# ---------------------------------------------------------------------------


def test_non_sequence_tasks_raises() -> None:
    with pytest.raises(ParallelFetchError, match="tasks"):
        parallel_fetch("not a list", _StubFetcher())  # type: ignore[arg-type]


def test_non_task_in_list_raises() -> None:
    with pytest.raises(ParallelFetchError, match="FetchTask"):
        parallel_fetch(
            [FetchTask("https://a.com", "default"), "not a task"],  # type: ignore[list-item]
            _StubFetcher(),
        )


def test_fetcher_without_fetch_method_raises() -> None:
    @dataclass
    class _NotAFetcher:
        pass

    with pytest.raises(ParallelFetchError, match="ParallelFetcher"):
        parallel_fetch([], _NotAFetcher())  # type: ignore[arg-type]


def test_max_workers_must_be_positive() -> None:
    with pytest.raises(ParallelFetchError, match="max_workers"):
        parallel_fetch([], _StubFetcher(), max_workers=0)


def test_per_task_timeout_must_be_positive() -> None:
    with pytest.raises(ParallelFetchError, match="per_task_timeout"):
        parallel_fetch(
            [], _StubFetcher(), per_task_timeout=-1.0,
        )


def test_per_backend_limit_must_be_positive_int() -> None:
    with pytest.raises(ParallelFetchError, match="per_backend_max_concurrent"):
        parallel_fetch(
            [], _StubFetcher(),
            per_backend_max_concurrent={"backend": 0},
        )


# ---------------------------------------------------------------------------
# Counts
# ---------------------------------------------------------------------------


def test_counts_match_results_length() -> None:
    fetcher = _ConditionalFetcher(
        raise_for={"https://bad.com"},
        exc_type=RuntimeError,
    )
    tasks = [
        FetchTask("https://good.com/1", "default"),
        FetchTask("https://bad.com", "default"),
        FetchTask("https://good.com/2", "default"),
    ]
    report = parallel_fetch(tasks, fetcher)
    assert (
        report.success_count + report.errored_count
        + report.timeout_count
        == len(report.results)
    )


def test_started_at_le_finished_at() -> None:
    fetcher = _StubFetcher()
    report = parallel_fetch(
        [FetchTask("https://a.com", "default")], fetcher,
    )
    assert report.started_at <= report.finished_at


# ---------------------------------------------------------------------------
# report_to_exit_code
# ---------------------------------------------------------------------------


def test_exit_code_zero_on_all_success() -> None:
    fetcher = _StubFetcher()
    report = parallel_fetch(
        [FetchTask("https://a.com", "default")], fetcher,
    )
    assert report_to_exit_code(report) == 0


def test_exit_code_one_on_any_errored() -> None:
    fetcher = _RaisingFetcher(exc=RuntimeError("boom"))
    report = parallel_fetch(
        [FetchTask("https://a.com", "default")], fetcher,
    )
    assert report_to_exit_code(report) == 1


def test_exit_code_one_on_any_timeout() -> None:
    fetcher = _StubFetcher(delay_seconds=0.5)
    report = parallel_fetch(
        [FetchTask("https://a.com", "default")], fetcher,
        per_task_timeout=0.05,
    )
    assert report_to_exit_code(report) == 1


def test_exit_code_zero_on_empty_report() -> None:
    fetcher = _StubFetcher()
    report = parallel_fetch([], fetcher)
    assert report_to_exit_code(report) == 0
