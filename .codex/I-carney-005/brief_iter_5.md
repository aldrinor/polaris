HARD ITERATION CAP: 5 per document. This is iter 5 of 5.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-carney-005 iter 5 — P1-009 resolution

## P1-009 — strengthen test_actors_module_calls_get_broker_at_import

Codex iter-4: the proposed test was vacuous because conftest had already installed a session StubBroker, so it passes even if actors.py never calls `_ensure_broker()`. Strengthen by:
1. Pre-set a SENTINEL broker (custom StubBroker subclass as marker)
2. Reset `_INITIALIZED=False`
3. Reload actors module
4. Assert the current broker is NOT the sentinel (proving actors.py DID call `_ensure_broker()`)
5. Assert `actors.enqueue_research_run.broker is dramatiq.get_broker()` (proving decoration bound to the post-reload broker)

### Resolution

```python
# tests/v6/test_broker_init_order.py
import pytest

pytest.importorskip("dramatiq")
import dramatiq
from dramatiq.brokers.stub import StubBroker


class _SentinelBroker(StubBroker):
    """Marker subclass so we can detect whether actors.py rebuilt the broker."""
    pass


@pytest.fixture(autouse=True)
def _restore_broker_state():
    from polaris_v6.queue import broker as br
    saved_broker = dramatiq.get_broker()
    saved_init = br._INITIALIZED
    br._INITIALIZED = False
    yield
    dramatiq.set_broker(saved_broker)
    br._INITIALIZED = saved_init


def test_get_broker_is_idempotent(monkeypatch):
    """Regression for I-carney-005 P1-001: repeated get_broker calls don't
    overwrite an already-set broker."""
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    from polaris_v6.queue import broker as br
    b1 = br.get_broker()
    b2 = br.get_broker()
    assert b1 is b2
    assert dramatiq.get_broker() is b1


def test_actors_module_calls_get_broker_at_import(monkeypatch):
    """Regression for I-carney-005 P1-001 (strengthened per Codex iter-4 P1-009).

    Pre-install a sentinel broker and reset the init flag. Reloading actors
    MUST cause _ensure_broker() to fire and replace the sentinel with a real
    StubBroker (because POLARIS_V6_QUEUE_USE_STUB=1). If actors.py forgot to
    call _ensure_broker(), the sentinel remains current and the assertion
    fails. Also verify actor.broker matches the post-reload current broker,
    proving decoration order is correct (init BEFORE @dramatiq.actor).
    """
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    # Install a sentinel non-actors broker.
    sentinel = _SentinelBroker()
    dramatiq.set_broker(sentinel)
    from polaris_v6.queue import broker as br
    br._INITIALIZED = False  # force the next get_broker() to rebuild

    import importlib
    from polaris_v6.queue import actors
    importlib.reload(actors)

    current = dramatiq.get_broker()
    assert current is not sentinel, (
        "actors.py did not call _ensure_broker() at import — "
        "sentinel broker is still the default"
    )
    assert isinstance(current, StubBroker), (
        f"expected StubBroker after reload, got {type(current).__name__}"
    )
    # P1-009 second half: decoration order — actors bind to the post-init broker.
    assert actors.enqueue_research_run.broker is current
    assert actors.cancel_research_run.broker is current
```

The test now FAILS LOUDLY if actors.py forgets to call `_ensure_broker()` at the top, AND if the init happens AFTER `@dramatiq.actor` decoration.

## P2 — accepted

- `pytest.importorskip('dramatiq')` added at top of test_broker_init_order.py per iter-4 P2.

## Direct questions iter 5

1. P1-009 strengthened test (sentinel broker + non-identity assertion + actor.broker decoration check) — APPROVE'd?
2. Anything else blocking iter-5 APPROVE? (Note: this is iter 5 of 5; per CLAUDE.md §8.3.1 force-APPROVE applies if REQUEST_CHANGES.)

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
