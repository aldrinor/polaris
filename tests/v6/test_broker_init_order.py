"""I-carney-005 P1-001 regression: broker init must happen at module import
of polaris_v6.queue.actors, BEFORE any @dramatiq.actor decoration.

Without this, deploying api + worker as separate containers would bind
actors against Dramatiq's default broker (localhost:6379), NOT the
POLARIS_V6_REDIS_URL the entrypoint sets. Result: enqueued messages
disappear into a phantom queue. This test pins the contract.
"""

from __future__ import annotations

import pytest

pytest.importorskip("dramatiq")
import dramatiq
from dramatiq.brokers.stub import StubBroker


class _SentinelBroker(StubBroker):
    """Marker subclass so we can detect whether actors.py rebuilt the broker."""

    pass


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
    """Repeated get_broker() calls don't overwrite an already-set broker."""
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    from polaris_v6.queue import broker as br

    b1 = br.get_broker()
    b2 = br.get_broker()
    assert b1 is b2
    assert dramatiq.get_broker() is b1


def test_reset_for_testing_allows_fresh_construction(monkeypatch):
    """`_reset_for_testing()` clears the sentinel so the NEXT get_broker
    rebuilds. Required for tests that need a fresh broker per case.
    """
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    from polaris_v6.queue import broker as br

    b1 = br.get_broker()
    br._reset_for_testing()
    b2 = br.get_broker()
    # Different instances (rebuilt), but both StubBrokers.
    assert b1 is not b2
    assert isinstance(b1, StubBroker)
    assert isinstance(b2, StubBroker)


def test_actors_module_calls_get_broker_at_import(monkeypatch):
    """Strengthened per Codex iter-4 P1-009.

    Pre-install a sentinel broker and reset the init flag. Reloading actors
    MUST cause _ensure_broker() to fire and replace the sentinel with a real
    StubBroker (because POLARIS_V6_QUEUE_USE_STUB=1). If actors.py forgot to
    call _ensure_broker(), the sentinel remains current and the assertion
    fails. Also verify actor.broker matches the post-reload current broker,
    proving decoration order is correct (init BEFORE @dramatiq.actor).
    """
    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
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
    assert actors.enqueue_research_run.broker is current
    assert actors.cancel_research_run.broker is current
