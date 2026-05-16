# Codex brief — I-rdy-013 (#509): 1-concurrent-session enforcement + queue/rejection UX

## §0. HARD ITERATION CAP (verbatim, CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**This is iter 3 of 5.** This is a BRIEF review (acceptance-criteria correctness), not a diff review.

## §0.5 Changes since prior iters

**iter 1** = REQUEST_CHANGES, 1 P1, 3 design rulings (all adopted: reject not queue; LOC-cap exemption; conftest-wide autouse DB isolation):
- P1 (DB init): §3.2 — `insert_run_if_idle` calls `init_db(path)` first (mirrors `insert_run`).
- P2 (race test): §3.5 — added a two-thread `insert_run_if_idle` race test.
- P2 (UX wording): §3.3 — 409 message no longer says "cancel it" (polaris has no cancel path).

**iter 2** = REQUEST_CHANGES, 1 P1 + 1 P2:
- **P1-001 (concurrency-safe init):** §3.2 now makes `init_db` itself thread-safe via a module-level `threading.Lock` — two concurrent first requests could otherwise collide inside `init_db`'s `PRAGMA journal_mode=WAL` / schema migration and raise `OperationalError` before the atomic gate is reached. `busy_timeout` alone does not cover that DDL path.
- **P2-001 (envelope unwrap):** §3.4 now explicitly unwraps FastAPI's `{"detail": {...}}` envelope — `const detail = body?.detail ?? body;` before the `detail.code` check.

## §1. Issue

**GH #509 — I-rdy-013, Phase 3.10.** Body verbatim:
> Phase 3. Enforce the locked 1-concurrent-session constraint; a second concurrent request is queued or cleanly rejected with UX.
> Acceptance: a second concurrent request is handled gracefully (no crash, clear UX); Codex APPROVE.
> Depends on: I-rdy-003.

## §2. Grounded current state (verified by Read this fire)

- **No concurrency limit exists anywhere.** `grep -rn` for `concurrent|in_progress|active_run|session` across `src/polaris_v6/` returns only `queue/actors.py`, `queue/run_events.py`, `queue/run_store.py`, `schemas/run_status.py` — none enforces a session cap.
- `POST /runs` → `src/polaris_v6/api/runs.py:23 create_run`: `uuid4().hex` → `run_store.insert_run(...)` → `enqueue_research_run.send(...)` → `get_run` → return `202`. **Unconditional** — fires every time.
- `run_store.py`: `insert_run` (line 103) inserts `lifecycle_status='queued'`. `mark_in_progress` → `'in_progress'`. `mark_completed`/`mark_aborted` → `'completed'`. `mark_failed` → `'failed'`. `get_run` (line 230) reads one row defensively (catches `no such table` → None; `no such column` → migrate+retry). `LifecycleStatus` literal (`schemas/run_status.py:14`) = `queued | in_progress | completed | cancelled | failed`. **Terminal = `completed`/`cancelled`/`failed`; active = `queued`/`in_progress`.** (polaris has no `mark_cancelled` writer — `cancelled` enum value is reserved; that is fine, it is still terminal for our purposes.)
- `_connect` (line 38) sets `row_factory` only — no `busy_timeout`. WAL is set by `init_db`.
- Frontend `web/lib/api.ts`: `createRun` (line 111) POSTs and pipes through `asJsonOrThrow` (line 98), which on `!ok` throws a generic `ApiError` (`status`, `body`) with message `"POLARIS backend returned <code>"`. Dashboard `onSubmit` catch (`web/app/dashboard/page.tsx:182`) does `setError(err.message)` → renders the raw string in the `role="alert"` block at line 436. There IS a typed-error precedent in api.ts: `IntakeBadRequestError`, `RetrievalBadRequestError`, `GenerationBadRequestError`, `AuditBundleError` (`extends Error`).
- **Test-isolation gap (verified):** `tests/v6/test_api_health_and_runs.py` `client` fixture = `TestClient(create_app())` with **no `POLARIS_V6_RUN_DB` override** → every test in that module shares the default `state/v6_runs.sqlite`. Today this is harmless (no gate). With a 1-concurrent gate, a `queued` run left by an earlier test (StubBroker `.send()` enqueues but does not auto-run the actor) would make a later test's `POST /runs` return `409`. `tests/v6/conftest.py` force-installs one shared `StubBroker` at import time; it does NOT isolate the run DB.

## §3. Proposed approach — DESIGN FORK FOR CODEX TO RULE

The issue offers two acceptable behaviors: **queue** the 2nd request, or **cleanly reject** it. I recommend **reject (HTTP 409)**; rationale + the rejected alternative below — **please rule.**

### 3.1 RECOMMENDED: reject the 2nd concurrent `POST /runs` with HTTP 409 + clear UX

