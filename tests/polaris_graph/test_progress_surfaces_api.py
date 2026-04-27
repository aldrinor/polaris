"""Tests for M-13 SSE + snapshot HTTP endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.polaris_graph.audit_ir import (
    JobQueue,
    MockJobRunner,
    register_runner,
)
from src.polaris_graph.audit_ir.inspector_router import (
    _set_job_queue_for_tests,
    _set_job_worker_for_tests,
    router,
)
from src.polaris_graph.audit_ir.job_runner import _reset_runners_for_tests
from src.polaris_graph.audit_ir.progress_surfaces import (
    SurfaceKind,
    get_surface_bus,
)


@pytest.fixture
def client_and_queue(tmp_path: Path):
    _reset_runners_for_tests()
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.3, step_seconds=0.05))
    queue = JobQueue(tmp_path / "jobs.sqlite")
    _set_job_queue_for_tests(queue)
    _set_job_worker_for_tests(None)
    bus = get_surface_bus()
    bus.clear_for_tests()

    app = FastAPI()
    app.include_router(router)
    yield TestClient(app, headers={"X-Polaris-Caller": "org_default:usr_test:owner"}), queue
    bus.clear_for_tests()
    _set_job_worker_for_tests(None)
    _set_job_queue_for_tests(None)
    _reset_runners_for_tests()


# ---------------------------------------------------------------------------
# Snapshot endpoint
# ---------------------------------------------------------------------------


def test_surfaces_snapshot_returns_emitted_events(client_and_queue) -> None:
    client, queue = client_and_queue
    job = queue.enqueue("mock", {})
    bus = get_surface_bus()
    bus.emit(job.job_id, SurfaceKind.PREFLIGHT, {"slug": "demo"})
    bus.emit(job.job_id, SurfaceKind.TIER_MIX, {"t1": 5})

    resp = client.get(f"/api/inspector/jobs/{job.job_id}/surfaces")
    assert resp.status_code == 200
    body = resp.json()
    assert body["job_id"] == job.job_id
    kinds = [s["kind"] for s in body["surfaces"]]
    assert "preflight" in kinds
    assert "tier_mix" in kinds


def test_surfaces_snapshot_unknown_job_returns_404(client_and_queue) -> None:
    client, _ = client_and_queue
    resp = client.get("/api/inspector/jobs/job_nope/surfaces")
    assert resp.status_code == 404


def test_surfaces_snapshot_empty_when_nothing_emitted(client_and_queue) -> None:
    client, queue = client_and_queue
    job = queue.enqueue("mock", {})
    resp = client.get(f"/api/inspector/jobs/{job.job_id}/surfaces")
    body = resp.json()
    assert body["surfaces"] == []


# ---------------------------------------------------------------------------
# SSE stream endpoint
# ---------------------------------------------------------------------------


def test_sse_stream_unknown_job_returns_404(client_and_queue) -> None:
    client, _ = client_and_queue
    resp = client.get("/api/inspector/jobs/job_nope/stream")
    assert resp.status_code == 404


def test_sse_stream_replays_snapshot_then_terminates_on_prune(
    client_and_queue,
) -> None:
    """SSE flow:
      1. Subscribe
      2. Replay snapshot (PREFLIGHT + TIER_MIX events)
      3. Prune sends sentinel; stream emits 'event: end' and stops
    """
    client, queue = client_and_queue
    job = queue.enqueue("mock", {})
    bus = get_surface_bus()
    bus.emit(job.job_id, SurfaceKind.PREFLIGHT, {"slug": "demo"})
    bus.emit(job.job_id, SurfaceKind.TIER_MIX, {"t1": 5})

    # Schedule prune to happen shortly after the request starts so
    # the stream terminates naturally.
    import threading
    threading.Timer(0.2, bus.prune, args=(job.job_id,)).start()

    with client.stream(
        "GET", f"/api/inspector/jobs/{job.job_id}/stream"
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        body = b"".join(resp.iter_bytes()).decode("utf-8")

    # Snapshot replay surfaces appear as `data: {...}\n\n` lines.
    data_lines = [
        line for line in body.split("\n") if line.startswith("data: ")
    ]
    payloads = [json.loads(line[len("data: "):]) for line in data_lines]
    kinds = {p.get("kind") for p in payloads}
    # Both initial surfaces should be replayed.
    assert "preflight" in kinds
    assert "tier_mix" in kinds
    # Stream should end with the `event: end` sentinel.
    assert "event: end" in body


def test_sse_stream_after_prune_terminates_immediately(client_and_queue) -> None:
    """Codex M-13 v2 review regression: if the worker has already
    pruned the job_id, a new SSE subscriber must NOT hang on an
    empty queue. The stream should replay the (possibly empty)
    snapshot then emit `event: end` immediately.
    """
    client, queue = client_and_queue
    job = queue.enqueue("mock", {})
    bus = get_surface_bus()
    bus.emit(job.job_id, SurfaceKind.PREFLIGHT, {"slug": "demo"})
    # Worker prunes BEFORE any subscriber attaches.
    bus.prune(job.job_id)

    # The request must complete in well under a second.
    import time
    started = time.time()
    with client.stream(
        "GET", f"/api/inspector/jobs/{job.job_id}/stream"
    ) as resp:
        assert resp.status_code == 200
        body = b"".join(resp.iter_bytes()).decode("utf-8")
    elapsed = time.time() - started
    assert elapsed < 2.0, f"stream hung for {elapsed:.2f}s after prune"
    assert "event: end" in body
    # Post-prune snapshot is empty (prune cleared it), so no
    # data lines should appear.
    data_lines = [
        line for line in body.split("\n") if line.startswith("data: ")
    ]
    # The only `data:` should be the empty payload accompanying
    # `event: end`. Any pre-prune surface has been cleared.
    for line in data_lines:
        payload = json.loads(line[len("data: "):])
        assert payload == {} or payload.get("kind") is None, (
            f"unexpected data payload after prune: {payload}"
        )


def test_sse_stream_no_duplicate_events_in_subscribe_snapshot_race(
    client_and_queue,
) -> None:
    """Codex M-13 v2 review regression: subscribe_with_snapshot()
    must capture snapshot atomically with subscriber registration
    so events emitted between the two don't appear twice."""
    client, queue = client_and_queue
    job = queue.enqueue("mock", {})
    bus = get_surface_bus()
    # Pre-existing snapshot.
    bus.emit(job.job_id, SurfaceKind.PREFLIGHT, {"slug": "demo"})

    # Schedule a new emission to land mid-request, then prune.
    import threading

    def emit_then_prune():
        # Small delay so the request is past subscribe but still
        # waiting on the queue.
        bus.emit(job.job_id, SurfaceKind.TIER_MIX, {"t1": 5})
        bus.prune(job.job_id)

    threading.Timer(0.1, emit_then_prune).start()

    with client.stream(
        "GET", f"/api/inspector/jobs/{job.job_id}/stream"
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode("utf-8")

    data_lines = [
        line for line in body.split("\n") if line.startswith("data: ")
    ]
    payloads = [json.loads(line[len("data: "):]) for line in data_lines]
    # Each kind must appear exactly once.
    kinds_count: dict[str, int] = {}
    for p in payloads:
        k = p.get("kind")
        if k:
            kinds_count[k] = kinds_count.get(k, 0) + 1
    for k, count in kinds_count.items():
        assert count == 1, f"surface kind {k!r} delivered {count}× (expected 1)"


def test_sse_stream_emits_subsequent_events(client_and_queue) -> None:
    """Subscribe-then-emit: events that land AFTER subscribe should
    flow to the SSE consumer."""
    client, queue = client_and_queue
    job = queue.enqueue("mock", {})
    bus = get_surface_bus()
    # No pre-subscribe emissions.

    import threading
    def emit_then_prune():
        bus.emit(job.job_id, SurfaceKind.PARSE_PROGRESS, {"docs_done": 1})
        bus.emit(job.job_id, SurfaceKind.FRAME_COVERAGE, {"covered": 3})
        bus.prune(job.job_id)

    threading.Timer(0.2, emit_then_prune).start()

    with client.stream(
        "GET", f"/api/inspector/jobs/{job.job_id}/stream"
    ) as resp:
        body = b"".join(resp.iter_bytes()).decode("utf-8")

    data_lines = [
        line for line in body.split("\n") if line.startswith("data: ")
    ]
    payloads = [json.loads(line[len("data: "):]) for line in data_lines]
    kinds = [p.get("kind") for p in payloads]
    assert "parse_progress" in kinds
    assert "frame_coverage" in kinds
