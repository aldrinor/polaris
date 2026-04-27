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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import (
    HTMLResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)

# Codex M-15b retrofit: every workspace-scoped, upload-scoped,
# job-scoped endpoint gets one of these dependencies. The
# dependency embeds authentication (resolves the caller from API
# key bearer or X-Polaris-Caller test header) AND authorization
# (returns 403 if the caller's org doesn't match the resource's
# owning org). NEW endpoints in this module MUST add the
# appropriate dependency or the M-15b authz invariant is broken.
from src.polaris_graph.audit_ir.auth_middleware import (
    Caller,
    require_authenticated_caller,
    require_job_member,
    require_job_viewer,
    require_upload_member,
    require_upload_viewer,
    require_workspace_admin,
    require_workspace_member,
    require_workspace_viewer,
)

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
_job_worker = None  # type: ignore[var-annotated]
_runners_registered: bool = False


def _ensure_runners_registered() -> None:
    """Codex M-8 review fix: deterministic runner registration runs
    independently of get_job_queue() so cold-start enqueues with no
    prior route hit still validate template_id correctly.

    M-9: also registers V30JobRunner under template_id 'v30_clinical'
    so the sweep can be launched as an asynchronous job.
    """
    global _runners_registered
    if _runners_registered:
        return
    # Mock runner for tests + demo.
    register_runner(MockJobRunner(template_id="mock", total_seconds=2.0, step_seconds=0.2))
    # V30 sweep runner — wraps scripts/run_full_scale_v30_phase2.py
    # as a subprocess and emits cooperative checkpoints per phase.
    try:
        from src.polaris_graph.audit_ir.v30_runner import make_default_v30_runner
        register_runner(make_default_v30_runner())
    except Exception:
        # If the V30 runner can't be constructed (missing script,
        # bad repo layout, etc.), don't crash the queue — just skip.
        # Operators see "v30_clinical not in available_templates" and
        # know to investigate.
        import logging
        logging.getLogger(__name__).warning("V30JobRunner registration failed", exc_info=True)
    _runners_registered = True


def get_job_queue() -> JobQueue:
    """Lazy-init the JobQueue. Tests patch this with a tmp_path queue."""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue(_JOB_DB_PATH)
    _ensure_runners_registered()
    return _job_queue


def get_or_start_job_worker():
    """Codex M-8 review fix: wire a singleton JobWorker so enqueued jobs
    actually run. The worker polls the queue every 0.5s and dispatches to
    registered JobRunners.

    Idempotent: safe to call multiple times. Tests can call
    `_set_job_worker_for_tests(None)` to disable.
    """
    global _job_worker
    if _job_worker is not None and _job_worker.is_alive():
        return _job_worker
    from src.polaris_graph.audit_ir.job_worker import JobWorker
    _job_worker = JobWorker(get_job_queue(), poll_interval_s=0.5)
    _job_worker.start()
    return _job_worker


def _set_job_queue_for_tests(queue: JobQueue | None) -> None:
    """Test helper: replace the singleton queue.

    Also stops any active worker bound to the old queue, since workers
    hold a queue reference and would keep polling the wrong db.
    """
    global _job_queue, _job_worker
    if _job_worker is not None:
        _job_worker.stop(join_timeout=2.0)
        _job_worker = None
    _job_queue = queue


def _set_job_worker_for_tests(worker) -> None:
    """Test helper: replace the singleton worker (or None to disable)."""
    global _job_worker
    if _job_worker is not None and _job_worker is not worker:
        _job_worker.stop(join_timeout=2.0)
    _job_worker = worker


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


