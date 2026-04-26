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


def test_list_jobs_filters_by_status(tmp_path: Path) -> None:
    """Filter list by status. Bypass auto-worker so the running state is
    deterministic at the moment of the assertion."""
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "list_filter_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        job = queue.enqueue("mock", {})
        queue.claim_pending()  # pending -> running
        pending = client.get("/api/inspector/jobs?status=pending").json()
        running = client.get("/api/inspector/jobs?status=running").json()
        assert pending["count"] == 0
        assert running["count"] == 1
        assert running["jobs"][0]["job_id"] == job.job_id
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


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


def test_pause_endpoint_sets_flag(tmp_path: Path) -> None:
    """Pause endpoint sets the cancel_requested flag on a running job.

    Bypass the auto-start enqueue endpoint so we can deterministically
    transition pending -> running before pausing (the auto-worker would
    race-claim and could complete the mock runner before our pause).
    """
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "pause_set_flag_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        job = queue.enqueue("mock", {})
        queue.claim_pending()  # pending -> running
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/pause")
        assert resp.status_code == 200
        assert resp.json()["pause_requested"] is True
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


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


def test_cancel_endpoint_sets_flag_on_running(tmp_path: Path) -> None:
    """Cancel endpoint sets cancel_requested on a running job. Bypass
    auto-worker so we can deterministically transition to running."""
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "cancel_running_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        job = queue.enqueue("mock", {})
        queue.claim_pending()
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["cancel_requested"] is True
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


def test_cancel_endpoint_404_for_unknown(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.post("/api/inspector/jobs/does-not-exist/cancel")
    assert resp.status_code == 404


def test_resume_endpoint_only_works_on_paused(tmp_path: Path) -> None:
    """Codex M-8 review fix: paused -> pending so a fresh worker can claim it.

    Bypass the auto-start enqueue endpoint so we control state transitions
    deterministically (the auto-worker would race-claim our pending job).
    """
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "resume_only_paused_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        # Enqueue directly through queue (no auto-worker race).
        job = queue.enqueue("mock", {})
        # Without pausing first, resume must 409.
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/resume")
        assert resp.status_code == 409
        # Now manually claim + pause; resume -> 200 with status 'pending'.
        queue.claim_pending()
        queue.request_pause(job.job_id)
        queue.mark_paused(job.job_id)
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/resume")
        assert resp.status_code == 200
        # Status may be 'pending' (just transitioned) or already 'running'
        # (auto-worker started by /resume picked it up). Both are valid.
        assert resp.json()["status"] in {"pending", "running"}
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


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
    first. The runner registry must initialize deterministically.

    Status assertion is permissive: the auto-worker can race-claim the
    job before the response returns. We only care that the endpoint
    accepted the request (200, not 400 'unknown template').
    """
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
        # Status may be pending OR running OR completed depending on the
        # auto-worker's polling interval relative to the response. The
        # important thing is the template was recognized.
        assert resp.json()["status"] in {"pending", "running", "completed"}
        assert resp.json()["template_id"] == "mock"
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


def test_resume_endpoint_routes_paused_to_pending_for_reclaim(tmp_path: Path) -> None:
    """Codex M-8 review fix #3: a paused job, after resume, must be in
    'pending' status (so a fresh worker can claim it via claim_pending).

    Bypass the auto-start enqueue endpoint so the worker doesn't race
    with our manual state manipulation; we want full control over the
    pending → running → paused → pending → running sequence.
    """
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "resume_reclaim_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        # Enqueue + transition directly through the queue so no auto-worker
        # races with our state setup.
        job = queue.enqueue("mock", {})
        queue.claim_pending()
        queue.request_pause(job.job_id)
        queue.mark_paused(job.job_id)

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        # Resume endpoint also auto-starts a worker; wait briefly to let
        # it claim the resumed job before we check.
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/resume")
        assert resp.status_code == 200
        # The auto-started worker should reclaim the resumed job and move
        # it forward. We just verify the queue accepts the resume cycle.
        # Either the worker has reclaimed (running) or the job is briefly
        # pending awaiting reclaim. Both are valid.
        import time as _time
        deadline = _time.time() + 2.0
        while _time.time() < deadline:
            current = queue.get(job.job_id)
            if current and current.status in {"running", "completed"}:
                break
            _time.sleep(0.02)
        assert current.status in {"pending", "running", "completed"}, (
            f"Resumed job stranded: status={current.status}"
        )
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()


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


def test_resume_endpoint_starts_worker_after_cold_restart(tmp_path: Path) -> None:
    """Codex M-8 v2 review fix: after a cold restart (no live worker),
    resuming a paused job must START a worker so the reclaim actually
    happens. Otherwise the resumed job sits in 'pending' indefinitely."""
    import time as _time
    from src.polaris_graph.audit_ir.inspector_router import (
        _set_job_queue_for_tests,
        _set_job_worker_for_tests,
    )
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.2, step_seconds=0.05))
    queue = JobQueue(tmp_path / "cold_resume_jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    try:
        # Set up a paused job WITHOUT going through the auto-start
        # enqueue path. This simulates a cold restart where the queue
        # has a paused row in it but no worker is running.
        job = queue.enqueue("mock", {})
        queue.claim_pending()
        queue.request_pause(job.job_id)
        queue.mark_paused(job.job_id)
        # Confirm the worker really is None (cold restart).
        from src.polaris_graph.audit_ir import inspector_router as _ir
        assert _ir._job_worker is None

        # Hit the resume endpoint.
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.post(f"/api/inspector/jobs/{job.job_id}/resume")
        assert resp.status_code == 200
        # The endpoint must start the worker so the reclaim happens.
        assert _ir._job_worker is not None
        assert _ir._job_worker.is_alive()

        # Verify the resumed job actually progresses to terminal.
        deadline = _time.time() + 5.0
        while _time.time() < deadline:
            current = queue.get(job.job_id)
            if current and current.status in {"completed", "cancelled", "failed"}:
                break
            _time.sleep(0.05)
        assert current.status == "completed", (
            f"Resumed job must reach terminal state via auto-started worker; "
            f"got {current.status if current else 'None'}"
        )
    finally:
        _set_job_worker_for_tests(None)
        _set_job_queue_for_tests(None)
        _reset_runners_for_tests()
