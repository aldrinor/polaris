"""I-cd-017 (#627) — pin-replay backend route tests.

Covers: GET /runs/{run_id}/pins (list) + GET /runs/{run_id}/pins/{date}
(single) with synthesis from real manifest.json shape variants:

* success-path generator block (sections_kept + sentences_dropped)
* abort_no_verified_sections generator block (sections_total +
  sections_dropped, no sentences_dropped — confirmed at
  scripts/run_honest_sweep_r3.py:2468-2473).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def auth_disabled(monkeypatch):
    monkeypatch.setenv("POLARIS_AUTH_DISABLED", "1")


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch) -> Path:
    from polaris_v6.queue import run_store

    db = tmp_path / "runs.sqlite"
    monkeypatch.setenv(run_store.ENV_DB_PATH, str(db))
    run_store.init_db(str(db))
    return db


def _seed_run(
    db_path: Path,
    *,
    run_id: str,
    query: str,
    query_slug: str,
    finished_at: str,
    pipeline_status: str = "success",
    artifact_dir: str | None = None,
    template: str = "clinical",
    lifecycle_status: str = "completed",
) -> None:
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO runs (run_id, template, question, lifecycle_status, "
            "queued_at, started_at, finished_at, query_slug, artifact_dir, "
            "pipeline_status, cancel_requested) VALUES (?,?,?,?,?,?,?,?,?,?,0)",
            (
                run_id,
                template,
                query,
                lifecycle_status,
                "2026-01-01T00:00:00Z",
                "2026-01-01T00:00:00Z",
                finished_at,
                query_slug,
                artifact_dir,
                pipeline_status,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_manifest(artifact_dir: Path, generator: dict[str, Any], status: str = "success") -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "manifest.json").write_text(
        json.dumps({"status": status, "generator": generator}),
        encoding="utf-8",
    )


@pytest.fixture
def client(auth_disabled, db_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from polaris_v6.api.app import create_app

    return TestClient(create_app())


def test_list_pins_success_path(client, tmp_path: Path, db_path: Path):
    """200 list response for completed run with success-path manifest."""
    artifact_dir = tmp_path / "run_a"
    _write_manifest(
        artifact_dir,
        generator={
            "outline_sections": ["a", "b", "c", "d", "e"],
            "sections_kept": 4,
            "sentences_verified": 14,
            "sentences_dropped": 45,
        },
    )
    _seed_run(
        db_path,
        run_id="r_a",
        query="tirzepatide vs semaglutide",
        query_slug="clinical_tirzepatide",
        finished_at="2026-05-01T12:30:00Z",
        artifact_dir=str(artifact_dir),
    )

    response = client.get("/runs/r_a/pins")
    assert response.status_code == 200
    pins = response.json()
    assert len(pins) == 1
    assert pins[0]["run_id"] == "r_a"
    assert pins[0]["pin_date"] == "2026-05-01"
    assert pins[0]["verdict"] == "success"
    assert pins[0]["section_count_kept"] == 4
    assert pins[0]["section_count_dropped"] == 1
    assert pins[0]["verified_sentence_count"] == 14
    assert abs(pins[0]["pass_rate"] - (14 / 59)) < 0.001
    assert pins[0]["retracted_source_ids"] is None


def test_list_pins_abort_no_verified_shape_variant(client, tmp_path: Path, db_path: Path):
    """Iter-2 P1.2: abort_no_verified_sections generator shape has
    sections_total + sections_dropped, NO sections_kept / sentences_dropped.
    """
    artifact_dir = tmp_path / "run_abort"
    _write_manifest(
        artifact_dir,
        generator={
            "outline_sections": ["a", "b", "c"],
            "sections_total": 3,
            "sections_dropped": 3,
            "sentences_verified": 0,
        },
        status="abort_no_verified_sections",
    )
    _seed_run(
        db_path,
        run_id="r_abort",
        query="tirzepatide vs semaglutide",
        query_slug="clinical_tirzepatide",
        finished_at="2026-05-02T11:00:00Z",
        pipeline_status="abort_no_verified_sections",
        artifact_dir=str(artifact_dir),
    )

    response = client.get("/runs/r_abort/pins")
    assert response.status_code == 200
    pins = response.json()
    assert len(pins) == 1
    assert pins[0]["verdict"] == "abort_no_verified_sections"
    assert pins[0]["section_count_kept"] == 0
    assert pins[0]["section_count_dropped"] == 3
    assert pins[0]["verified_sentence_count"] == 0
    assert pins[0]["pass_rate"] == 0.0


def test_list_pins_multi_run_chronological_ordering(client, tmp_path: Path, db_path: Path):
    """Series of same query_slug runs returned in finished_at ASC order."""
    for idx, (run_id, finished_at, kept, verified, dropped) in enumerate(
        [
            ("r_old", "2026-03-01T10:00:00Z", 3, 10, 30),
            ("r_mid", "2026-04-15T10:00:00Z", 4, 15, 20),
            ("r_new", "2026-05-15T10:00:00Z", 5, 22, 10),
        ]
    ):
        artifact_dir = tmp_path / f"d_{idx}"
        _write_manifest(
            artifact_dir,
            generator={
                "outline_sections": ["a"] * 5,
                "sections_kept": kept,
                "sentences_verified": verified,
                "sentences_dropped": dropped,
            },
        )
        _seed_run(
            db_path,
            run_id=run_id,
            query="Q",
            query_slug="series_query",
            finished_at=finished_at,
            artifact_dir=str(artifact_dir),
        )

    response = client.get("/runs/r_mid/pins")
    assert response.status_code == 200
    pins = response.json()
    assert [p["pin_date"] for p in pins] == ["2026-03-01", "2026-04-15", "2026-05-15"]


def test_list_pins_unknown_run_returns_404(client, db_path: Path):
    response = client.get("/runs/missing/pins")
    assert response.status_code == 404


def test_list_pins_excludes_in_progress_and_aborted_corpus(
    client, tmp_path: Path, db_path: Path
):
    """Only completed × qualifying-pipeline-status runs are pin-eligible."""
    artifact_dir = tmp_path / "anchor"
    _write_manifest(
        artifact_dir,
        generator={
            "outline_sections": ["a"],
            "sections_kept": 1,
            "sentences_verified": 5,
            "sentences_dropped": 5,
        },
    )
    _seed_run(
        db_path,
        run_id="r_anchor",
        query="Q",
        query_slug="q_slug",
        finished_at="2026-05-10T00:00:00Z",
        artifact_dir=str(artifact_dir),
    )
    _seed_run(
        db_path,
        run_id="r_in_progress",
        query="Q",
        query_slug="q_slug",
        finished_at="2026-05-11T00:00:00Z",
        lifecycle_status="in_progress",
        pipeline_status=None,
        artifact_dir=None,
    )
    _seed_run(
        db_path,
        run_id="r_corpus_abort",
        query="Q",
        query_slug="q_slug",
        finished_at="2026-05-12T00:00:00Z",
        pipeline_status="abort_corpus_inadequate",
        artifact_dir=None,
    )

    response = client.get("/runs/r_anchor/pins")
    assert response.status_code == 200
    pins = response.json()
    assert [p["run_id"] for p in pins] == ["r_anchor"]


def test_get_pin_by_date_exact_match(client, tmp_path: Path, db_path: Path):
    artifact_dir = tmp_path / "exact"
    _write_manifest(
        artifact_dir,
        generator={
            "outline_sections": ["a", "b"],
            "sections_kept": 2,
            "sentences_verified": 8,
            "sentences_dropped": 2,
        },
    )
    _seed_run(
        db_path,
        run_id="r_e",
        query="Q",
        query_slug="q",
        finished_at="2026-05-20T15:00:00Z",
        artifact_dir=str(artifact_dir),
    )

    response = client.get("/runs/r_e/pins/2026-05-20")
    assert response.status_code == 200
    assert response.json()["pin_date"] == "2026-05-20"


def test_get_pin_by_date_wrong_date_returns_404(client, tmp_path: Path, db_path: Path):
    artifact_dir = tmp_path / "wrong"
    _write_manifest(
        artifact_dir,
        generator={
            "outline_sections": ["a"],
            "sections_kept": 1,
            "sentences_verified": 5,
            "sentences_dropped": 5,
        },
    )
    _seed_run(
        db_path,
        run_id="r_w",
        query="Q",
        query_slug="q",
        finished_at="2026-05-20T00:00:00Z",
        artifact_dir=str(artifact_dir),
    )

    response = client.get("/runs/r_w/pins/2026-05-21")
    assert response.status_code == 404


def test_get_pin_by_date_malformed_returns_422(client, db_path: Path):
    response = client.get("/runs/r_w/pins/not-a-date")
    assert response.status_code == 422


def test_list_pins_includes_partial_qwen_advisory(client, tmp_path: Path, db_path: Path):
    """Codex diff iter-2 P1: partial_qwen_advisory MUST be pin-eligible.

    pipeline-A maps ok_qwen_advisory → partial_qwen_advisory; the v6 actor
    persists it as a completed run. Excluding it would 404 a real run.
    """
    artifact_dir = tmp_path / "qwen_advisory"
    _write_manifest(
        artifact_dir,
        generator={
            "outline_sections": ["a", "b", "c"],
            "sections_kept": 2,
            "sentences_verified": 10,
            "sentences_dropped": 6,
        },
        status="partial_qwen_advisory",
    )
    _seed_run(
        db_path,
        run_id="r_qwen",
        query="Q",
        query_slug="q",
        finished_at="2026-05-20T00:00:00Z",
        pipeline_status="partial_qwen_advisory",
        artifact_dir=str(artifact_dir),
    )

    response = client.get("/runs/r_qwen/pins")
    assert response.status_code == 200
    pins = response.json()
    assert len(pins) == 1
    # verdict is collapsed to "success" — only abort_no_verified_sections
    # keeps its own verdict in the PinSnapshot frontend contract.
    assert pins[0]["verdict"] == "success"

    response = client.get("/runs/r_qwen/pins/2026-05-20")
    assert response.status_code == 200


def test_pass_rate_zero_denominator_returns_zero(client, tmp_path: Path, db_path: Path):
    """sentences_verified=0 AND sentences_dropped=0 → pass_rate=0.0 not NaN."""
    artifact_dir = tmp_path / "zero"
    _write_manifest(
        artifact_dir,
        generator={
            "outline_sections": ["a"],
            "sections_total": 1,
            "sections_dropped": 1,
            "sentences_verified": 0,
        },
        status="abort_no_verified_sections",
    )
    _seed_run(
        db_path,
        run_id="r_z",
        query="Q",
        query_slug="q",
        finished_at="2026-05-20T00:00:00Z",
        pipeline_status="abort_no_verified_sections",
        artifact_dir=str(artifact_dir),
    )

    response = client.get("/runs/r_z/pins/2026-05-20")
    assert response.status_code == 200
    assert response.json()["pass_rate"] == 0.0