# Codex M-16 v2 review fix: /api/inspector/runs/diff MUST be
# declared BEFORE /api/inspector/runs/{slug}. FastAPI matches
# routes in registration order, and the dynamic {slug} pattern
# would otherwise eat the literal "diff" path.
@router.get("/api/inspector/runs/diff")
async def get_run_diff(a_slug: str, b_slug: str) -> dict:
    """Codex M-16: structured diff between two runs.

    Both runs MUST share `slug`. Returns 400 if not (LAW II — diff
    across different audit shapes is meaningless). Returns 404 if
    either slug is unknown.

    Note: run endpoints (M-1..M-7) don't have org_id tagging yet
    (deferred to M-15c), so this endpoint is currently
    unauthenticated like the rest of the run-* surface.
    """
    from src.polaris_graph.audit_ir.loader import (
        AuditIRSchemaError,
        load_audit_ir,
    )
    from src.polaris_graph.audit_ir.run_diff import (
        diff_runs,
        diff_to_dict,
    )
    summary_a = find_run_by_slug(a_slug)
    if summary_a is None:
        raise HTTPException(
            status_code=404, detail=f"unknown run slug: {a_slug}",
        )
    summary_b = find_run_by_slug(b_slug)
    if summary_b is None:
        raise HTTPException(
            status_code=404, detail=f"unknown run slug: {b_slug}",
        )
    try:
        ir_a = load_audit_ir(summary_a.artifact_dir)
        ir_b = load_audit_ir(summary_b.artifact_dir)
    except AuditIRSchemaError as exc:
        raise HTTPException(
            status_code=500, detail=f"cannot load AuditIR: {exc}",
        )
    try:
        d = diff_runs(ir_a, ir_b)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return diff_to_dict(d)


# M-18: regression alerts — same registration-order constraint as
# /runs/diff. Must live above /runs/{slug} so FastAPI doesn't
# match `slug=regression`.
@router.get("/api/inspector/runs/regression")
async def get_run_regression(slug: str, baseline_slug: str) -> dict:
    """M-18: regression alerts comparing a new run against a baseline.

    Both runs MUST share the same audit shape (slug). The underlying
    slug-equality check raises 400 via ValueError if they don't.

    Like `/runs/diff`, this endpoint is declared BEFORE the
    `/runs/{slug}` dynamic route to avoid path collision (FastAPI
    matches in registration order).

    Same auth posture as the rest of the run-* surface (currently
    unauthenticated; org-scoped retrofit deferred to M-15c).
    """
    from src.polaris_graph.audit_ir.regression_alerts import (
        detect_regressions,
        report_to_dict,
    )
    new_summary = find_run_by_slug(slug)
    if new_summary is None:
        raise HTTPException(
            status_code=404, detail=f"unknown run slug: {slug}",
        )
    baseline_summary = find_run_by_slug(baseline_slug)
    if baseline_summary is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown baseline slug: {baseline_slug}",
        )
    try:
        ir_a = load_audit_ir(baseline_summary.artifact_dir)
        ir_b = load_audit_ir(new_summary.artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError) as exc:
        raise HTTPException(
            status_code=500, detail=f"cannot load AuditIR: {exc}",
        )
    try:
        report = detect_regressions(ir_a, ir_b)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return report_to_dict(report)


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

    # Codex M-16: also embed the AuditIR JSON projection so the
    # bundle is round-trippable through `load_audit_ir` without
    # re-running the loader on the raw artifact files. Without
    # this, downstream consumers (e.g. M-23 review queue, M-25
    # private-corpus sync) have to re-parse manifest+contradictions
    # +verification+bibliography just to render the same Inspector
    # view the bundle is meant to capture.
    auditir_json = None
    try:
        from src.polaris_graph.audit_ir.loader import load_audit_ir
        from src.polaris_graph.audit_ir.serializer import to_json_dict
        ir = load_audit_ir(artifact_dir)
        auditir_json = json.dumps(to_json_dict(ir), indent=2, sort_keys=True)
    except Exception as exc:  # noqa: BLE001 — best-effort
        # Don't fail the whole bundle if AuditIR projection has
        # issues; the raw artifact files are still complete.
        # M-16 review may want this stricter — change to raise.
        auditir_json = None

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

        # Codex M-16: AuditIR JSON projection.
        if auditir_json is not None:
            data = auditir_json.encode("utf-8")
            digest = hashlib.sha256(data).hexdigest()
            digests.append(("audit_ir.json", len(data), digest))
            zf.writestr("audit_ir.json", data)

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


@router.get("/api/inspector/runs/{slug}/health")
async def get_run_citation_health(slug: str) -> dict:
    """M-17: synchronous citation health check for one run.

    Returns the full health report (issues + summary). Designed to
    be polled by the Inspector UI (header badge: green/yellow/red)
    and embedded in M-23 review-queue triage. Pure check over the
    loaded IR — no network, no source-content load.

    Like the rest of the run-* surface, this endpoint is currently
    unauthenticated; org-scoped retrofit deferred to M-15c.
    """
    from src.polaris_graph.audit_ir.citation_health import (
        check_citation_health,
        report_to_dict,
    )
    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Unknown run slug: {slug}")
    try:
        ir = load_audit_ir(summary.artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load IR: {exc}"
        )
    report = check_citation_health(ir)
    return report_to_dict(report)


