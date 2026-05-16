"""Tests for I-rdy-011 (#507) — run cancellation.

Covers the cancel path end to end, offline (no real broker, no network):
* run_store cancel methods — request_cancel (queued→cancelled T1, in_progress
  →flag T2), is_cancel_requested, mark_cancelled, and the mark_in_progress
  compare-and-swap (a queued cancel must not be overwritten by worker pickup).
* POST /runs/{id}/cancel (the `cancel_run` route function) — 404 / terminal
  no-op / queued→cancelled.
* The actor honoring a cancel requested before pipeline start.
* run_one_query's `_abort_if_cancelled` cooperative checkpoint.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from polaris_v6.api.runs import cancel_run
from polaris_v6.queue import run_store


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Isolate the run-store DB per test via POLARIS_V6_RUN_DB."""
    path = str(tmp_path / "cancel_test.sqlite")
    monkeypatch.setenv("POLARIS_V6_RUN_DB", path)
    return path


# --------------------------------------------------------------------------
# run_store cancel methods
# --------------------------------------------------------------------------

def test_request_cancel_queued_is_instant(db):
    run_store.insert_run("r1", "clinical", "question?")
    assert run_store.request_cancel("r1") == "cancelled"
    rec = run_store.get_run("r1")
    assert rec is not None
    assert rec.lifecycle_status == "cancelled"
    assert rec.cancel_requested is True
    assert rec.finished_at is not None


def test_request_cancel_in_progress_sets_flag(db):
    run_store.insert_run("r2", "clinical", "question?")
    assert run_store.mark_in_progress("r2") is True
    # T2: in_progress → flag set, lifecycle stays in_progress (cooperative).
    assert run_store.request_cancel("r2") == "in_progress"
    rec = run_store.get_run("r2")
    assert rec is not None
    assert rec.lifecycle_status == "in_progress"
    assert rec.cancel_requested is True


def test_request_cancel_unknown_returns_none(db):
    run_store.init_db()
    assert run_store.request_cancel("does-not-exist") is None


def test_request_cancel_terminal_returns_none(db):
    run_store.insert_run("r3", "clinical", "question?")
    run_store.mark_in_progress("r3")
    run_store.mark_completed("r3", {"ok": True})
    assert run_store.request_cancel("r3") is None


def test_mark_in_progress_cas_does_not_overwrite_cancelled(db):
    """P2-2: a queued cancel must not be overwritten by a concurrent
    worker mark_in_progress."""
    run_store.insert_run("r4", "clinical", "question?")
    run_store.request_cancel("r4")  # queued → cancelled
    assert run_store.mark_in_progress("r4") is False  # CAS no-op
    rec = run_store.get_run("r4")
    assert rec is not None
    assert rec.lifecycle_status == "cancelled"


def test_is_cancel_requested(db):
    run_store.insert_run("r5", "clinical", "question?")
    assert run_store.is_cancel_requested("r5") is False
    run_store.request_cancel("r5")
    assert run_store.is_cancel_requested("r5") is True


def test_is_cancel_requested_missing_run(db):
    run_store.init_db()
    assert run_store.is_cancel_requested("does-not-exist") is False


def test_mark_cancelled(db):
    run_store.insert_run("r6", "clinical", "question?")
    run_store.mark_in_progress("r6")
    run_store.mark_cancelled("r6")
    rec = run_store.get_run("r6")
    assert rec is not None
    assert rec.lifecycle_status == "cancelled"
    assert rec.cancel_requested is True
    assert rec.finished_at is not None


# --------------------------------------------------------------------------
# POST /runs/{id}/cancel — the cancel_run route function
# --------------------------------------------------------------------------

def test_cancel_run_unknown_raises_404(db):
    run_store.init_db()
    with pytest.raises(HTTPException) as exc:
        cancel_run("does-not-exist")
    assert exc.value.status_code == 404


def test_cancel_run_queued_cancels(db):
    run_store.insert_run("r7", "clinical", "question?")
    rec = cancel_run("r7")
    assert rec.lifecycle_status == "cancelled"
    assert rec.cancel_requested is True


def test_cancel_run_terminal_is_idempotent_noop(db):
    run_store.insert_run("r8", "clinical", "question?")
    run_store.mark_in_progress("r8")
    run_store.mark_completed("r8", {"ok": True})
    rec = cancel_run("r8")  # already terminal — no-op
    assert rec.lifecycle_status == "completed"


# --------------------------------------------------------------------------
# Actor honors a cancel requested before pipeline start
# --------------------------------------------------------------------------

