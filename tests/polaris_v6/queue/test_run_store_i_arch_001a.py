"""I-arch-001a — schema migration + new helper coverage."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from polaris_v6.queue import run_store


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "v6_runs.sqlite")


def test_init_db_fresh_creates_canonical_schema(db_path: str) -> None:
    """init_db on a fresh DB creates the v6 schema directly (no legacy column)."""
    run_store.init_db(path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    finally:
        conn.close()
    assert "lifecycle_status" in cols
    assert "status" not in cols
    for new_col in ("query_slug", "manifest_run_id", "artifact_dir", "pipeline_status", "cost_usd", "decision_id"):
        assert new_col in cols, f"missing new column {new_col!r}"


def test_migration_rename_preserves_values(db_path: str) -> None:
    """Legacy `status` column gets renamed to lifecycle_status; values preserved."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY, template TEXT NOT NULL, question TEXT NOT NULL,
                status TEXT NOT NULL, queued_at TEXT NOT NULL,
                started_at TEXT, finished_at TEXT, result_json TEXT, error_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO runs (run_id, template, question, status, queued_at) "
            "VALUES ('r1', 'clinical', 'q?', 'completed', '2026-05-12T00:00:00+00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    run_store.init_db(path=db_path)
    row = run_store.get_run("r1", path=db_path)
    assert row is not None
    assert row.lifecycle_status == "completed"
    assert row.status == "completed"  # computed_field alias preserved


def test_migration_is_idempotent(db_path: str) -> None:
    """Calling init_db twice on an already-migrated DB is a no-op (no ALTER errors)."""
    run_store.init_db(path=db_path)
    run_store.init_db(path=db_path)  # second call must not raise


def test_full_lifecycle_completed(db_path: str) -> None:
    """insert → mark_in_progress → set_pipeline_meta → mark_completed end-to-end."""
    run_store.init_db(path=db_path)
    run_store.insert_run("r1", "clinical", "q?", path=db_path)
    run_store.mark_in_progress("r1", path=db_path)
    run_store.set_pipeline_meta(
        "r1",
        query_slug="clinical_q",
        manifest_run_id="SWEEP_clinical_q_123",
        artifact_dir="/tmp/v6_runs/r1",
        decision_id="dec_uuid",
        path=db_path,
    )
    run_store.mark_completed("r1", {"k": "v"}, pipeline_status="success", cost_usd=0.42, path=db_path)
    row = run_store.get_run("r1", path=db_path)
    assert row is not None
    assert row.lifecycle_status == "completed"
    assert row.pipeline_status == "success"
    assert row.query_slug == "clinical_q"
    assert row.manifest_run_id == "SWEEP_clinical_q_123"
    assert row.artifact_dir == "/tmp/v6_runs/r1"
    assert row.cost_usd == 0.42
    assert row.decision_id == "dec_uuid"
    assert json.loads(row.result_json or "{}") == {"k": "v"}


def test_mark_aborted_persists_cost_and_reason(db_path: str) -> None:
    """abort_* keeps lifecycle_status='completed' (the run finished operationally)."""
    run_store.init_db(path=db_path)
    run_store.insert_run("r2", "clinical", "q?", path=db_path)
    run_store.mark_in_progress("r2", path=db_path)
    run_store.mark_aborted(
        "r2",
        pipeline_status="abort_corpus_inadequate",
        abort_reason="not enough T1 sources",
        cost_usd=0.10,
        path=db_path,
    )
    row = run_store.get_run("r2", path=db_path)
    assert row is not None
    assert row.lifecycle_status == "completed"
    assert row.pipeline_status == "abort_corpus_inadequate"
    assert row.cost_usd == 0.10
    err = json.loads(row.error_json or "{}")
    assert err["abort_reason"] == "not enough T1 sources"


def test_mark_failed_sets_failed_status_and_error(db_path: str) -> None:
    """Operational failure: lifecycle_status='failed', pipeline_status='error_unexpected'."""
    run_store.init_db(path=db_path)
    run_store.insert_run("r3", "clinical", "q?", path=db_path)
    run_store.mark_in_progress("r3", path=db_path)
    run_store.mark_failed("r3", "pipeline_exception: RuntimeError: boom", path=db_path)
    row = run_store.get_run("r3", path=db_path)
    assert row is not None
    assert row.lifecycle_status == "failed"
    assert row.pipeline_status == "error_unexpected"
    err = json.loads(row.error_json or "{}")
    assert "boom" in err["error"]


def test_get_run_returns_none_when_table_missing(tmp_path: Path) -> None:
    """Stub-mode contract: missing table returns None, not OperationalError."""
    db_path = str(tmp_path / "no_init.sqlite")
    # No init_db call; table doesn't exist.
    assert run_store.get_run("anything", path=db_path) is None
