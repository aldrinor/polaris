"""M-D8 phase 1 v1 (Phase D): Parallel-fetch substrate.

The existing live retrieval pipeline (`src/polaris_graph/
retrieval/live_retriever.py`) issues one fetch at a time
across heterogeneous backends (Serper, Semantic Scholar,
DuckDuckGo, etc.). M-D8 phase 1 ships the **parallel-fetch
substrate** that callers can wire up to those backends to
fan out N fetches concurrently, with per-backend
concurrency limits.

## Why this milestone matters

For predictable workloads where the URL list is known
ahead of time (cache warming via M-D7 phase 2, batch
audit re-runs, scheduled freshness checks), serial fetching
pays first-byte latency on every URL. Phase 1 ships the
substrate primitive that turns that serial loop into a
concurrent fan-out with operator-controllable concurrency.

Phase 1 does NOT integrate with `live_retriever.py` itself
— that's phase 2 territory and requires touching production
retrieval flow. v1 here is the deterministic substrate the
integration will sit on top of.

## What v1 ships

  - `ParallelFetcher` Protocol — pluggable per-task fetcher
  - `FetchTask` dataclass — source_url + backend_id
  - `FetchOutcome` enum: SUCCESS | ERRORED | TIMEOUT
  - `FetchResultRecord` per-task outcome (renamed from
    FetchResult to avoid collision with M-D7 phase 2's
    `cache_warming.FetchResult`)
  - `ParallelFetchReport` aggregate
  - `parallel_fetch(tasks, fetcher, *, max_workers,
    per_backend_max_concurrent, per_task_timeout)` —
    pure substrate

## Substrate boundary

Imports stdlib only (`concurrent.futures`, `threading`,
`dataclasses`, `enum`). No HTTP client. No DB. No LLM. The
Fetcher Protocol is the seam: caller code wires up actual
HTTP / Crossref / Semantic Scholar clients.

The substrate uses `ThreadPoolExecutor` for parallelism
(stdlib, no async/await refactor on the caller side). Per-
backend concurrency limits are enforced via
`threading.Semaphore` instances keyed by `backend_id`.

See `docs/md8_phase1_threat_model.md` for boundaries.
"""

from __future__ import annotations

import concurrent.futures
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Protocol, Sequence


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ParallelFetchError(ValueError):
    """Raised on contract violations — empty tasks not actually
    empty, bad fetcher Protocol, invalid concurrency limits."""


class FetcherProtocolError(ParallelFetchError):
    """Fetcher returned something other than a FetchResultRecord
    payload tuple. Caller-side bug — surface loudly per LAW II."""


# ---------------------------------------------------------------------------
# Task + outcome types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FetchTask:
    """One unit of work for the parallel fetcher.

    `source_url` is the URL to fetch (caller's responsibility
    to canonicalize if needed — substrate doesn't normalize).

    `backend_id` is the rate-limit class — Serper, Semantic
    Scholar, DuckDuckGo, etc. Per-backend concurrency limits
    use this as the semaphore key. Tasks with no specific
    backend should use a sentinel like `"default"`.

    `task_metadata` is opaque caller-supplied metadata
    surfaced back in `FetchResultRecord.task_metadata` for
    correlation. Common usage: tier classification, domain
    tag, request-id-for-tracing. The substrate doesn't read
    or interpret this dict.
    """

    source_url: str
    backend_id: str
    task_metadata: Mapping[str, object] = field(default_factory=dict)


