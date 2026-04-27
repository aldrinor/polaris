"""Durable SQLite-backed job queue for Phase B.

Per FINAL_PLAN.md (jointly Codex+Claude GREEN): Phase B requires queue-
backed concurrency + pause/cancel/resume mid-run. This module is the
foundation — Phase A's `PipelineRunner` single-concurrency lock is
replaced with this queue, and the Inspector router exposes
job lifecycle endpoints.

Status state machine:
    pending → running → completed
                     → cancelled
                     → failed
                     → paused → running → completed / cancelled / failed

Design constraints:
- SQLite stdlib only (no Redis dep yet — Phase C may upgrade)
- All ops thread-safe via per-call connection + WAL mode
- Pause/cancel are REQUEST flags that workers check at checkpoint
  boundaries (workers cooperatively yield; no signal/kill semantics)
- Checkpoints are JSON blobs — workers serialize their internal state
  so restart-after-crash + resume-after-pause use the same code path

Codex M-8 design choices (anticipating review):
- run_id (UUID4) is the canonical identifier; slug-style identifiers
  belong in the registry, not the queue
- claim_pending() is the worker pull primitive; uses SQLite's
  atomic UPDATE-WHERE-status='pending' to prevent two workers
  picking the same job
- All timestamps are float Unix epoch seconds (UTC)
- All status transitions are explicit; the queue refuses invalid
  ones to fail loud rather than silently corrupt state
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping

# All valid job statuses, in canonical order.
JOB_STATUSES = (
    "pending",
    "running",
    "paused",
    "completed",
    "cancelled",
    "failed",
)
TERMINAL_STATUSES = frozenset({"completed", "cancelled", "failed"})

# Canonical state-transition graph. Other transitions raise.
#
# Codex M-8 review fix: paused -> running is NOT a real edge under the
# current "no worker heartbeat" design. After JobControl.Paused exits
# runner.run(), the worker thread returns and no live executor is
# attached to the paused row. Resume therefore goes paused -> pending
# so a fresh worker can claim it via claim_pending() and re-enter
# runner.run(job, control) with job.checkpoint providing the resume
# state. This also makes paused -> cancelled direct (paused jobs are
# quiescent, so no need to ask a non-existent worker to honor a flag).
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "cancelled"}),
    "running": frozenset({"paused", "completed", "cancelled", "failed"}),
    "paused": frozenset({"pending", "cancelled"}),
    "completed": frozenset(),  # terminal
    "cancelled": frozenset(),
    "failed": frozenset(),
}


class JobQueueError(RuntimeError):
    """Raised on queue-level errors (invalid transitions, schema issues)."""


@dataclass(frozen=True)
class Job:
    """An immutable snapshot of a job at read time.

    Mutations happen through JobQueue methods, which return new snapshots.

    Codex M-15b review fix: `org_id` and `workspace_id` added so
    job lookups can gate on org membership. Pre-M-15b jobs default
    to `org_default` / None, making the M-15b authz dependency
    treat them as the notional system org.
    """

    job_id: str
    template_id: str
    params: Mapping[str, Any]
    status: str
    created_at: float
    started_at: float | None
    paused_at: float | None
    completed_at: float | None
    pause_requested: bool
    cancel_requested: bool
    progress_pct: float
    progress_message: str
    checkpoint: Mapping[str, Any] | None
    artifact_dir: str | None
    error: str | None
    org_id: str = "org_default"
    workspace_id: str | None = None


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    params_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL,
    started_at REAL,
    paused_at REAL,
    completed_at REAL,
    pause_requested INTEGER NOT NULL DEFAULT 0,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    progress_pct REAL NOT NULL DEFAULT 0,
    progress_message TEXT NOT NULL DEFAULT '',
    checkpoint_json TEXT,
    artifact_dir TEXT,
    error TEXT,
    org_id TEXT NOT NULL DEFAULT 'org_default',
    workspace_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs (status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_org ON jobs (org_id);
"""