**Why reject over queue:**
- True "queue with position UX" requires a queue-position model, per-position display, and reconciling with Dramatiq's own broker queue — materially more code/UX for no demo benefit.
- The demo is single-operator, one session. A second run silently queueing with no feedback IS the UX bug the issue names ("queued or cleanly rejected **with UX**").
- Each run bills a V4 Pro generation; blocking an accidental double-submit prevents double-spend.
- Reject fully satisfies acceptance: "handled gracefully (no crash, clear UX)."

**Rejected alternative — queue:** accept the 2nd run as `queued` and show queue position. More code, more UX surface, and Dramatiq already FIFO-serializes `.send()`'d jobs at the broker — so "queue" mostly duplicates broker behavior while still needing the same UX work. Not worth it for a single-operator demo. *(Codex: if you disagree and want queue, say so and I will re-brief.)*

### 3.2 Backend — atomic check-and-insert (race-free)

A naive "`get_active_run()` then `insert_run`" has a TOCTOU race: two simultaneous POSTs both see no active run and both insert. Fix with a **single `BEGIN IMMEDIATE` transaction** in run_store:

- **`run_store._connect`**: add `conn.execute("PRAGMA busy_timeout=5000")` so a concurrent writer waits for the lock instead of erroring `SQLITE_BUSY` (directly serves the issue's "no crash"). 1 line, benefits all callers.
- **`run_store.init_db`**: wrap the body in a module-level `_INIT_LOCK = threading.Lock()` (`with _INIT_LOCK:`). Without it, two concurrent first requests (= two FastAPI worker threads, one process) can both enter `init_db` and collide inside `PRAGMA journal_mode=WAL` / the schema migration's `ADD COLUMN`, raising `sqlite3.OperationalError` *before* the atomic gate. The lock serializes all in-process callers → thread A migrates fully, thread B then sees every `CREATE TABLE IF NOT EXISTS` / `col not in cols` as a no-op. This is exactly the "two concurrent first requests" scenario; both the FastAPI thread pool and the §3.5 race test are same-process, so a `threading.Lock` fully covers it. `import threading` added to run_store. ~3 lines.
- **`run_store._row_to_response(row)`** (new private helper): build a `RunStatusResponse` from a `sqlite3.Row`. Refactor `get_run` to use it (removes ~16 dup lines); `get_active_run` + `insert_run_if_idle` reuse it.
- **`run_store.get_active_run(*, path=None) -> RunStatusResponse | None`** (new): `SELECT ... WHERE lifecycle_status IN ('queued','in_progress') ORDER BY queued_at LIMIT 1`. Same defensive `no such table`→None / `no such column`→migrate+retry guard as `get_run`. Read-side counterpart used by tests (and available to future status UI).
- **`run_store.insert_run_if_idle(run_id, template, question, *, path=None) -> RunStatusResponse | None`** (new): **call `init_db(path)` first** (mirrors `insert_run` line 105 — `create_app` does not init the runs DB, so this is what makes the very first `POST /runs` work; omitting it 500s on `no such table: runs`). Then `conn = _connect(path)`, set `conn.isolation_level = None` (manual txn control), `BEGIN IMMEDIATE`, `SELECT` for an active run; if found → `ROLLBACK`, return that run; else `INSERT ... 'queued'`, `COMMIT`, return `None`. `BEGIN IMMEDIATE` grabs the write lock up-front so the 2nd concurrent POST blocks until the 1st commits, then sees the row → race-free.
- `insert_run` stays unchanged (unconditional primitive, still used by test fixtures); `insert_run_if_idle` is the concurrency-gated variant.

`_ACTIVE_STATUSES = ("queued", "in_progress")` module constant (LAW VI — no magic literals).

### 3.3 Backend — `api/runs.py:create_run`

Swap `insert_run` → `insert_run_if_idle`. If it returns a non-None active run, raise **`HTTPException(409, detail={...})`** with a structured dict detail (FastAPI serializes any JSON-able detail):
```
{"code": "concurrent_run_active",
 "active_run_id": <id>, "active_status": <queued|in_progress>,
 "message": "POLARIS runs one research session at a time. Run <id8> is currently <status>. Wait for it to finish before starting a new run."}
```
`enqueue_research_run.send(...)` moves to **after** the reject check — a rejected run is never enqueued. The pre-existing uuid-collision `409` keeps its plain-string detail (distinguishable: dict-detail w/ `code` vs string-detail).

### 3.4 Frontend

- `web/lib/api.ts`: new `export class ConcurrentRunError extends Error` (`activeRunId`, `activeStatus` fields) mirroring `IntakeBadRequestError`. `createRun` intercepts `response.status === 409`: read body **once** (`const body = await response.json().catch(() => null);`), then **explicitly unwrap the FastAPI envelope** — `const detail = body?.detail ?? body;` (the response is `{"detail": {...}}`; a literal top-level `body.code` check would miss it). If `detail?.code === "concurrent_run_active"` throw `ConcurrentRunError(detail.message, detail.active_run_id, detail.active_status)`, else rebuild the generic `ApiError` (non-concurrent 409); non-409 flows through `asJsonOrThrow` untouched (body not pre-consumed).
- `web/app/dashboard/page.tsx`: new `concurrentRun` state `{runId, status} | null`; cleared at `onSubmit` start. `onSubmit` catch: `if (err instanceof ConcurrentRunError)` → set `concurrentRun` + `setError(err.message)` + `setSubmitting(false)`. Render a callout next to the existing `role="alert"` block containing the message and a `<Link href={`/runs/${runId}`}>` "Open the active run →" — that link IS the "clear UX" (operator can jump straight to the run that is blocking).

### 3.5 Tests

- **`tests/v6/conftest.py`** — add an `autouse` fixture that `monkeypatch`-sets `POLARIS_V6_RUN_DB` to a unique temp path per test. Fixes the §2 isolation gap **universally** (run_store reads the env on every `_connect`, so this is sufficient). This is required collateral, not scope creep: without it the gate makes existing `test_api_health_and_runs.py` tests fail on stale `queued` rows. *(Codex: conftest-wide autouse vs patching each `client` fixture individually — I chose conftest-wide as the more robust single fix; rule if you prefer per-fixture.)*
- **`tests/v6/test_concurrency.py`** (new) — `insert_run_if_idle` inserts when idle (→None); rejects when a `queued` run exists; rejects when an `in_progress` run exists; allows a new run after the prior is `completed`/`failed`/`aborted`; `get_active_run` returns the active run / None. API-level (mirror `test_api_health_and_runs.py` `client` fixture exactly): 2nd `POST /runs` → `409` with `detail.code == "concurrent_run_active"` and `active_run_id` present; after marking run 1 `completed`, a fresh `POST /runs` → `202`. **Race test:** two `threading.Thread`s each calling `insert_run_if_idle` against one shared **fresh** temp DB path concurrently → assert **no thread raised an exception**, exactly one returns `None` (inserted), exactly one returns the active run, and exactly one row exists in the table. This exercises both the `_INIT_LOCK` first-use safety and the `BEGIN IMMEDIATE` gate that sequential tests cannot.

## §4. Deliverables + LOC

| File | Change | ~LOC |
|---|---|---|
| `src/polaris_v6/queue/run_store.py` | `_row_to_response`, `get_active_run`, `insert_run_if_idle`, `busy_timeout`, `_INIT_LOCK`-guarded `init_db`, `_ACTIVE_STATUSES` | +80 (`get_run` shrinks ~16 via helper) |
| `src/polaris_v6/api/runs.py` | `insert_run_if_idle` + 409 reject | +14 |
| `web/lib/api.ts` | `ConcurrentRunError` + `createRun` 409 handling | +32 |
| `web/app/dashboard/page.tsx` | `concurrentRun` state + callout + catch | +20 |
| `tests/v6/conftest.py` | autouse run-DB isolation fixture | +9 |
| `tests/v6/test_concurrency.py` | NEW (incl. two-thread race test) | +125 |

**Total ≈ 275 LOC; non-test ≈ 150, test ≈ 125.** Exceeds the 200-LOC PR cap; iter-1 granted the cap exemption (test-dominated, non-test diff ≈150). No trim found that keeps the race-free guarantee and the required test isolation.

## §5. Files I have ALSO checked and they are clean

- `src/polaris_v6/queue/actors.py` — `enqueue_research_run` actor; no concurrency cap; unaffected (a rejected run is never `.send()`'d).
- `src/polaris_v6/queue/run_events.py` — SSE lifecycle; reads run status, does not create runs.
- `src/polaris_v6/schemas/run_status.py` / `run_request.py` — `LifecycleStatus` literal already has all states; no schema change needed.
- `tests/v6/test_actors.py` — calls actor `.fn()` directly; benefits from (not broken by) the conftest DB-isolation fixture.
- `tests/v6/test_run_benchmark_script.py` — benchmark script test; does not POST `/runs`.
- `web/app/runs/[runId]/page.tsx` — run detail page; the callout's `<Link>` targets it; no change required.
- No other `src/` caller of `insert_run` exists (only `create_run`); `insert_run` is preserved for test fixtures.

## §6. Output schema (CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

All three iter-1 design forks resolved: reject (§3.1) ✓, LOC-cap exemption (§4) ✓, conftest-wide autouse DB isolation (§3.5) ✓. No open decisions for iter 2 — verifying the P1 fix landed.
