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
import math
import os
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
    TIMEOUT: per-task timeout fired AFTER the task STARTED (it
       reached `fetcher.fetch` and over-ran its own start-anchored
       budget — or the global batch budget fired while it was
       in-flight past its deadline).
    NOT_DISPATCHED: the global batch budget (I-fetch-003) fired
       while this task was still QUEUED and had never started — the
       worker pool was starved by abandoned in-flight fetches, so
       this task never reached `fetcher.fetch`. Distinct from
       TIMEOUT (which means the task DID run): NOT_DISPATCHED is a
       never-ran non-result. Downstream consumers treat it as a
       non-result, the same class as TIMEOUT/ERRORED (no payload).
    """

    SUCCESS = "success"
    ERRORED = "errored"
    TIMEOUT = "timeout"
    NOT_DISPATCHED = "not_dispatched"


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

    `started_at` / `finished_at` are UNIX epoch floats. For
    SUCCESS / ERRORED they mark when the task began (after
    backend semaphore acquired) and ended. For TIMEOUT,
    `started_at` is best-effort actual task start if the
    worker reached the fetch path; otherwise it falls back to
    the submit-time timeout-budget anchor (a task can time out
    before entering `fetcher.fetch` under contention).

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

    `not_dispatched_count` (I-fetch-003) counts tasks the global
    batch budget cancelled while still QUEUED (never started) —
    see `FetchOutcome.NOT_DISPATCHED`. It is its own bucket so the
    invariant below stays honest.

    Counts sum to `len(results)`:
    `success_count + errored_count + timeout_count
    + not_dispatched_count == len(results)`.
    """

    started_at: float
    finished_at: float
    results: tuple[FetchResultRecord, ...] = field(default_factory=tuple)
    success_count: int = 0
    errored_count: int = 0
    timeout_count: int = 0
    not_dispatched_count: int = 0


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
# Harvest-loop poll interval (I-fetch-003 / BB5-C01)
# ---------------------------------------------------------------------------


# Upper bound on a single harvest-loop wait. The deadline is anchored at
# each task's OBSERVED start (`task_started_monotonic_by_index`), not submit,
# so a task that has not started yet can never be marked TIMEOUT. To detect
# a task that STARTS after the previous snapshot (or one that hangs) within
# a bounded delay of its own start-anchored budget, the harvest loop never
# waits unbounded: it re-snapshots start-times + recomputes the expired set
# at least this often. Small enough to be responsive, large enough to avoid
# a busy-poll. The actual wait is `min(next_deadline - now, this)`.
_HARVEST_POLL_INTERVAL_SECONDS = 2.0


# ---------------------------------------------------------------------------
# Global batch-budget termination guarantee (I-fetch-003 / BB5-C01 P1)
# ---------------------------------------------------------------------------


# The per-task START-anchored timeout guarantees a STARTED task terminates,
# but a never-started task carries a +inf deadline: if every worker thread is
# wedged on an abandoned (timed-out but un-cancellable) in-flight fetch, the
# queued siblings keep their +inf deadline and the harvest loop could spin
# forever. The GLOBAL batch budget is the backstop that guarantees
# `parallel_fetch` ALWAYS returns in bounded time even under all-workers-wedged
# + queued-siblings. When the budget fires, every still-remaining future is
# recorded — started-but-unfinished as TIMEOUT (it ran, over-ran its budget),
# never-started as NOT_DISPATCHED (it never reached the fetcher) — and the
# harvest loop breaks.
#
# Operators override the budget directly with this env var (seconds). When
# UNSET, the budget is DERIVED from `per_task_timeout` and the number of
# submission waves: `per_task_timeout * (ceil(len(deduped)/max_workers)
# + _BATCH_BUDGET_WAVE_SLACK)`. `ceil(len/max_workers)` is the number of waves
# needed to run every task once if each task takes a full per_task_timeout; the
# slack adds head-room so a healthy batch (tasks finishing well inside budget,
# semaphore queuing) is never tripped spuriously.
PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS_ENV = (
    "PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS"
)
_BATCH_BUDGET_WAVE_SLACK = 2


