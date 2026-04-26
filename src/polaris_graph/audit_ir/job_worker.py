"""JobWorker: background thread that pulls pending jobs and runs them.

Per FINAL_PLAN.md: Phase B keeps a small in-process worker pool that
polls the JobQueue, claims jobs atomically, dispatches to the right
JobRunner, and converts cooperative-yield exceptions
(JobControl.Cancelled / JobControl.Paused) into queue state transitions.

Phase B starts with one worker thread; Phase C scales horizontally
once the worker pool talks to a shared SQLite/Postgres store.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from src.polaris_graph.audit_ir.job_queue import Job, JobQueue, JobQueueError
from src.polaris_graph.audit_ir.job_runner import JobControl, get_runner

logger = logging.getLogger(__name__)


class JobWorker:
    """Single-thread worker that drains the queue.

    Usage:
        worker = JobWorker(queue, poll_interval_s=1.0)
        worker.start()
        # ... later
        worker.stop()
    """

    def __init__(
        self,
        queue: JobQueue,
        poll_interval_s: float = 1.0,
        on_job_completed: Optional[callable] = None,
    ) -> None:
        self._queue = queue
        self._poll_interval = poll_interval_s
        self._on_job_completed = on_job_completed
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="polaris-job-worker")
        self._thread.start()

    def stop(self, join_timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=join_timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def run_one(self) -> Job | None:
        """Synchronous single-job drain. Used by tests."""
        job = self._queue.claim_pending()
        if job is None:
            return None
        return self._dispatch(job)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue.claim_pending()
            except JobQueueError as exc:
                logger.warning("worker: claim_pending failed: %s", exc)
                self._stop_event.wait(self._poll_interval)
                continue
            if job is None:
                # No work; sleep and poll again.
                self._stop_event.wait(self._poll_interval)
                continue
            try:
                self._dispatch(job)
            except Exception as exc:  # noqa: BLE001 — last-resort safety
                logger.exception("worker: unhandled exception on job %s: %s", job.job_id, exc)

    def _dispatch(self, job: Job) -> Job:
        runner = get_runner(job.template_id)
        if runner is None:
            return self._queue.mark_failed(
                job.job_id,
                error=f"no runner registered for template_id={job.template_id!r}",
            )
        control = JobControl(self._queue, job.job_id)
        try:
            artifact_dir = runner.run(job, control)
        except JobControl.Cancelled:
            logger.info("worker: job %s cancelled cooperatively", job.job_id)
            result = self._queue.mark_cancelled(job.job_id)
            if self._on_job_completed:
                self._on_job_completed(result)
            return result
        except JobControl.Paused:
            logger.info("worker: job %s paused cooperatively", job.job_id)
            return self._queue.mark_paused(job.job_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("worker: job %s failed: %s", job.job_id, exc)
            result = self._queue.mark_failed(
                job.job_id,
                error=f"{type(exc).__name__}: {exc}",
            )
            if self._on_job_completed:
                self._on_job_completed(result)
            return result
        result = self._queue.mark_completed(job.job_id, artifact_dir=artifact_dir)
        if self._on_job_completed:
            self._on_job_completed(result)
        return result
