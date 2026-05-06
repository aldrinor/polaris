# Codex Diff Review Brief — I-phase0-005 (ITER 2)

**Iter:** 2 of N (no hard cap per CLAUDE.md §8.3.1)

## Why this iter exists

Iter-1 returned narrative + sandbox failures **without the structured verdict block**. The CI required check `polaris/codex-required` parses `codex_diff_audit.txt` for the YAML schema; a narrative-only audit cannot land. Iter-2 MUST emit the schema block enumerating ALL findings.

Additionally, Codex iter-1 raised one architectural observation (RedisBroker default outside pytest). It is addressed below; classify as P2 out-of-scope-for-this-Issue or escalate with explicit reasoning.

## Hard requirements for iter-2 output

1. **Static review against the brief is sufficient. Do NOT re-run pytest.** Codex iter-1 hit `PermissionError [WinError 5] 'C:\Users\msn\AppData\Local\Temp\pytest-of-msn'` — that is a Codex-sandbox ACL problem, not a test bug. The empirical pytest output is pasted verbatim below.

2. **Emit the YAML schema block.** Verdict APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

3. **List ALL findings this iteration. No toothpaste-squeeze across iters.** Same quality bar as iter-1.

## Empirical pytest output (Claude verified, Windows 11, Python 3.13.13, pytest 8.4.1)

```
$ PYTHONPATH=src python -m pytest tests/v6/acceptance/test_runs_db_integration.py tests/v6/acceptance/test_dramatiq_acceptance.py::test_scenario_1_enqueue_and_complete tests/v6/test_actors.py -v

============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-8.4.1, pluggy-1.6.0 -- C:\Python313\python.exe
configfile: pytest.ini
collecting ... collected 13 items

tests/v6/acceptance/test_runs_db_integration.py::test_init_db_creates_schema PASSED [  7%]
tests/v6/acceptance/test_runs_db_integration.py::test_actor_marks_completed_after_pre_insert PASSED [ 15%]
tests/v6/acceptance/test_runs_db_integration.py::test_post_runs_persists_row PASSED [ 23%]
tests/v6/acceptance/test_runs_db_integration.py::test_get_run_after_drain_returns_completed PASSED [ 30%]
tests/v6/acceptance/test_dramatiq_acceptance.py::test_scenario_1_enqueue_and_complete PASSED [ 38%]
tests/v6/test_actors.py::test_enqueue_returns_completed_status_and_echoes_payload PASSED [ 46%]
tests/v6/test_actors.py::test_enqueue_handles_empty_payload PASSED       [ 53%]
tests/v6/test_actors.py::test_enqueue_max_retries_constant_is_3 PASSED   [ 61%]
tests/v6/test_actors.py::test_enqueue_actor_carries_max_retries_3 PASSED [ 69%]
tests/v6/test_actors.py::test_enqueue_actor_time_limit_is_30_minutes_in_ms PASSED [ 76%]
tests/v6/test_actors.py::test_cancel_returns_cancel_requested_status PASSED [ 84%]
tests/v6/test_actors.py::test_cancel_actor_max_retries_is_0 PASSED       [ 92%]
tests/v6/test_actors.py::test_actors_are_dramatiq_actor_instances PASSED [100%]

============================= 13 passed in 2.35s ==============================
```

**StubBroker binding verified independently:**

```
$ PYTHONPATH=src python -c "import sys; sys.path.insert(0,'tests/v6'); import conftest; import dramatiq; print(type(dramatiq.get_broker()).__name__); from polaris_v6.queue.actors import enqueue_research_run; print(type(enqueue_research_run.broker).__name__)"
StubBroker
StubBroker
```

`tests/v6/conftest.py` installs the StubBroker at module-import time (line 33: `_SHARED_TEST_BROKER = _get_broker(use_stub=True)`) BEFORE any test module imports `polaris_v6.queue.actors`, so the `@dramatiq.actor` decorator binds against StubBroker. Acceptance tests #1-4 + scenario 1 + all 8 existing test_actors.py: 13/13 PASS in 2.35s.

## Pre-answer to iter-1's RedisBroker-default observation

Iter-1 narrative said:

> outside pytest, even with `POLARIS_V6_QUEUE_USE_STUB=1`, importing `polaris_v6.api.app` binds `enqueue_research_run` to `RedisBroker`, and `POST /runs` attempts localhost Redis.

**Claude's response:** This is correct production behavior, not a bug.

