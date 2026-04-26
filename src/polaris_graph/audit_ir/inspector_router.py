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

Trust boundary (Codex M-2 review correction):
  This router does NOT enforce auth. The trust boundary in Phase A is
  DEPLOYMENT-LEVEL (controlled-access invite-only environment), NOT
  application-level. Anyone who can reach the live_server can reach the
  inspector. Phase B adds queue + per-route auth + workspace isolation.
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
    find_run_by_id,
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


@router.get("/api/inspector/runs/{slug}/audit-bundle.zip")
async def get_audit_bundle(slug: str):
    """Return a procurement-grade audit bundle as a zip file.

    The bundle contains report.md + manifest.json + bibliography.json +
    contradictions.json + verification_details.json + frame_coverage_report
    (extracted from manifest) + protocol.json + evaluator_rule_checks.json
    + qwen_judge_output.json + a top-level INDEX.txt with run hashes.

    Phase A: streams a zip from the artifact directory at request time.
    Phase B: pre-builds + caches per-run bundles in object storage.
    """
    import io
    import zipfile

    from fastapi.responses import StreamingResponse

    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown run slug: {slug}")
    artifact_dir = summary.artifact_dir

    # Files included in the audit bundle, in canonical order.
    bundle_files = [
        "report.md",
        "manifest.json",
        "bibliography.json",
        "contradictions.json",
        "verification_details.json",
        "protocol.json",
        "evaluator_rule_checks.json",
        "qwen_judge_output.json",
        "completeness.json",
        "corpus_adequacy.json",
        "corpus_approval.json",
        "human_gap_tasks.json",
    ]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # INDEX.txt: human-readable provenance header
        index_lines = [
            f"POLARIS V30 Phase-2 Audit Bundle",
            f"================================",
            f"Run slug:           {summary.slug}",
            f"Run ID:             {summary.run_id}",
            f"Status:             {summary.status}",
            f"Created at (ISO):   {summary.created_at_iso or '—'}",
            f"Word count:         {summary.word_count}",
            f"Cost (USD):         {summary.cost_usd:.6f}",
            f"Contradictions:     {summary.contradictions_found}",
            f"Release allowed:    {summary.release_allowed}",
            f"",
            f"Files in this bundle:",
        ]
        for fname in bundle_files:
            path = artifact_dir / fname
            if path.exists():
                index_lines.append(f"  - {fname} ({path.stat().st_size} bytes)")
        index_lines.append("")
        index_lines.append(
            "This bundle is the procurement-grade reproducibility artifact. "
            "Every claim in report.md is bound to an evidence_id in "
            "verification_details.json; bibliography.json maps [N] -> "
            "evidence_id; contradictions.json declares disagreements; "
            "manifest.json carries gates, costs, and the protocol_sha256."
        )
        zf.writestr("INDEX.txt", "\n".join(index_lines))
        for fname in bundle_files:
            path = artifact_dir / fname
            if path.exists():
                zf.write(path, arcname=fname)

    buf.seek(0)
    headers = {
        "Content-Disposition": (
            f'attachment; filename="polaris-audit-bundle-{summary.slug}.zip"'
        ),
    }
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers=headers,
    )


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
