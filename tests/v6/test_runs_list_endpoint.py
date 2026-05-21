"""I-cd-705 (#705) — GET /api/v6/runs list endpoint + run_store.list_completed_runs.

Feeds the compare picker (#543), follow-up picker (#542), and the home
recent-runs strip. Completed + non-aborted only, newest-first, limit-clamped.
"""

from __future__ import annotations

import sqlite3

import pytest


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from polaris_v6.queue import run_store

    db = tmp_path / "runs.sqlite"
    monkeypatch.setenv(run_store.ENV_DB_PATH, str(db))
    run_store.init_db(str(db))
    return str(db)


def _seed(db_path, run_id, lifecycle, pipeline_status, finished_at):
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO runs (run_id, template, question, lifecycle_status, "
            "queued_at, started_at, finished_at, artifact_dir, "
            "pipeline_status, cancel_requested) VALUES (?,?,?,?,?,?,?,?,?,0)",
            (
                run_id,
                "clinical",
                "Q",
                lifecycle,
                "2026-05-20T00:00:00Z",
                "2026-05-20T00:00:00Z",
                finished_at,
                f"/tmp/{run_id}",
                pipeline_status,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_list_completed_runs_newest_first_excludes_abort_and_active(db_path):
    from polaris_v6.queue import run_store

    _seed(db_path, "older", "completed", "success", "2026-05-20T01:00:00Z")
    _seed(db_path, "newer", "completed", "success", "2026-05-20T03:00:00Z")
    _seed(db_path, "aborted", "completed", "abort_no_verified_sections", "2026-05-20T04:00:00Z")
    _seed(db_path, "running", "in_progress", None, None)

    runs = run_store.list_completed_runs(limit=20, path=db_path)
    ids = [r.run_id for r in runs]
    assert ids == ["newer", "older"]  # newest-first, abort + active excluded


def test_list_completed_runs_respects_limit(db_path):
    from polaris_v6.queue import run_store

    for i in range(5):
        _seed(db_path, f"run{i}", "completed", "success", f"2026-05-20T0{i}:00:00Z")
    runs = run_store.list_completed_runs(limit=2, path=db_path)
    assert len(runs) == 2
    assert [r.run_id for r in runs] == ["run4", "run3"]


def test_list_completed_runs_empty_when_none(db_path):
    from polaris_v6.queue import run_store

    assert run_store.list_completed_runs(limit=20, path=db_path) == []


# ─── endpoint ──────────────────────────────────────────────────────────────


@pytest.fixture
def client(db_path, monkeypatch):
    pytest.importorskip("fastapi")
    monkeypatch.setenv("POLARIS_AUTH_DISABLED", "1")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_get_runs_returns_completed_list(client, db_path):
    _seed(db_path, "a", "completed", "success", "2026-05-20T01:00:00Z")
    _seed(db_path, "b", "completed", "success", "2026-05-20T02:00:00Z")
    resp = client.get("/runs?status=completed&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert [r["run_id"] for r in body] == ["b", "a"]


def test_get_runs_rejects_non_completed_status(client):
    resp = client.get("/runs?status=queued")
    assert resp.status_code == 400


def test_get_runs_clamps_limit(client, db_path):
    for i in range(3):
        _seed(db_path, f"r{i}", "completed", "success", f"2026-05-20T0{i}:00:00Z")
    # limit far above the [1,100] clamp ceiling still returns (clamped, no error)
    resp = client.get("/runs?limit=99999")
    assert resp.status_code == 200
    assert len(resp.json()) == 3
