# Brief — I-phase0-005 — Backend modernization + Dramatiq queue

**GitHub Issue:** #86 (`bot/I-phase0-005`)
**LOC budget:** 200 (CHARTER §3 hard cap)
**Phase / Feature:** 0 / infra (per §3a defaults)

**Iter:** 4 of N (no hard cap per CLAUDE.md §8.3.1)

## iter-3 findings addressed

- **iter-3 P0-I3-001 (over 200-LOC cap) RESOLVED via scope-down.** Brief is rewritten ground-up to fit the 200-LOC ceiling. Acceptance #3 (missing-row direct `.fn()` test), #6 (idempotency on re-execution), and #7 (failure-path with re-raise) are MOVED to a follow-up Issue `I-phase0-005-followup` (already-open Issue #87 in `state/polaris_restart/issue_github_map.json`... actually no such Issue exists; brief commits to opening it as a separate operator-side action AFTER this Issue ships, AND files it under existing precedent: cleanup_audit.md follow-up PR pattern). This Issue keeps 5 acceptance criteria (was 9 in iter 3): schema, actor success path, POST persists, GET reads from store, scenario-1-still-green. Net result: 195 LOC, under the 200 cap.

- **iter-3 P1-I3-001 (residual `running` references) RESOLVED.** All occurrences of `running` outside the iter-2 fix-summary block replaced with `in_progress`. Schema uses `in_progress`. Function name is `mark_in_progress`. Allowed transitions: `queued → in_progress → completed`, `queued → in_progress → failed` (deferred test), `completed → completed` (idempotent no-op, tested in follow-up Issue).

- **iter-3 P1-I3-002 (env-unset / default-DB / no-op contract contradiction) RESOLVED with a SINGLE contract:**
  - `init_db(path: str | None = None)` ALWAYS initializes a real SQLite. When `path` is None, it resolves from `os.environ.get("POLARIS_V6_RUN_DB", "state/v6_runs.sqlite")`. Default path is ALWAYS active.
  - There is NO env-flag for skip-DB mode. The earlier "POLARIS_V6_QUEUE_SKIP_DB" idea is dropped.
  - For `tests/v6/test_actors.py` compatibility: the actor's body checks `run_store.get_run(run_id)`. If the row exists, it transitions status (DB-mode). If the row does NOT exist, it returns the noop stub WITHOUT calling mark_in_progress/mark_completed (preserves the existing pre-Phase-1 stub-mode behavior documented in `actors.py:39-44`). This keeps `test_actors.py` green WITHOUT modification because those tests don't pre-insert rows; the actor just returns the deterministic noop. New integration tests pre-insert rows and exercise the DB path.

- **iter-3 P2-I3-001 (failure-path test helper name) ACKNOWLEDGED for follow-up.** Failure test is deferred per scope-down. The follow-up Issue's brief will require a named helper `_execute_run_body(run_id, payload) -> dict` in `actors.py` so tests can monkeypatch deterministically. NOT in this Issue's LOC.

- **iter-3 P2-I3-002 (RunRequest.model_dump() shape) RESOLVED.** Confirmed via reading `src/polaris_v6/schemas/run_request.py:32-39`: `RunRequest` has 3 fields — `template`, `question`, `document_ids` (default `[]`). `model_dump()` includes all three including the empty-list default. The actor's noop return value is `{"run_id": run_id, "status": "completed", "echo": {"template": ..., "question": ..., "document_ids": []}}`. Test assertions explicitly include `document_ids: []` in the expected echo dict.

- **iter-3 P2-I3-003 (stale LOC-table wording about `tests/v6/test_actors.py`) FIXED.** That file is NOT in the LOC table this iteration. Acceptance #5 ("scenario 1 still green") is achieved by the DB-default-on / row-not-found-stub-noop contract above; `test_actors.py` requires zero changes (verified by manual inspection — those tests call `.fn()` without pre-inserting; new actor code returns noop on missing row, matching pre-PR behavior).

## Problem statement

POLARIS v6 has Dramatiq actor scaffolding (`src/polaris_v6/queue/actors.py`, `broker.py`, middleware) and one in-process Stub-broker acceptance test (`tests/v6/acceptance/test_dramatiq_acceptance.py` scenario 1) that asserts "queue drained without error." The existing FastAPI route `POST /runs` (`src/polaris_v6/api/runs.py`) writes records to an in-memory dict `_run_table` and explicitly comments out the actor `.send()` call as Phase-0-stub.