@router.get("/inspector", response_class=HTMLResponse)
async def inspector_root() -> RedirectResponse:
    """Redirect to the canonical demo run for Phase A."""
    return RedirectResponse(url=f"/inspector/{CANONICAL_DEMO_SLUG}")


# Codex M-16 v2 review fix: /runs/diff was moved to a higher
# position in the file (above /runs/{slug}) so FastAPI's path
# matching reaches it first. v1 declared /runs/diff AFTER the
# dynamic /runs/{slug} route, so requests matched as "slug=diff"
# and 404'd. The endpoint now lives just above the run list at
# the top of this file.


# ---------------------------------------------------------------------------
# Job lifecycle endpoints (M-8)
# ---------------------------------------------------------------------------


class EnqueueJobRequest(BaseModel):
    template_id: str = Field(..., description="Job template, e.g. 'mock' (M-8) or 'v30_clinical' (M-9)")
    params: dict = Field(default_factory=dict)


@router.post("/api/inspector/jobs")
async def enqueue_job(
    req: EnqueueJobRequest,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Create a new pending job.

    Codex M-15b retrofit: jobs are tagged with the caller's org_id
    at enqueue time. Cross-org access via the per-job endpoints
    is gated by the org_id check.
    """
    _ensure_runners_registered()
    available = set(list_runners())
    if req.template_id not in available:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown template_id={req.template_id!r}. Available: {sorted(available)}",
        )
    queue = get_job_queue()
    get_or_start_job_worker()
    job = queue.enqueue(req.template_id, req.params, org_id=caller.org_id)
    return job_to_dict(job)


@router.get("/api/inspector/jobs")
async def list_jobs(
    status: str | None = None,
    limit: int = 100,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Codex M-15b retrofit: list ONLY the caller's org's jobs."""
    _ensure_runners_registered()
    queue = get_job_queue()
    try:
        jobs = queue.list_by_org(caller.org_id, status=status, limit=limit)
    except JobQueueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "count": len(jobs),
        "available_templates": list_runners(),
        "jobs": [job_to_dict(j) for j in jobs],
    }


@router.get("/api/inspector/jobs/{job_id}")
async def get_job(
    job_id: str,
    caller: Caller = Depends(require_job_viewer),
) -> dict:
    """Codex M-15b retrofit: job_viewer dependency gates on org membership."""
    queue = get_job_queue()
    job = queue.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job_id={job_id}")
    return job_to_dict(job)


@router.post("/api/inspector/jobs/{job_id}/pause")
async def pause_job(
    job_id: str,
    caller: Caller = Depends(require_job_member),
) -> dict:
    """Codex M-15b retrofit: pause requires member+ role."""
    queue = get_job_queue()
    try:
        job = queue.request_pause(job_id)
    except JobQueueError as exc:
        msg = str(exc)
        if "unknown job" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return job_to_dict(job)


@router.post("/api/inspector/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    caller: Caller = Depends(require_job_member),
) -> dict:
    """Codex M-15b retrofit: cancel requires member+ role."""
    queue = get_job_queue()
    try:
        job = queue.request_cancel(job_id)
    except JobQueueError as exc:
        msg = str(exc)
        if "unknown job" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    return job_to_dict(job)


# ---------------------------------------------------------------------------
# Curated template router (M-10)
# ---------------------------------------------------------------------------


class RouteQueryRequest(BaseModel):
    question: str = Field(..., description="User's free-form audit question.")


@router.get("/api/inspector/templates/catalog")
async def list_template_catalog() -> dict:
    """Return the curated template catalog for the scope page.

    Phase B M-10: doubles as the scope-page data source so the UI
    can show users which kinds of questions are supported and what's
    not yet in scope. Per FINAL_PLAN scope-page reinforcement
    mitigation for Risk #13.
    """
    from src.polaris_graph.audit_ir.template_catalog import list_catalog
    return {
        "templates": [
            {
                "template_id": t.template_id,
                "display_name": t.display_name,
                "description": t.description,
                "scope_summary": t.scope_summary,
                "scope_examples": list(t.scope_examples),
            }
            for t in list_catalog()
        ],
    }