- The brief's acceptance criteria #1-4 specify SQLite persistence + actor transitions + POST→DB→GET round-trip via the StubBroker test path. None specify "POST /runs must succeed without Redis."
- Production broker selection is governed by `POLARIS_V6_QUEUE_USE_STUB` and `POLARIS_V6_REDIS_URL` env vars (see `src/polaris_v6/queue/broker.py`). Production deploys (Phase 0 Task 0.3 Vast.ai dev cluster, Phase 4 OVH BHS H200) require a real Redis broker — that is by design.
- `tests/v6/conftest.py` sets `POLARIS_V6_QUEUE_USE_STUB=1` at module-import time so the test session uses StubBroker. Outside pytest with the env var unset, dramatiq auto-creates a RedisBroker — also by design.
- The diff does not change broker selection logic. `enqueue_research_run.send(...)` uses whatever broker is active (test or production).

**Classification:** P2 out-of-scope-for-this-Issue. Production broker availability is Phase 0 Task 0.3 (Vast.ai dev cluster) and Phase 4 (OVH BHS H200) scope. If Codex disagrees with the classification, escalate with explicit reasoning citing brief acceptance #N or a specific spec violation.

## Artifacts under review

- `.codex/I-phase0-005/brief.md` — the Codex-APPROVE'd iter-4 spec (verdict in `codex_brief_verdict.txt`)
- `.codex/I-phase0-005/codex_diff.patch` — canonical PR diff with `# canonical-diff-sha256: a363def93a144c23a72766c5f325a7ff3bc8eb850bb1c9b16b95b26908c94b3c` trailer
- `outputs/audits/I-phase0-005/claude_audit.md` — Claude's architect self-audit (includes LOC overrun disclosure)

## Files in this diff (6 files, +347 / -33 = +314 net)

```
src/polaris_v6/queue/run_store.py        NEW    +148
src/polaris_v6/queue/actors.py           MOD    +15 / -1
src/polaris_v6/api/runs.py               MOD    +44 / -33
src/polaris_v6/schemas/run_status.py     MOD    +3 / -0
tests/v6/acceptance/test_runs_db_integration.py    NEW    +151
tests/v6/acceptance/test_dramatiq_acceptance.py    MOD    +13 / -7
```

## Specific risks for Codex Red-Team (re-review of iter-1 + new)

1. **CHARTER §3 LOC cap.** Brief budgeted 200; diff is 314 net (47% over). claude_audit.md §"LOC honesty disclosure" lists trimming options. Strict-cap or accept-the-overrun is your call. Recommendation: accept; future Issues split substrate-vs-tests.

2. **Stub-mode "row missing → noop" contract.** `actors.py:54` checks `if run_store.get_run(run_id) is not None:` before any DB write. `run_store.py:124-130` catches `sqlite3.OperationalError` → returns None. This handles `tests/v6/test_actors.py` calling `.fn()` directly without `init_db`. Risk: defensive behavior could mask DB-rotation-under-running-worker (acknowledged, not handled this Issue).

3. **POST /runs IntegrityError → 409 path.** uuid4 collision is theoretically impossible (122 bits). Code path exists for defense; not test-covered. Acceptable per brief.

4. **`canonical-diff-sha256` trailer.** Trailer `a363def93a144c23a72766c5f325a7ff3bc8eb850bb1c9b16b95b26908c94b3c` produced via `git diff --cached -- ":(exclude).codex/I-phase0-005/" ":(exclude)outputs/audits/I-phase0-005/"`. Workflow extracts the hash via `grep -E '^# canonical-diff-sha256: [a-f0-9]{64}$' | tail -1 | awk '{print $3}'`.

5. **Test isolation against session-shared StubBroker.** New `isolated_db` fixture calls `broker.flush_all()` before AND after each test. It is `@pytest.fixture` not `@pytest.fixture(autouse=True)`; explicit param ensures `monkeypatch.setenv` lands BEFORE imports.

6. **Scenario 1 strengthening.** Old: `assert True`. New: `record.status == "completed"`. PASS confirmed in pytest output above.

7. **`document_ids: []` echo.** `RunRequest.model_dump()` includes the default empty list per `src/polaris_v6/schemas/run_request.py:32`. Tests #2 + #4 assert echo includes `document_ids: []`. Verified by passing pytest.

8. **Pydantic forward-compat.** `result_json: str | None = None` is additive. Existing JSON deserializers unaffected (default). Existing serializers add `result_json: null` to payload (benign). `web/lib/api.ts` types are TypeScript permissive.

9. **Brief follow-up Issue id naming (P2-I4-001).** Brief mentioned `I-phase0-005-followup` — would collide with regex. Acknowledged in claude_audit.md; deferred to PR-E follow-up time. No code-change risk.

10. **NEW: Production RedisBroker default (iter-1 narrative).** Classified P2 out-of-scope (Task 0.3 / Phase 4 scope). See pre-answer above.

## Output schema (mandatory)

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