class FetchOutcome(str, Enum):
    """Per-task outcome.

    SUCCESS: fetcher returned a payload (regardless of HTTP
       status code — caller's Fetcher decides what to raise on).
    ERRORED: fetcher raised an exception.
    TIMEOUT: per-task timeout fired before the fetcher returned.
    """

    SUCCESS = "success"
    ERRORED = "errored"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class FetchResultRecord:
    """One task's result.

    `payload` is None unless `outcome == SUCCESS`. Type is
    deliberately `bytes | None` — substrate doesn't dictate
    whether the caller's Fetcher returns text/JSON/binary;
    bytes is the lowest-common-denominator transport.

    `content_type` and `fetch_status_code` are caller-supplied
    metadata when SUCCESS; None otherwise.

    `error` is None unless `outcome == ERRORED` or `TIMEOUT`,
    in which case it carries `str(exc)` (ERRORED) or the
    string `"per-task timeout exceeded"` (TIMEOUT). Exception
    type is NOT preserved — callers wanting structured errors
    should make their Fetcher catch + convert.

    `started_at` / `finished_at` are UNIX epoch floats marking
    when the task began (after backend semaphore acquired)
    and ended.

    `task_metadata` echoes the FetchTask's metadata for
    correlation.
    """

    source_url: str
    backend_id: str
    outcome: FetchOutcome
    payload: bytes | None
    content_type: str | None
    fetch_status_code: int | None
    error: str | None
    started_at: float
    finished_at: float
    task_metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ParallelFetchReport:
    """Aggregate of all tasks in one parallel_fetch call.

    `started_at` / `finished_at` are wall-clock bounds of the
    full call (NOT sum of per-task times — they're concurrent).

    `results` is one entry per UNIQUE (source_url, backend_id)
    in the input. Duplicates collapse to first-occurrence
    (the substrate doesn't fetch the same URL twice in one
    call by design).

    Counts sum to `len(results)`.
    """

    started_at: float
    finished_at: float
    results: tuple[FetchResultRecord, ...] = field(default_factory=tuple)
    success_count: int = 0
    errored_count: int = 0
    timeout_count: int = 0


# ---------------------------------------------------------------------------
# Fetcher Protocol
# ---------------------------------------------------------------------------


class ParallelFetcher(Protocol):
    """Pluggable fetcher contract — single-task, called
    concurrently by `parallel_fetch`.

    Implementers MUST:
      - Be thread-safe (concurrent invocations from worker
        threads are the norm)
      - Return a `tuple[bytes, str, int]` of (payload,
        content_type, fetch_status_code) on success
      - Raise an exception on transport / parse failure
        (callers should NOT signal failure via a non-2xx
        status code in the returned tuple — that IS a
        successful fetch of an error response)

    Implementers MUST NOT:
      - Mutate any cache directly (that's caller orchestration)
      - Block the calling thread indefinitely (use the
        per-task timeout if your backend doesn't enforce one)
    """

    def fetch(
        self, task: FetchTask
    ) -> tuple[bytes, str, int]:
        ...


# ---------------------------------------------------------------------------
# Default per-backend limit
# ---------------------------------------------------------------------------


