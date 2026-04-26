"""Tests for src/polaris_graph/audit_ir/job_worker.py + job_runner.py.

End-to-end: enqueue a job, let the worker drain it via the MockJobRunner,
then verify pause/cancel/resume mechanics.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from src.polaris_graph.audit_ir import (
    Job,
    JobControl,
    JobQueue,
    JobRunner,
    JobWorker,
    MockJobRunner,
    register_runner,
)
from src.polaris_graph.audit_ir.job_runner import _reset_runners_for_tests


@pytest.fixture(autouse=True)
def _clear_runners():
    """Each test gets a clean runner registry."""
    _reset_runners_for_tests()
    yield
    _reset_runners_for_tests()


@pytest.fixture
def queue(tmp_path: Path) -> JobQueue:
    return JobQueue(tmp_path / "jobs.sqlite")


# ---------------------------------------------------------------------------
# MockJobRunner
# ---------------------------------------------------------------------------


def test_mock_runner_completes_with_progress(queue: JobQueue) -> None:
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.4, step_seconds=0.1))
    queue.enqueue("mock", {})
    worker = JobWorker(queue, poll_interval_s=0.05)
    completed = worker.run_one()
    assert completed is not None
    assert completed.status == "completed"
    assert completed.progress_pct == 100.0


def test_run_one_returns_none_when_no_pending(queue: JobQueue) -> None:
    worker = JobWorker(queue, poll_interval_s=0.05)
    assert worker.run_one() is None


def test_unknown_template_marks_failed(queue: JobQueue) -> None:
    queue.enqueue("not_registered", {})
    worker = JobWorker(queue, poll_interval_s=0.05)
    failed = worker.run_one()
    assert failed is not None
    assert failed.status == "failed"
    assert "no runner" in (failed.error or "")


# ---------------------------------------------------------------------------
# Cooperative yield: pause + resume + cancel
# ---------------------------------------------------------------------------


class _SlowMockRunner(JobRunner):
    """Runner that takes long enough for an external thread to request pause."""

    template_id = "slow_mock"

    def __init__(self, total_seconds: float = 1.0, step_seconds: float = 0.05) -> None:
        self.total_seconds = total_seconds
        self.step_seconds = step_seconds

    def run(self, job: Job, control: JobControl) -> str | None:
        steps = max(1, int(self.total_seconds / self.step_seconds))
        for i in range(steps):
            pct = (i + 1) / steps * 100.0
            control.checkpoint(
                progress_pct=pct,
                message=f"step {i + 1}/{steps}",
                state={"step": i + 1},
            )
            time.sleep(self.step_seconds)
        return None


def test_pause_request_honored_at_checkpoint(queue: JobQueue) -> None:
    register_runner(_SlowMockRunner(total_seconds=2.0, step_seconds=0.05))
    job = queue.enqueue("slow_mock", {})

    # Start a worker thread; immediately request pause.
    worker = JobWorker(queue, poll_interval_s=0.02)
    worker.start()
    try:
        # Wait for the worker to claim the job (up to 1s).
        for _ in range(50):
            time.sleep(0.02)
            current = queue.get(job.job_id)
            if current and current.status == "running" and current.progress_pct > 0:
                break
        # Request pause and wait for the worker to honor it.
        queue.request_pause(job.job_id)
        for _ in range(100):
            time.sleep(0.02)
            current = queue.get(job.job_id)
            if current and current.status == "paused":
                break
        assert current.status == "paused", f"expected paused, got {current.status}"
        assert current.checkpoint is not None
        # Pause should fire BEFORE 100% progress (cooperative yield).
        assert current.progress_pct < 100.0
    finally:
        worker.stop(join_timeout=2.0)


def test_cancel_request_honored_at_checkpoint(queue: JobQueue) -> None:
    register_runner(_SlowMockRunner(total_seconds=2.0, step_seconds=0.05))
    job = queue.enqueue("slow_mock", {})

    worker = JobWorker(queue, poll_interval_s=0.02)
    worker.start()
    try:
        for _ in range(50):
            time.sleep(0.02)
            current = queue.get(job.job_id)
            if current and current.status == "running" and current.progress_pct > 0:
                break
        queue.request_cancel(job.job_id)
        for _ in range(100):
            time.sleep(0.02)
            current = queue.get(job.job_id)
            if current and current.status == "cancelled":
                break
        assert current.status == "cancelled", f"expected cancelled, got {current.status}"
        assert current.progress_pct < 100.0
    finally:
        worker.stop(join_timeout=2.0)


def test_resume_after_pause_completes(queue: JobQueue) -> None:
    register_runner(_SlowMockRunner(total_seconds=1.0, step_seconds=0.05))
    job = queue.enqueue("slow_mock", {})

    worker = JobWorker(queue, poll_interval_s=0.02)
    worker.start()
    try:
        # Wait for run + pause cycle.
        for _ in range(50):
            time.sleep(0.02)
            current = queue.get(job.job_id)
            if current and current.status == "running" and current.progress_pct > 0:
                break
        queue.request_pause(job.job_id)
        for _ in range(100):
            time.sleep(0.02)
            current = queue.get(job.job_id)
            if current and current.status == "paused":
                break
        assert current.status == "paused"
        # Resume by transitioning back to pending. Workers pick up pending
        # jobs; in a real Phase B build we'd have a dedicated re-queue
        # mechanism that resumes from checkpoint. For this smoke test we
        # just verify the queue exposes the resume-paused transition.
        resumed = queue.resume_paused(job.job_id)
        assert resumed.status == "running"
        # The original worker thread already exited the runner; the resume
        # transition is the API surface, not a re-entrant runner.
    finally:
        worker.stop(join_timeout=2.0)


# ---------------------------------------------------------------------------
# Worker lifecycle
# ---------------------------------------------------------------------------


def test_worker_start_stop(queue: JobQueue) -> None:
    worker = JobWorker(queue, poll_interval_s=0.05)
    worker.start()
    assert worker.is_alive()
    worker.stop(join_timeout=2.0)
    assert not worker.is_alive()


def test_worker_drains_pending_jobs(queue: JobQueue) -> None:
    register_runner(MockJobRunner(template_id="mock", total_seconds=0.1, step_seconds=0.05))
    jobs = [queue.enqueue("mock", {"i": i}) for i in range(3)]

    worker = JobWorker(queue, poll_interval_s=0.02)
    worker.start()
    try:
        # Wait up to 5s for all jobs to reach a terminal state.
        deadline = time.time() + 5.0
        while time.time() < deadline:
            statuses = [queue.get(j.job_id).status for j in jobs]
            if all(s in {"completed", "cancelled", "failed"} for s in statuses):
                break
            time.sleep(0.05)
    finally:
        worker.stop(join_timeout=2.0)

    final_statuses = [queue.get(j.job_id).status for j in jobs]
    assert all(s == "completed" for s in final_statuses)
