# Per-commit Codex brief — `0c49d57`

**Commit:** `0c49d57 PL: v6.2 backend coverage — queue.broker.get_broker (9 tests)`
**Format:** v2 minimal
**Files changed (1):** `tests/v6/test_broker.py` (new, 89 lines, 9 tests)

## What this commit does

`src/polaris_v6/queue/broker.py` was uncovered. The `get_broker()` function is the seam between dev (StubBroker, in-process) and prod (RedisBroker against `POLARIS_V6_REDIS_URL`). Misconfiguration here = workers boot against the wrong queue.

9 tests cover:
1. `use_stub=True` returns StubBroker.
2. Env var `POLARIS_V6_QUEUE_USE_STUB=1` activates stub.
3. Env var `=0` falls through to RedisBroker.
4. URL arg overrides env (`arg-host` ≠ `env-host`).
5. URL env used when arg missing.
6. URL default `redis://localhost:6379/0` when neither arg nor env.
7. `DEFAULT_HEARTBEAT_SECONDS == 30`.
8. `DEFAULT_REDIS_URL == "redis://localhost:6379/0"`.
9. `dramatiq.get_broker()` returns the constructed broker (global registration).

RedisBroker tests don't actually connect (would require a Redis server). Instead, they inspect `broker.client.connection_pool.connection_kwargs` to verify URL parsing.

All 9 PASS in 1.00s. v6 test count: 228 → 237.

## Acceptance criteria

1. **Both broker code paths exercised** — Stub + Redis. Earlier coverage only touched StubBroker via the existing `acceptance/test_dramatiq_acceptance.py`; this widens to the prod path.
2. **No real Redis connection in tests** — verified by reading `broker.client.connection_pool.connection_kwargs` (a property; doesn't open socket).
3. **Env-var precedence asserted** — three explicit tests for arg / env / default. Misconfiguration (e.g., env reset accidentally) would surface here.
4. **Global registration verified** — without `dramatiq.set_broker(broker)`, downstream actor-decorators wouldn't pick it up. Test #9 catches accidental removal.
5. **No mock of dramatiq itself** — tests use the real `RedisBroker` constructor; only env vars are mocked via `monkeypatch`.

## Codex focus

- **P1:** Test #3 expects `POLARIS_V6_QUEUE_USE_STUB=0` to fall through to Redis. The check is `os.environ.get("POLARIS_V6_QUEUE_USE_STUB", "") == "1"` — strictly `"1"`, so any other value (including `"true"`, `"yes"`, `0`, etc.) falls through. Should we document/widen the truthy values? Tradeoff: stricter "1-only" prevents accidental enablement; looser is more user-friendly.
- **P2:** No test asserts middleware ordering (heartbeat / sticky-conn / throttle / OTEL-propagate). The actors module probably wires those; out of scope for this commit but a gap to flag.
- **P3:** RedisBroker connection-pool tests rely on `connection_kwargs` being on the pool object — a redis-py implementation detail. Could break on a redis bump.

## Cross-review

Lands at `outputs/audits/continuous/0c49d57/cross_review.md`. Counter at **1/5** in the post-bb60495 batch (cycle-3 subagent currently running).
