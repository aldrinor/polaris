"""Integration tests for I-phase0-005 — POST /runs -> Dramatiq -> SQLite.

Per Codex APPROVE iter 4 brief, exercises the queue-to-DB loop:
- Schema applied via init_db.
- Actor success path persists status + result_json.
- POST /runs persists row + enqueues actor.
- GET /runs/{id} reads from store.

Existing scenario 1 (test_dramatiq_acceptance.py) covers the strengthened
"row reaches completed after broker drain" assertion.

Out of scope this Issue (deferred to follow-up I-phase0-005b):
- mark_failed + error_json + failure-path test
- Idempotency-on-completed short-circuit + test
- Missing-row direct .fn() RuntimeError (inverted by stub-mode contract)
"""

from __future__ import annotations

import json
import sqlite3

import pytest

pytest.importorskip("dramatiq")
pytest.importorskip("fastapi")


@pytest.fixture
def isolated_db(monkeypatch, tmp_path):
    """Per-test SQLite DB + StubBroker flush before/after.

    Per brief P2-I4-002 closure: imports MUST stay inside test bodies /
    fixtures so monkeypatch.setenv lands before run_store reads env.
    """
    db_path = tmp_path / "runs_integration.sqlite"
    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(db_path))
    import dramatiq
    broker = dramatiq.get_broker()
    broker.flush_all()
    yield db_path
    broker.flush_all()


def test_init_db_creates_schema(isolated_db):
    """Acceptance #1: init_db creates the runs table with all named columns."""
    from polaris_v6.queue import run_store

    run_store.init_db()

    conn = sqlite3.connect(str(isolated_db))
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
    finally:
        conn.close()
    # I-arch-001a (2026-05-12): status -> lifecycle_status + new metadata columns.
    expected = {
        "run_id", "template", "question", "lifecycle_status",
        "queued_at", "started_at", "finished_at",
        "result_json", "error_json",
        # New I-arch-001a columns:
        "query_slug", "manifest_run_id", "artifact_dir",
        "pipeline_status", "cost_usd", "decision_id",
        # I-rdy-011 (#507): cancellation-support column.
        "cancel_requested",
    }
    assert cols == expected


def test_actor_marks_completed_after_pre_insert(isolated_db, monkeypatch, tmp_path):
    """Acceptance #2: pre-inserted row reaches lifecycle_status=completed after broker drain.

    I-arch-001a (2026-05-12): actor now invokes pipeline-A via
    scripts.run_honest_sweep_r3.run_one_query and reads the manifest it
    writes. The test mocks the import to return a synthetic summary +
    write a minimal valid manifest, keeping the acceptance hermetic.
    """
    import dramatiq
    from dramatiq.worker import Worker
    from polaris_v6.queue import run_store
    from polaris_v6.queue.actors import enqueue_research_run

    # Mock pipeline-A: write a minimal manifest and return a summary dict.
    async def _fake_run_one_query(q, out_root):
        out_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "run_id": f"SWEEP_{q['domain']}_{q['slug']}_fixture",
            "status": "success",
            "cost_usd": 0.01,
            "slug": q["slug"],
            "domain": q["domain"],
            "question": q["question"],
        }
        (out_root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
        return {"manifest": manifest, "cost_usd": 0.01, "status": "success"}

    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query",
        _fake_run_one_query,
        raising=False,
    )
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path / "v6_runs"))

    run_store.insert_run("run_002", "clinical", "noop?")
    payload = {"template": "clinical", "question": "noop?", "document_ids": []}
    enqueue_research_run.send("run_002", payload)

    broker = dramatiq.get_broker()
    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        broker.join(enqueue_research_run.queue_name, timeout=10000)
        worker.join()
    finally:
        worker.stop()

    record = run_store.get_run("run_002")
    assert record is not None
    assert record.lifecycle_status == "completed"
    assert record.pipeline_status == "success"
    assert record.status == "completed"  # computed_field backcompat alias
    assert record.query_slug is not None
    assert record.artifact_dir is not None
    assert record.cost_usd == 0.01


def test_post_runs_persists_row(isolated_db):
    """Acceptance #3: POST /runs returns 202 with status='queued' and persists a row."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from polaris_v6.api.runs import router
    from polaris_v6.queue import run_store

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.post("/runs", json={"template": "clinical", "question": "noop?"})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    run_id = body["run_id"]

    record = run_store.get_run(run_id)
    assert record is not None
    assert record.status == "queued"


def test_get_run_after_drain_returns_completed(isolated_db, monkeypatch, tmp_path):
    """Acceptance #4: full POST + drain + GET loop returns lifecycle_status=completed.

    I-arch-001a (2026-05-12): mock pipeline-A as in test #2.
    """
    import dramatiq
    from dramatiq.worker import Worker
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from polaris_v6.api.runs import router
    from polaris_v6.queue.actors import enqueue_research_run

    async def _fake_run_one_query(q, out_root):
        out_root.mkdir(parents=True, exist_ok=True)
        manifest = {
            "run_id": f"SWEEP_{q['domain']}_{q['slug']}_fixture",
            "status": "success",
            "cost_usd": 0.02,
        }
        (out_root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
        return {"manifest": manifest, "cost_usd": 0.02, "status": "success"}

    monkeypatch.setattr(
        "scripts.run_honest_sweep_r3.run_one_query",
        _fake_run_one_query,
        raising=False,
    )
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path / "v6_runs"))

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    post_resp = client.post("/runs", json={"template": "clinical", "question": "noop?"})
    assert post_resp.status_code == 202
    run_id = post_resp.json()["run_id"]
    assert post_resp.json()["status"] == "queued"  # computed_field alias works at API surface

    broker = dramatiq.get_broker()
    worker = Worker(broker, worker_timeout=100)
    worker.start()
    try:
        broker.join(enqueue_research_run.queue_name, timeout=10000)
        worker.join()
    finally:
        worker.stop()

    get_resp = client.get(f"/runs/{run_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["status"] == "completed"  # alias
    assert body["lifecycle_status"] == "completed"
    assert body["pipeline_status"] == "success"
    assert body["cost_usd"] == 0.02