def test_actor_honors_cancel_before_pipeline(db, tmp_path, monkeypatch):
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path / "v6_runs"))
    from polaris_v6.queue.actors import enqueue_research_run

    run_store.insert_run("r9", "clinical", "What does the data show?")
    run_store.request_cancel("r9")  # queued → cancelled before worker pickup
    result = enqueue_research_run.fn(
        "r9",
        {"template": "clinical", "question": "What does the data show?", "document_ids": []},
    )
    # Actor returns cancelled without ever invoking pipeline-A.
    assert result["status"] == "cancelled"
    rec = run_store.get_run("r9")
    assert rec is not None
    assert rec.lifecycle_status == "cancelled"


def test_actor_retry_of_failed_run_not_marked_cancelled(db, tmp_path, monkeypatch):
    """Codex diff-iter-1 P1: a Dramatiq retry of an already-failed run must
    NOT be rewritten to 'cancelled'. The actor detects cancellation only via
    is_cancel_requested — never from the mark_in_progress CAS return (which is
    also False for a non-queued retry row)."""
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path / "v6_runs"))

    async def _fake_run_one_query(q, out_root):  # noqa: ARG001
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / "manifest.json").write_text(
            json.dumps({"run_id": "SWEEP_x", "status": "success"}) + "\n"
        )
        return {"status": "success"}

    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query, raising=False
    )
    from polaris_v6.queue.actors import enqueue_research_run

    run_store.insert_run("r12", "clinical", "Question?")
    run_store.mark_in_progress("r12")
    run_store.mark_failed("r12", "attempt-1 crash")  # a prior failed attempt
    # No cancel requested — the retry must run the pipeline, not false-cancel.
    enqueue_research_run.fn(
        "r12", {"template": "clinical", "question": "Question?", "document_ids": []}
    )
    rec = run_store.get_run("r12")
    assert rec is not None
    # The buggy code would have marked the failed row 'cancelled'; the retry
    # instead re-runs the pipeline and reaches 'completed'.
    assert rec.lifecycle_status == "completed"


def test_actor_late_cancel_overrides_success_manifest(db, tmp_path, monkeypatch):
    """Codex diff-iter-2 P1: a cancel requested during run_one_query's final
    stage (past the last cooperative checkpoint) must still win — the actor's
    post-run backstop marks the run cancelled even though the manifest is a
    success verdict."""
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path / "v6_runs"))

    async def _fake_run_one_query(q, out_root):  # noqa: ARG001
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / "manifest.json").write_text(
            json.dumps({"run_id": "SWEEP_x", "status": "success"}) + "\n"
        )
        # A cancel lands during the run's final (post-checkpoint) stage.
        run_store.request_cancel("r13")
        return {"status": "success"}

    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query, raising=False
    )
    from polaris_v6.queue.actors import enqueue_research_run

    run_store.insert_run("r13", "clinical", "Question?")
    enqueue_research_run.fn(
        "r13", {"template": "clinical", "question": "Question?", "document_ids": []}
    )
    rec = run_store.get_run("r13")
    assert rec is not None
    # The success manifest must NOT win — the user cancelled.
    assert rec.lifecycle_status == "cancelled"


# --------------------------------------------------------------------------
# run_one_query cooperative checkpoint — _abort_if_cancelled
# --------------------------------------------------------------------------

def test_abort_if_cancelled_non_v6_run_is_noop(db, tmp_path):
    from scripts.run_honest_sweep_r3 import _abort_if_cancelled

    summary: dict = {}
    q = {"slug": "s", "domain": "d", "question": "q"}  # no v6_mode
    assert _abort_if_cancelled(q, tmp_path, "rid", summary, lambda _m: None) is False
    assert not (tmp_path / "manifest.json").exists()


def test_abort_if_cancelled_v6_cancelled(db, tmp_path):
    from scripts.run_honest_sweep_r3 import _abort_if_cancelled

    run_store.insert_run("r10", "clinical", "question?")
    run_store.mark_in_progress("r10")
    run_store.request_cancel("r10")  # in_progress → cancel flag set
    summary: dict = {}
    q = {
        "v6_mode": True,
        "external_run_id": "r10",
        "slug": "s",
        "domain": "clinical",
        "question": "question?",
    }
    assert _abort_if_cancelled(q, tmp_path, "SWEEP_x", summary, lambda _m: None) is True
    assert summary["status"] == "cancelled"
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["status"] == "cancelled"
    assert manifest["run_id"] == "SWEEP_x"


def test_abort_if_cancelled_v6_not_cancelled(db, tmp_path):
    from scripts.run_honest_sweep_r3 import _abort_if_cancelled

    run_store.insert_run("r11", "clinical", "question?")
    run_store.mark_in_progress("r11")
    summary: dict = {}
    q = {
        "v6_mode": True,
        "external_run_id": "r11",
        "slug": "s",
        "domain": "clinical",
        "question": "question?",
    }
    assert _abort_if_cancelled(q, tmp_path, "SWEEP_x", summary, lambda _m: None) is False
    assert not (tmp_path / "manifest.json").exists()
