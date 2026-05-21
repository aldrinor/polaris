"""Tests for the F15 bundle export endpoint."""

from __future__ import annotations

import pytest


@pytest.fixture
def client():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_bundle_returns_404_for_unknown_run(client):
    response = client.get("/runs/does_not_exist/bundle")
    assert response.status_code == 404


def test_bundle_returns_clinical_golden_run(client):
    response = client.get("/runs/golden_clinical_001/bundle")
    assert response.status_code == 200
    body = response.json()
    assert body["contract_version"] == "1.0"
    assert body["run_id"] == "golden_clinical_001"
    assert body["template"] == "clinical"
    assert body["family_segregation_passed"] is True
    assert body["pipeline_status"] == "success"
    assert len(body["evidence_pool"]) >= 1


def test_bundle_returns_contradiction_golden_run(client):
    response = client.get("/runs/golden_housing_002/bundle")
    assert response.status_code == 200
    body = response.json()
    assert body["template"] == "policy"
    assert len(body["contradictions"]) == 1
    assert body["contradictions"][0]["resolution"] == "noted_both"


def test_bundle_returns_abort_run(client):
    response = client.get("/runs/golden_abort_003/bundle")
    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_status"] == "abort_no_verified_sections"
    assert body["verified_sentences"] == []


# ─── I-cd-020 (#630) Option D — real-run 404 disambiguation ────────────────


@pytest.fixture
def auth_disabled(monkeypatch):
    monkeypatch.setenv("POLARIS_AUTH_DISABLED", "1")


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    from polaris_v6.queue import run_store

    db = tmp_path / "runs.sqlite"
    monkeypatch.setenv(run_store.ENV_DB_PATH, str(db))
    run_store.init_db(str(db))
    return db


def _seed_completed_run(db_path, run_id: str, artifact_dir: str):
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO runs (run_id, template, question, lifecycle_status, "
            "queued_at, started_at, finished_at, artifact_dir, "
            "pipeline_status, cancel_requested) VALUES (?,?,?,?,?,?,?,?,?,0)",
            (
                run_id,
                "clinical",
                "Q",
                "completed",
                "2026-05-20T00:00:00Z",
                "2026-05-20T00:00:00Z",
                "2026-05-20T00:05:00Z",
                artifact_dir,
                "success",
            ),
        )
        conn.commit()
    finally:
        conn.close()


def test_bundle_real_run_missing_artifacts_returns_404(
    auth_disabled, db_path, tmp_path,
):
    """I-cd-680 (Codex Option B): a real completed run is now resolved to a
    typed EvidenceContract via the slice-chain — the old #630 '404 pointing
    to bundle.tar.gz' behavior is replaced. A run whose artifact_dir is
    missing the required canonical files (no manifest.json) → 404 'missing
    required files', distinct from an unknown-id 404.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from polaris_v6.api.app import create_app

    run_id = "real_run_uuid_xyz"
    artifact_dir = tmp_path / run_id
    artifact_dir.mkdir(parents=True)  # empty — no manifest.json
    _seed_completed_run(db_path, run_id, str(artifact_dir))

    client = TestClient(create_app())
    response = client.get(f"/runs/{run_id}/bundle")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert run_id in detail
    assert "missing required files" in detail


def test_bundle_unknown_run_returns_generic_404(auth_disabled, db_path):
    """Unknown UUID gets the original golden-fixtures 404 — distinguishable
    from the real-run enriched 404.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from polaris_v6.api.app import create_app

    client = TestClient(create_app())
    response = client.get("/runs/totally_unknown_id/bundle")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "Available golden fixtures" in detail
    assert "bundle.tar.gz" not in detail