def _row_to_job(row: sqlite3.Row) -> Job:
    # Codex M-15b: tolerant column read so older DBs that ran the
    # migration still work even if a row materialized before the
    # ALTER picked up.
    org_id = "org_default"
    workspace_id = None
    try:
        org_id = row["org_id"] or "org_default"
    except (IndexError, KeyError):
        pass
    try:
        workspace_id = row["workspace_id"]
    except (IndexError, KeyError):
        pass
    return Job(
        job_id=row["job_id"],
        template_id=row["template_id"],
        params=json.loads(row["params_json"]),
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        paused_at=row["paused_at"],
        completed_at=row["completed_at"],
        pause_requested=bool(row["pause_requested"]),
        cancel_requested=bool(row["cancel_requested"]),
        progress_pct=row["progress_pct"],
        progress_message=row["progress_message"],
        checkpoint=(json.loads(row["checkpoint_json"]) if row["checkpoint_json"] else None),
        artifact_dir=row["artifact_dir"],
        error=row["error"],
        org_id=org_id,
        workspace_id=workspace_id,
    )


class JobQueue:
    """Durable SQLite-backed queue. Thread-safe via per-call connections + WAL."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_lock = threading.Lock()
        self._initialized = False
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._init_lock:
            if self._initialized:
                return
            with self._connect() as conn:
                conn.executescript("PRAGMA journal_mode=WAL;")
                conn.executescript(_SCHEMA_SQL)
                # Codex M-15b review fix: migration for pre-M-15b
                # databases. CREATE TABLE IF NOT EXISTS is a no-op
                # when the table exists, so old DBs need ALTER.
                cols = [
                    r[1] for r in conn.execute(
                        "PRAGMA table_info(jobs)"
                    ).fetchall()
                ]
                if "org_id" not in cols:
                    conn.execute(
                        "ALTER TABLE jobs ADD COLUMN org_id TEXT NOT NULL "
                        "DEFAULT 'org_default'"
                    )
                if "workspace_id" not in cols:
                    conn.execute(
                        "ALTER TABLE jobs ADD COLUMN workspace_id TEXT"
                    )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_jobs_org ON jobs(org_id)"
                )
            self._initialized = True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path, timeout=10.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def enqueue(
        self,
        template_id: str,
        params: Mapping[str, Any],
        org_id: str = "org_default",
        workspace_id: str | None = None,
    ) -> Job:
        """Create a new pending job. Returns the persisted Job.

        Codex M-15b review fix: `org_id` and `workspace_id` are
        now parameters. Pre-M-15b callers without auth context
        default to `org_default` / None — the M-15b retrofit
        treats those as the notional system org so cross-org
        gates still apply consistently.
        """
        if not template_id:
            raise JobQueueError("enqueue: template_id required")
        if not isinstance(params, Mapping):
            raise JobQueueError("enqueue: params must be a Mapping")
        if not org_id or not org_id.strip():
            raise JobQueueError("enqueue: org_id must be non-empty")
        job_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO jobs (job_id, template_id, params_json, "
                "status, created_at, org_id, workspace_id) "
                "VALUES (?, ?, ?, 'pending', ?, ?, ?)",
                (job_id, template_id, json.dumps(dict(params)), now,
                 org_id.strip(), workspace_id),
            )
        return self._must_get(job_id)

    def list_by_org(
        self,
        org_id: str,
        status: str | None = None,
        limit: int = 100,
    ) -> list[Job]:
        """Codex M-15b review fix: org-scoped listing. Plain
        list_by_status is now used only for platform-admin code
        paths."""
        with self._connect() as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE org_id = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (org_id, limit),
                ).fetchall()
            else:
                if status not in JOB_STATUSES:
                    raise JobQueueError(
                        f"list_by_org: unknown status {status!r}"
                    )
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE org_id = ? AND status = ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (org_id, status, limit),
                ).fetchall()
        return [_row_to_job(r) for r in rows]

    def get(self, job_id: str) -> Job | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
            ).fetchone()
        return _row_to_job(row) if row is not None else None

    def list_by_status(self, status: str | None = None, limit: int = 100) -> list[Job]:
        with self._connect() as conn:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                if status not in JOB_STATUSES:
                    raise JobQueueError(f"list_by_status: unknown status {status!r}")
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
        return [_row_to_job(r) for r in rows]

    def claim_pending(self) -> Job | None:
        """Atomically claim a pending job for a worker. Returns None if none.

        Implementation: UPDATE WHERE status='pending' is atomic in SQLite;
        we use last_insert_rowid trick is not portable, so we use:
        - SELECT job_id WHERE status='pending' ORDER BY created_at LIMIT 1
        - UPDATE WHERE job_id=? AND status='pending' SET status='running'
        - check changes() == 1
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT job_id FROM jobs WHERE status='pending' "
                "ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            now = time.time()
            cursor = conn.execute(
                "UPDATE jobs SET status='running', started_at=? "
                "WHERE job_id=? AND status='pending'",
                (now, row["job_id"]),
            )
            if cursor.rowcount != 1:
                # Another worker grabbed it. Caller should retry.
                return None
        return self._must_get(row["job_id"])

    def request_pause(self, job_id: str) -> Job:
        """Set the pause_requested flag. Worker will pause at next checkpoint."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET pause_requested=1 "
                "WHERE job_id=? AND status='running'",
                (job_id,),
            )
            if cursor.rowcount == 0:
                # Either job doesn't exist or isn't running; surface clearly.
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"request_pause: unknown job {job_id}")
                raise JobQueueError(
                    f"request_pause: job {job_id} status={job.status} cannot be paused"
                )
        return self._must_get(job_id)

    def request_cancel(self, job_id: str) -> Job:
        """Cancel a job.

        Codex M-8 review fix: pending and paused jobs are quiescent (no
        live worker), so we transition them directly to 'cancelled'.
        Running jobs get the cancel_requested flag and the worker
        cooperatively yields at the next checkpoint.
        """
        with self._connect() as conn:
            now = time.time()
            # Pending or paused -> directly mark cancelled (no live worker).
            cursor = conn.execute(
                "UPDATE jobs SET status='cancelled', cancel_requested=1, completed_at=? "
                "WHERE job_id=? AND status IN ('pending', 'paused')",
                (now, job_id),
            )
            if cursor.rowcount == 1:
                return self._must_get(job_id)
            # Running -> set the flag; worker yields at next checkpoint.
            cursor = conn.execute(
                "UPDATE jobs SET cancel_requested=1 "
                "WHERE job_id=? AND status='running'",
                (job_id,),
            )
            if cursor.rowcount == 0:
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"request_cancel: unknown job {job_id}")
                raise JobQueueError(
                    f"request_cancel: job {job_id} status={job.status} cannot be cancelled"
                )
        return self._must_get(job_id)

    def resume_paused(self, job_id: str) -> Job:
        """Transition paused -> pending so a fresh worker can claim it.

        Codex M-8 review fix: under the cooperative-yield design, the
        original worker exited runner.run() when Paused fired. To resume,
        we put the job back in the pending queue with the checkpoint
        intact; claim_pending() will pick it up and the runner re-enters
        from job.checkpoint.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status='pending', pause_requested=0, paused_at=NULL "
                "WHERE job_id=? AND status='paused'",
                (job_id,),
            )
            if cursor.rowcount == 0:
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"resume_paused: unknown job {job_id}")
                raise JobQueueError(
                    f"resume_paused: job {job_id} status={job.status} is not paused"
                )
        return self._must_get(job_id)

    def mark_paused(self, job_id: str) -> Job:
        """Worker calls this when it hits a checkpoint after pause was requested."""
        self._transition(job_id, "running", "paused", paused_at=time.time(),
                         pause_requested=0)
        return self._must_get(job_id)

    def mark_completed(self, job_id: str, artifact_dir: str | None = None) -> Job:
        with self._connect() as conn:
            now = time.time()
            cursor = conn.execute(
                "UPDATE jobs SET status='completed', completed_at=?, artifact_dir=?, "
                "progress_pct=100.0, progress_message='completed' "
                "WHERE job_id=? AND status='running'",
                (now, artifact_dir, job_id),
            )
            if cursor.rowcount == 0:
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"mark_completed: unknown job {job_id}")
                raise JobQueueError(
                    f"mark_completed: job {job_id} status={job.status} not running"
                )
        return self._must_get(job_id)

    def mark_cancelled(self, job_id: str) -> Job:
        """Worker calls this after honoring a cancel request mid-run.

        Pending/paused jobs are cancelled atomically via request_cancel()
        (no live worker needed). This path only fires when a worker
        catches JobControl.Cancelled mid-run.
        """
        with self._connect() as conn:
            now = time.time()
            cursor = conn.execute(
                "UPDATE jobs SET status='cancelled', completed_at=? "
                "WHERE job_id=? AND status='running'",
                (now, job_id),
            )
            if cursor.rowcount == 0:
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"mark_cancelled: unknown job {job_id}")
                raise JobQueueError(
                    f"mark_cancelled: job {job_id} status={job.status} not running"
                )
        return self._must_get(job_id)

    def mark_failed(self, job_id: str, error: str) -> Job:
        with self._connect() as conn:
            now = time.time()
            cursor = conn.execute(
                "UPDATE jobs SET status='failed', completed_at=?, error=? "
                "WHERE job_id=? AND status='running'",
                (now, error, job_id),
            )
            if cursor.rowcount == 0:
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"mark_failed: unknown job {job_id}")
                raise JobQueueError(
                    f"mark_failed: job {job_id} status={job.status} not running"
                )
        return self._must_get(job_id)

    def record_progress(
        self,
        job_id: str,
        progress_pct: float,
        progress_message: str = "",
        checkpoint: Mapping[str, Any] | None = None,
    ) -> Job:
        """Worker calls this to update progress and persist checkpoint state.

        Pre-condition: job is running. Raises if not.
        """
        if not (0.0 <= progress_pct <= 100.0):
            raise JobQueueError(f"record_progress: progress_pct {progress_pct} out of [0,100]")
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET progress_pct=?, progress_message=?, checkpoint_json=? "
                "WHERE job_id=? AND status='running'",
                (
                    float(progress_pct),
                    str(progress_message),
                    json.dumps(dict(checkpoint)) if checkpoint is not None else None,
                    job_id,
                ),
            )
            if cursor.rowcount == 0:
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"record_progress: unknown job {job_id}")
                raise JobQueueError(
                    f"record_progress: job {job_id} status={job.status} not running"
                )
        return self._must_get(job_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _must_get(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise JobQueueError(f"job {job_id} disappeared after write")
        return job

    def _transition(
        self,
        job_id: str,
        from_status: str,
        to_status: str,
        **fields: Any,
    ) -> None:
        if to_status not in ALLOWED_TRANSITIONS.get(from_status, frozenset()):
            raise JobQueueError(
                f"_transition: illegal {from_status} -> {to_status}"
            )
        cols = ["status=?"] + [f"{k}=?" for k in fields.keys()]
        vals = [to_status] + list(fields.values()) + [job_id, from_status]
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE jobs SET {', '.join(cols)} "
                f"WHERE job_id=? AND status=?",
                vals,
            )
            if cursor.rowcount == 0:
                job = self.get(job_id)
                if job is None:
                    raise JobQueueError(f"_transition: unknown job {job_id}")
                raise JobQueueError(
                    f"_transition: job {job_id} status={job.status}, "
                    f"expected {from_status}"
                )

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def _wipe_for_tests(self) -> None:
        """Clear all jobs. Tests only. Production code never calls this."""
        with self._connect() as conn:
            conn.execute("DELETE FROM jobs")


def job_to_dict(job: Job) -> dict[str, Any]:
    """Serialize a Job into a JSON-safe dict for API responses.

    Codex M-15b retrofit: surface `org_id` + `workspace_id` so
    UI / cross-org-leakage tests can verify org tagging.
    """
    return {
        "job_id": job.job_id,
        "template_id": job.template_id,
        "params": dict(job.params),
        "status": job.status,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "paused_at": job.paused_at,
        "completed_at": job.completed_at,
        "pause_requested": job.pause_requested,
        "cancel_requested": job.cancel_requested,
        "progress_pct": job.progress_pct,
        "progress_message": job.progress_message,
        "checkpoint": dict(job.checkpoint) if job.checkpoint else None,
        "artifact_dir": job.artifact_dir,
        "error": job.error,
        "org_id": job.org_id,
        "workspace_id": job.workspace_id,
    }