# Conservative default — any backend not explicitly configured
# in `per_backend_max_concurrent` gets this limit. Operators
# can tune for known backends (Semantic Scholar = 1 per their
# docs; Serper = 10; etc.) by passing a dict.
DEFAULT_PER_BACKEND_LIMIT = 4


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parallel_fetch(
    tasks: Sequence[FetchTask],
    fetcher: ParallelFetcher,
    *,
    max_workers: int = 8,
    per_backend_max_concurrent: Mapping[str, int] | None = None,
    per_task_timeout: float | None = None,
) -> ParallelFetchReport:
    """Fan out `tasks` to a thread pool and collect results.

    `max_workers` caps the global concurrency. Per-backend
    limits gate concurrent-by-backend further: a task on
    backend `"semantic_scholar"` can only proceed when both a
    worker is free AND the backend's semaphore has capacity.

    `per_backend_max_concurrent` maps `backend_id` to its
    concurrency limit. Backends absent from the map use
    `DEFAULT_PER_BACKEND_LIMIT`. Pass `{"semantic_scholar": 1,
    "serper": 10, ...}` to set explicit ceilings.

    `per_task_timeout` is the wall-clock seconds before a
    task is marked `TIMEOUT`. None disables timeout.
    The cancel attempt is best-effort: in-flight tasks may
    continue running after the timeout fires (Python's
    Future.cancel() can't interrupt synchronous code), but
    the report records TIMEOUT and the worker thread is
    abandoned. Backend semaphore is released either way (in a
    finally block), so subsequent tasks on the same backend
    don't deadlock waiting on a leaked permit.

    Returns a `ParallelFetchReport` summarizing per-task
    outcomes. Order of `results` is the input task order,
    NOT completion order — callers correlate via task_metadata
    if they need other orderings.

    Duplicate (source_url, backend_id) pairs in input collapse
    to first-occurrence (subsequent dupes dropped silently).
    """
    if not isinstance(tasks, Sequence) or isinstance(
        tasks, (str, bytes)
    ):
        raise ParallelFetchError(
            f"tasks must be a sequence of FetchTask, got "
            f"{type(tasks).__name__}"
        )
    if fetcher is None or not hasattr(fetcher, "fetch"):
        raise ParallelFetchError(
            "fetcher must implement the ParallelFetcher Protocol"
        )
    if max_workers < 1:
        raise ParallelFetchError(
            f"max_workers must be >= 1, got {max_workers}"
        )
    if per_task_timeout is not None and per_task_timeout <= 0:
        raise ParallelFetchError(
            f"per_task_timeout must be > 0 or None, got "
            f"{per_task_timeout}"
        )

    if per_backend_max_concurrent is not None:
        for k, v in per_backend_max_concurrent.items():
            if not isinstance(v, int) or v < 1:
                raise ParallelFetchError(
                    f"per_backend_max_concurrent[{k!r}] must be "
                    f"a positive int, got {v!r}"
                )

    # Build deduplicated task list (first wins).
    seen_keys: set[tuple[str, str]] = set()
    deduped: list[FetchTask] = []
    for i, task in enumerate(tasks):
        if not isinstance(task, FetchTask):
            raise ParallelFetchError(
                f"tasks[{i}] must be FetchTask, got "
                f"{type(task).__name__}"
            )
        key = (task.source_url, task.backend_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(task)

    started_at = time.time()

    if not deduped:
        return ParallelFetchReport(
            started_at=started_at,
            finished_at=started_at,
            results=(),
            success_count=0,
            errored_count=0,
            timeout_count=0,
        )

    # Per-backend semaphores. Lazily allocated on first task
    # for each backend.
    backend_limits: dict[str, int] = dict(per_backend_max_concurrent or {})
    semaphores: dict[str, threading.Semaphore] = {}
    semaphores_lock = threading.Lock()

    def _get_semaphore(backend_id: str) -> threading.Semaphore:
        with semaphores_lock:
            sem = semaphores.get(backend_id)
            if sem is None:
                limit = backend_limits.get(
                    backend_id, DEFAULT_PER_BACKEND_LIMIT,
                )
                sem = threading.Semaphore(limit)
                semaphores[backend_id] = sem
            return sem

    def _run_task(task: FetchTask) -> FetchResultRecord:
        sem = _get_semaphore(task.backend_id)
        sem.acquire()
        task_started = time.time()
        try:
            try:
                result = fetcher.fetch(task)
            except Exception as exc:  # noqa: BLE001 — intentional broad
                return FetchResultRecord(
                    source_url=task.source_url,
                    backend_id=task.backend_id,
                    outcome=FetchOutcome.ERRORED,
                    payload=None,
                    content_type=None,
                    fetch_status_code=None,
                    error=str(exc),
                    started_at=task_started,
                    finished_at=time.time(),
                    task_metadata=task.task_metadata,
                )

            if (
                not isinstance(result, tuple)
                or len(result) != 3
                or not isinstance(result[0], (bytes, bytearray))
                or not isinstance(result[1], str)
                or not isinstance(result[2], int)
            ):
                raise FetcherProtocolError(
                    f"fetcher.fetch({task.source_url!r}) returned "
                    f"{type(result).__name__}, expected "
                    "tuple[bytes, str, int]"
                )

            payload, content_type, status = result
            return FetchResultRecord(
                source_url=task.source_url,
                backend_id=task.backend_id,
                outcome=FetchOutcome.SUCCESS,
                payload=bytes(payload),
                content_type=content_type,
                fetch_status_code=status,
                error=None,
                started_at=task_started,
                finished_at=time.time(),
                task_metadata=task.task_metadata,
            )
        finally:
            sem.release()

    results_by_index: dict[int, FetchResultRecord] = {}

    # Codex round-1 HIGH fix (v2): manage executor manually so we
    # can shutdown(wait=False, cancel_futures=True) on TIMEOUT.
    # The `with` block's __exit__ calls shutdown(wait=True) which
    # blocks until all in-flight workers finish — defeating
    # boundary 3's caller-latency promise.
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=max_workers,
    )
    try:
        future_to_index: dict[concurrent.futures.Future, int] = {}
        deadline_per_future: dict[concurrent.futures.Future, float] = {}
        submit_now = time.time()
        for idx, task in enumerate(deduped):
            fut = executor.submit(_run_task, task)
            future_to_index[fut] = idx
            if per_task_timeout is not None:
                deadline_per_future[fut] = submit_now + per_task_timeout

        remaining: set[concurrent.futures.Future] = set(future_to_index)
        protocol_error_to_raise: FetcherProtocolError | None = None

        while remaining and protocol_error_to_raise is None:
            if per_task_timeout is None:
                # No timeout — just wait for the next completion.
                done, _ = concurrent.futures.wait(
                    remaining,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
            else:
                now = time.time()
                # Earliest deadline among still-running futures.
                next_deadline = min(deadline_per_future[f] for f in remaining)
                wait_timeout = max(0.0, next_deadline - now)
                done, _ = concurrent.futures.wait(
                    remaining,
                    timeout=wait_timeout,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

            if done:
                for fut in done:
                    idx = future_to_index[fut]
                    task = deduped[idx]
                    try:
                        rec = fut.result()
                    except FetcherProtocolError as exc:
                        protocol_error_to_raise = exc
                        break
                    results_by_index[idx] = rec
                    remaining.discard(fut)
                    deadline_per_future.pop(fut, None)
            else:
                # Wait expired with no completions — at least one
                # future has hit its deadline. Mark expired futures
                # as TIMEOUT and continue.
                now = time.time()
                expired = [
                    f for f in list(remaining)
                    if deadline_per_future.get(f, float("inf")) <= now
                ]
                if not expired:
                    # No expired but no completions either — defensive
                    # tiny-deadline race; loop again.
                    continue
                for fut in expired:
                    idx = future_to_index[fut]
                    task = deduped[idx]
                    fut.cancel()  # best-effort
                    results_by_index[idx] = FetchResultRecord(
                        source_url=task.source_url,
                        backend_id=task.backend_id,
                        outcome=FetchOutcome.TIMEOUT,
                        payload=None,
                        content_type=None,
                        fetch_status_code=None,
                        error="per-task timeout exceeded",
                        started_at=started_at,
                        finished_at=now,
                        task_metadata=task.task_metadata,
                    )
                    remaining.discard(fut)
                    deadline_per_future.pop(fut, None)

        if protocol_error_to_raise is not None:
            for other_fut in remaining:
                other_fut.cancel()
            # Codex round-1 MEDIUM fix (v2): release the executor
            # without waiting so the protocol error propagates
            # promptly. In-flight workers continue but caller
            # gets control back.
            executor.shutdown(wait=False, cancel_futures=True)
            raise protocol_error_to_raise
    finally:
        # Codex round-1 HIGH fix (v2): non-blocking shutdown.
        # Pending (not-yet-started) futures are cancelled;
        # in-flight workers continue but don't gate our return.
        executor.shutdown(wait=False, cancel_futures=True)

    # Reorder by input index.
    results = tuple(
        results_by_index[i] for i in range(len(deduped))
    )

    success = sum(1 for r in results if r.outcome == FetchOutcome.SUCCESS)
    errored = sum(1 for r in results if r.outcome == FetchOutcome.ERRORED)
    timed_out = sum(1 for r in results if r.outcome == FetchOutcome.TIMEOUT)

    return ParallelFetchReport(
        started_at=started_at,
        finished_at=time.time(),
        results=results,
        success_count=success,
        errored_count=errored,
        timeout_count=timed_out,
    )


def report_to_exit_code(report: ParallelFetchReport) -> int:
    """Map outcome to CI exit code.

    Convention: any errored OR timeout → 1; all-success or
    empty → 0.
    """
    if report.errored_count > 0 or report.timeout_count > 0:
        return 1
    return 0
