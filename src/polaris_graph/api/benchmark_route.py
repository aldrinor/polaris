"""FastAPI route for slice 005 BEAT-BOTH benchmark scoreboard serving.

Per `.codex/slices/slice_005/architecture_proposal.md` §"benchmark_route".

GET /api/benchmark/{benchmark_id}/scoreboard  -> Scoreboard JSON
GET /api/benchmark/{benchmark_id}/report      -> report.html
GET /api/benchmark/{benchmark_id}/summary     -> summary.md

The route reads pre-computed artifacts from a results directory laid
out by scripts/run_benchmark.py:
    benchmark_results/
      <benchmark_id>/
        scoreboard.json
        summary.md
        report.html

POST endpoints (re-running benchmarks via HTTP) are intentionally
out of scope — benchmarks are operator-triggered via CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse


router = APIRouter(tags=["benchmark"])


# ---------------------------------------------------------------------------
# Dependency: results-directory injection
# ---------------------------------------------------------------------------

def get_results_root() -> Path | None:
    """Returns the root directory containing per-benchmark subdirs.

    None when not configured (POLARIS_BENCHMARK_RESULTS_DIR unset).
    Tests override via app.dependency_overrides.
    """
    return None


def _safe_benchmark_id(benchmark_id: str) -> str:
    """Reject path-traversal attempts in URL params."""
    if "/" in benchmark_id or "\\" in benchmark_id or ".." in benchmark_id:
        raise HTTPException(
            status_code=400,
            detail={"error": True, "code": "invalid_benchmark_id"},
        )
    return benchmark_id


def _resolve_artifact(
    results_root: Path | None,
    benchmark_id: str,
    filename: str,
) -> Path:
    if results_root is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": True,
                "code": "benchmark_results_unavailable",
                "message": (
                    "POLARIS_BENCHMARK_RESULTS_DIR not configured. Set the "
                    "env var to point at the results root."
                ),
            },
        )
    safe_id = _safe_benchmark_id(benchmark_id)
    artifact = results_root / safe_id / filename
    if not artifact.exists() or not artifact.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "error": True,
                "code": "benchmark_artifact_not_found",
                "message": (
                    f"benchmark_id={benchmark_id!r} has no {filename}. "
                    f"Run scripts/run_benchmark.py first."
                ),
            },
        )
    return artifact


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/benchmark/{benchmark_id}/scoreboard")
def get_scoreboard(
    benchmark_id: str,
    results_root: Path | None = Depends(get_results_root),
) -> dict[str, Any]:
    """Return scoreboard.json as parsed JSON."""
    path = _resolve_artifact(results_root, benchmark_id, "scoreboard.json")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/benchmark/{benchmark_id}/report", response_class=HTMLResponse)
def get_report_html(
    benchmark_id: str,
    results_root: Path | None = Depends(get_results_root),
) -> HTMLResponse:
    """Return report.html as text/html."""
    path = _resolve_artifact(results_root, benchmark_id, "report.html")
    return HTMLResponse(content=path.read_text(encoding="utf-8"))


@router.get("/benchmark/{benchmark_id}/summary", response_class=PlainTextResponse)
def get_summary_md(
    benchmark_id: str,
    results_root: Path | None = Depends(get_results_root),
) -> PlainTextResponse:
    """Return summary.md as text/plain."""
    path = _resolve_artifact(results_root, benchmark_id, "summary.md")
    return PlainTextResponse(
        content=path.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.get("/benchmark/health")
def get_benchmark_health(
    results_root: Path | None = Depends(get_results_root),
) -> dict[str, Any]:
    """Liveness + which benchmarks are available."""
    available: list[str] = []
    if results_root is not None and results_root.is_dir():
        for child in results_root.iterdir():
            if child.is_dir() and (child / "scoreboard.json").exists():
                available.append(child.name)
    return {
        "status": "ok",
        "slice": "slice_005_beat_both_benchmark",
        "results_root": str(results_root) if results_root else None,
        "available_benchmarks": sorted(available),
    }
