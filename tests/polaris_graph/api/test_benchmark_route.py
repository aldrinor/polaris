"""Tests for the benchmark FastAPI route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from polaris_graph.api.benchmark_route import get_results_root, router


@pytest.fixture
def app() -> FastAPI:
    a = FastAPI()
    a.include_router(router, prefix="/api")
    return a


@pytest.fixture
def results_root_with_artifacts(tmp_path: Path) -> Path:
    """Create a results root with one benchmark's artifacts in it."""
    bench_dir = tmp_path / "test_bench_v1"
    bench_dir.mkdir()
    (bench_dir / "scoreboard.json").write_text(
        json.dumps({"benchmark_id": "test_bench_v1", "polaris_wins": 5}),
        encoding="utf-8",
    )
    (bench_dir / "summary.md").write_text(
        "# Summary\nPOLARIS won 5 comparisons.\n",
        encoding="utf-8",
    )
    (bench_dir / "report.html").write_text(
        "<html><body><h1>Report</h1></body></html>",
        encoding="utf-8",
    )
    return tmp_path


def _override(app: FastAPI, root: Path | None):
    app.dependency_overrides[get_results_root] = lambda: root


# ---------- Health ----------

def test_health_no_results_root(app: FastAPI):
    _override(app, None)
    r = TestClient(app).get("/api/benchmark/health")
    assert r.status_code == 200
    body = r.json()
    assert body["slice"] == "slice_005_beat_both_benchmark"
    assert body["results_root"] is None
    assert body["available_benchmarks"] == []


def test_health_with_artifacts_lists_benchmarks(
    app: FastAPI, results_root_with_artifacts: Path
):
    _override(app, results_root_with_artifacts)
    r = TestClient(app).get("/api/benchmark/health")
    assert r.status_code == 200
    body = r.json()
    assert "test_bench_v1" in body["available_benchmarks"]


# ---------- 503 (no results root configured) ----------

def test_get_scoreboard_503_when_no_root(app: FastAPI):
    _override(app, None)
    r = TestClient(app).get("/api/benchmark/test_bench/scoreboard")
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "benchmark_results_unavailable"


def test_get_report_503_when_no_root(app: FastAPI):
    _override(app, None)
    r = TestClient(app).get("/api/benchmark/test_bench/report")
    assert r.status_code == 503


def test_get_summary_503_when_no_root(app: FastAPI):
    _override(app, None)
    r = TestClient(app).get("/api/benchmark/test_bench/summary")
    assert r.status_code == 503


# ---------- 400 (path traversal) ----------

def test_get_scoreboard_rejects_path_traversal(
    app: FastAPI, results_root_with_artifacts: Path
):
    _override(app, results_root_with_artifacts)
    # ".." in path forces FastAPI to URL-decode and pass to handler
    r = TestClient(app).get("/api/benchmark/..%2Fetc/scoreboard")
    # Either 400 from our validator or 404 from FastAPI; both are safe
    assert r.status_code in (400, 404)


# ---------- 404 (benchmark not found) ----------

def test_get_scoreboard_404_when_benchmark_missing(
    app: FastAPI, results_root_with_artifacts: Path
):
    _override(app, results_root_with_artifacts)
    r = TestClient(app).get("/api/benchmark/no_such_bench/scoreboard")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "benchmark_artifact_not_found"


def test_get_scoreboard_404_when_artifact_missing(
    app: FastAPI, tmp_path: Path
):
    """Benchmark dir exists but scoreboard.json missing -> 404."""
    bench = tmp_path / "incomplete_bench"
    bench.mkdir()
    (bench / "summary.md").write_text("only summary", encoding="utf-8")
    _override(app, tmp_path)
    r = TestClient(app).get("/api/benchmark/incomplete_bench/scoreboard")
    assert r.status_code == 404


# ---------- Happy paths ----------

def test_get_scoreboard_returns_json(
    app: FastAPI, results_root_with_artifacts: Path
):
    _override(app, results_root_with_artifacts)
    r = TestClient(app).get("/api/benchmark/test_bench_v1/scoreboard")
    assert r.status_code == 200
    body = r.json()
    assert body["benchmark_id"] == "test_bench_v1"
    assert body["polaris_wins"] == 5


def test_get_report_returns_html(
    app: FastAPI, results_root_with_artifacts: Path
):
    _override(app, results_root_with_artifacts)
    r = TestClient(app).get("/api/benchmark/test_bench_v1/report")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<h1>Report</h1>" in r.text


def test_get_summary_returns_markdown(
    app: FastAPI, results_root_with_artifacts: Path
):
    _override(app, results_root_with_artifacts)
    r = TestClient(app).get("/api/benchmark/test_bench_v1/summary")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert "POLARIS won 5" in r.text
