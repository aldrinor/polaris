"""Tests for src/polaris_graph/audit_ir/job_queue.py.

Phase B M-8 foundation: durable JobQueue with status state machine,
pause/cancel/resume mechanics, and SQLite persistence across reopens.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir import (
    ALLOWED_TRANSITIONS,
    JOB_STATUSES,
    TERMINAL_STATUSES,
    Job,
    JobQueue,
    JobQueueError,
    job_to_dict,
)


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "jobs.sqlite")


# ---------------------------------------------------------------------------
# Schema + persistence
# ---------------------------------------------------------------------------


def test_queue_creates_db_if_missing(tmp_path: Path) -> None:
    db = tmp_path / "deep" / "nested" / "jobs.sqlite"
    assert not db.exists()
    JobQueue(db)
    assert db.exists()


def test_enqueue_persists_across_reopen(tmp_path: Path) -> None:
    db = tmp_path / "jobs.sqlite"
    q1 = JobQueue(db)
    job = q1.enqueue("mock", {"foo": "bar"})

    q2 = JobQueue(db)
    rehydrated = q2.get(job.job_id)
    assert rehydrated is not None
    assert rehydrated.job_id == job.job_id
    assert rehydrated.status == "pending"
    assert rehydrated.params == {"foo": "bar"}


# ---------------------------------------------------------------------------
# Enqueue + read
# ---------------------------------------------------------------------------


def test_enqueue_returns_pending_job(queue: JobQueue) -> None:
    job = queue.enqueue("mock", {"q": "tirzepatide"})
    assert isinstance(job, Job)
    assert job.status == "pending"
    assert job.template_id == "mock"
    assert job.params == {"q": "tirzepatide"}
    assert job.created_at > 0
    assert job.started_at is None
    assert job.cancel_requested is False
    assert job.pause_requested is False
    assert job.progress_pct == 0.0


def test_enqueue_rejects_empty_template(queue: JobQueue) -> None:
    with pytest.raises(JobQueueError, match="template_id required"):
        queue.enqueue("", {})


def test_enqueue_rejects_non_mapping_params(queue: JobQueue) -> None:
    with pytest.raises(JobQueueError, match="must be a Mapping"):
        queue.enqueue("mock", ["not", "a", "mapping"])  # type: ignore[arg-type]


def test_get_returns_none_for_unknown(queue: JobQueue) -> None:
    assert queue.get("does-not-exist") is None


def test_list_by_status_filters(queue: JobQueue) -> None:
    a = queue.enqueue("mock", {})
    b = queue.enqueue("mock", {})
    queue.claim_pending()  # claim one
    pending = queue.list_by_status("pending")
    running = queue.list_by_status("running")
    assert len(pending) == 1
    assert len(running) == 1
    assert {j.job_id for j in pending} | {j.job_id for j in running} == {a.job_id, b.job_id}


def test_list_by_status_rejects_unknown(queue: JobQueue) -> None:
    with pytest.raises(JobQueueError, match="unknown status"):
        queue.list_by_status("not-a-status")


# ---------------------------------------------------------------------------
# claim_pending atomicity
# ---------------------------------------------------------------------------


def test_claim_pending_returns_running_job(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    assert job is not None
    assert job.status == "running"
    assert job.started_at is not None


def test_claim_pending_returns_none_when_empty(queue: JobQueue) -> None:
    assert queue.claim_pending() is None


def test_claim_pending_is_atomic_under_concurrency(queue: JobQueue) -> None:
    """Multiple threads racing to claim the same job get exactly one winner."""
    queue.enqueue("mock", {})
    results: list[Job | None] = []
    lock = threading.Lock()

    def worker():
        result = queue.claim_pending()
        with lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    claimed = [r for r in results if r is not None]
    assert len(claimed) == 1
    assert all(r.status == "running" for r in claimed)


# ---------------------------------------------------------------------------
# Pause / cancel / resume
# ---------------------------------------------------------------------------


def test_request_pause_only_works_on_running_jobs(queue: JobQueue) -> None:
    job = queue.enqueue("mock", {})
    with pytest.raises(JobQueueError, match="cannot be paused"):
        queue.request_pause(job.job_id)


def test_request_pause_sets_flag(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    paused = queue.request_pause(job.job_id)
    assert paused.pause_requested is True
    assert paused.status == "running"  # worker hasn't honored yet


def test_mark_paused_after_request(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    queue.request_pause(job.job_id)
    paused = queue.mark_paused(job.job_id)
    assert paused.status == "paused"
    assert paused.paused_at is not None
    assert paused.pause_requested is False  # cleared on transition


def test_resume_paused_transitions_to_running(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    queue.request_pause(job.job_id)
    queue.mark_paused(job.job_id)
    resumed = queue.resume_paused(job.job_id)
    assert resumed.status == "running"
    assert resumed.paused_at is None


def test_resume_paused_rejects_non_paused(queue: JobQueue) -> None:
    job = queue.enqueue("mock", {})
    with pytest.raises(JobQueueError, match="is not paused"):
        queue.resume_paused(job.job_id)


def test_request_cancel_on_pending_immediately_cancels(queue: JobQueue) -> None:
    job = queue.enqueue("mock", {})
    cancelled = queue.request_cancel(job.job_id)
    assert cancelled.status == "cancelled"
    assert cancelled.cancel_requested is True
    assert cancelled.completed_at is not None


def test_request_cancel_on_running_sets_flag(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    cancelled = queue.request_cancel(job.job_id)
    assert cancelled.status == "running"  # worker hasn't honored yet
    assert cancelled.cancel_requested is True


def test_request_cancel_on_paused_sets_flag(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    queue.request_pause(job.job_id)
    queue.mark_paused(job.job_id)
    cancelled = queue.request_cancel(job.job_id)
    assert cancelled.status == "paused"
    assert cancelled.cancel_requested is True


def test_request_cancel_on_terminal_raises(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    queue.mark_completed(job.job_id)
    with pytest.raises(JobQueueError, match="cannot be cancelled"):
        queue.request_cancel(job.job_id)


# ---------------------------------------------------------------------------
# Terminal transitions
# ---------------------------------------------------------------------------


def test_mark_completed_only_from_running(queue: JobQueue) -> None:
    job = queue.enqueue("mock", {})
    with pytest.raises(JobQueueError, match="not running"):
        queue.mark_completed(job.job_id)
    queue.claim_pending()
    completed = queue.mark_completed(job.job_id, artifact_dir="/tmp/x")
    assert completed.status == "completed"
    assert completed.artifact_dir == "/tmp/x"
    assert completed.progress_pct == 100.0
    assert completed.completed_at is not None


def test_mark_failed_records_error(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    failed = queue.mark_failed(job.job_id, error="boom")
    assert failed.status == "failed"
    assert failed.error == "boom"


def test_mark_cancelled_after_request(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    queue.request_cancel(job.job_id)
    cancelled = queue.mark_cancelled(job.job_id)
    assert cancelled.status == "cancelled"


# ---------------------------------------------------------------------------
# Progress + checkpoint
# ---------------------------------------------------------------------------


def test_record_progress_persists_checkpoint(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    updated = queue.record_progress(
        job.job_id,
        progress_pct=42.5,
        progress_message="halfway",
        checkpoint={"step": 5, "of": 10},
    )
    assert updated.progress_pct == 42.5
    assert updated.progress_message == "halfway"
    assert updated.checkpoint == {"step": 5, "of": 10}


def test_record_progress_rejects_out_of_range(queue: JobQueue) -> None:
    queue.enqueue("mock", {})
    job = queue.claim_pending()
    with pytest.raises(JobQueueError, match="out of"):
        queue.record_progress(job.job_id, progress_pct=150.0)
    with pytest.raises(JobQueueError, match="out of"):
        queue.record_progress(job.job_id, progress_pct=-1.0)


def test_record_progress_rejects_non_running(queue: JobQueue) -> None:
    job = queue.enqueue("mock", {})
    with pytest.raises(JobQueueError, match="not running"):
        queue.record_progress(job.job_id, progress_pct=10.0)


# ---------------------------------------------------------------------------
# State machine constants + serialization
# ---------------------------------------------------------------------------


def test_status_constants() -> None:
    assert "pending" in JOB_STATUSES
    assert "running" in JOB_STATUSES
    assert "paused" in JOB_STATUSES
    assert TERMINAL_STATUSES == frozenset({"completed", "cancelled", "failed"})


def test_allowed_transitions_define_terminals() -> None:
    for terminal in TERMINAL_STATUSES:
        assert ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_job_to_dict_round_trips_through_json(queue: JobQueue) -> None:
    job = queue.enqueue("mock", {"q": "tirzepatide"})
    d = job_to_dict(job)
    payload = json.dumps(d)
    restored = json.loads(payload)
    assert restored["job_id"] == job.job_id
    assert restored["status"] == "pending"
    assert restored["params"] == {"q": "tirzepatide"}
    assert restored["pause_requested"] is False
