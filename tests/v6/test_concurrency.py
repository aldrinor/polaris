"""Tests for the 1-concurrent-session constraint (I-rdy-013).

POST /runs admits at most one active (queued | in_progress) research run.
A 2nd concurrent request is cleanly rejected with HTTP 409; completed,
failed and aborted runs free the session slot.
"""

from __future__ import annotations

import sqlite3
import threading
import uuid

import pytest

from polaris_v6.queue import run_store


def _new_id() -> str:
    return uuid.uuid4().hex


# --- run_store.insert_run_if_idle / get_active_run -------------------------


def test_insert_run_if_idle_inserts_when_idle(tmp_path):
    db = str(tmp_path / "runs.sqlite")
    result = run_store.insert_run_if_idle(
        _new_id(), "clinical", "First idle question?", path=db
    )
    assert result is None
    active = run_store.get_active_run(path=db)
    assert active is not None
    assert active.lifecycle_status == "queued"


def test_insert_run_if_idle_rejects_when_queued_run_exists(tmp_path):
    db = str(tmp_path / "runs.sqlite")
    first = _new_id()
    assert (
        run_store.insert_run_if_idle(first, "clinical", "First question?", path=db)
        is None
    )
    blocking = run_store.insert_run_if_idle(
        _new_id(), "clinical", "Second question?", path=db
    )
    assert blocking is not None
    assert blocking.run_id == first
    assert blocking.lifecycle_status == "queued"


def test_insert_run_if_idle_rejects_when_in_progress(tmp_path):
    db = str(tmp_path / "runs.sqlite")
    first = _new_id()
    run_store.insert_run_if_idle(first, "clinical", "First question?", path=db)
    run_store.mark_in_progress(first, path=db)
    blocking = run_store.insert_run_if_idle(
        _new_id(), "clinical", "Second question?", path=db
    )
    assert blocking is not None
    assert blocking.run_id == first
    assert blocking.lifecycle_status == "in_progress"


def test_insert_run_if_idle_allows_after_completed(tmp_path):
    db = str(tmp_path / "runs.sqlite")
    first = _new_id()
    run_store.insert_run_if_idle(first, "clinical", "First question?", path=db)
    run_store.mark_completed(first, {"verdict": "success"}, path=db)
    assert (
        run_store.insert_run_if_idle(_new_id(), "clinical", "Next question?", path=db)
        is None
    )


def test_insert_run_if_idle_allows_after_failed(tmp_path):
    db = str(tmp_path / "runs.sqlite")
    first = _new_id()
    run_store.insert_run_if_idle(first, "clinical", "First question?", path=db)
    run_store.mark_failed(first, "boom", path=db)
    assert (
        run_store.insert_run_if_idle(_new_id(), "clinical", "Next question?", path=db)
        is None
    )


def test_insert_run_if_idle_allows_after_aborted(tmp_path):
    db = str(tmp_path / "runs.sqlite")
    first = _new_id()
    run_store.insert_run_if_idle(first, "clinical", "First question?", path=db)
    run_store.mark_aborted(
        first,
        pipeline_status="abort_corpus_inadequate",
        abort_reason="thin corpus",
        path=db,
    )
    assert (
        run_store.insert_run_if_idle(_new_id(), "clinical", "Next question?", path=db)
        is None
    )


def test_get_active_run_none_when_empty(tmp_path):
    db = str(tmp_path / "fresh.sqlite")
    assert run_store.get_active_run(path=db) is None


def test_get_active_run_returns_the_active_run(tmp_path):
    db = str(tmp_path / "runs.sqlite")
    rid = _new_id()
    run_store.insert_run_if_idle(rid, "policy", "Active question?", path=db)
    active = run_store.get_active_run(path=db)
    assert active is not None
    assert active.run_id == rid


def test_concurrent_inserts_race_is_serialized(tmp_path):
    """Two threads insert against one fresh DB at the same instant.

    Exercises both the `_INIT_LOCK` first-use safety and the
    `BEGIN IMMEDIATE` gate that sequential tests cannot. Exactly one insert
    must win; no thread may raise.
    """
    db = str(tmp_path / "race.sqlite")
    barrier = threading.Barrier(2)
    results: list[object] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait()
            outcome = run_store.insert_run_if_idle(
                _new_id(), "clinical", "Race question?", path=db
            )
        except Exception as exc:  # test must capture any raise under contention
            with lock:
                errors.append(exc)
            return
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == [], f"insert_run_if_idle raised under contention: {errors}"
    assert len(results) == 2
    inserted = [r for r in results if r is None]
    rejected = [r for r in results if r is not None]
    assert len(inserted) == 1, "exactly one insert should succeed"
    assert len(rejected) == 1, "exactly one insert should be rejected"

    conn = sqlite3.connect(db)
    try:
        count = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    finally:
        conn.close()
    assert count == 1, "exactly one run row should exist"


# --- POST /runs API level --------------------------------------------------


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_second_concurrent_post_is_rejected_409(client):
    first = client.post(
        "/runs",
        json={"template": "clinical", "question": "First concurrent question?"},
    )
    assert first.status_code == 202

    second = client.post(
        "/runs",
        json={"template": "clinical", "question": "Second concurrent question?"},
    )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "concurrent_run_active"
    assert detail["active_run_id"] == first.json()["run_id"]
    assert detail["active_status"] == "queued"
    assert "one research session at a time" in detail["message"]


def test_post_allowed_after_active_run_completes(client):
    first = client.post(
        "/runs",
        json={"template": "clinical", "question": "First then complete?"},
    )
    assert first.status_code == 202
    run_store.mark_completed(first.json()["run_id"], {"verdict": "success"})

    second = client.post(
        "/runs",
        json={"template": "clinical", "question": "Allowed after completion?"},
    )
    assert second.status_code == 202
    assert second.json()["run_id"] != first.json()["run_id"]


def test_post_frees_slot_when_enqueue_fails(client, monkeypatch):
    """Codex diff P1-001: a committed queued row whose enqueue then fails
    must NOT permanently hold the single-session slot."""
    from polaris_v6.api import runs as runs_module

    def _boom(*args, **kwargs):
        raise RuntimeError("broker down")

    monkeypatch.setattr(runs_module.enqueue_research_run, "send", _boom)
    failed = client.post(
        "/runs",
        json={"template": "clinical", "question": "Enqueue failure question?"},
    )
    assert failed.status_code == 503
    # The failed-to-enqueue run must not still hold the session slot.
    assert run_store.get_active_run() is None

    # And a fresh run can start once the slot is freed.
    monkeypatch.setattr(
        runs_module.enqueue_research_run, "send", lambda *a, **k: None
    )
    recovered = client.post(
        "/runs",
        json={"template": "clinical", "question": "Recovered question?"},
    )
    assert recovered.status_code == 202
