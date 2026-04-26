"""Tests for the M-8 job lifecycle endpoints in inspector_router.py."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir import JobQueue, MockJobRunner, register_runner
from src.polaris_graph.audit_ir.inspector_router import (
    _set_job_queue_for_tests,
    router,
)
from src.polaris_graph.audit_ir.job_runner import _reset_runners_for_tests


@pytest.fixture
def client_with_isolated_queue(tmp_path: Path):
    """Each test gets a fresh queue + clean runner registry."""
    from src.polaris_graph.audit_ir.inspector_router import _set_job_worker_for_tests
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "jobs.sqlite")
    _set_job_queue_for_tests(queue)
    # Disable the worker for these tests so we control state transitions
    # explicitly (the cold-start test below explicitly verifies worker
    # auto-start).
    _set_job_worker_for_tests(None)

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app), queue

    _set_job_worker_for_tests(None)
    _set_job_queue_for_tests(None)
    _reset_runners_for_tests()


def test_enqueue_endpoint_creates_job(client_with_isolated_queue) -> None:
    """The enqueue endpoint persists the job and returns its initial state.
    Status may be 'pending' or already 'running' — auto-started worker
    races with the response. We only assert the job was created with the
    right template_id + params."""
    client, queue = client_with_isolated_queue
    resp = client.post(
        "/api/inspector/jobs",
        json={"template_id": "mock", "params": {"q": "tirzepatide"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"pending", "running"}
    assert body["template_id"] == "mock"
    assert body["params"] == {"q": "tirzepatide"}
    # Verify it persisted in the queue
    assert queue.get(body["job_id"]) is not None


def test_enqueue_rejects_unknown_template(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.post(
        "/api/inspector/jobs",
        json={"template_id": "not_registered", "params": {}},
    )
    assert resp.status_code == 400
    assert "Unknown template_id" in resp.json()["detail"]


def test_list_jobs_returns_recent_jobs(client_with_isolated_queue) -> None:
    """Two enqueued jobs appear in the list. Auto-started worker may have
    transitioned them already; we just assert count + templates here."""
    client, _ = client_with_isolated_queue
    client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {"i": 1}})
    client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {"i": 2}})
    resp = client.get("/api/inspector/jobs")
    body = resp.json()
    assert body["count"] == 2
    assert "mock" in body["available_templates"]
    # Status may be any non-error state; the auto-started worker can race.
    valid_statuses = {"pending", "running", "completed"}
    assert all(j["status"] in valid_statuses for j in body["jobs"])


def test_list_jobs_filters_by_status(client_with_isolated_queue) -> None:
    client, queue = client_with_isolated_queue
    job_resp = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}})
    job_id = job_resp.json()["job_id"]
    queue.claim_pending()  # transition to running
    pending = client.get("/api/inspector/jobs?status=pending").json()
    running = client.get("/api/inspector/jobs?status=running").json()
    assert pending["count"] == 0
    assert running["count"] == 1
    assert running["jobs"][0]["job_id"] == job_id


def test_list_jobs_rejects_unknown_status(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.get("/api/inspector/jobs?status=not-a-status")
    assert resp.status_code == 400


def test_get_job_returns_404_for_unknown(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.get("/api/inspector/jobs/does-not-exist")
    assert resp.status_code == 404


def test_get_job_returns_full_payload(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    job_id = client.post(
        "/api/inspector/jobs", json={"template_id": "mock", "params": {"q": "test"}}
    ).json()["job_id"]
    resp = client.get(f"/api/inspector/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == job_id
    assert body["params"] == {"q": "test"}


def test_pause_endpoint_sets_flag(client_with_isolated_queue) -> None:
    client, queue = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    queue.claim_pending()
    resp = client.post(f"/api/inspector/jobs/{job_id}/pause")
    assert resp.status_code == 200
    assert resp.json()["pause_requested"] is True


def test_pause_endpoint_409_on_pending_job(tmp_path: Path) -> None:
    """Pausing a pending job is a state-conflict error.

    We bypass the auto-start worker so the job stays pending long enough
    for the assertion."""
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "pause_pending_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        # Enqueue directly so no auto-worker fires.
        job = queue.enqueue("mock", {})
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/pause")
        assert resp.status_code == 409
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


def test_pause_endpoint_404_for_unknown(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.post("/api/inspector/jobs/does-not-exist/pause")
    assert resp.status_code == 404


def test_cancel_endpoint_terminates_pending_job(tmp_path: Path) -> None:
    """Cancelling a pending job terminates it directly (no live worker
    needed). We use an isolated client without an auto-started worker
    so we can guarantee the job is still pending when we cancel."""
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "cancel_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        # Enqueue directly through the queue (skips the auto-start worker
        # that the enqueue endpoint would trigger).
        job = queue.enqueue("mock", {})
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


def test_cancel_endpoint_sets_flag_on_running(client_with_isolated_queue) -> None:
    client, queue = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    queue.claim_pending()
    resp = client.post(f"/api/inspector/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["cancel_requested"] is True


def test_cancel_endpoint_404_for_unknown(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.post("/api/inspector/jobs/does-not-exist/cancel")
    assert resp.status_code == 404


def test_resume_endpoint_only_works_on_paused(client_with_isolated_queue) -> None:
    """Codex M-8 review fix: paused -> pending so a fresh worker can claim it."""
    client, queue = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    # Without pausing first, resume must 409.
    resp = client.post(f"/api/inspector/jobs/{job_id}/resume")
    assert resp.status_code == 409
    # Now claim + pause + resume -> 200, and status is 'pending' (not 'running').
    queue.claim_pending()
    queue.request_pause(job_id)
    queue.mark_paused(job_id)
    resp = client.post(f"/api/inspector/jobs/{job_id}/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_resume_endpoint_404_for_unknown(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.post("/api/inspector/jobs/does-not-exist/resume")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Codex M-8 review fixes: cold-start runner registration + worker auto-start
# ---------------------------------------------------------------------------


def test_enqueue_works_on_cold_start_with_no_prior_route_hit(tmp_path: Path) -> None:
    """Codex M-8 review fix #1: cold-start `POST /api/inspector/jobs` must
    accept the `mock` template even if no other endpoint has been called
    first. The runner registry must initialize deterministically."""
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    # Wipe all module-level state, then immediately POST a job.
    _reset_runners_for_tests()
    queue = JobQueue(tmp_path / "cold_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        # First call into the router after a fresh process boot.
        resp = client.post(
            "/api/inspector/jobs",
            json={"template_id": "mock", "params": {"q": "cold"}},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "pending"
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


def test_enqueue_starts_worker_so_jobs_actually_run(tmp_path: Path) -> None:
    """Codex M-8 review fix #2: the router must auto-start a JobWorker so
    enqueued jobs progress to terminal state. Otherwise jobs sit pending
    forever in the live app path."""
    import time as _time
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.2, step_seconds=0.05))
    queue = JobQueue(tmp_path / "auto_worker_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)  # guarantee no worker before the request
    try:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}})
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
        # Wait for the auto-started worker to drain the job.
        deadline = _time.time() + 5.0
        while _time.time() < deadline:
            current = queue.get(job_id)
            if current and current.status in {"completed", "cancelled", "failed"}:
                break
            _time.sleep(0.05)
        assert current.status == "completed", (
            f"Expected job to reach 'completed' via auto-started worker, "
            f"got {current.status if current else 'None'}"
        )
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


def test_resume_endpoint_routes_paused_to_pending_for_reclaim(client_with_isolated_queue) -> None:
    """Codex M-8 review fix #3: a paused job, after resume, must be in
    'pending' status (so a fresh worker can claim it via claim_pending)."""
    client, queue = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    queue.claim_pending()
    queue.request_pause(job_id)
    queue.mark_paused(job_id)

    client.post(f"/api/inspector/jobs/{job_id}/resume")
    # The resumed job must be reclaimable
    reclaimed = queue.claim_pending()
    assert reclaimed is not None
    assert reclaimed.job_id == job_id
    assert reclaimed.status == "running"


def test_cancel_paused_job_via_endpoint_terminates_directly(client_with_isolated_queue) -> None:
    """Codex M-8 review fix #4: cancelling a paused job (no live worker) must
    transition directly to 'cancelled', not just set a flag."""
    client, queue = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    queue.claim_pending()
    queue.request_pause(job_id)
    queue.mark_paused(job_id)
    resp = client.post(f"/api/inspector/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"
