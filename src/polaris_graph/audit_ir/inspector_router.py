"""FastAPI router for the Evidence Inspector.

Mounted into the existing live_server FastAPI app. Per FINAL_PLAN.md
(Phase A): the Evidence Inspector is the canonical primary renderer
over the AuditIR.

Routes:
  GET  /api/inspector/runs                       -> list available runs
  GET  /api/inspector/runs/{slug}                -> full AuditIR JSON
  GET  /api/inspector/runs/{slug}/report.md      -> raw markdown
  GET  /inspector                                -> redirect to canonical demo
  GET  /inspector/{slug}                         -> HTML shell (5-view scaffold)

Phase A intentionally serves controlled-access traffic only (no auth on
this router yet; the live_server existing auth will gate access in
Phase B once queue+concurrency lands).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse

from src.polaris_graph.audit_ir.loader import (
    AuditIRSchemaError,
    load_audit_ir,
)
from src.polaris_graph.audit_ir.registry import (
    CANONICAL_DEMO_SLUG,
    find_run_by_slug,
    list_available_runs,
)
from src.polaris_graph.audit_ir.serializer import to_json_dict

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "scripts" / "templates"
INSPECTOR_HTML_PATH = TEMPLATES_DIR / "inspector_shell.html"


@router.get("/api/inspector/runs")
async def list_runs() -> dict:
    """List every discoverable V30 Phase-2 audit artifact."""
    runs = list_available_runs()
    return {
        "count": len(runs),
        "canonical_demo_slug": CANONICAL_DEMO_SLUG,
        "runs": [
            {
                "slug": r.slug,
                "run_id": r.run_id,
                "domain": r.domain,
                "status": r.status,
                "cost_usd": r.cost_usd,
                "word_count": r.word_count,
                "contradictions_found": r.contradictions_found,
                "release_allowed": r.release_allowed,
                "created_at_iso": r.created_at_iso,
            }
            for r in runs
        ],
    }


@router.get("/api/inspector/runs/{slug}")
async def get_run(slug: str) -> dict:
    """Return the full AuditIR for a run as a JSON-safe dict.

    M-3 (Inspector view 1) and downstream views consume this. Heavy payload —
    expected to be cached client-side per page load.
    """
    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown run slug: {slug}")
    try:
        ir = load_audit_ir(summary.artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError) as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load IR: {exc}")
    return to_json_dict(ir)


@router.get("/api/inspector/runs/{slug}/report.md", response_class=PlainTextResponse)
async def get_report_markdown(slug: str) -> str:
    """Return the raw report.md for the run. Used by the markdown renderer."""
    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown run slug: {slug}")
    report_path = summary.artifact_dir / "report.md"
    if not report_path.exists():
        raise HTTPException(status_code=500, detail="report.md missing for run")
    return report_path.read_text(encoding="utf-8")


@router.get("/inspector", response_class=HTMLResponse)
async def inspector_root() -> RedirectResponse:
    """Redirect to the canonical demo run for Phase A."""
    return RedirectResponse(url=f"/inspector/{CANONICAL_DEMO_SLUG}")


@router.get("/inspector/{slug}", response_class=HTMLResponse)
async def inspector_page(slug: str) -> HTMLResponse:
    """Serve the Evidence Inspector HTML shell for a given run.

    The shell is a 5-view scaffold (Report / Contradictions / Frame Coverage /
    Methods / Tier Mix). Phase A wires View 1 in M-3; Views 2-5 wire in M-4..M-7.
    """
    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown run slug: {slug}")
    if not INSPECTOR_HTML_PATH.exists():
        raise HTTPException(status_code=500, detail="inspector_shell.html missing")
    html = INSPECTOR_HTML_PATH.read_text(encoding="utf-8")
    html = html.replace("{{ run_slug }}", slug)
    html = html.replace("{{ run_id }}", summary.run_id)
    return HTMLResponse(content=html)
