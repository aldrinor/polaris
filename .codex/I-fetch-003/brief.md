HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- Reserve P0/P1 for real execution risks; classify non-blockers P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## ITER-3 CHANGELOG (addressing your iter-2 P1 worker-slot hoarding + 3 P2s)
- **P1 (worker-slot hoarding):** CORRECT. The semaphore is acquired INSIDE the worker (`_run_task` L352), so a clustered same-host prefix makes the first max_workers workers block on one host-semaphore, starving distinct-host tasks queued behind them. REVISED: **round-robin the submit order by `backend_id`** in `parallel_fetch` BEFORE the submit loop (L416) — interleave `deduped` so consecutive submissions are different backends/hosts. The first max_workers submissions then span up to max_workers distinct hosts → no hoarding. This is a generic, localized fix in the concurrency layer (parallel_fetch already keys semaphores by backend_id; it should also submit in round-robin backend order). NEW AC + adversarial test below.
- **P2-1 (api_calls contract):** existing `retrieval.api_calls.parallel_fetch_*` fields are KEPT unchanged (no M-INT-1/smoke breakage); AC3 diagnostics are ADDED as NEW sibling fields only.
- **P2-2 (monotonic clock):** deadline arithmetic uses `time.monotonic()`; wall-clock `time.time()` is kept ONLY for the `started_at`/`finished_at` report timestamps.
- **P2-3 (success-rate denominator):** define explicitly = `usable_fetched / (usable_fetched + failed)` from the final fetch outcomes (named `retrieval.fetch_success_rate`); distinct from `parallel_completion_rate` (completed-in-deadline / submitted) which is also emitted.

## ITER-2 CHANGELOG (addressing your two iter-1 P1 blockers)
- **P1-1 (per-backend semaphore is the real limiter):** CORRECT and the key catch. `live_retriever.py:2815` creates every FetchTask with `backend_id="default"`, and `parallel_fetch.py:226` caps each backend at `DEFAULT_PER_BACKEND_LIMIT=4`, so all 740 share ONE semaphore of 4 — raising max_workers alone is inert. REVISED C02: key `backend_id` by the URL **host** so distinct hosts fetch in parallel (politely capped at 4 PER HOST), AND scale max_workers. Per-host limit stays env-overridable.
- **P1-2 (unbounded inf wait race):** CORRECT. REVISED C01: the harvest loop NEVER waits unbounded — `wait_timeout = min(max(0, next_deadline - now), _HARVEST_POLL_INTERVAL_SECONDS)` (small bound, e.g. 2s). The loop re-snapshots start-times + recomputes expired every ≤2s, so a task that STARTS after a snapshot, or hangs, is caught within the poll interval of its own start-anchored deadline — no reliance on a sibling completing.
- **P2 (your notes) folded:** parallel-layer timeout kept as start-anchored defense-in-depth (not removed); default worker ceiling lowered to 48 (env-overridable to 64); AC3 telemetry goes into NEW retrieval-diagnostics manifest fields, NOT stuffed into the `api_calls: dict[str,int]` contract.

# Brief review — I-fetch-003 (#1175): parallel_fetch global-deadline starvation + per-backend/worker throughput (BB5-C01/C02)

## Context (beat-both run-5 forensic — dominant completeness lever)
85–92% of fetch candidates are batch-marked TIMEOUT before running (queue starvation, `errored=0`). Timeouts of 740: 631/667/673/661/684. Evidence pool collapses to 9–34 (vs max_rows=150). POLARIS is faithful but far too THIN vs ChatGPT — completeness is the beat-both gap.

## Root cause (code-confirmed)
- **C01 deadline:** `parallel_fetch.py:415-420` sets `deadline_per_future[fut] = submit_now + per_task_timeout` (ONE shared instant for all 740); the harvest loop (L425-489) marks every still-running future TIMEOUT at that instant, killing ~631 that mostly never started. `_run_task` records the true start at L353-355 (`task_started_by_index[index]`, under `task_started_lock`) but the deadline ignores it.
- **C02 concurrency (TWO limiters, both unscaled):** (a) `live_retriever.py:2794` `max_workers` default 8 (never set by any sweep script); (b) THE binding limiter — every FetchTask is `backend_id="default"` (`live_retriever.py:2815`) and `parallel_fetch.py:226` `DEFAULT_PER_BACKEND_LIMIT=4`, so effective concurrency is 4, not 8.

