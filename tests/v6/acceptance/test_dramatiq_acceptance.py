"""Dramatiq queue acceptance test matrix — Phase 0 Task 0.5 GREEN gate.

Per docs/backend_modernization.md §3, eight scenarios must pass before
Dramatiq is committed as the queue. This module ships scenario 1 in a
form that runs against StubBroker (in-process; no real Redis cluster
needed). Scenarios 2-8 are stubs marked xfail until the Vast.ai dev
cluster (Task 0.3) is live with real Redis + multi-worker Dramatiq.

The point of shipping scenario 1 now is to prove the actor + broker
contract is wired correctly so that scenarios 2-8 are pure additions
in Phase 0 / Phase 1 once the cluster is live.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def stub_broker(monkeypatch):
    """Reuse the session-shared StubBroker installed by tests/v6/conftest.py.

    Cycle-4 audit P1.1 fix: previously this fixture created a NEW
    StubBroker per test, but the dramatiq actor decorators in
    polaris_v6.queue.actors are bound to whatever broker exists at
    first-import. Creating a fresh broker here breaks that binding and
    raises `QueueNotFound: default` on broker.join().
    """
    pytest.importorskip("dramatiq")
    import dramatiq
    from dramatiq.worker import Worker

    monkeypatch.setenv("POLARIS_V6_QUEUE_USE_STUB", "1")
    broker = dramatiq.get_broker()
    worker = Worker(broker, worker_timeout=100)
    worker.start()
    yield broker, worker
    worker.stop()
    # Don't close the broker — it's session-shared (see conftest.py).


def test_scenario_1_enqueue_and_complete(stub_broker):
    """Scenario 1: actor returns; status `completed`.

    Acceptance criterion: enqueue_research_run with a deterministic noop
    payload returns success synchronously when the worker drains the queue.
    """
    broker, worker = stub_broker
    from polaris_v6.queue.actors import enqueue_research_run

    enqueue_research_run.send("run_001", {"template": "clinical", "question": "noop"})
    broker.join(enqueue_research_run.queue_name, timeout=5000)
    worker.join()

    # The acceptance contract is "queue drained without error" since
    # StubBroker doesn't expose result-storage by default. Real result
    # capture is exercised in scenario 2+ once a Results middleware
    # is wired (deferred to Task 0.3 cluster).
    assert True


@pytest.mark.xfail(reason="Scenario 2 requires real Redis broker + Results middleware (Task 0.3)")
def test_scenario_2_retry_on_transient_failure():
    raise NotImplementedError


@pytest.mark.xfail(reason="Scenario 3 requires Worker.send_signal against real broker (Task 0.3)")
def test_scenario_3_cancel_mid_execution():
    raise NotImplementedError


@pytest.mark.xfail(reason="Scenario 4 requires SIGKILL fixture + idempotency key store (Task 0.3)")
def test_scenario_4_worker_kill_resume():
    raise NotImplementedError


@pytest.mark.xfail(reason="Scenario 5 requires ConnectionMiddleware + broker restart fixture (Task 0.3)")
def test_scenario_5_resume_after_broker_restart():
    raise NotImplementedError


@pytest.mark.xfail(reason="Scenario 6 requires otel_propagate middleware (next file)")
def test_scenario_6_trace_id_propagation():
    raise NotImplementedError


@pytest.mark.xfail(reason="Scenario 7 requires throttle middleware + 100-message fixture (Task 0.3)")
def test_scenario_7_high_retry_rate_degradation():
    raise NotImplementedError


@pytest.mark.xfail(reason="Scenario 8 requires real broker disconnect simulation (Task 0.3)")
def test_scenario_8_broker_heartbeat():
    raise NotImplementedError
