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
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "jobs.sqlite")
    _set_job_queue_for_tests(queue)

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app), queue

    _set_job_queue_for_tests(None)
    _reset_runners_for_tests()


def test_enqueue_endpoint_creates_pending_job(client_with_isolated_queue) -> None:
    client, queue = client_with_isolated_queue
    resp = client.post(
        "/api/inspector/jobs",
        json={"template_id": "mock", "params": {"q": "tirzepatide"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "pending"
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
    client, _ = client_with_isolated_queue
    client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {"i": 1}})
    client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {"i": 2}})
    resp = client.get("/api/inspector/jobs")
    body = resp.json()
    assert body["count"] == 2
    assert "mock" in body["available_templates"]
    assert all(j["status"] == "pending" for j in body["jobs"])


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


def test_pause_endpoint_409_on_pending_job(client_with_isolated_queue) -> None:
    """Pausing a pending job is a state-conflict error."""
    client, _ = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    resp = client.post(f"/api/inspector/jobs/{job_id}/pause")
    assert resp.status_code == 409


def test_pause_endpoint_404_for_unknown(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.post("/api/inspector/jobs/does-not-exist/pause")
    assert resp.status_code == 404


def test_cancel_endpoint_works_on_pending(client_with_isolated_queue) -> None:
    client, queue = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    resp = client.post(f"/api/inspector/jobs/{job_id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


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
    client, queue = client_with_isolated_queue
    job_id = client.post("/api/inspector/jobs", json={"template_id": "mock", "params": {}}).json()["job_id"]
    # Without pausing first, resume must 409.
    resp = client.post(f"/api/inspector/jobs/{job_id}/resume")
    assert resp.status_code == 409
    # Now claim + pause + resume -> 200.
    queue.claim_pending()
    queue.request_pause(job_id)
    queue.mark_paused(job_id)
    resp = client.post(f"/api/inspector/jobs/{job_id}/resume")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_resume_endpoint_404_for_unknown(client_with_isolated_queue) -> None:
    client, _ = client_with_isolated_queue
    resp = client.post("/api/inspector/jobs/does-not-exist/resume")
    assert resp.status_code == 404