# ---------------------------------------------------------------------------
# Round-robin submit ordering (I-fetch-003 / BB5-C02)
# ---------------------------------------------------------------------------


def _round_robin_indices(
    tasks: Sequence[FetchTask],
) -> list[int]:
    """Return ORIGINAL task indices reordered into round-robin
    `backend_id` order.

    Group indices by `backend_id` (preserving first-seen group order
    and intra-group input order), then emit one index per backend per
    round until every group is exhausted. So the first ``len(groups)``
    indices span distinct backends/hosts.

    The result is a permutation of ``range(len(tasks))`` — every input
    index appears exactly once — so callers map results back to the
    ORIGINAL index unchanged. Pure / deterministic / allocation-light.
    """
    groups: dict[str, list[int]] = {}
    for idx, task in enumerate(tasks):
        groups.setdefault(task.backend_id, []).append(idx)

    ordered: list[int] = []
    group_queues = list(groups.values())
    while group_queues:
        next_round: list[list[int]] = []
        for queue in group_queues:
            ordered.append(queue.pop(0))
            if queue:
                next_round.append(queue)
        group_queues = next_round
    return ordered


# ---------------------------------------------------------------------------
# Global batch-budget derivation (I-fetch-003 / BB5-C01 P1)
# ---------------------------------------------------------------------------


