# Claude architect audit — GH #509 (I-rdy-013)

**Issue:** GH #509 (I-rdy-013) — Phase 3.10: 1-concurrent-session
enforcement + queue/rejection UX. Acceptance: a 2nd concurrent request is
handled gracefully (no crash, clear UX); Codex APPROVE.
**Branch:** `bot/I-rdy-013` off `polaris` HEAD `7b504cc2`.
**Commit 1:** `af6e4ac6` — 6 files, +517/-32.
**Brief:** Codex brief review APPROVE iter 1 (0 P0/P1/P2, accept_remaining).

## 1. Recut provenance

Recut of PR #541 (`bot/I-rdy-013-concurrent-session-limit`). #541 earned
Codex brief APPROVE iter-3 + diff APPROVE iter-2 but became unmergeable: 44
commits stale, and its `.codex/I-rdy-013/` committed 1.2 MB / 2.4 MB raw
Codex transcripts as the verdict files (verdict-only-rule violation,
CLAUDE.md §8.3 / #535). The recut re-applies #541's APPROVE'd #509
implementation onto current `polaris` HEAD with proper slim artifacts;
PR #541 is closed. All 4 polaris-touched source files diverged because
#505/#506/#507 (this session) modified them — #509's deltas were layered
on; 2 test files re-applied verbatim.

## 2. What shipped

`POST /runs` enforces the locked 1-concurrent-session constraint; a 2nd
concurrent request is cleanly rejected (HTTP 409, never enqueued, with UX)
— never a crash.

## 3. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — atomic 1-session gate.** `insert_run_if_idle` runs the
  active-run SELECT and the INSERT inside ONE `BEGIN IMMEDIATE`
  transaction. `BEGIN IMMEDIATE` takes the write lock up-front, so two
  concurrent `POST /runs` cannot both pass the check — the 2nd writer
  blocks on the lock (up to `busy_timeout`), then sees the 1st's inserted
  row and is rejected. `conn.isolation_level = None` is required for manual
  `BEGIN/COMMIT/ROLLBACK` (Python sqlite3's autocommit cannot express
  explicit-transaction semantics). `test_concurrency.py` exercises the
  concurrent-request path.
- **VERIFIED — no crash on the 2nd request.** `_connect` sets `PRAGMA
  busy_timeout=5000` so a concurrent writer waits up to 5s for the write
  lock instead of raising `SQLITE_BUSY` immediately — the issue's "no
  crash". `init_db` is `_INIT_LOCK`-serialized so two concurrent first
  requests cannot collide inside `PRAGMA journal_mode=WAL` / the migration.
- **VERIFIED — clear UX.** `create_run` 409s with a structured `detail`
  (`code=concurrent_run_active`, `active_run_id`, `active_status`,
  `message`); `web/lib/api.ts` `createRun` unwraps the 409 into a typed
  `ConcurrentRunError`; `dashboard/page.tsx` catches it and renders a
  dedicated callout with a link to the run holding the session.
- **VERIFIED — enqueue-failure frees the slot (#541 diff P1-001).** The
  queued row is committed before `enqueue`. If `enqueue` raises, `create_run`
  `mark_failed`s the row (terminal → frees the single-session slot) then
  503s — without this a failed enqueue would permanently wedge the slot.
- **VERIFIED — the run_store.py #507 overlap.** #507 already added
  `_RUN_COLUMNS` (16-col) + `_row_to_response` (16-field) + the CAS
  `mark_in_progress`. The recut applied ONLY #509's net-new pieces and kept
  #507's versions; `insert_run_if_idle` / `get_active_run` SELECT the
  16-col `_RUN_COLUMNS` and call `_row_to_response` — consistent (verified
  by `pytest tests/v6/` 499 green, incl. `test_cancellation` 17/17).
- **VERIFIED — conftest autouse fixture is safe.** `_isolated_run_db` is
  mandatory now: the 1-session gate would make a leftover `queued` row from
  an earlier test 409 a later test's `POST /runs`. The whole-directory
  smoke (`pytest tests/v6/` 499 passed) confirms it composes with every v6
  test, including `test_runs_db_integration.py`'s own `isolated_db`.
- **VERIFIED — scope.** #509 = cleanly-rejected (not server-side
  queueing); the constraint is "locked" per the issue, so rejection is the
  honest minimal satisfaction of "handled gracefully". #552 (a separate
  asyncio-teardown concurrency bug) is excluded and out of #509.

## 4. Smoke

`ast.parse` 4/4. `pytest tests/v6/` — 499 passed, 4 skipped, 7 xfailed (the
whole v6 directory, no regression). Web: prettier, `npm run lint` (0
errors, 3 pre-existing warnings), `tsc --noEmit` clean, `npm run build`
succeeded.

## 5. Codex iteration trail

- PR #541 (recut-from): brief APPROVE iter-3, diff APPROVE iter-2.
- Recut brief: Codex brief review APPROVE iter 1 — 0 P0/P1/P2,
  accept_remaining.

## 6. Verdict

Faithful recut of #541's Codex-APPROVE'd #509 implementation onto current
`polaris` HEAD, with #509's concurrency deltas correctly layered on
#505/#506/#507's just-merged changes (run_store.py kept #507's 16-col
projection; create_run wraps #506's enqueue). `POST /runs` enforces the
1-concurrent-session constraint atomically (`BEGIN IMMEDIATE`); a 2nd
request is rejected with a typed error + UX callout, never a crash; a
failed enqueue frees the slot. Ready for Codex diff review.
