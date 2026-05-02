# Codex round 1 — M-INT-1 v1 (commit 8f8df41)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_m_int_1_parallel_fetch_integration.py`
- DO NOT run rg/find — read directly:
  - `src/polaris_graph/retrieval/live_retriever.py` ~line 1210-1310
    (M-INT-1 integration block + the per-candidate loop body)
  - `tests/polaris_graph/test_m_int_1_parallel_fetch_integration.py`

## Scope
Phase E1 first integration. Wires `parallel_fetch.parallel_fetch(...)`
into `live_retriever.py`'s content-fetch loop (the OLD serial
`for i, cand in enumerate(candidates): _fetch_content(...)` loop).

## Acceptance bar

1. **Imported.** `parallel_fetch` + `FetchTask` are imported
   inside the M-INT-1 block of `live_retriever.py`.
2. **Invoked.** `parallel_fetch(tasks, fetcher, ...)` is called
   when `PG_USE_PARALLEL_FETCH != "0"` AND candidates is non-empty.
3. **Run-log evidence.** `api_calls` dict carries
   `parallel_fetch_success_count`, `parallel_fetch_errored_count`,
   `parallel_fetch_timeout_count` after the call.
4. **Rollback flag works.** `PG_USE_PARALLEL_FETCH=0` falls
   back to the original serial loop; no parallel_fetch_*
   keys in api_calls.

## Public-API change

- New env vars: `PG_USE_PARALLEL_FETCH` (default 1),
  `PG_LIVE_RETRIEVER_MAX_WORKERS` (default 8),
  `PG_LIVE_RETRIEVER_FETCH_TIMEOUT_SECONDS` (default 120).
- `LiveRetrievalResult.api_calls` dict gains 3 new keys when
  parallel path runs. Existing keys (fetch, openalex, s2,
  serper) preserved.
- Per-candidate processing (tier classification, evidence row
  build) UNCHANGED — only the fetch step is parallelized.

## Diff-against-baseline

OLD: serial loop calling `_fetch_content(cand.url, ...)` per
candidate, with a `time.sleep(0.2)` rate limit every 5
iterations.

NEW (additive only):
- Before the loop: build FetchTasks, call parallel_fetch with
  custom adapter that wraps `_fetch_content` and stashes the
  full 4-tuple in a thread-safe `fetched_side` dict
- The loop body now reads from `fetched_side[cand.url]` when
  parallel path ran, OR falls back to inline `_fetch_content`
  when flag disabled
- All post-fetch processing (tier classify, evidence build,
  OpenAlex enrich) is UNCHANGED

## What might Codex probe

- Thread-safety of `fetched_side` (uses threading.Lock)
- AccessBypass already runs each fetch in a daemon thread
  with its own event loop; running N of those concurrently
  via parallel_fetch's ThreadPoolExecutor should be safe
  (each fetch starts its own daemon).
- `errors="replace"` on UTF-8 encode for non-text payloads
- `fetched_side.get(cand.url, ("", False, "", ""))` defaults
  on cache miss — preserves the old "fetch failed → empty
  content + failed_fetch increment" behavior
- backend_id="default" for all candidates means no per-host
  rate-limit. Live retrieval upstream already throttles via
  Serper/SS query rate limits; per-fetch rate limiting was
  the old `time.sleep(0.2)` which we replaced with workers=8
- per_task_timeout=120s default matches AccessBypass's
  PG_FETCH_DEADLINE_SECONDS=90 + buffer
- Fallback path correctness when PG_USE_PARALLEL_FETCH=0
  (preserves old time.sleep gating)

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Acceptance bar
- [x/ ] Imported (parallel_fetch + FetchTask in M-INT-1 block)
- [x/ ] Invoked (parallel_fetch called when flag default)
- [x/ ] Run-log evidence (api_calls.parallel_fetch_*_count)
- [x/ ] PG_USE_PARALLEL_FETCH=0 falls back to serial path

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
