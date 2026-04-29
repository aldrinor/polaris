# M-D8 phase 1 v1 — parallel-fetch substrate boundary

**Status:** v1 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/parallel_fetch.py`
**Tests:** `tests/polaris_graph/test_md8_phase1_parallel_fetch.py` (29 passing)
**Pairs with:** M-D7 phase 1 retrieval cache + M-D7 phase 2
cache warming. Phase 2 of M-D8 will integrate with the
production live retriever (`src/polaris_graph/retrieval/
live_retriever.py`).
**Substrate:** stdlib only (`concurrent.futures`, `threading`).
No HTTP, no DB, no LLM clients.

---

## Scope

The existing live retrieval pipeline issues one fetch at a
time across heterogeneous backends. M-D8 phase 1 ships the
**parallel-fetch substrate** that callers can wire up to
those backends to fan out N fetches concurrently, with
per-backend concurrency limits.

Phase 1 v1 ships:
  - `ParallelFetcher` Protocol (pluggable per-task fetcher)
  - `FetchTask` dataclass (`source_url + backend_id +
    task_metadata`)
  - `FetchOutcome` enum: SUCCESS | ERRORED | TIMEOUT
  - `FetchResultRecord` per-task outcome
  - `ParallelFetchReport` aggregate
  - `parallel_fetch(tasks, fetcher, *, max_workers,
    per_backend_max_concurrent, per_task_timeout)` substrate
  - `report_to_exit_code` (any errored or timeout → 1)

Phase 2 (deferred):
  - Integration with `live_retriever.py` itself
  - Async/await variant of the Fetcher Protocol
  - Caller-side retry/backoff coordination
  - Cross-backend dependency edges (e.g. "fetch via Crossref
    only if Semantic Scholar succeeded")
  - Token-bucket rate limiting (vs simple semaphore)

---

## v1 boundaries

### 1. Pure substrate — no HTTP, no Crossref/SS coupling

`parallel_fetch.py` imports stdlib only. The Fetcher
Protocol is the seam: caller code wires up actual HTTP /
Crossref / Semantic Scholar / DuckDuckGo clients.

ThreadPoolExecutor (stdlib) provides parallelism without
forcing an async/await refactor on the caller side. Per-
backend concurrency limits use `threading.Semaphore`.

### 2. Per-backend concurrency limits via Semaphore

`per_backend_max_concurrent: Mapping[str, int] | None`
maps `backend_id` to its concurrent-task ceiling. Backends
absent from the map use `DEFAULT_PER_BACKEND_LIMIT` (4).

Operators tune for known rate limits:
  - Semantic Scholar: 1 (per their docs)
  - Serper: 10
  - DuckDuckGo: 4

Semaphores are lazily allocated on first task per backend.
Acquired in `_run_task` before `fetcher.fetch(task)`,
released in `finally` so a fetcher exception does NOT leak
the semaphore (verified by
`test_fetcher_exception_does_not_leak_backend_semaphore`).

### 3. Per-task timeout via deadline-wait loop

`per_task_timeout: float | None` — wall-clock seconds before
a task is marked TIMEOUT. None disables.

Implementation: `concurrent.futures.wait(timeout=...)` in a
loop with per-future deadlines. Naïve approach (`as_completed`
+ `fut.result(timeout=)`) fails because as_completed waits
until the future is done — so the timeout never fires. v1
uses a proper deadline-based wait loop.

**Cancel is best-effort**: Python threads can't be
interrupted. `fut.cancel()` only succeeds if the worker
hasn't started yet. For an in-flight fetcher, the worker
continues running in the background after parallel_fetch
returns; the report records TIMEOUT and the result is
discarded. The backend semaphore IS released (in the
worker's finally block), so subsequent calls don't deadlock.

**Mitigation**: callers wanting hard cancellation should
wrap their Fetcher with subprocess isolation or use an
async fetcher with explicit cancellation semantics
(deferred to phase 2).

### 4. Result order matches input task order

`results` is in the same order as the input `tasks` list,
regardless of completion order. This makes correlation
trivial for callers iterating both. Operators wanting
completion-order processing can sort by `finished_at`.

### 5. Duplicate (source_url, backend_id) collapses to first

Two tasks with the same `(source_url, backend_id)` pair
canonicalize as duplicates. The first occurrence is
processed; subsequent dupes are dropped from the report.
Same URL on DIFFERENT backends are distinct (e.g. caller
might want Serper AND DuckDuckGo for cross-checking) — the
backend_id is part of the dedup key.

**Mitigation**: tests pin both
(`test_duplicate_url_backend_pair_collapses` +
`test_same_url_different_backend_does_not_dedup`).

### 6. ERRORED captures str(exc); other tasks proceed

A fetcher exception on task N marks that task ERRORED with
`error=str(exc)` and continues with remaining tasks. The
exception type is NOT preserved — callers wanting structured
errors should make their Fetcher catch and convert.

`FetcherProtocolError` (the fetcher returned a non-tuple or
wrong-arity tuple) is NOT caught by ERRORED — it's a
programmer error that propagates up immediately, with
remaining futures cancelled best-effort.

### 7. FetchResultRecord shape validation at the substrate

The substrate validates that `fetcher.fetch(task)` returned
`tuple[bytes | bytearray, str, int]`. Anything else raises
`FetcherProtocolError`. This catches caller-side bugs at
the substrate boundary rather than letting malformed data
propagate to the report.

`bytearray` is accepted (and converted to `bytes` for the
record); `str` payload is rejected. Rationale: bytes is
the lowest-common-denominator transport — caller decoding
to str belongs in their post-processing, not at the fetch
layer.

---

## v1 NON-goals (defer to phase 2)

  - **No live_retriever integration**: substrate stands
    alone. Phase 2 wires it into the production retrieval
    pipeline.
  - **No async/await variant**: only `ParallelFetcher` (sync,
    thread-friendly). Phase 2 may add `AsyncParallelFetcher`.
  - **No retry/backoff**: caller's Fetcher impl handles
    transient errors.
  - **No token-bucket rate limiting**: simple semaphore
    only. Token bucket (with per-second refill) is phase 2.
  - **No cross-backend dependencies**: tasks are
    independent. "Fetch via Crossref only if SS succeeded"
    is caller orchestration.
  - **No fetch budget**: cumulative cost / byte caps are
    caller territory.
  - **No content validation**: substrate doesn't inspect
    payload beyond shape validation.

---

## Codex review trail

Round-1 brief incoming. Tool hints:
- `python -m pytest -q tests\polaris_graph\test_md8_phase1_parallel_fetch.py`
- DO NOT run rg/find — read source/tests/threat-model directly
- DO NOT run Python verification scripts that print Unicode
- 29 tests pin all 7 boundaries

Targeted at 1-2 round convergence per the M-D7 phase 2 +
M-D11 phase 2 v1 patterns (substrate work with v1-shipped
threat-model docs). Note: this milestone has more concurrency
surface than the recent aggregation substrates, so Codex may
probe semaphore release semantics, deadline-wait correctness,
and ThreadPoolExecutor cleanup more carefully.

---

## Lock note

v1 GREEN-lock target after Codex round 1-2. v2 (live_retriever
integration, async variant, token bucket, retry coordination)
tracked separately.