## Proposed fix direction (REVISED)
**C01 (parallel_fetch.py) — start-anchored, bounded-poll deadline:**
- Effective deadline per future: not-yet-started (idx ∉ `task_started_by_index`) → +inf (cannot TIMEOUT before it runs); started → `task_started_by_index[idx] + per_task_timeout` (re-read under `task_started_lock`).
- Harvest loop waits `wait_timeout = min(max(0.0, next_deadline - now), _HARVEST_POLL_INTERVAL_SECONDS)` (named const, ~2s) — ALWAYS bounded, never `timeout=None`. After each wake, recompute effective deadlines + `expired` from CURRENT start-times. A task is TIMEOUT iff IT exceeded ITS OWN budget. Remove the static `deadline_per_future` dict.

**C02 (host-keyed backend + round-robin submit + scaled workers):**
- **live_retriever.py:2815** — set each FetchTask's `backend_id` to the URL **host** (`urlsplit(url).hostname or "default"`), so `_get_semaphore` gives each host its own `Semaphore(per_host_limit)` → cross-host parallelism, per-host politeness preserved. Per-host limit env-overridable (`PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT`, default = DEFAULT_PER_BACKEND_LIMIT=4).
- **parallel_fetch.py (NEW, fixes the iter-2 P1 hoarding)** — before the submit loop, reorder `deduped` into **round-robin backend order** (group by backend_id, then emit one-per-backend per round). So the first max_workers submissions span up to max_workers distinct hosts → workers never hoard one host-semaphore. Submit order only; result indexing preserved (map back to original index for `results_by_index`).
- **live_retriever.py:2794** — `max_workers`: explicit env `PG_LIVE_RETRIEVER_MAX_WORKERS` override; when UNSET, `min(_CEILING, max(_FLOOR, len(candidates)//_WORKERS_PER_CANDIDATE))` with NAMED constants (floor=8, ceiling=48, per_candidate=16 → ~46 for 740). No magic numbers.
- Verify `backend_id` is not consumed elsewhere in a way host-keying breaks (grep FetchResultRecord.backend_id consumers; it is telemetry/grouping — confirm in build).

**AC3 fail-loud:** emit `retrieval.fetch_success_rate` + `retrieval.fetch_workers` + `retrieval.distinct_hosts` as NEW manifest fields (NOT inside `api_calls: dict[str,int]`); WARN when success_rate < a floor.

## Acceptance criteria
- AC1: deadline anchored at task START (monotonic clock); not-yet-started never TIMEOUT; the harvest wait is ALWAYS bounded (poll interval) so a start-after-snapshot or hung task is caught within the interval — never relies on a sibling completing.
- AC2: backend_id keyed by URL host AND submit order round-robin'd by backend so distinct hosts fetch concurrently EVEN under a clustered same-host candidate prefix; per-host limit + max_workers both env-overridable, named constants, bounded.
- AC3: NEW retrieval-diagnostics manifest fields (`fetch_success_rate` = usable/(usable+failed), `parallel_completion_rate`, `fetch_workers`, `distinct_hosts`); WARN below a floor; existing `api_calls.parallel_fetch_*` fields UNCHANGED (no contract widening).
- AC4: NO faithfulness impact — retrieval throughput only; strict_verify / 4-role / redactor untouched.
- AC5: offline deterministic unit tests (mock fetcher + monkeypatched monotonic clock/sleep, NO network): (a) a single slow task does NOT time out fast/queued siblings under start-anchoring + bounded poll; (b) a task exceeding ITS OWN budget IS TIMEOUT even if no sibling completes; (c) two distinct hosts run concurrently while same-host is capped; (d) ADVERSARIAL — >max_workers same-host tasks followed by a different-host task: the other host STARTS before the same-host prefix drains (proves round-robin submit defeats hoarding).
- AC6: bounded — cannot hang; inner `_fetch_content` deadline still bounds each task; abandoned-thread teardown is BB5-S02 (separate).
- AC7: deadline arithmetic uses `time.monotonic()`; wall-clock kept only for `started_at`/`finished_at` report fields.

## Files I have ALSO checked and they're clean
- `parallel_fetch.py:226` DEFAULT_PER_BACKEND_LIMIT=4; `_get_semaphore` keys by backend_id; `_run_task` L353-355 records start under lock; TIMEOUT branch L468-487 already reads `task_started_by_index`. Protocol-error path L491-499 unchanged.
- `live_retriever.py:2799-2804` per_task_timeout env (default 120) kept; `candidates` in scope at L2794 for len(); inner `_fetch_content` 90s deadline (L1909) bounds each task (BB5-S02/S03 separate).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