@router.post("/api/inspector/templates/route")
async def route_query(req: RouteQueryRequest) -> dict:
    """Classify a user query against the curated template catalog.

    Advisory only — does NOT enqueue a job. UI flow: call this, surface
    the verdict + rationale to the user, on confirmation call
    /api/inspector/jobs to actually enqueue.

    Returns:
      verdict: one of 'routed' / 'operator_review_required' /
               'unsupported_scope'
      template_id: candidate template (None when unsupported)
      confidence: float in [0, 1]
      candidates: list of {template_id, score, keyword_hits,
                  example_jaccard}
      rationale: human-readable explanation
    """
    from src.polaris_graph.audit_ir.template_classifier import classify_query
    result = classify_query(req.question)
    return {
        "verdict": result.verdict.value,
        "template_id": result.template_id,
        "confidence": result.confidence,
        "candidates": [
            {
                "template_id": c.template_id,
                "score": c.score,
                "keyword_hits": list(c.keyword_hits),
                "drug_hits": list(c.drug_hits),
                "medical_hits": list(c.medical_hits),
                "example_jaccard": c.example_jaccard,
            }
            for c in result.candidates
        ],
        "rationale": result.rationale,
    }


# ---------------------------------------------------------------------------
# Progressive in-run Inspector surfaces (M-13)
# ---------------------------------------------------------------------------


@router.get("/api/inspector/jobs/{job_id}/surfaces")
async def get_job_surfaces(
    job_id: str,
    caller: Caller = Depends(require_job_viewer),
) -> dict:
    """Snapshot of every progressive surface emitted for this job.

    Per FINAL_PLAN's t-table: PREFLIGHT / PARSE_PROGRESS / TIER_MIX
    / FRAME_COVERAGE / CONTRADICTION_QUEUE / VERIFIED_CLAIM /
    SYNTHESIS_COMPLETE. Each kind appears at most once in the
    snapshot — the most recent emission wins.

    Returns 404 if the job_id is unknown to the queue.
    """
    from src.polaris_graph.audit_ir.progress_surfaces import (
        get_surface_bus,
    )
    queue = get_job_queue()
    if queue.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id={job_id}")
    bus = get_surface_bus()
    events = bus.latest_snapshot(job_id)
    return {
        "job_id": job_id,
        "surfaces": [e.to_dict() for e in events],
    }


@router.get("/api/inspector/jobs/{job_id}/stream")
async def stream_job_surfaces(
    job_id: str,
    caller: Caller = Depends(require_job_viewer),
) -> StreamingResponse:
    """Server-Sent Events stream of progressive surfaces for this
    job. Snapshot replays first (so a late-joining client gets the
    full state), then live tail.

    Stream terminates when the bus prunes the job_id (worker has
    transitioned to a terminal status).
    """
    import json as _json
    from src.polaris_graph.audit_ir.progress_surfaces import (
        get_surface_bus,
    )
    queue = get_job_queue()
    if queue.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown job_id={job_id}")
    bus = get_surface_bus()

    async def _event_stream():
        # Codex M-13 v2 review fix: atomic subscribe + snapshot
        # capture so events emitted between subscribe and
        # snapshot-read aren't double-delivered. Also returns
        # is_terminal=True if the worker already pruned the
        # job_id; in that case there will never be a sentinel
        # so we replay the snapshot and emit `event: end`
        # immediately rather than hanging on the empty queue.
        sub_q, snapshot, terminal = bus.subscribe_with_snapshot(job_id)
        try:
            for event in snapshot:
                yield f"data: {_json.dumps(event.to_dict())}\n\n"
            if terminal:
                yield "event: end\ndata: {}\n\n"
                return
            while True:
                event = await sub_q.get()
                if event is None:
                    # Sentinel from prune() — job is terminal.
                    yield "event: end\ndata: {}\n\n"
                    return
                yield f"data: {_json.dumps(event.to_dict())}\n\n"
        finally:
            bus.unsubscribe(job_id, sub_q)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable proxy buffering
        },
    )


@router.post("/api/inspector/jobs/{job_id}/resume")
async def resume_job(
    job_id: str,
    caller: Caller = Depends(require_job_member),
) -> dict:
    """Resume a paused job by transitioning it to 'pending'.

    Codex M-8 v2 review fix: also ensure a worker is running so the
    reclaim happens promptly (even after a cold restart, where no
    worker exists until something requests one).
    """
    _ensure_runners_registered()
    queue = get_job_queue()
    try:
        job = queue.resume_paused(job_id)
    except JobQueueError as exc:
        msg = str(exc)
        if "unknown job" in msg:
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=409, detail=msg)
    # Codex M-8 v2 fix: start the worker so the resumed job actually
    # gets reclaimed. Idempotent.
    get_or_start_job_worker()
    return job_to_dict(job)


