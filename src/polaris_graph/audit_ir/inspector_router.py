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

from pydantic import BaseModel, Field

from src.polaris_graph.audit_ir.job_queue import (
    JobQueue,
    JobQueueError,
    job_to_dict,
)
from src.polaris_graph.audit_ir.job_runner import (
    MockJobRunner,
    list_runners,
    register_runner,
)
from src.polaris_graph.audit_ir.loader import (
    AuditIRSchemaError,
    load_audit_ir,
)
from src.polaris_graph.audit_ir.registry import (
    CANONICAL_DEMO_SLUG,
    REPO_ROOT,
    find_run_by_id,
    find_run_by_slug,
    list_available_runs,
)
from src.polaris_graph.audit_ir.serializer import to_json_dict

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "scripts" / "templates"
INSPECTOR_HTML_PATH = TEMPLATES_DIR / "inspector_shell.html"

# ---------------------------------------------------------------------------
# Job queue lifecycle (Phase B M-8)
# ---------------------------------------------------------------------------

# In-process JobQueue + worker. Phase A scope: single worker. Phase C upgrades
# to a shared queue + multi-worker pool.
_JOB_DB_PATH = REPO_ROOT / "state" / "polaris_jobs.sqlite"
_job_queue: JobQueue | None = None


def get_job_queue() -> JobQueue:
    """Lazy-init the JobQueue. Tests patch this with a tmp_path queue."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue(_JOB_DB_PATH)
        # Register the mock runner so tests + the live demo have something
        # to enqueue against without a full V30 sweep. M-9 will register
        # the V30JobRunner on top of this.
        register_runner(MockJobRunner(template_id="mock", total_seconds=2.0, step_seconds=0.2))
    return _job_queue


def _set_job_queue_for_tests(queue: JobQueue | None) -> None:
    """Test helper: replace the singleton queue."""
    global _job_queue
    _job_queue = queue


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

    The bundle contains the canonical V30 artifact files + INDEX.txt
    (human-readable header with run identity, model provenance, gate
    decisions) + MANIFEST.SHA256 (per-file digests for tamper-evidence).

    Phase A: builds the ZIP in-memory from the artifact directory.
    Phase B: pre-builds + caches per-run bundles in object storage with
    detached signatures.

    Codex M-6 review fixes integrated:
    - Fails loud (500) if any canonical-required file is missing
    - INDEX.txt includes protocol_sha256, model IDs, gate decisions,
      file digests
    - MANIFEST.SHA256 carries SHA-256 of each bundled file
    - Adds run_log.txt + live_corpus_dump.json + cost_ledger.jsonl
      (optional, included if present)
    """
    import hashlib
    import io
    import json
    import zipfile

    from fastapi.responses import StreamingResponse

    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown run slug: {slug}")
    artifact_dir = summary.artifact_dir

    # Canonical-required files: must be present for the bundle to be valid.
    # Codex M-6 fix: fail loud if any are missing.
    required_files = [
        "report.md",
        "manifest.json",
        "bibliography.json",
        "contradictions.json",
        "verification_details.json",
    ]
    # Optional canonical artifacts: included if present.
    optional_files = [
        "protocol.json",
        "evaluator_rule_checks.json",
        "qwen_judge_output.json",
        "completeness.json",
        "corpus_adequacy.json",
        "corpus_approval.json",
        "human_gap_tasks.json",
        # Codex M-6 fix: add scope SHA + stage trail + corpus provenance.
        "run_log.txt",
        "live_corpus_dump.json",
        "cost_ledger.jsonl",
    ]

    missing_required = [f for f in required_files if not (artifact_dir / f).exists()]
    if missing_required:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Audit bundle cannot be built: required artifact files "
                f"missing for run {summary.run_id}: {missing_required}"
            ),
        )

    # Pull additional provenance fields from manifest for the INDEX header.
    try:
        with (artifact_dir / "manifest.json").open("r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail=f"manifest.json unreadable: {exc}")

    eval_rules = {}
    eval_rules_path = artifact_dir / "evaluator_rule_checks.json"
    if eval_rules_path.exists():
        try:
            with eval_rules_path.open("r", encoding="utf-8") as f:
                eval_rules = json.load(f)
        except (OSError, json.JSONDecodeError):
            eval_rules = {}

    eval_gate = manifest.get("evaluator_gate", {})
    if not isinstance(eval_gate, dict):
        eval_gate = {"gate_class": str(eval_gate)}
    adequacy = manifest.get("adequacy", {}) or {}
    corpus = manifest.get("corpus", {}) or {}

    bundle_files = required_files + optional_files

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # First pass: compute digests + write each file
        digests: list[tuple[str, int, str]] = []
        for fname in bundle_files:
            path = artifact_dir / fname
            if not path.exists():
                continue
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            digests.append((fname, len(data), digest))
            zf.writestr(fname, data)

        # MANIFEST.SHA256 — per-file digests for tamper-evidence.
        sha_lines = [f"{digest}  {fname}" for (fname, _size, digest) in digests]
        zf.writestr("MANIFEST.SHA256", "\n".join(sha_lines) + "\n")

        # INDEX.txt — comprehensive procurement header.
        index_lines = [
            "POLARIS V30 Phase-2 Audit Bundle",
            "================================",
            "",
            "RUN IDENTITY",
            "------------",
            f"Run slug:           {summary.slug}",
            f"Run ID:             {summary.run_id}",
            f"Protocol SHA-256:   {manifest.get('protocol_sha256', '—')}",
            f"Status:             {summary.status}",
            f"Created at (ISO):   {summary.created_at_iso or '—'}",
            f"Word count:         {summary.word_count}",
            f"Cost (USD):         {summary.cost_usd:.6f}",
            f"Contradictions:     {summary.contradictions_found}",
            f"Release allowed:    {summary.release_allowed}",
            "",
            "MODEL PROVENANCE",
            "----------------",
            f"Generator family:   {eval_rules.get('generator_family', '—')}",
            f"Generator model:    {eval_rules.get('generator_model', '—')}",
            f"Evaluator family:   {eval_rules.get('evaluator_family', '—')}",
            f"Evaluator model:    {eval_rules.get('evaluator_model', '—')}",
            "",
            "GATE DECISIONS",
            "--------------",
            f"Adequacy:           decision={adequacy.get('decision', '—')}, "
            f"findings_ok={adequacy.get('findings_ok', '—')}/{adequacy.get('findings_total', '—')}",
            f"Corpus approved:    {corpus.get('approved', '—')} "
            f"(material_deviation={corpus.get('material_deviation', '—')}, count={corpus.get('count', '—')})",
            f"Evaluator gate:     class={eval_gate.get('gate_class', '—')}, "
            f"release_allowed={eval_gate.get('release_allowed', '—')}",
            f"Reasons:            {', '.join(str(r) for r in eval_gate.get('reasons', [])) or '—'}",
            f"Rule blockers:      {', '.join(str(r) for r in eval_gate.get('rule_blockers', [])) or '—'}",
            "",
            "BUNDLE FILES + DIGESTS (SHA-256)",
            "--------------------------------",
        ]
        for fname, size, digest in digests:
            index_lines.append(f"  {digest}  {size:>10} bytes  {fname}")
        index_lines.append("")
        index_lines.append(
            "Verify: sha256sum -c MANIFEST.SHA256"
        )
        index_lines.append("")
        index_lines.append(
            "This bundle is the procurement-grade reproducibility artifact. "
            "Every claim in report.md is bound to an evidence_id in "
            "verification_details.json; bibliography.json maps [N] -> "
            "evidence_id; contradictions.json declares disagreements; "
            "manifest.json carries gates, costs, and the protocol_sha256."
        )
        zf.writestr("INDEX.txt", "\n".join(index_lines))

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


# ---------------------------------------------------------------------------
# Job lifecycle endpoints (M-8)
# ---------------------------------------------------------------------------


class EnqueueJobRequest(BaseModel):
    template_id: str = Field(..., description="Job template, e.g. 'mock' (M-8) or 'v30_clinical' (M-9)")
    params: dict = Field(default_factory=dict)


@router.post("/api/inspector/jobs")
async def enqueue_job(req: EnqueueJobRequest) -> dict:
    """Create a new pending job.

    Phase A: only `mock` template_id is supported. M-9 adds `v30_clinical`
    + the rest of the curated template library.
    """
    available = set(list_runners())
    if req.template_id not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template_id={req.template_id!r}. Available: {sorted(available)}",
        )
    queue = get_job_queue()
    job = queue.enqueue(req.template_id, req.params)
    return job_to_dict(job)


