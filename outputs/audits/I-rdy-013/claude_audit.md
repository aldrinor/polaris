# Claude architect audit — I-rdy-013 (#509)

**Issue:** Phase 3.10 — enforce the 1-concurrent-session constraint; a 2nd
concurrent `POST /runs` is cleanly rejected with clear UX.
**Branch:** `bot/I-rdy-013-concurrent-session-limit` off `polaris`.
**Canonical diff sha256:** `95f1948b91a38b848e223e8e9d9b4a7334ee407bb1dad1f595f64e55a19b370d`
**Brief:** Codex APPROVE iter 3 (`.codex/I-rdy-013/codex_brief_verdict.txt`).
**Codex diff iter 1:** REQUEST_CHANGES P1-001 (orphan-queued-row on enqueue
failure) — fixed; see `api/runs.py` section below.

## Diff-vs-brief verification (file by file)

### `src/polaris_v6/queue/run_store.py` (+179 / −31)
- `_ACTIVE_STATUSES = ("queued", "in_progress")` — module constant; the two
  lifecycle states that hold a session. `completed`/`cancelled`/`failed` are
  terminal and free the slot. **Verified** against `LifecycleStatus` literal
  in `schemas/run_status.py:14`.
- `_INIT_LOCK = threading.Lock()` + `init_db` body wrapped `with _INIT_LOCK:`
  — serializes in-process `init_db` callers (FastAPI worker threads) so two
  concurrent first requests cannot collide inside `PRAGMA journal_mode=WAL`
  or the schema migration. Addresses Codex brief iter-2 P1-001. **Verified.**
- `_connect` adds `PRAGMA busy_timeout=5000` — a concurrent writer waits for
  the write lock instead of raising `SQLITE_BUSY`. Benefits all callers.
- `_RUN_COLUMNS` constant + `_row_to_response(row)` helper — the 15-column
  projection and `RunStatusResponse` builder are now defined once; `get_run`
  refactored to use both (the −31 lines are the removed duplication).
  **Verified**: field order matches the original `get_run` builder exactly.
- `insert_run_if_idle`: `init_db(path)` first (mirrors `insert_run`, the
  reason `POST /runs` works on a cold DB); then `isolation_level=None`,
  `BEGIN IMMEDIATE`, SELECT active, `ROLLBACK`+return on hit, else INSERT +
  `COMMIT` + return `None`. `BEGIN IMMEDIATE` takes the write lock up-front
  → the 2nd concurrent POST blocks on it, then sees the row. Race-free.
  **Verified** by `test_concurrent_inserts_race_is_serialized`.
- `get_active_run`: SELECT oldest `queued|in_progress`, same defensive
  `no such table`→None / `no such column`→migrate+retry guard as `get_run`.
- `insert_run` left unchanged — unconditional primitive for test fixtures.

### `src/polaris_v6/api/runs.py` (+41 / −1)
- `create_run` calls `insert_run_if_idle`; on a non-None return raises
  `HTTPException(409, detail={code, active_run_id, active_status, message})`.
  `enqueue_research_run.send` is now **after** the reject branch — a rejected
  run is never enqueued. **Verified.** The pre-existing uuid-collision 409
  keeps its plain-string detail (distinguishable: dict vs str).
- **Codex diff P1-001 fix:** `enqueue_research_run.send` is wrapped in
  `try/except`. The `queued` row is already committed by `insert_run_if_idle`;
  if enqueue then fails the run would never run yet would hold the session
  slot forever. On failure → `run_store.mark_failed(run_id, ...)` (terminal →
  frees the slot) then `HTTPException(503)`. **Verified** by
  `test_post_frees_slot_when_enqueue_fails`.

### `web/lib/api.ts` (+40)
- `ConcurrentRunError` class (`activeRunId`, `activeStatus`).
- `createRun` intercepts `status === 409`, reads the body **once**, unwraps
  FastAPI's `{detail:{...}}` envelope (`body?.detail ?? body`), throws
  `ConcurrentRunError` on `code === "concurrent_run_active"`, else rebuilds a
  generic `ApiError`. Non-409 → `asJsonOrThrow` untouched. Addresses Codex
  brief iter-2 P2-001. `tsc --noEmit` exit 0. **Verified.**

### `web/app/dashboard/page.tsx` (+37)
- `concurrentRun` state; cleared at `onSubmit` start; `onSubmit` catch sets
  it on `ConcurrentRunError` (no generic `error`, so no double message).
- A `role="alert"` callout renders the message + a `<Link>` to the active
  run — that link is the "clear UX" the acceptance criterion requires.
  `onSubmit` change is in an event handler, not a `useEffect` (no
  `react-hooks/set-state-in-effect`). eslint clean.

### `tests/v6/conftest.py` (+15)
- Autouse `_isolated_run_db` fixture monkeypatches `POLARIS_V6_RUN_DB` to a
  per-test temp path. **Required** by the gate: a stale `queued` run from an
  earlier test would otherwise 409 a later `POST /runs`. Conftest-wide per
  Codex brief iter-1 ruling.

### `tests/v6/test_concurrency.py` (+237, new)
- 12 tests: idle-insert, reject-on-queued, reject-on-in_progress,
  allow-after-completed/failed/aborted, `get_active_run` empty/active,
  two-thread race (`threading.Barrier`, asserts no raise + exactly one
  insert + one row), API 2nd-POST→409, API allowed-after-completion,
  enqueue-failure slot-recovery (`test_post_frees_slot_when_enqueue_fails`
  — covers Codex diff P1-001).

## Test evidence
- `tests/v6/test_concurrency.py` — 12 passed (post P1-001 fix).
- `tests/v6/` full suite — **427 passed, 7 xfailed, 0 failed** (re-run after
  the P1-001 fix). Confirms the conftest autouse fixture is non-breaking.
- Backend import smoke — `run_store` exposes `insert_run_if_idle` +
  `get_active_run`; `api.runs` imports clean.
- Frontend — `npx eslint lib/api.ts app/dashboard/page.tsx` clean;
  `npx tsc --noEmit` exit 0.

## §-1.1 note
Not a clinical-content change — no report claims, citations, or evidence
spans touched. This is run-lifecycle concurrency control; the line-by-line
clinical audit standard does not apply. The audit above is diff-vs-brief
correctness verification.

## Residual / out of scope (honest disclosure)
- A run stuck `queued` forever (broker never picks it up) would block new
  runs indefinitely. Recovery is via cancel (I-rdy-011/#507, not on
  `polaris`) or a stuck-run reaper — out of scope for #509.
- Cross-*process* `init_db` races (two OS processes) are mitigated by
  `busy_timeout` + `CREATE TABLE IF NOT EXISTS` but not the in-process
  `_INIT_LOCK`. The Carney demo runs one app process; acceptable.

## Verdict
Implementation matches the Codex-APPROVE'd brief. Acceptance criterion met:
a 2nd concurrent request is handled gracefully (HTTP 409, no crash, callout
+ link UX). Recommend APPROVE.