# ---------------------------------------------------------------------------
# Workspace + upload endpoints (M-11)
# ---------------------------------------------------------------------------

_WORKSPACE_DB_PATH = REPO_ROOT / "state" / "polaris_workspaces.sqlite"
_WORKSPACE_FILES_ROOT = REPO_ROOT / "state" / "polaris_workspace_files"
_workspace_store = None  # type: ignore[var-annotated]


def get_workspace_store():
    """Lazy-init the WorkspaceStore. Tests patch this with a tmp_path store."""
    from src.polaris_graph.audit_ir.workspace_store import WorkspaceStore
    global _workspace_store
    if _workspace_store is None:
        _workspace_store = WorkspaceStore(_WORKSPACE_DB_PATH)
    return _workspace_store


def _set_workspace_store_for_tests(store) -> None:
    global _workspace_store
    _workspace_store = store


def _get_workspace_files_root() -> Path:
    """Override for tests via _set_workspace_files_root_for_tests."""
    return _WORKSPACE_FILES_ROOT_OVERRIDE or _WORKSPACE_FILES_ROOT


_WORKSPACE_FILES_ROOT_OVERRIDE: Path | None = None


def _set_workspace_files_root_for_tests(root: Path | None) -> None:
    global _WORKSPACE_FILES_ROOT_OVERRIDE
    _WORKSPACE_FILES_ROOT_OVERRIDE = root


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(..., description="Human-readable workspace name.")
    max_docs: int | None = Field(
        default=None,
        description="Override workspace doc cap. Defaults to PG_WORKSPACE_MAX_DOCS / 50.",
    )