@router.get("/api/inspector/jobs")
async def list_jobs(status: str | None = None, limit: int = 100) -> dict:
    queue = get_job_queue()
    try:
        jobs = queue.list_by_status(status=status, limit=limit)
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "count": len(jobs),
        "available_templates": list_runners(),
        "jobs": [job_to_dict(j) for j in jobs],
    }


@router.get("/api/inspector/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    queue = get_job_queue()
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id={job_id}")
    return job_to_dict(job)


@router.post("/api/inspector/jobs/{job_id}/pause")
async def pause_job(job_id: str) -> dict:
    queue = get_job_queue()
    try:
        job = queue.request_pause(job_id)
    except JobQueueError as exc:
        # Surface clearly: 404 for unknown, 409 for state conflict.
        msg = str(exc)
        if "unknown job" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return job_to_dict(job)


@router.post("/api/inspector/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    queue = get_job_queue()
    try:
        job = queue.request_cancel(job_id)
    except JobQueueError as exc:
        msg = str(exc)
        if "unknown job" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return job_to_dict(job)


@router.post("/api/inspector/jobs/{job_id}/resume")
async def resume_job(job_id: str) -> dict:
    queue = get_job_queue()
    try:
        job = queue.resume_paused(job_id)
    except JobQueueError as exc:
        msg = str(exc)
        if "unknown job" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return job_to_dict(job)


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
