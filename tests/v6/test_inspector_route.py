"""GET /api/inspector/runs/{run_id} — v6 live-inspector AuditIR route.

I-rdy-008 (#504) slice 1. Covers the 5 resolution outcomes: unknown run,
not-completed run, abort run, completed-but-unloadable run, and a loadable
completed run. The loadable case builds a complete minimal artifact_dir under
tmp_path — clean-checkout reproducible, no dependency on the gitignored
outputs/ tree (Codex brief iter-1 P1).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polaris_v6.queue import run_store

_QUESTION = "What does the latest evidence show on this topic?"


def _write_minimal_artifact_dir(d: Path) -> Path:
    """A complete minimal artifact_dir that ``load_audit_ir()`` accepts.

    Writes exactly the 5 loader-required files with the keys
    ``src/polaris_graph/audit_ir/loader.py`` requires — no more.
    """
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": "manifest_run_1",
                "slug": "inspector_test_slug",
                "status": "success",
                "question": _QUESTION,
                "protocol_sha256": "0" * 64,
                "completeness": {"covered_fraction": 1.0},
                "evaluator_gate": {"gate_class": "release", "release_allowed": True},
                "corpus": {"count": 1, "tier_fractions": {"T1": 1.0}},
                "frame_coverage_report": {"entries": [], "by_status": {}},
            }
        ),
        encoding="utf-8",
    )
    (d / "report.md").write_text("# Research report\n\nMinimal.\n", encoding="utf-8")
    (d / "bibliography.json").write_text("[]", encoding="utf-8")
    (d / "contradictions.json").write_text("[]", encoding="utf-8")
    (d / "verification_details.json").write_text(
        json.dumps({"sections": [], "totals": {}}), encoding="utf-8"
    )
    return d


@pytest.fixture
def client(tmp_path, monkeypatch):
    """TestClient on a fresh per-test run-store DB.

    POLARIS_V6_RUN_DB is set BEFORE create_app() so both the seeding calls and
    the route resolve to the same temp DB, never state/v6_runs.sqlite.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    monkeypatch.setenv("POLARIS_V6_RUN_DB", str(tmp_path / "runs.sqlite"))
    run_store.init_db()
    return TestClient(create_app())


def test_unknown_run_returns_404(client):
    response = client.get("/api/inspector/runs/no_such_run")
    assert response.status_code == 404


def test_not_completed_run_returns_409(client):
    run_store.insert_run("queued_run", "clinical", _QUESTION)
    response = client.get("/api/inspector/runs/queued_run")
    assert response.status_code == 409


def test_abort_run_returns_422(client):
    run_store.insert_run("abort_run", "policy", _QUESTION)
    run_store.mark_aborted(
        "abort_run",
        pipeline_status="abort_corpus_inadequate",
        abort_reason="corpus fails T1 threshold",
    )
    response = client.get("/api/inspector/runs/abort_run")
    assert response.status_code == 422


def test_completed_run_missing_artifact_dir_returns_404(client, tmp_path):
    run_store.insert_run("nodir_run", "clinical", _QUESTION)
    run_store.set_pipeline_meta(
        "nodir_run", artifact_dir=str(tmp_path / "artifacts" / "does_not_exist")
    )
    run_store.mark_completed("nodir_run", {}, pipeline_status="success")
    response = client.get("/api/inspector/runs/nodir_run")
    assert response.status_code == 404


def test_loadable_completed_run_returns_200_audit_ir(client, tmp_path):
    artifact_dir = _write_minimal_artifact_dir(tmp_path / "artifacts" / "good_run")
    run_store.insert_run("good_run", "clinical", _QUESTION)
    run_store.set_pipeline_meta("good_run", artifact_dir=str(artifact_dir))
    run_store.mark_completed("good_run", {}, pipeline_status="success")

    response = client.get("/api/inspector/runs/good_run")
    assert response.status_code == 200, response.text
    body = response.json()
    # Faithful AuditIR JSON — top-level run_id is the manifest run_id, plus the
    # canonical IR blocks the rich surfaces project from.
    assert body["run_id"] == "manifest_run_1"
    assert body["ir_schema_version"]
    assert "manifest" in body
    assert "bibliography" in body
    assert "verified_report" in body