@router.post("/api/inspector/workspaces")
async def create_workspace(
    req: CreateWorkspaceRequest,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Codex M-15b retrofit: workspace creation requires
    authentication; workspace inherits the caller's org_id."""
    from src.polaris_graph.audit_ir.workspace_store import (
        WorkspaceStateError,
        workspace_to_dict,
    )
    store = get_workspace_store()
    try:
        ws = store.create_workspace(
            req.name, max_docs=req.max_docs, org_id=caller.org_id,
        )
    except WorkspaceStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return workspace_to_dict(ws)


@router.get("/api/inspector/workspaces")
async def list_workspaces(
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Codex M-15b retrofit: list ONLY the caller's org's workspaces.
    No cross-org leakage."""
    from src.polaris_graph.audit_ir.workspace_store import workspace_to_dict
    store = get_workspace_store()
    return {
        "workspaces": [
            workspace_to_dict(w)
            for w in store.list_workspaces_for_org(caller.org_id)
        ],
    }


@router.get("/api/inspector/workspaces/{workspace_id}")
async def get_workspace(
    workspace_id: str,
    caller: Caller = Depends(require_workspace_viewer),
) -> dict:
    """Codex M-15b retrofit: workspace_viewer dependency gates on
    org membership."""
    from src.polaris_graph.audit_ir.workspace_store import workspace_to_dict
    store = get_workspace_store()
    ws = store.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail=f"unknown workspace: {workspace_id}")
    return workspace_to_dict(ws)


def _sanitize_upload_filename(raw: str | None) -> str:
    """Codex M-11 review fix: reduce a multipart filename to a safe
    basename. Defends against:
      - path traversal: "../../etc/passwd"
      - absolute paths: "/etc/passwd", "C:/abs.txt", "C:\\abs.txt"
      - nested paths: "subdir/name.txt"
      - Unicode separators / NUL bytes
      - empty / dot-only names

    Phase B always rewrites the on-disk path to
    `<root>/<workspace_id>/<upload_id>/<sanitized>` so even a
    malicious sanitized basename cannot escape the upload-specific
    directory.
    """
    if not raw:
        return "upload"
    # Strip NUL bytes (Windows can choke on these); strip whitespace.
    # FastAPI's multipart parser URL-encodes literal NUL to "%00" by
    # the time we see it, so strip both forms.
    name = raw.replace("\x00", "").replace("%00", "").strip()
    # Take the basename via both path separators so paths constructed
    # on either OS get reduced. Apply repeatedly to defend against
    # encoded "../" sequences.
    while True:
        prev = name
        # Strip leading drive letters ("C:") and root markers.
        if len(name) >= 2 and name[1] == ":":
            name = name[2:]
        # Strip both separators in priority order.
        for sep in ("/", "\\"):
            if sep in name:
                name = name.rsplit(sep, 1)[-1]
        if name == prev:
            break
    # Reject parent-dir / current-dir markers.
    if name in {"", ".", ".."}:
        return "upload"
    # Reject leading dot-segment (still hides the file but cleaner UX).
    while name.startswith("../") or name.startswith("..\\"):
        name = name[3:]
    # Final basename via os.path.basename for parity.
    import os as _os
    name = _os.path.basename(name)
    if not name or name in {".", ".."}:
        return "upload"
    return name


@router.post("/api/inspector/workspaces/{workspace_id}/uploads")
async def upload_to_workspace(
    workspace_id: str,
    file: UploadFile = File(...),
    caller: Caller = Depends(require_workspace_member),
) -> dict:
    """Upload a file to the workspace. Phase B parses text uploads
    synchronously; PDF and other formats land as `pending` /
    `failed` per the parser's `can_handle` decision.

    Bounded enforcement happens BEFORE the file bytes are written
    so a rejected upload doesn't leave orphaned files on disk.

    Codex M-11 review fix: filename is sanitized to a basename
    before any disk write, and the on-disk path is constructed
    inside the per-upload directory and verified to be within
    the workspace root.
    """
    from src.polaris_graph.audit_ir.parser_runner import (
        ParserError,
        select_parser,
        parse_result_to_chunk_dicts,
    )
    from src.polaris_graph.audit_ir.workspace_store import (
        BoundedError,
        WorkspaceStateError,
        upload_to_dict,
    )

    store = get_workspace_store()
    if store.get_workspace(workspace_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown workspace: {workspace_id}")

    filename = _sanitize_upload_filename(file.filename)
    content_type = file.content_type
    payload = await file.read()
    size_bytes = len(payload)

    # Reserve the upload row first (with a tentative storage_path)
    # so bounded enforcement happens before we touch the disk.
    files_root = _get_workspace_files_root()
    workspace_dir = files_root / workspace_id
    workspace_dir.mkdir(parents=True, exist_ok=True)
    try:
        upload = store.upload_file(
            workspace_id=workspace_id, filename=filename,
            content_type=content_type, size_bytes=size_bytes,
            storage_path="",  # filled in below
        )
    except BoundedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except WorkspaceStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    upload_dir = workspace_dir / upload.upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    storage_path = upload_dir / filename

    # Defense in depth: resolve and verify the path is inside the
    # workspace root. Sanitization above should already prevent
    # escape, but a corrupted filesystem (symlink) could still
    # redirect — refuse if so.
    resolved = storage_path.resolve()
    workspace_root_resolved = files_root.resolve()
    try:
        resolved.relative_to(workspace_root_resolved)
    except ValueError:
        # Soft-delete the reserved row so the cap recovers.
        store.soft_delete_upload(upload.upload_id)
        raise HTTPException(
            status_code=400,
            detail="upload path escapes workspace root; refused",
        )

    storage_path.write_bytes(payload)
    # Codex M-11 v2 review fix: if a concurrent soft-delete races
    # past our reservation, update_storage_path now raises rather
    # than silently no-opping. Clean up the bytes on disk so we
    # don't leak orphaned files for a deleted upload.
    try:
        store.update_storage_path(upload.upload_id, str(storage_path))
    except WorkspaceStateError as exc:
        try:
            storage_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=409, detail=str(exc))

    # Synchronously parse if a parser claims it. Phase C M-11.5
    # will switch this to async via JobQueue for slow extractors.
    parser = select_parser(filename, content_type)
    if parser is None:
        # No parser → leave status='pending'; operator decides.
        refreshed = store.get_upload(upload.upload_id)
        return upload_to_dict(refreshed)

    store.transition_parser_status(upload.upload_id, "parsing")
    try:
        result = parser.parse(upload.upload_id, storage_path)
    except ParserError as exc:
        failed = store.transition_parser_status(
            upload.upload_id, "failed", parser_error=str(exc),
        )
        return upload_to_dict(failed)

    chunk_dicts = parse_result_to_chunk_dicts(result)
    if chunk_dicts:
        store.insert_chunks(upload.upload_id, chunk_dicts)
    parsed = store.transition_parser_status(upload.upload_id, "parsed")
    return upload_to_dict(parsed)


@router.get("/api/inspector/workspaces/{workspace_id}/uploads")
async def list_workspace_uploads(
    workspace_id: str,
    include_deleted: bool = False,
    caller: Caller = Depends(require_workspace_viewer),
) -> dict:
    from src.polaris_graph.audit_ir.workspace_store import upload_to_dict
    store = get_workspace_store()
    if store.get_workspace(workspace_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown workspace: {workspace_id}")
    uploads = store.list_uploads(workspace_id, include_deleted=include_deleted)
    return {"uploads": [upload_to_dict(u) for u in uploads]}


@router.get("/api/inspector/uploads/{upload_id}")
async def get_upload(
    upload_id: str,
    caller: Caller = Depends(require_upload_viewer),
) -> dict:
    """Codex M-15b retrofit: upload_viewer dependency resolves
    upload → workspace → org and gates on caller membership."""
    from src.polaris_graph.audit_ir.workspace_store import upload_to_dict
    store = get_workspace_store()
    upload = store.get_upload(upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail=f"unknown upload: {upload_id}")
    return upload_to_dict(upload)


@router.delete("/api/inspector/uploads/{upload_id}")
async def delete_upload(
    upload_id: str,
    caller: Caller = Depends(require_upload_member),
) -> dict:
    """Codex M-15b retrofit: requires member+ role to soft-delete."""
    from src.polaris_graph.audit_ir.workspace_store import (
        WorkspaceStateError,
        upload_to_dict,
    )
    store = get_workspace_store()
    try:
        upload = store.soft_delete_upload(upload_id)
    except WorkspaceStateError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return upload_to_dict(upload)


@router.get("/api/inspector/uploads/{upload_id}/chunks")
async def list_upload_chunks(
    upload_id: str,
    caller: Caller = Depends(require_upload_viewer),
) -> dict:
    """Codex M-15b retrofit: upload_viewer required to read parsed chunks."""
    store = get_workspace_store()
    if store.get_upload(upload_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown upload: {upload_id}")
    return {"chunks": store.list_chunks(upload_id)}


# ---------------------------------------------------------------------------
# Question-Bound Corpus Brief (M-12)
# ---------------------------------------------------------------------------


# Tests inject a fake LlmClient via this hook so unit tests don't
# need network credentials. None means "use the real OpenRouter
# client lazily".
_BRIEF_LLM_OVERRIDE = None  # type: ignore[var-annotated]


def _set_brief_llm_for_tests(llm) -> None:
    global _BRIEF_LLM_OVERRIDE
    _BRIEF_LLM_OVERRIDE = llm


def _get_brief_llm():
    """Resolve the LlmClient for /brief.

    Tests set _BRIEF_LLM_OVERRIDE to a fake. Production lazily
    constructs an OpenRouterBriefClient on first use.
    """
    if _BRIEF_LLM_OVERRIDE is not None:
        return _BRIEF_LLM_OVERRIDE
    from src.polaris_graph.audit_ir.corpus_brief import OpenRouterBriefClient
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient
    return OpenRouterBriefClient(OpenRouterClient())


class ComposeBriefRequest(BaseModel):
    question: str = Field(..., description="The single question to answer.")
    top_k: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.5, ge=0.0)


@router.post("/api/inspector/workspaces/{workspace_id}/brief")
async def compose_workspace_brief(
    workspace_id: str,
    req: ComposeBriefRequest,
    caller: Caller = Depends(require_workspace_member),
) -> dict:
    """M-12 Question-Bound Corpus Brief endpoint.

    Returns a brief whose paragraphs are either supported (with
    inline citations to retrieved chunks) or labeled
    insufficient_support. Per FINAL_PLAN: "every paragraph cited
    or 'insufficient support'."
    """
    from src.polaris_graph.audit_ir.corpus_brief import (
        brief_to_dict,
        compose_brief,
    )
    store = get_workspace_store()
    if store.get_workspace(workspace_id) is None:
        raise HTTPException(
            status_code=404, detail=f"unknown workspace: {workspace_id}",
        )
    llm = _get_brief_llm()
    try:
        brief = await compose_brief(
            store=store, workspace_id=workspace_id,
            question=req.question, llm=llm,
            top_k=req.top_k, min_score=req.min_score,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return brief_to_dict(brief)


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