Issue acceptance requires:

1. Dramatiq worker consumes job from queue.
2. **Result materialized in DB.**
3. Integration test green.

#1 is met by existing scenario 1. #2 + #3 are NOT met today: dict-backed `_run_table` is process-local memory, no DB; no integration test covers POST /runs → worker drain → GET returns persisted result.

## Scope (in scope)

1. **Add SQLite-backed run-status store** at `src/polaris_v6/queue/run_store.py`:
   - Schema: `runs(run_id TEXT PRIMARY KEY, template TEXT, question TEXT, status TEXT, queued_at TEXT, started_at TEXT, finished_at TEXT, result_json TEXT, error_json TEXT)` — 9 columns. Names match `RunStatusResponse` field names exactly.
   - Functions: `init_db(path: str | None = None)` (default-active; resolves from env or `state/v6_runs.sqlite`; idempotent via `CREATE TABLE IF NOT EXISTS`; enables WAL); `insert_run(run_id, template, question)`; `mark_in_progress(run_id)`; `mark_completed(run_id, result: dict)`; `get_run(run_id) -> RunStatusResponse | None`.
   - **NOT in scope this Issue:** `mark_failed`, idempotency-on-completed short-circuit, error_json fields. (Deferred to follow-up Issue.)
   - SQLite filename gitignored.

2. **Wire actor to store** at `src/polaris_v6/queue/actors.py`:
   - On entry: call `get_run(run_id)`. If `None`, return existing noop dict (preserves stub-mode + `test_actors.py` compatibility).
   - If row found: call `mark_in_progress(run_id)`, do the noop work, call `mark_completed(run_id, result)`, return result.
   - **NOT in scope:** failure handling, retry semantics, idempotency check on already-completed rows. Actor still has `max_retries=3` decorator from existing code; failure path is exercised only in follow-up Issue.

3. **Extend `RunStatusResponse`** at `src/polaris_v6/schemas/run_status.py`:
   - Add `result_json: str | None = None`. (No `error_json` this Issue — deferred.)
   - Existing 7 fields unchanged.

4. **Wire POST /runs** at `src/polaris_v6/api/runs.py`:
   - Replace the `_run_table[run_id] = record` line with `run_store.insert_run(run_id, payload.template, payload.question)`.
   - Replace the commented `# enqueue_research_run.send(...)` with the actual `.send(run_id, payload.model_dump())`.
   - On `sqlite3.IntegrityError` (duplicate run_id, theoretically impossible since uuid4 but defensive): translate to HTTP 409.
   - Return shape unchanged otherwise.

5. **Wire GET /runs/{id}** same file:
   - Replace `_run_table.get(run_id)` with `run_store.get_run(run_id)` (returns `RunStatusResponse | None`).
   - 404 unchanged when None.

6. **Add 4 integration tests** at `tests/v6/acceptance/test_runs_db_integration.py`:
   - autouse fixture: `broker.flush_all()` before/after each test + `tmp_path`-backed DB via `monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "test.sqlite"))` BEFORE any import.

