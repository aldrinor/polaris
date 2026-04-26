"""JobRunner abstraction + MockJobRunner.

A JobRunner is a callable that executes a single job. It receives a
"control" object exposing pause-check + checkpoint persistence, so the
runner cooperatively yields when the queue requests pause or cancel.

Concrete runners:
  - MockJobRunner: sleeps + checkpoints periodically. Used by tests
    and Phase A demo to validate the queue/worker plumbing without
    burning a full V30 sweep.
  - V30JobRunner (M-9): wires the actual V30 Phase-2 sweep.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from src.polaris_graph.audit_ir.job_queue import Job, JobQueue, JobQueueError


class JobControl:
    """Cooperative-yield control surface passed to JobRunner.run().

    The runner must call `checkpoint(...)` periodically. checkpoint()
    persists progress to the queue AND raises a sentinel if pause/cancel
    was requested.
    """

    class Cancelled(Exception):
        """Raised inside runner code when cancel was requested."""

    class Paused(Exception):
        """Raised inside runner code when pause was requested."""

    def __init__(self, queue: JobQueue, job_id: str) -> None:
        self._queue = queue
        self._job_id = job_id

    def checkpoint(
        self,
        progress_pct: float,
        message: str = "",
        state: Mapping[str, Any] | None = None,
    ) -> None:
        """Persist progress and check for pause/cancel requests.

        Raises JobControl.Cancelled or JobControl.Paused if the queue
        signals either. The runner should let the exception propagate;
        the worker handler converts it to the right queue state.
        """
        # Persist first so we don't lose progress on cooperative-yield
        # exceptions.
        self._queue.record_progress(
            self._job_id,
            progress_pct=progress_pct,
            progress_message=message,
            checkpoint=state,
        )
        # Then check for control-flag requests.
        job = self._queue.get(self._job_id)
        if job is None:
            raise JobQueueError(f"checkpoint: job {self._job_id} disappeared")
        if job.cancel_requested:
            raise JobControl.Cancelled()
        if job.pause_requested:
            raise JobControl.Paused()


class JobRunner(ABC):
    """Pluggable executor for one job type."""

    template_id: str  # set by concrete subclasses

    @abstractmethod
    def run(self, job: Job, control: JobControl) -> str | None:
        """Execute the job. Return the artifact_dir path on success.

        Implementations should call control.checkpoint(...) at least once
        per significant step so pause/cancel requests are honored within
        a reasonable time bound.
        """


@dataclass
class MockJobRunner(JobRunner):
    """Test runner: sleeps total_seconds, checkpointing every step_seconds."""

    template_id: str = "mock"
    total_seconds: float = 5.0
    step_seconds: float = 0.5
    artifact_dir: str | None = None

    def run(self, job: Job, control: JobControl) -> str | None:
        steps = max(1, int(self.total_seconds / self.step_seconds))
        for i in range(steps):
            pct = (i + 1) / steps * 100.0
            control.checkpoint(
                progress_pct=pct,
                message=f"mock step {i + 1}/{steps}",
                state={"step": i + 1, "of": steps},
            )
            time.sleep(self.step_seconds)
        return self.artifact_dir


# Registry of runners, keyed by template_id. M-9 / M-10 register V30 + clinical
# templates here.
_RUNNERS: dict[str, JobRunner] = {}


def register_runner(runner: JobRunner) -> None:
    if not runner.template_id:
        raise ValueError("register_runner: runner.template_id required")
    _RUNNERS[runner.template_id] = runner


def get_runner(template_id: str) -> JobRunner | None:
    return _RUNNERS.get(template_id)


def list_runners() -> list[str]:
    return sorted(_RUNNERS.keys())


def _reset_runners_for_tests() -> None:
    _RUNNERS.clear()
