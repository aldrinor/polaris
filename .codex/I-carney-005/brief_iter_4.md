HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings. Don't bank for iter 6 — it doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 iter 4 — P1-007 + P1-008 resolutions

## P1-007 — existing tests/v6/test_broker.py needs fresh-construction per test

`_INITIALIZED` sentinel breaks existing tests that pass explicit `use_stub=True` / `redis_url=...` expecting a fresh construction. Existing autouse fixture `_restore_session_broker` already saves/restores `dramatiq.get_broker()` — extend it to ALSO save/restore the sentinel.

### Resolution

**Patch 1: `src/polaris_v6/queue/broker.py`** — add `_INITIALIZED` sentinel + a test-only helper:

```python
_INITIALIZED = False

def _reset_for_testing() -> None:
    """Test-only: reset the init sentinel so the next get_broker() rebuilds.

    Callers (autouse fixtures in tests/) MUST also save and restore the
    current `dramatiq.get_broker()` reference. Production code never calls
    this — the sentinel is meant to be one-way per process.
    """
    global _INITIALIZED
    _INITIALIZED = False

def get_broker(*, use_stub=None, redis_url=None, heartbeat_seconds=DEFAULT_HEARTBEAT_SECONDS):
    global _INITIALIZED
    if _INITIALIZED:
        return dramatiq.get_broker()
    # ... existing construction logic ...
    dramatiq.set_broker(broker)
    _INITIALIZED = True
    return broker
```

**Patch 2: `tests/v6/test_broker.py`** — extend autouse fixture to reset+restore sentinel:

```python
@pytest.fixture(autouse=True)
def _restore_session_broker():
    from polaris_v6.queue import broker as br
    saved_broker = dramatiq.get_broker()
    saved_init = br._INITIALIZED
    br._INITIALIZED = False  # let each test construct fresh
    yield
    dramatiq.set_broker(saved_broker)
    br._INITIALIZED = saved_init
```

With this, every existing assertion in test_broker.py works unchanged:
- `test_use_stub_explicit_true_returns_stubbroker`: sentinel reset → builds fresh StubBroker → assertion passes
- `test_use_stub_via_env_var`: same
- `test_redis_url_arg_overrides_env`: sentinel reset → builds RedisBroker with arg URL → passes
- `test_redis_url_env_used_when_arg_missing`: same
- `test_set_broker_registers_globally`: builds fresh stub → registers → passes
- After-yield restore puts the session stub broker back so subsequent test files (test_actors.py, test_acceptance.py) see the SHARED stub from conftest, preserving session continuity

## P1-008 — new test_broker_init_order.py state restoration

### Resolution

```python
# tests/v6/test_broker_init_order.py
import pytest
import dramatiq


@pytest.fixture(autouse=True)
def _restore_broker_state():
    """Same save/restore pattern as test_broker.py, scoped to this file."""
    from polaris_v6.queue import broker as br
    saved_broker = dramatiq.get_broker()
    saved_init = br._INITIALIZED
    br._INITIALIZED = False
    yield
    dramatiq.set_broker(saved_broker)
    br._INITIALIZED = saved_init


def test_get_broker_is_idempotent(monkeypatch):
    """Regression for I-carney-005 P1-001: repeated get_broker calls don't
    overwrite an already-set broker. The autouse fixture has reset the
    sentinel + saved the prior state; this test runs cleanly in isolation."""
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    from polaris_v6.queue import broker as br
    b1 = br.get_broker()
    b2 = br.get_broker()
    assert b1 is b2
    assert dramatiq.get_broker() is b1


def test_actors_module_calls_get_broker_at_import(monkeypatch):
    """Regression for I-carney-005 P1-001: importing actors triggers
    broker init BEFORE any @dramatiq.actor decoration."""
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    # Force reimport so the top-of-module _ensure_broker fires.
    import importlib
    from polaris_v6.queue import actors
    importlib.reload(actors)
    # After reimport, a stub broker MUST be the current default.
    current = dramatiq.get_broker()
    from dramatiq.brokers.stub import StubBroker
    assert isinstance(current, StubBroker)
```

The autouse fixture preserves CHARTER for downstream tests.

## P2 — accepted

- iter-3 P2 (`from __future__` + docstring before `_ensure_broker` import in actors.py): noted; the production patch will keep:
  ```python
  """<module docstring>"""
  from __future__ import annotations
  from polaris_v6.queue.broker import get_broker as _ensure_broker
  _ensure_broker()
  import dramatiq  # noqa: E402
  # ... rest
  ```

## Direct questions iter 4

1. The `_reset_for_testing()` helper + extended `_restore_session_broker` autouse fixture pattern — APPROVE'd?
2. Two new regression tests in `test_broker_init_order.py` (idempotence + module-load broker init) — APPROVE'd?
3. Anything else blocking iter-4 APPROVE?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
