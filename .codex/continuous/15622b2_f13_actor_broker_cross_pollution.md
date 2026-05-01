# Per-commit Codex brief — `15622b2`

**Commit:** `15622b2 PL: v6.2 F-13 root_cause — fix actor/broker test cross-pollution (cycle-4 P1.1)`
**Format:** v2 minimal
**Files changed (5):**
- `tests/v6/conftest.py` (new, 30 lines) — module-level StubBroker setup
- `tests/v6/test_actors.py` (-7/+4) — drop module-level `get_broker`
- `tests/v6/test_broker.py` (+12/0) — autouse save+restore broker
- `tests/v6/acceptance/test_dramatiq_acceptance.py` (-7/+9) — use shared broker
- `outputs/audits/continuous/97b9c1f_audit.md` (cycle-4 audit deliverable)

## What this commit does

Closes cycle-4 audit P1.1 — the SUBAGENT-FOUND REGRESSION. The fix has 3 parts because the broker-binding bug was actually a state-leak class, not a single line.

**Root cause**: dramatiq's `@actor` decorator binds against `dramatiq.get_broker()` at MODULE IMPORT TIME. If broker A exists when actors module is imported, the actor's queue is registered on A and only A. Subsequent broker B can't `.join()` that queue — `QueueNotFound`.

**Fix layers:**
1. **`tests/v6/conftest.py` (NEW)** — module-level (not fixture) call to `get_broker(use_stub=True)`. Pytest imports conftest.py BEFORE collecting other test modules, so this StubBroker is the one that catches the actor decorators when test_actors.py later imports `polaris_v6.queue.actors`.
2. **`test_actors.py`** — removed module-level `get_broker()` call (no longer needed; conftest handles it).
3. **`test_dramatiq_acceptance.py` fixture** — switched from `StubBroker(); dramatiq.set_broker(broker)` (creates a NEW broker, breaks binding) to `dramatiq.get_broker()` (uses the conftest's broker; binding preserved).
4. **`test_broker.py` autouse fixture** — saves+restores `dramatiq.get_broker()` per test, since test_broker.py exercises `get_broker(redis_url=...)` which has a `dramatiq.set_broker()` side effect that would otherwise leak.

**Verification**: `pytest tests/v6/` → **238 passed + 7 xfailed in 19.29s**. The previously-failing `test_scenario_1_enqueue_and_complete` now passes consistently in both orderings.

## Acceptance criteria

1. **Reproduces the subagent's failure pre-fix** — confirmed: pre-fix `pytest tests/v6/` showed `FAILED ... test_scenario_1_enqueue_and_complete` with `QueueNotFound: default`.
2. **Full suite passes post-fix** — 238/238 + 7 xfailed. NO test modules silently skip.
3. **conftest.py runs at import time, not in a fixture** — the comment block explains WHY (pytest collection order). Future-Claude won't be tempted to "refactor into a fixture" without understanding the import-order dependency.
4. **Acceptance fixture preserves session broker** — does NOT call `broker.close()` on teardown (would invalidate the shared broker for other tests).
5. **Per-commit audit committed alongside** — cycle-4 audit at `outputs/audits/continuous/97b9c1f_audit.md` is the durable record of the regression + verdict.

## Codex focus (cycle-5 will probe)

- **P0:** Does the conftest.py import-time setup pollute parallel test runs? `pytest -n auto` would spawn workers each with their own conftest import, each with its own StubBroker. Acceptable for the single-worker default; flag if we ever enable xdist.
- **P1:** The comment "do NOT close() the broker on teardown" in conftest.py is critical — if anyone removes it (or the conftest's session fixture is "cleaned up" later), the regression returns. Worth a comment-test? Or a `pytest_sessionfinish` hook that asserts the broker still has the actor queues?
- **P2:** test_broker.py's save-restore fixture is autouse — runs on EVERY test in the file, even ones that don't call `get_broker`. Tiny overhead (~0.1ms per test); acceptable.
- **P3:** The fix uncovered an architectural detail that the future Phase 1 production code will need: when a real worker boots, the actors module must be imported AFTER `get_broker()` has been called. Document in `docs/backend_modernization.md`?

## Cross-review

Lands at `outputs/audits/continuous/15622b2/cross_review.md`. **Counter at 1/5 in the post-97b9c1f batch.** Cycle-5 (locking-target) fires after 5 substrate commits.