7. **Update scenario 1** in existing `test_dramatiq_acceptance.py`:
   - Add 2 lines: set `POLARIS_V6_RUN_DB` env to tmp path, call `insert_run("run_001", "clinical", "noop?")` before `.send()`. Then assert `get_run("run_001").status == "completed"`. (Strengthens scenario 1 from "drained without error" → "row reached completed". Acceptance #5.)

## Out of scope (deferred to follow-up Issue I-phase0-005-followup)

- `mark_failed` + error_json + failure-path test (acceptance #7 from iter 3).
- Idempotency-on-completed short-circuit + test (acceptance #6 from iter 3).
- Missing-row direct `.fn()` `RuntimeError` (acceptance #3 from iter 3) — inverted: actor returns noop on missing row, so this test is moot under the new contract.
- Real Redis broker, Postgres, pipeline-A bridge (out of Phase 0 scope).

## Acceptance criteria (each item testable; 5 total)

1. **Schema applied:** `init_db(path)` creates the `runs` table with 9 named columns. `test_init_db_creates_schema` introspects `sqlite_master`.
2. **Actor success path persists:** test pre-inserts row via `insert_run("run_002", "clinical", "noop?")`, calls `enqueue_research_run.send("run_002", {"template": "clinical", "question": "noop?", "document_ids": []})`, drains broker. `get_run("run_002").status == "completed"` AND `json.loads(get_run("run_002").result_json) == {"run_id": "run_002", "status": "completed", "echo": {"template": "clinical", "question": "noop?", "document_ids": []}}`. Test: `test_actor_marks_completed_after_pre_insert`.
3. **POST /runs persists row:** `TestClient.post("/runs", json={"template": "clinical", "question": "noop?"})` returns 202 with `status='queued'`; SQLite row exists with `status='queued'`. Test: `test_post_runs_persists_row`.
4. **GET /runs/{id} reads from store:** after POST + broker drain, `TestClient.get("/runs/{id}")` returns 200 with `status='completed'` and `result_json` matching the actor return value. Test: `test_get_run_after_drain_returns_completed`.
5. **Scenario 1 strengthened:** existing `test_scenario_1_enqueue_and_complete` updated to set env + pre-insert + assert `get_run("run_001").status == "completed"`. Test continues to pass with the strengthened assertion.

## Adversarial inputs

- Concurrent inserts of same `run_id`: SQLite PRIMARY KEY UNIQUE → `sqlite3.IntegrityError` → POST handler returns 409. Not tested in this Issue (deferred).
- DB file permission denied: `init_db` raises `RuntimeError`. POST handler catches → 503. Not tested in this Issue.
- Large `result_json`: SQLite TEXT effective 1 GB; documented in module docstring; not tested.
- WAL mode: enabled in `init_db()` so Dramatiq workers (writers) don't block FastAPI handlers (readers).
- Test isolation: autouse `broker.flush_all()` before/after each test in the new file prevents StubBroker (session-shared per `tests/v6/conftest.py`) cross-test pollution.

## LOC estimate

200 (at the cap):

| File | Action | LOC |
|---|---|---|
| `src/polaris_v6/queue/run_store.py` | NEW (schema + 5 functions: init_db, insert_run, mark_in_progress, mark_completed, get_run; WAL; row→`RunStatusResponse` adapter) | ~75 |
| `src/polaris_v6/queue/actors.py` | MODIFY (get_run check; mark_in_progress + mark_completed if row exists; preserve noop-return when row missing) | ~20 |
| `src/polaris_v6/api/runs.py` | MODIFY (replace dict with run_store calls; .send() for actor enqueue; IntegrityError → 409) | ~25 |
| `src/polaris_v6/schemas/run_status.py` | MODIFY (add `result_json: str | None = None`) | ~3 |
| `tests/v6/acceptance/test_runs_db_integration.py` | NEW (4 tests + autouse fixture; tmp_path DB; broker flush) | ~65 |
| `tests/v6/acceptance/test_dramatiq_acceptance.py` | MODIFY scenario 1 (env set + insert_run + status assertion) | ~10 |
| **Total** | | **~198** |

`tests/v6/test_actors.py` NOT in scope, NO changes (verified compatible via row-not-found-stub-noop contract).

## Foundation refs

- `state/polaris_restart/plan.md` §4 + §3.0
- `polaris-controls/CHARTER.md` §1 + §3 + §4 + §7
- `docs/carney_delivery_plan_v6_2.md` Phase 0 Task 0.5
- `docs/backend_modernization.md` §3 (Dramatiq acceptance scenarios)
- Existing: `src/polaris_v6/queue/{actors,broker}.py`, `src/polaris_v6/api/runs.py`, `src/polaris_v6/schemas/{run_request,run_status}.py`, `tests/v6/acceptance/test_dramatiq_acceptance.py`, `tests/v6/conftest.py`

## Per-Issue artifacts required at PR open (CHARTER §7)

- `.codex/I-phase0-005/brief.md` (this file; Codex APPROVE on acceptance correctness)
- `.codex/I-phase0-005/codex_brief_verdict.txt` (Codex APPROVE)
- `.codex/I-phase0-005/codex_diff.patch` (Claude-written diff with `# canonical-diff-sha256: <64-hex>` trailer)
- `.codex/I-phase0-005/codex_diff_audit.txt` (Codex APPROVE on Red-Team checklist)
- `outputs/audits/I-phase0-005/claude_audit.md` (Claude architect review)

## Output schema for Codex review

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1 (per plan §7.C LOCKED C2).

List ALL findings this iteration. Do NOT hold any back to drip-feed across iterations. Same quality bar regardless of iteration count. No hard cap on iterations.
