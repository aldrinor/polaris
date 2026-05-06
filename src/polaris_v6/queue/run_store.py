"""SQLite-backed run-status store for POLARIS v6 Dramatiq queue.

Per Issue I-phase0-005 (Codex APPROVE iter 4), this module persists
research-run lifecycle state to a SQLite file so the Dramatiq actor in
`actors.py` can transition status `queued -> in_progress -> completed`
and the FastAPI `/runs` route in `api/runs.py` can read persisted state
across restarts (replacing the previous in-memory dict).

Default DB path: state/v6_runs.sqlite (gitignored). Override via env
`POLARIS_V6_RUN_DB`. WAL mode enabled so Dramatiq writers don't block
FastAPI readers.

Out of scope this Issue (deferred to follow-up I-phase0-005b):
- mark_failed + error_json
- idempotency-on-completed short-circuit
- failure-path tests
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any

from polaris_v6.schemas.run_status import RunStatusResponse

DEFAULT_DB_PATH = "state/v6_runs.sqlite"
ENV_DB_PATH = "POLARIS_V6_RUN_DB"


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
    return conn


def init_db(path: str | None = None) -> None:
    """Create the runs table if absent. Idempotent. Enables WAL mode."""
    conn = _connect(path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                template TEXT NOT NULL,
                question TEXT NOT NULL,
                status TEXT NOT NULL,
                queued_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                result_json TEXT,
                error_json TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def insert_run(run_id: str, template: str, question: str, *, path: str | None = None) -> None:
    """Insert a new row with status='queued'. Raises sqlite3.IntegrityError on duplicate run_id."""
    init_db(path)
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, template, question, status, queued_at) VALUES (?, ?, ?, 'queued', ?)",
            (run_id, template, question, _now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


def mark_in_progress(run_id: str, *, path: str | None = None) -> None:
    """Transition queued -> in_progress, set started_at."""
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE runs SET status='in_progress', started_at=? WHERE run_id=?",
            (_now_iso(), run_id),
        )
        conn.commit()
    finally:
        conn.close()


def mark_completed(run_id: str, result: dict[str, Any], *, path: str | None = None) -> None:
    """Transition in_progress -> completed, set finished_at + result_json."""
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE runs SET status='completed', finished_at=?, result_json=? WHERE run_id=?",
            (_now_iso(), json.dumps(result, sort_keys=True), run_id),
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
    """
    conn = _connect(path)
    try:
        try:
            row = conn.execute(
                "SELECT run_id, template, question, status, queued_at, started_at, finished_at, result_json FROM runs WHERE run_id=?",
                (run_id,),
            ).fetchone()
        except sqlite3.OperationalError:
            return None
    finally:
        conn.close()
    if row is None:
        return None
    return RunStatusResponse(
        run_id=row["run_id"],
        template=row["template"],
        question=row["question"],
        status=row["status"],
        queued_at=row["queued_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        result_json=row["result_json"],
    )
