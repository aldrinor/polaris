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


def test_scenario_1_enqueue_and_complete(stub_broker, tmp_path, monkeypatch):
    """Scenario 1: actor returns; lifecycle_status `completed`.

    I-phase0-005: strengthened to assert the run row reaches `completed`
    in the run_store DB after broker drain.

    I-arch-001a (2026-05-12): mocks pipeline-A (run_one_query) to write
    a minimal valid manifest. Without the mock the actor would attempt
    a real pipeline-A invocation and hit retrieval / LLM dependencies.
    """
    import json

    broker, worker = stub_broker
    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "scenario_1.sqlite"))
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path / "v6_runs"))

    async def _fake_run_one_query(q, out_root):
        out_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "run_id": f"SWEEP_{q['domain']}_{q['slug']}_fixture",
            "status": "success",
            "cost_usd": 0.01,
        }
        (out_root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
        return {"manifest": manifest, "cost_usd": 0.01, "status": "success"}

    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query",
        _fake_run_one_query,
        raising=False,
    )

    from polaris_v6.queue import run_store
    from polaris_v6.queue.actors import enqueue_research_run

    run_store.insert_run("run_001", "clinical", "noop?")
    enqueue_research_run.send("run_001", {"template": "clinical", "question": "noop?", "document_ids": []})
    broker.join(enqueue_research_run.queue_name, timeout=10000)
    worker.join()

    record = run_store.get_run("run_001")
    assert record is not None
    assert record.lifecycle_status == "completed"
    assert record.pipeline_status == "success"
    assert record.status == "completed"  # computed_field backcompat alias


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
