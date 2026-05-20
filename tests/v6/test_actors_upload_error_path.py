"""I-cd-018 (#628) — error-path observability for uploaded documents.

Ensures the three actor error sites (pipeline_exception, manifest_missing,
manifest_invalid) thread `uploaded_documents_used` +
`uploaded_documents_blocked` counts into `error_json` via `mark_failed`.

Also covers the new `RunRequest.document_ids` max_length=20 cap (422
when exceeded; valid otherwise).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch) -> Path:
    from polaris_v6.queue import run_store

    db = tmp_path / "runs.sqlite"
    monkeypatch.setenv(run_store.ENV_DB_PATH, str(db))
    run_store.init_db(str(db))
    return db


@pytest.fixture
def auth_disabled(monkeypatch):
    monkeypatch.setenv("POLARIS_AUTH_DISABLED", "1")


def _read_error_json(db_path: Path, run_id: str) -> dict[str, Any]:
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT error_json FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
    finally:
        conn.close()
    assert row is not None and row[0]
    return json.loads(row[0])


def _invoke_actor(*, run_id: str, allowed: list[dict], blocked_count: int, run_one_query_behavior):
    """Run the v6 actor logic with a controlled mock of run_one_query.

    Returns the resulting run_store state so tests can inspect mark_failed
    pathways without an actual dramatiq broker.
    """
    from polaris_v6.queue import actors, run_store

    run_store.insert_run(run_id, "clinical", "test question?")
    run_store.set_pipeline_meta(run_id, query_slug="q_slug", artifact_dir=None)

    request_payload = {
        "template": "clinical",
        "question": "test question?",
        "uploaded_documents": allowed,
    }

    with patch(
        "polaris_v6.adapters.upload_evidence.partition_uploads_by_sovereignty",
        return_value=(allowed, [{"document_id": f"blocked_{i}"} for i in range(blocked_count)]),
    ):
        with patch("scripts.run_honest_sweep_r3.run_one_query", side_effect=run_one_query_behavior):
            try:
                actors.enqueue_research_run.fn(run_id, request_payload)
            except RuntimeError:
                # The actor re-raises pipeline_exception per noqa BLE001; that
                # is the documented contract for dramatiq retry.
                pass


def test_pipeline_exception_records_upload_counts(db_path: Path):
    run_id = "r_exc"
    allowed = [{"document_id": "d1", "classification": "PUBLIC_SYNTHETIC", "chunks": []}]

    def _raises(*_args, **_kwargs):
        raise RuntimeError("simulated pipeline crash")

    _invoke_actor(run_id=run_id, allowed=allowed, blocked_count=2, run_one_query_behavior=_raises)

    error_json = _read_error_json(db_path, run_id)
    assert error_json["uploaded_documents_used"] == 1
    assert error_json["uploaded_documents_blocked"] == 2
    assert "pipeline_exception" in error_json["error"]


def test_manifest_missing_records_upload_counts(db_path: Path, tmp_path: Path, monkeypatch):
    run_id = "r_no_manifest"
    allowed = [
        {"document_id": "d1", "classification": "PUBLIC_SYNTHETIC", "chunks": []},
        {"document_id": "d2", "classification": "PUBLIC_SYNTHETIC", "chunks": []},
    ]
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path))

    def _returns_no_manifest(q, artifact_dir_root):
        # Intentionally don't write manifest.json — exercise the missing path.
        return {"run_id": q.get("external_run_id"), "cost_usd": 0.0}

    _invoke_actor(
        run_id=run_id, allowed=allowed, blocked_count=0,
        run_one_query_behavior=_returns_no_manifest,
    )

    error_json = _read_error_json(db_path, run_id)
    assert error_json["uploaded_documents_used"] == 2
    assert error_json["uploaded_documents_blocked"] == 0
    assert "manifest_missing" in error_json["error"]


def test_manifest_invalid_records_upload_counts(db_path: Path, tmp_path: Path, monkeypatch):
    run_id = "r_bad_manifest"
    monkeypatch.setenv("POLARIS_V6_OUTPUT_ROOT", str(tmp_path))

    def _writes_garbage(q, artifact_dir_root):
        Path(artifact_dir_root).mkdir(parents=True, exist_ok=True)
        (Path(artifact_dir_root) / "manifest.json").write_text(
            "{not valid json", encoding="utf-8"
        )
        return {"run_id": q.get("external_run_id"), "cost_usd": 0.0}

    _invoke_actor(
        run_id=run_id,
        allowed=[{"document_id": "d1", "classification": "PUBLIC_SYNTHETIC", "chunks": []}],
        blocked_count=3,
        run_one_query_behavior=_writes_garbage,
    )

    error_json = _read_error_json(db_path, run_id)
    assert error_json["uploaded_documents_used"] == 1
    assert error_json["uploaded_documents_blocked"] == 3
    assert "manifest_invalid" in error_json["error"]


def test_run_request_document_ids_cap_rejects_21(auth_disabled, db_path: Path):
    """RunRequest.document_ids max_length=20 → POST /runs with 21 ids returns 422."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from polaris_v6.api.app import create_app

    client = TestClient(create_app())
    response = client.post(
        "/runs",
        json={
            "template": "clinical",
            "question": "test question with sufficient length",
            "document_ids": [f"d_{i}" for i in range(21)],
        },
    )
    assert response.status_code == 422
    detail = response.json().get("detail", [])
    assert any("document_ids" in str(item) for item in detail)


def test_run_request_document_ids_accepts_20(auth_disabled, db_path: Path):
    """20 document_ids accepted (boundary inclusive)."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from polaris_v6.api.app import create_app

    client = TestClient(create_app())
    # 20 ids → upload-resolver may 400 since the docs don't actually exist,
    # but the request must NOT 422 on the schema validation.
    response = client.post(
        "/runs",
        json={
            "template": "clinical",
            "question": "test question with sufficient length",
            "document_ids": [f"d_{i}" for i in range(20)],
        },
    )
    assert response.status_code != 422