def _derive_batch_budget_seconds(
    *,
    num_tasks: int,
    max_workers: int,
    per_task_timeout: float | None,
) -> float | None:
    """Derive the GLOBAL batch budget (seconds) or None to disable it.

    Precedence:
      1. Env `PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS` (positive float) wins.
      2. Else, if `per_task_timeout` is set: derive from the wave count —
         `per_task_timeout * (ceil(num_tasks / max_workers)
         + _BATCH_BUDGET_WAVE_SLACK)`. The ceil term is how many sequential
         waves it takes to run every task once if each consumes a full
         per_task_timeout; the slack is head-room so a healthy batch is never
         tripped spuriously.
      3. Else (no env AND no per-task timeout): None — preserve the existing
         "None disables timeout" contract. With no per-task budget there is no
         natural time-scale to derive from; the caller opted out of bounding.

    An env value that is empty, non-numeric, or <= 0 is ignored (falls through
    to the derived/None path) — a malformed knob must never silently disable
    the termination guarantee when a per_task_timeout is in force.
    """
    env_raw = os.environ.get(PG_PARALLEL_FETCH_BATCH_BUDGET_SECONDS_ENV)
    if env_raw is not None and env_raw.strip():
        try:
            env_val = float(env_raw)
        except ValueError:
            env_val = None
        if env_val is not None and env_val > 0:
            return env_val

    if per_task_timeout is None:
        return None

    waves = math.ceil(num_tasks / max_workers) + _BATCH_BUDGET_WAVE_SLACK
    return per_task_timeout * waves


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

    # I-fetch-003 (BB5-C01): the deadline is START-anchored, so we record the
    # MONOTONIC start of each task (immune to wall-clock jumps) keyed by index
    # under the lock. The wall-clock start is kept separately ONLY for the
    # FetchResultRecord.started_at report field (AC7 — never used in deadline
    # arithmetic). A not-yet-started index is absent from BOTH maps → +inf
    # effective deadline → cannot TIMEOUT before it runs.
    task_started_monotonic_by_index: dict[int, float] = {}
    task_started_wall_by_index: dict[int, float] = {}
    task_started_lock = threading.Lock()

    def _run_task(
        index: int, task: FetchTask,
    ) -> FetchResultRecord:
        sem = _get_semaphore(task.backend_id)
        sem.acquire()
        task_started = time.time()
        task_started_mono = time.monotonic()
        with task_started_lock:
            task_started_monotonic_by_index[index] = task_started_mono
            task_started_wall_by_index[index] = task_started
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
        # I-fetch-003 (BB5-C02): submit in ROUND-ROBIN backend order so the
        # first `max_workers` submissions span up to `max_workers` distinct
        # backends/hosts. Without this, a clustered same-host candidate prefix
        # makes the first workers all block on ONE host-semaphore (acquired
        # inside `_run_task`), starving distinct-host tasks queued behind them.
        # `_round_robin_indices` returns ORIGINAL deduped indices, so result
        # indexing into `results_by_index` is unchanged (correctness preserved).
        submit_order = _round_robin_indices(deduped)
        # I-fetch-003 (BB5-C01 P1): anchor the GLOBAL batch budget at submit.
        batch_start = time.monotonic()
        for idx in submit_order:
            task = deduped[idx]
            fut = executor.submit(_run_task, idx, task)
            future_to_index[fut] = idx

        # I-fetch-003 (BB5-C01 P1): derive the GLOBAL batch budget — the
        # termination backstop that guarantees this call returns in bounded
        # time even when every worker is wedged on an abandoned in-flight fetch
        # and the queued siblings keep their +inf per-task deadline. Env wins;
        # else derive from per_task_timeout and the wave count; else (no
        # per-task timeout AND no env) the batch budget is disabled (None),
        # preserving the existing "None disables timeout" contract.
        batch_budget = _derive_batch_budget_seconds(
            num_tasks=len(deduped),
            max_workers=max_workers,
            per_task_timeout=per_task_timeout,
        )

        remaining: set[concurrent.futures.Future] = set(future_to_index)
        protocol_error_to_raise: FetcherProtocolError | None = None

        def _effective_deadline_monotonic(idx: int) -> float:
            # I-fetch-003 (BB5-C01): START-anchored, MONOTONIC effective
            # deadline. A not-yet-started index (absent from the start map)
            # → +inf: it CANNOT TIMEOUT before it runs. A started index →
            # its OWN observed start + per_task_timeout. Caller holds
            # `task_started_lock`.
            started = task_started_monotonic_by_index.get(idx)
            if started is None:
                return float("inf")
            return started + per_task_timeout  # type: ignore[operator]

        batch_deadline = (
            batch_start + batch_budget if batch_budget is not None else None
        )

        while remaining and protocol_error_to_raise is None:
            if per_task_timeout is None and batch_deadline is None:
                # No per-task timeout AND no batch budget — just wait for the
                # next completion (the original "None disables timeout" path).
                done, _ = concurrent.futures.wait(
                    remaining,
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )
            else:
                # I-fetch-003 (BB5-C01): BOUNDED-POLL harvest. The wait is
                # ALWAYS bounded by `_HARVEST_POLL_INTERVAL_SECONDS`, never
                # `timeout=None`, so a task that STARTS after this snapshot
                # (or one that hangs), AND the GLOBAL batch deadline, are
                # re-checked within the poll interval — the harvest never
                # relies on a sibling completing to make progress. When there
                # is no per-task timeout (batch budget only), the per-task
                # deadlines are all +inf so the poll interval alone bounds the
                # wait until the batch deadline fires.
                now_mono = time.monotonic()
                if per_task_timeout is None:
                    next_deadline = float("inf")
                else:
                    with task_started_lock:
                        next_deadline = min(
                            _effective_deadline_monotonic(future_to_index[f])
                            for f in remaining
                        )
                if batch_deadline is not None:
                    next_deadline = min(next_deadline, batch_deadline)
                wait_timeout = min(
                    max(0.0, next_deadline - now_mono),
                    _HARVEST_POLL_INTERVAL_SECONDS,
                )
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

            if protocol_error_to_raise is not None:
                break

            if per_task_timeout is not None:
                # Recompute the expired set from CURRENT start-times after
                # every wake (whether or not anything completed). A task is
                # TIMEOUT iff IT exceeded ITS OWN start-anchored budget.
                now_mono = time.monotonic()
                with task_started_lock:
                    expired = [
                        f for f in list(remaining)
                        if _effective_deadline_monotonic(
                            future_to_index[f]
                        ) <= now_mono
                    ]
                if expired:
                    now_wall = time.time()
                    for fut in expired:
                        idx = future_to_index[fut]
                        task = deduped[idx]
                        fut.cancel()  # best-effort
                        with task_started_lock:
                            timeout_started_at = (
                                task_started_wall_by_index.get(idx, now_wall)
                            )
                        results_by_index[idx] = FetchResultRecord(
                            source_url=task.source_url,
                            backend_id=task.backend_id,
                            outcome=FetchOutcome.TIMEOUT,
                            payload=None,
                            content_type=None,
                            fetch_status_code=None,
                            error="per-task timeout exceeded",
                            started_at=timeout_started_at,
                            finished_at=now_wall,
                            task_metadata=task.task_metadata,
                        )
                        remaining.discard(fut)

            # I-fetch-003 (BB5-C01 P1): GLOBAL batch-budget termination
            # guarantee. If the batch deadline has passed, the batch did NOT
            # converge in bounded time — almost always because every worker is
            # wedged on an abandoned (timed-out but un-cancellable) in-flight
            # fetch while distinct-host siblings sit queued behind it forever.
            # Record EVERY still-remaining future (not just never-started ones,
            # or the final `results_by_index[i]` reduction KeyErrors on a
            # started-but-unfinished index) and break so the call ALWAYS
            # returns:
            #   - started-but-unfinished (idx in the start map) → TIMEOUT (it
            #     ran and over-ran; same class as a normal per-task timeout).
            #   - never-started (idx absent from the start map) → NOT_DISPATCHED
            #     (it never reached the fetcher; distinct outcome, NOT a
            #     mislabelled TIMEOUT).
            if (
                batch_deadline is not None
                and remaining
                and time.monotonic() > batch_deadline
            ):
                now_wall = time.time()
                for fut in list(remaining):
                    idx = future_to_index[fut]
                    task = deduped[idx]
                    fut.cancel()  # best-effort
                    with task_started_lock:
                        was_started = (
                            idx in task_started_monotonic_by_index
                        )
                        started_wall = task_started_wall_by_index.get(
                            idx, now_wall,
                        )
                    if was_started:
                        results_by_index[idx] = FetchResultRecord(
                            source_url=task.source_url,
                            backend_id=task.backend_id,
                            outcome=FetchOutcome.TIMEOUT,
                            payload=None,
                            content_type=None,
                            fetch_status_code=None,
                            error="per-task timeout exceeded",
                            started_at=started_wall,
                            finished_at=now_wall,
                            task_metadata=task.task_metadata,
                        )
                    else:
                        results_by_index[idx] = FetchResultRecord(
                            source_url=task.source_url,
                            backend_id=task.backend_id,
                            outcome=FetchOutcome.NOT_DISPATCHED,
                            payload=None,
                            content_type=None,
                            fetch_status_code=None,
                            error=(
                                "never dispatched: parallel-fetch batch "
                                "budget exceeded (worker pool starved by "
                                "abandoned in-flight tasks)"
                            ),
                            started_at=now_wall,
                            finished_at=now_wall,
                            task_metadata=task.task_metadata,
                        )
                    remaining.discard(fut)
                break

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
    not_dispatched = sum(
        1 for r in results if r.outcome == FetchOutcome.NOT_DISPATCHED
    )

    return ParallelFetchReport(
        started_at=started_at,
        finished_at=time.time(),
        results=results,
        success_count=success,
        errored_count=errored,
        timeout_count=timed_out,
        not_dispatched_count=not_dispatched,
    )


def report_to_exit_code(report: ParallelFetchReport) -> int:
    """Map outcome to CI exit code.

    Convention: any errored OR timeout OR not-dispatched → 1;
    all-success or empty → 0. NOT_DISPATCHED (I-fetch-003) is a
    starvation failure — a batch that never ran its queued tasks
    must NOT report success, so it is treated the same as TIMEOUT.
    """
    if (
        report.errored_count > 0
        or report.timeout_count > 0
        or report.not_dispatched_count > 0
    ):
        return 1
    return 0
