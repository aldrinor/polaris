"""SQLite-backed run-status store for POLARIS v6 Dramatiq queue.

I-arch-001a (2026-05-12):
- Migration: RENAME COLUMN status → lifecycle_status (SQLite 3.25+)
- New columns: query_slug, manifest_run_id, artifact_dir, pipeline_status,
  cost_usd, decision_id (all nullable; backward-compatible)
- New helpers: mark_failed, mark_aborted, set_pipeline_meta
- get_run returns the full RunStatusResponse with new optional fields

I-rdy-013 (2026-05-16): 1-concurrent-session enforcement.
- get_active_run: read-side helper — the run currently holding the session.
- insert_run_if_idle: atomic check-and-insert (BEGIN IMMEDIATE) used by
  POST /runs so a 2nd concurrent request cannot start a parallel session.
- init_db serialized by `_INIT_LOCK`; `_connect` sets `busy_timeout`.

Default DB path: state/v6_runs.sqlite (gitignored). Override via env
`POLARIS_V6_RUN_DB`. WAL mode enabled.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from polaris_v6.schemas.run_status import RunStatusResponse

DEFAULT_DB_PATH = "state/v6_runs.sqlite"
ENV_DB_PATH = "POLARIS_V6_RUN_DB"

# I-rdy-013: lifecycle states that count as an active research session. A run
# in one of these blocks a new POST /runs (1-concurrent-session constraint).
# `completed`, `cancelled`, `failed` are terminal and free the session slot.
_ACTIVE_STATUSES = ("queued", "in_progress")

# I-rdy-013: serializes init_db across in-process threads so two concurrent
# first requests cannot collide inside `PRAGMA journal_mode=WAL` or the schema
# migration and raise sqlite3.OperationalError before the atomic gate runs.
_INIT_LOCK = threading.Lock()

# Shared 15-column projection — used identically by get_run, get_active_run
# and insert_run_if_idle so `_row_to_response` can build the model from any.
_RUN_COLUMNS = (
    "run_id, template, question, lifecycle_status, pipeline_status, "
    "queued_at, started_at, finished_at, result_json, error_json, "
    "query_slug, manifest_run_id, artifact_dir, cost_usd, decision_id"
)


def _resolve_path(path: str | None) -> str:
    if path is not None:
        return path
    return os.environ.get(ENV_DB_PATH, DEFAULT_DB_PATH)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect(path: str | None = None) -> sqlite3.Connection:
    resolved = _resolve_path(path)
    parent = os.path.dirname(resolved)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(resolved)
    conn.row_factory = sqlite3.Row
    # I-rdy-013: a concurrent writer waits up to 5s for the write lock
    # instead of raising SQLITE_BUSY immediately (the issue's "no crash").
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _row_to_response(row: sqlite3.Row) -> RunStatusResponse:
    """Build a RunStatusResponse from a runs-table row.

    Shared by get_run, get_active_run and insert_run_if_idle, all of which
    SELECT the same `_RUN_COLUMNS` projection.
    """
    return RunStatusResponse(
        run_id=row["run_id"],
        template=row["template"],
        question=row["question"],
        lifecycle_status=row["lifecycle_status"],
        pipeline_status=row["pipeline_status"],
        queued_at=row["queued_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        result_json=row["result_json"],
        error_json=row["error_json"],
        query_slug=row["query_slug"],
        manifest_run_id=row["manifest_run_id"],
        artifact_dir=row["artifact_dir"],
        cost_usd=row["cost_usd"],
        decision_id=row["decision_id"],
    )


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Idempotent additive migration. Safe to call on every init_db.

    1. Create base table if absent.
    2. If legacy `status` column exists and `lifecycle_status` doesn't,
       RENAME COLUMN to preserve values (SQLite 3.25+, Python 3.11 ships
       SQLite 3.34+).
    3. ADD COLUMN for each I-arch-001a field if missing.
    4. CREATE INDEX IF NOT EXISTS for query lookups.
    """
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            template TEXT NOT NULL,
            question TEXT NOT NULL,
            lifecycle_status TEXT NOT NULL,
            queued_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            result_json TEXT,
            error_json TEXT
        )
        """
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    if "status" in cols and "lifecycle_status" not in cols:
        conn.execute("ALTER TABLE runs RENAME COLUMN status TO lifecycle_status")
        cols.discard("status")
        cols.add("lifecycle_status")
    for col_name, col_type in {
        "query_slug": "TEXT",
        "manifest_run_id": "TEXT",
        "artifact_dir": "TEXT",
        "pipeline_status": "TEXT",
        "cost_usd": "REAL",
        "decision_id": "TEXT",
    }.items():
        if col_name not in cols:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col_name} {col_type}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_query_slug ON runs(query_slug)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_manifest_run_id ON runs(manifest_run_id)")


def init_db(path: str | None = None) -> None:
    """Create the runs table if absent, run migrations. Idempotent.

    I-rdy-013: serialized by `_INIT_LOCK` so two concurrent first requests
    (FastAPI worker threads, one process) cannot collide inside
    `PRAGMA journal_mode=WAL` or the schema migration and raise
    sqlite3.OperationalError before the atomic gate is reached.
    """
    with _INIT_LOCK:
        conn = _connect(path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            _migrate_schema(conn)
            conn.commit()
        finally:
            conn.close()


def insert_run(run_id: str, template: str, question: str, *, path: str | None = None) -> None:
    """Insert a new row with lifecycle_status='queued'. Raises IntegrityError on duplicate.

    Unconditional primitive — does NOT enforce the 1-concurrent-session
    constraint. POST /runs uses `insert_run_if_idle`; this remains for test
    fixtures and any caller that deliberately wants an unconditional insert.
    """
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, template, question, lifecycle_status, queued_at) "
            "VALUES (?, ?, ?, 'queued', ?)",
            (run_id, template, question, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def insert_run_if_idle(
    run_id: str, template: str, question: str, *, path: str | None = None
) -> RunStatusResponse | None:
    """Atomically insert a new queued run IFF no run is currently active.

    I-rdy-013 (1-concurrent-session enforcement): the check-for-active and
    the INSERT run inside one `BEGIN IMMEDIATE` transaction, so two
    concurrent POST /runs cannot both pass the check. `BEGIN IMMEDIATE`
    takes the write lock up-front; the 2nd writer blocks on it (up to the
    `busy_timeout`) until the 1st commits, then sees the inserted row.

    Returns None when the run was inserted; returns the blocking active
    RunStatusResponse when rejected (caller raises HTTP 409).
    """
    init_db(path)
    placeholders = ", ".join("?" for _ in _ACTIVE_STATUSES)
    conn = _connect(path)
    conn.isolation_level = None  # manual transaction control
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            f"SELECT {_RUN_COLUMNS} FROM runs "
            f"WHERE lifecycle_status IN ({placeholders}) "
            "ORDER BY queued_at LIMIT 1",
            _ACTIVE_STATUSES,
        ).fetchone()
        if row is not None:
            conn.execute("ROLLBACK")
            return _row_to_response(row)
        conn.execute(
            "INSERT INTO runs (run_id, template, question, lifecycle_status, queued_at) "
            "VALUES (?, ?, ?, 'queued', ?)",
            (run_id, template, question, _now_iso()),
        )
        conn.execute("COMMIT")
        return None
    finally:
        conn.close()


def mark_in_progress(run_id: str, *, path: str | None = None) -> None:
    """Transition queued → in_progress, set started_at."""
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE runs SET lifecycle_status='in_progress', started_at=? WHERE run_id=?",
            (_now_iso(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def set_pipeline_meta(
    run_id: str,
    *,
    query_slug: str | None = None,
    manifest_run_id: str | None = None,
    artifact_dir: str | None = None,
    decision_id: str | None = None,
    path: str | None = None,
) -> None:
    """Set pipeline-A metadata after the actor learns the slug/dir.

    Independent of lifecycle transition so the actor can record meta as
    soon as pipeline-A starts, before the run completes.
    """
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE runs SET query_slug=COALESCE(?, query_slug), "
            "manifest_run_id=COALESCE(?, manifest_run_id), "
            "artifact_dir=COALESCE(?, artifact_dir), "
            "decision_id=COALESCE(?, decision_id) WHERE run_id=?",
            (query_slug, manifest_run_id, artifact_dir, decision_id, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_completed(
    run_id: str,
    result: dict[str, Any],
    *,
    pipeline_status: str = "success",
    cost_usd: float | None = None,
    path: str | None = None,
) -> None:
    """Transition in_progress → completed; set finished_at + result_json + pipeline_status + cost_usd."""
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE runs SET lifecycle_status='completed', finished_at=?, result_json=?, "
            "pipeline_status=?, cost_usd=? WHERE run_id=?",
            (_now_iso(), json.dumps(result, sort_keys=True), pipeline_status, cost_usd, run_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_aborted(
    run_id: str,
    *,
    pipeline_status: str,
    abort_reason: str,
    cost_usd: float | None = None,
    path: str | None = None,
) -> None:
    """Pipeline ran to completion but hit a gate; lifecycle_status='completed', pipeline_status='abort_*'.

    Per CLAUDE.md §9.3, abort_* are pipeline verdicts (not errors). The run
    completed operationally; the pipeline-A logic chose to halt at a gate.
    """
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE runs SET lifecycle_status='completed', finished_at=?, "
            "pipeline_status=?, error_json=?, cost_usd=? WHERE run_id=?",
            (
                _now_iso(),
                pipeline_status,
                json.dumps({"abort_reason": abort_reason}, sort_keys=True),
                cost_usd,
                run_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def mark_failed(run_id: str, error: str, *, path: str | None = None) -> None:
    """Operational failure (exception, missing manifest, unknown status, etc).

    Distinct from mark_aborted: failures are unplanned (exception or invariant
    violation); aborts are planned (pipeline_status='abort_*' written by
    pipeline-A at a gate).
    """
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE runs SET lifecycle_status='failed', finished_at=?, "
            "pipeline_status='error_unexpected', error_json=? WHERE run_id=?",
            (_now_iso(), json.dumps({"error": error}, sort_keys=True), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_run(run_id: str, *, path: str | None = None) -> RunStatusResponse | None:
    """Return the run record or None if missing.

    Defensive against `OperationalError: no such table` so callers in stub
    mode (e.g. `tests/v6/test_actors.py` direct `.fn()` invocation without
    init_db) get None back, matching the actor's row-missing-stub-noop
    contract.

    I-arch-001a Codex iter-2 P2-002: if a known DB exists with the legacy
    schema, the first read-only `get_run` call would 500 on column-missing.
    The defensive catch below detects "no such column" and triggers a
    one-time migration via init_db before retrying.
    """
    conn = _connect(path)
    try:
        try:
            row = conn.execute(
                f"SELECT {_RUN_COLUMNS} FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            # Narrow per Codex iter-1 P2-001: only the missing-table stub
            # path returns None; surface other operational errors (schema
            # corruption, migration faults) so they aren't masked as
            # missing-row.
            if "no such table" in msg:
                return None
            # Codex iter-2 P2-002: legacy schema → migrate then retry once.
            if "no such column" in msg:
                conn.close()
                init_db(path)
                conn = _connect(path)
                row = conn.execute(
                    f"SELECT {_RUN_COLUMNS} FROM runs WHERE run_id=?",
                    (run_id,),
                ).fetchone()
            else:
                raise
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_response(row)


def get_active_run(*, path: str | None = None) -> RunStatusResponse | None:
    """Return the oldest run still queued or in_progress, else None.

    I-rdy-013: read-side helper for the 1-concurrent-session constraint —
    the run currently holding the session slot. At most one run is active
    once `insert_run_if_idle` gates all inserts; the `ORDER BY queued_at`
    is defensive (oldest first) for any pre-gate legacy rows.

    Defensive against a missing/legacy table, mirroring `get_run`.
    """
    placeholders = ", ".join("?" for _ in _ACTIVE_STATUSES)
    query = (
        f"SELECT {_RUN_COLUMNS} FROM runs "
        f"WHERE lifecycle_status IN ({placeholders}) "
        "ORDER BY queued_at LIMIT 1"
    )
    conn = _connect(path)
    try:
        try:
            row = conn.execute(query, _ACTIVE_STATUSES).fetchone()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            if "no such table" in msg:
                return None
            if "no such column" in msg:
                conn.close()
                init_db(path)
                conn = _connect(path)
                row = conn.execute(query, _ACTIVE_STATUSES).fetchone()
            else:
                raise
    finally:
        conn.close()
    return None if row is None else _row_to_response(row)
