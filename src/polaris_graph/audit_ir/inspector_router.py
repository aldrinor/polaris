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

import json
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
    optional_caller,
    require_authenticated_caller,
    require_job_member,
    require_job_viewer,
    require_review_admin,
    require_review_member,
    require_review_viewer,
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
# M-INT-8: M-22 slide deck endpoint
from src.polaris_graph.audit_ir.slide_deck import (  # noqa: E402
    SlideDeckEmptyReportError,
    SlideDeckError,
    build_slide_deck,
    deck_to_dict,
    render_deck_html,
)
# M-INT-9: M-26 contract drafting endpoint
from src.polaris_graph.audit_ir.contract_draft_store import (  # noqa: E402
    ContractDraft,
    ContractDraftError,
    ContractDraftStateError,
    ContractDraftStatus,
    ContractDraftStore,
    ContractKind,
    draft_to_dict,
)
# M-INT-10: M-25 Drive connector v2 (narrow) endpoint
from src.polaris_graph.audit_ir.private_corpus_sync import (  # noqa: E402
    CorpusSource,
    PrivateCorpusSyncError,
    PrivateCorpusSyncStore,
    SourceConnector,
    SourceStateError,
    SourceStatus,
    source_to_dict,
)
# M-INT-11: M-24 customer support tickets endpoint
from src.polaris_graph.audit_ir.support_ticket_store import (  # noqa: E402
    SupportTicket,
    SupportTicketError,
    SupportTicketStateError,
    SupportTicketStore,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    ticket_to_dict,
)
# M-LIVE-3: operator dashboard aggregates
from src.polaris_graph.audit_ir.decision_aggregates import (  # noqa: E402
    DecisionAggregates,
    DecisionAggregatesError,
    compute_aggregates,
)
from src.polaris_graph.audit_ir.freshness_aggregates import (  # noqa: E402
    FreshnessAggregates,
    FreshnessAggregatesError,
    compute_freshness_aggregates,
)
from src.polaris_graph.audit_ir.freshness_monitor import (  # noqa: E402
    FreshnessAlertStore,
)
from src.polaris_graph.audit_ir.pin_trends import (  # noqa: E402
    PinTrendError,
    PinTrendReport,
    analyze_pin_trends,
)
from src.polaris_graph.audit_ir.model_pin import (  # noqa: E402
    pin_from_dict,
)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "scripts" / "templates"
INSPECTOR_HTML_PATH = TEMPLATES_DIR / "inspector_shell.html"


# ---------------------------------------------------------------------------
# M-INT-0a — Decision telemetry integration (Phase E0)
# ---------------------------------------------------------------------------
#
# Wires decision_telemetry.record_decision(...) into the production
# scope-gate call site (/api/inspector/templates/route). Every
# scope-gate call by an authenticated caller writes a DecisionRecord
# in PENDING state. M-D3 phase 2 (decision_aggregates) consumes
# these records for trust-gate calibration (M-D4, calendar-blocked).
#
# Telemetry is best-effort:
#   - Failure to write MUST NOT gate the scope-gate decision
#   - Anonymous callers skip telemetry (no workspace_id available)
#   - PG_RECORD_DECISIONS=0 disables the write path entirely
#
# Per locked memory feedback_substrate_is_not_product.md: this is
# the integration that converts M-D3 substrate into product. The
# substrate writes the decision; the production code path now
# imports and invokes it.
#
# Per FINAL_PLAN.md M-INT-0a + state/restart_instructions.md:
#   - PG_RECORD_DECISIONS=1 (default) records decisions
#   - PG_RECORD_DECISIONS=0 disables (rollback)
#   - PG_DECISION_DB_PATH overrides the SQLite path (for tests)


import logging
import os
import threading

from src.polaris_graph.audit_ir.decision_telemetry import (
    DecisionKind,
    DecisionRecordStore,
)

_INT_0A_LOGGER = logging.getLogger("polaris.m_int_0a.decision_telemetry")
_DECISION_STORE: DecisionRecordStore | None = None
_DECISION_STORE_LOCK = threading.Lock()

# M-INT-9: contract draft store singleton (lazy init).
_CONTRACT_DRAFT_STORE: ContractDraftStore | None = None
_CONTRACT_DRAFT_STORE_LOCK = threading.Lock()

# M-INT-10: private corpus sync store singleton (lazy init).
_PRIVATE_CORPUS_SYNC_STORE: PrivateCorpusSyncStore | None = None
_PRIVATE_CORPUS_SYNC_STORE_LOCK = threading.Lock()


def _private_corpus_db_path() -> Path:
    raw = os.environ.get("PG_PRIVATE_CORPUS_DB_PATH")
    if raw:
        return Path(raw)
    base = Path(__file__).resolve().parents[3] / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "private_corpus_sync.sqlite"


def _get_private_corpus_sync_store() -> PrivateCorpusSyncStore:
    global _PRIVATE_CORPUS_SYNC_STORE
    with _PRIVATE_CORPUS_SYNC_STORE_LOCK:
        if _PRIVATE_CORPUS_SYNC_STORE is None:
            _PRIVATE_CORPUS_SYNC_STORE = PrivateCorpusSyncStore(
                _private_corpus_db_path()
            )
        return _PRIVATE_CORPUS_SYNC_STORE


def _reset_private_corpus_sync_store_for_test() -> None:
    global _PRIVATE_CORPUS_SYNC_STORE
    with _PRIVATE_CORPUS_SYNC_STORE_LOCK:
        _PRIVATE_CORPUS_SYNC_STORE = None


def _drive_connector_endpoint_enabled() -> bool:
    return os.environ.get(
        "PG_USE_DRIVE_CONNECTOR_ENDPOINT", "1",
    ) != "0"


async def _require_drive_connector_endpoint_enabled() -> None:
    if not _drive_connector_endpoint_enabled():
        raise HTTPException(
            status_code=404,
            detail="drive connector endpoint disabled",
        )

# M-INT-11: support ticket store singleton (lazy init).
_SUPPORT_TICKET_STORE: SupportTicketStore | None = None
_SUPPORT_TICKET_STORE_LOCK = threading.Lock()


def _support_ticket_db_path() -> Path:
    raw = os.environ.get("PG_SUPPORT_TICKET_DB_PATH")
    if raw:
        return Path(raw)
    base = Path(__file__).resolve().parents[3] / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "support_tickets.sqlite"


def _get_support_ticket_store() -> SupportTicketStore:
    global _SUPPORT_TICKET_STORE
    with _SUPPORT_TICKET_STORE_LOCK:
        if _SUPPORT_TICKET_STORE is None:
            _SUPPORT_TICKET_STORE = SupportTicketStore(
                _support_ticket_db_path()
            )
        return _SUPPORT_TICKET_STORE


def _reset_support_ticket_store_for_test() -> None:
    global _SUPPORT_TICKET_STORE
    with _SUPPORT_TICKET_STORE_LOCK:
        _SUPPORT_TICKET_STORE = None


def _support_ticket_endpoint_enabled() -> bool:
    return os.environ.get(
        "PG_USE_SUPPORT_TICKET_ENDPOINT", "1",
    ) != "0"


async def _require_support_ticket_endpoint_enabled() -> None:
    if not _support_ticket_endpoint_enabled():
        raise HTTPException(
            status_code=404,
            detail="support ticket endpoint disabled",
        )


def _contract_draft_db_path() -> Path:
    """Contract draft SQLite path. Per LAW VI: env-overridable."""
    raw = os.environ.get("PG_CONTRACT_DRAFT_DB_PATH")
    if raw:
        return Path(raw)
    base = Path(__file__).resolve().parents[3] / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "contract_drafts.sqlite"


def _get_contract_draft_store() -> ContractDraftStore:
    """Singleton contract-draft store. Lazily initialized so test
    environments can monkeypatch PG_CONTRACT_DRAFT_DB_PATH before
    first use."""
    global _CONTRACT_DRAFT_STORE
    with _CONTRACT_DRAFT_STORE_LOCK:
        if _CONTRACT_DRAFT_STORE is None:
            _CONTRACT_DRAFT_STORE = ContractDraftStore(
                _contract_draft_db_path()
            )
        return _CONTRACT_DRAFT_STORE


def _reset_contract_draft_store_for_test() -> None:
    """Test helper: drop the singleton so the next
    _get_contract_draft_store() call rebuilds against current
    PG_CONTRACT_DRAFT_DB_PATH. Production code MUST NOT call this."""
    global _CONTRACT_DRAFT_STORE
    with _CONTRACT_DRAFT_STORE_LOCK:
        _CONTRACT_DRAFT_STORE = None


def _contract_draft_endpoint_enabled() -> bool:
    return os.environ.get(
        "PG_USE_CONTRACT_DRAFT_ENDPOINT", "1",
    ) != "0"


def _decision_db_path() -> Path:
    """Decision-telemetry SQLite path. Per LAW VI: env-overridable."""
    raw = os.environ.get("PG_DECISION_DB_PATH")
    if raw:
        return Path(raw)
    base = Path(__file__).resolve().parents[3] / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "decision_records.sqlite"


def _get_decision_store() -> DecisionRecordStore:
    """Singleton decision-telemetry store. Lazily initialized so
    test environments can monkeypatch PG_DECISION_DB_PATH before
    first use."""
    global _DECISION_STORE
    with _DECISION_STORE_LOCK:
        if _DECISION_STORE is None:
            _DECISION_STORE = DecisionRecordStore(_decision_db_path())
        return _DECISION_STORE


def _reset_decision_store_for_test() -> None:
    """Test helper: drop the singleton so the next _get_decision_store()
    call rebuilds it against the current PG_DECISION_DB_PATH env value.
    Production code MUST NOT call this."""
    global _DECISION_STORE
    with _DECISION_STORE_LOCK:
        _DECISION_STORE = None


def _record_scope_gate_decision(
    question: str,
    routing_result: object,
    *,
    workspace_id: str | None,
) -> None:
    """Best-effort scope-gate decision record.

    Failure to write is logged but does NOT raise — telemetry must
    never gate the actual scope-gate decision. PG_RECORD_DECISIONS=0
    disables the write path.

    `workspace_id` is the auth caller's org_id (one record per
    org's scope-gate calls). Anonymous calls (workspace_id=None)
    skip telemetry silently.
    """
    if os.environ.get("PG_RECORD_DECISIONS", "1") == "0":
        return
    if not workspace_id:
        return
    try:
        store = _get_decision_store()
        store.record_decision(
            workspace_id=workspace_id,
            decision_kind=DecisionKind.SCOPE_GATE,
            query=question,
            proposed_payload={
                "verdict": getattr(
                    getattr(routing_result, "verdict", None), "value", None,
                ),
                "template_id": getattr(routing_result, "template_id", None),
            },
            proposed_confidence=float(
                getattr(routing_result, "confidence", 0.0) or 0.0
            ),
        )
    except Exception as exc:  # noqa: BLE001 — intentional broad
        _INT_0A_LOGGER.warning(
            "scope-gate decision telemetry failed (workspace_id=%s): %s",
            workspace_id, exc,
        )

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


# ---------------------------------------------------------------------------
# M-INT-8 — M-22 slide deck endpoint (Phase E4)
# ---------------------------------------------------------------------------
#
# Wires build_slide_deck + deck_to_dict / render_deck_html into the
# inspector router. Two endpoints:
#   - /api/inspector/runs/{slug}/slide-deck → JSON deck dict
#   - /api/inspector/runs/{slug}/slide-deck.html → rendered HTML
#
# Both require authenticated caller (M-15b retrofit). Both gate on
# PG_USE_SLIDE_DECK_ENDPOINT (default 1 — feature ships ON; set to
# 0 only for emergency rollback).
#
# Codex round-1 cross-org note (system-wide, deferred): These
# endpoints do require_authenticated_caller but do NOT enforce
# run-level org authorization — same as get_run, get_audit_bundle,
# get_report_markdown, get_run_citation_health (which don't even
# require authentication). RunSummary has no org_id field; the
# registry does a global allowlist scan. Cross-org access to runs
# is a system-wide pattern that requires:
#   1. Adding org_id to RunSummary (registry schema migration)
#   2. Updating all 5+ /api/inspector/runs/{slug}/* endpoints to
#      check caller.org_id == run.org_id
#   3. Backfilling org_id on existing run artifacts
# This is its own milestone — tracked for Phase F / M-PROD-1
# (SOC2 dry-run scope). M-INT-8 ships AT PARITY with the existing
# pattern, not introducing a new gap.


def _slide_deck_endpoint_enabled() -> bool:
    return os.environ.get("PG_USE_SLIDE_DECK_ENDPOINT", "1") != "0"


@router.get("/api/inspector/runs/{slug}/slide-deck")
async def get_slide_deck_json(
    slug: str,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Return the slide deck for a run as a JSON-safe dict.

    Wraps build_slide_deck → deck_to_dict. Per FINAL_PLAN
    M-INT-8 acceptance:
      - Title + scope + section + contradictions + appendix slides
      - Empty-report runs return 422 with structured error
      - Unknown slug returns 404
    """
    if not _slide_deck_endpoint_enabled():
        raise HTTPException(
            status_code=404,
            detail="slide deck endpoint disabled",
        )
    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown run slug: {slug}",
        )
    try:
        ir = load_audit_ir(summary.artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load IR: {exc}",
        )
    try:
        deck = build_slide_deck(ir)
    except SlideDeckEmptyReportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"slide deck unavailable (empty report): {exc}",
        )
    except SlideDeckError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"slide deck build failed: {exc}",
        )
    return deck_to_dict(deck)


@router.get(
    "/api/inspector/runs/{slug}/slide-deck.html",
    response_class=HTMLResponse,
)
async def get_slide_deck_html(
    slug: str,
    caller: Caller = Depends(require_authenticated_caller),
) -> str:
    """Return the slide deck for a run as rendered HTML."""
    if not _slide_deck_endpoint_enabled():
        raise HTTPException(
            status_code=404,
            detail="slide deck endpoint disabled",
        )
    summary = find_run_by_slug(slug)
    if summary is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown run slug: {slug}",
        )
    try:
        ir = load_audit_ir(summary.artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError) as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to load IR: {exc}",
        )
    try:
        deck = build_slide_deck(ir)
    except SlideDeckEmptyReportError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"slide deck unavailable (empty report): {exc}",
        )
    except SlideDeckError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"slide deck build failed: {exc}",
        )
    return render_deck_html(deck)


# ---------------------------------------------------------------------------
# M-INT-9 — M-26 contract drafting endpoints (Phase E4)
# ---------------------------------------------------------------------------
#
# Org-scoped CRUD for contract drafts. Mirrors the substrate
# pattern: every read/write is bound to caller.org_id. PG_USE_
# CONTRACT_DRAFT_ENDPOINT=0 disables (returns 404).


class _ContractDraftCreateRequest(BaseModel):
    audit_run_id: str = Field(..., min_length=1)
    kind: str = Field(
        ..., min_length=1,
        description="One of: msa, sow, dpa, baa",
    )
    title: str = Field(..., min_length=1)
    counterparty_name: str = Field(..., min_length=1)
    workspace_id: str | None = Field(
        default=None,
        description=(
            "Optional workspace_id; defaults to "
            "f'ws_default_{caller.org_id}' for v1. Real workspace "
            "selection is Phase F UI."
        ),
    )


async def _require_contract_draft_endpoint_enabled() -> None:
    """Codex round-1 MEDIUM fix (v2): hoist the flag check to a
    FastAPI dependency so it runs BEFORE the auth dependency
    resolves. v1 checked inside the handler body, which meant
    PG_USE_CONTRACT_DRAFT_ENDPOINT=0 returned 401 for anonymous
    callers (auth dep ran first) instead of the intended 404.
    """
    if not _contract_draft_endpoint_enabled():
        raise HTTPException(
            status_code=404,
            detail="contract draft endpoint disabled",
        )


@router.post(
    "/api/inspector/contract-drafts",
    status_code=201,
    dependencies=[Depends(_require_contract_draft_endpoint_enabled)],
)
async def create_contract_draft(
    body: _ContractDraftCreateRequest,
    # Codex round-1 MEDIUM fix (v2): write requires member+
    # (not just authenticated). v1 used require_authenticated_caller
    # which let viewer-role callers create drafts. Substrate's
    # store stamps submitter_user_id but does NOT validate role.
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Create a new contract draft anchored to a specific audit run.

    Per FINAL_PLAN M-INT-9: every contract is bound to a verified
    audit run (audit_run_id is required). The store enforces this
    invariant — the endpoint just routes the request.

    Authorization: requires member+ role on caller.org_id (viewers
    get 403). Codex round-1 v2 fix.
    """
    # Codex round-1 MEDIUM fix (v2): explicit role gate. v1
    # only used require_authenticated_caller which accepted any
    # authenticated user including viewer role. Use the role
    # field on Caller to gate writes to member or owner.
    if caller.role not in {"member", "admin", "owner"}:
        raise HTTPException(
            status_code=403,
            detail=(
                f"caller role {caller.role!r} insufficient to "
                "create contract drafts; member+ required"
            ),
        )
    try:
        kind_enum = ContractKind(body.kind)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid kind {body.kind!r}; must be one of: "
                f"{', '.join(k.value for k in ContractKind)}"
            ),
        )
    workspace_id = body.workspace_id or f"ws_default_{caller.org_id}"
    store = _get_contract_draft_store()
    try:
        draft = store.create_draft(
            org_id=caller.org_id,
            workspace_id=workspace_id,
            submitter_user_id=caller.user_id,
            audit_run_id=body.audit_run_id,
            kind=kind_enum,
            title=body.title,
            counterparty_name=body.counterparty_name,
        )
    except ContractDraftStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ContractDraftError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return draft_to_dict(draft)


@router.get(
    "/api/inspector/contract-drafts",
    dependencies=[Depends(_require_contract_draft_endpoint_enabled)],
)
async def list_contract_drafts(
    status: str | None = None,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """List contract drafts for the caller's org. Optional
    `status` filter (one of: draft, awaiting_approval, approved,
    rejected — see ContractDraftStatus enum).

    Codex round-1 LOW fix (v2): the v1 docstring incorrectly
    listed values 'drafting / pending_approval'; corrected to
    match the actual enum values."""
    status_enum: ContractDraftStatus | None = None
    if status is not None:
        try:
            status_enum = ContractDraftStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"invalid status {status!r}; must be one of: "
                    f"{', '.join(s.value for s in ContractDraftStatus)}"
                ),
            )
    store = _get_contract_draft_store()
    drafts = store.list_drafts_for_org(
        org_id=caller.org_id, status=status_enum,
    )
    return {"drafts": [draft_to_dict(d) for d in drafts]}


@router.get(
    "/api/inspector/contract-drafts/{draft_id}",
    dependencies=[Depends(_require_contract_draft_endpoint_enabled)],
)
async def get_contract_draft(
    draft_id: str,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Fetch one contract draft by id. The store's get_draft
    is org-scoped, so cross-org access returns None → 404."""
    store = _get_contract_draft_store()
    draft = store.get_draft(
        draft_id=draft_id, org_id=caller.org_id,
    )
    if draft is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown draft_id: {draft_id}",
        )
    return draft_to_dict(draft)


# ---------------------------------------------------------------------------
# M-INT-10 — M-25 Drive connector v2 (narrow) endpoints (Phase E4)
# ---------------------------------------------------------------------------
#
# Per FINAL_PLAN: NARROW scope — Google Drive only. SharePoint and
# Confluence connectors exist in the substrate enum but are NOT
# exposed at the endpoint layer in v1. The endpoint hardcodes
# connector=GOOGLE_DRIVE so callers cannot register non-Drive
# sources.


class _PrivateCorpusSourceCreateRequest(BaseModel):
    """Codex round-1 MEDIUM fix (v2): enforce extra='forbid' so
    callers cannot pass a `connector` field at all (v1 used
    Pydantic default which silently dropped extras, leaving room
    for confusion). v2 explicitly rejects unknown fields with 422.
    """
    model_config = {"extra": "forbid"}
    workspace_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    external_uri: str = Field(
        ..., min_length=1,
        description=(
            "Google Drive folder ID (e.g. '1AbC...'). "
            "URLs and other non-folder-ID values are rejected."
        ),
    )
    credential_ref: str = Field(
        ..., min_length=1,
        description=(
            "Vault pointer (e.g. vault://secrets/drive-key). "
            "Raw secrets are rejected at substrate level."
        ),
    )


# Codex round-1 MEDIUM fix (v2): validate external_uri shape.
# Drive folder IDs are 28-44 chars of [A-Za-z0-9_-], no slashes
# or dots. Reject URLs (anything containing '://', '.', or '/')
# at endpoint level — substrate only checks non-empty.
import re as _re  # local alias to avoid shadowing top-level imports
_DRIVE_FOLDER_ID_RE = _re.compile(r"^[A-Za-z0-9_-]{20,80}$")


def _validate_drive_folder_id(uri: str) -> None:
    """Raise HTTPException(400) if uri doesn't look like a Drive
    folder ID. Per FINAL_PLAN narrow scope, we want callers to
    fail fast at the endpoint instead of mislabeled SharePoint
    URLs landing as connector=google_drive."""
    if not _DRIVE_FOLDER_ID_RE.match(uri):
        raise HTTPException(
            status_code=400,
            detail=(
                f"external_uri {uri!r} is not a valid Google Drive "
                "folder ID; expected 20-80 chars of [A-Za-z0-9_-] "
                "(e.g. '1AbC...DEF'). URLs and other shapes are not "
                "accepted at this endpoint."
            ),
        )


@router.post(
    "/api/inspector/private-corpus-sources",
    status_code=201,
    dependencies=[Depends(_require_drive_connector_endpoint_enabled)],
)
async def register_private_corpus_source(
    body: _PrivateCorpusSourceCreateRequest,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Register a new Google Drive source for the caller's workspace.

    Per FINAL_PLAN narrow scope: connector is hardcoded to
    GOOGLE_DRIVE. Source lands in PENDING state — admin must
    call approve_source() before sync_now() will run (admin-only
    write, deferred to Phase F UI).
    """
    if caller.role not in {"member", "admin", "owner"}:
        raise HTTPException(
            status_code=403,
            detail=(
                f"caller role {caller.role!r} insufficient to "
                "register corpus sources; member+ required"
            ),
        )
    # Codex round-1 MEDIUM fix (v2): validate external_uri shape
    # at endpoint before substrate sees it.
    _validate_drive_folder_id(body.external_uri)
    store = _get_private_corpus_sync_store()
    try:
        source = store.register_source(
            workspace_id=body.workspace_id,
            org_id=caller.org_id,
            connector=SourceConnector.GOOGLE_DRIVE,
            name=body.name,
            external_uri=body.external_uri,
            credential_ref=body.credential_ref,
        )
    except SourceStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except PrivateCorpusSyncError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return source_to_dict(source)


@router.get(
    "/api/inspector/private-corpus-sources",
    dependencies=[Depends(_require_drive_connector_endpoint_enabled)],
)
async def list_private_corpus_sources(
    workspace_id: str | None = None,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """List corpus sources for a workspace (caller's org enforced).

    Codex round-1 LOW fix (v2): differentiate omitted (returns [])
    from explicitly empty (returns 400). v1 conflated both via
    `if not workspace_id` which hid client bugs.
    """
    if workspace_id is None:
        return {"sources": []}
    # Codex round-2 LOW fix (v3): normalize workspace_id by
    # stripping. v1+v2 had POST strip whitespace via substrate
    # (workspace_id.strip() in register_source), but GET passed
    # raw query text through, so "  ws  " on POST stored "ws"
    # but GET ?workspace_id=%20%20ws%20%20 returned []. v3 strips
    # consistently before the substrate call.
    stripped = workspace_id.strip()
    if not stripped:
        raise HTTPException(
            status_code=400,
            detail=(
                "workspace_id query parameter must be non-empty if "
                "provided; omit the parameter entirely for an empty "
                "list"
            ),
        )
    store = _get_private_corpus_sync_store()
    sources = store.list_sources_for_workspace(
        workspace_id=stripped,
        org_id=caller.org_id,
    )
    return {"sources": [source_to_dict(s) for s in sources]}


@router.get(
    "/api/inspector/private-corpus-sources/{source_id}",
    dependencies=[Depends(_require_drive_connector_endpoint_enabled)],
)
async def get_private_corpus_source(
    source_id: str,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Fetch one corpus source. Org-scoped — cross-org → 404."""
    store = _get_private_corpus_sync_store()
    source = store.get_source(
        source_id=source_id, org_id=caller.org_id,
    )
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown source_id: {source_id}",
        )
    return source_to_dict(source)


# ---------------------------------------------------------------------------
# M-INT-11 — M-24 customer support tickets endpoints (Phase E4)
# ---------------------------------------------------------------------------
#
# Final integration milestone before LIVE phase. Ships narrow CRUD
# (open + read); assignment/resolve/close/message-append are
# admin-only flows deferred to Phase F UI.


class _SupportTicketCreateRequest(BaseModel):
    model_config = {"extra": "forbid"}
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    category: str = Field(
        ..., min_length=1,
        description="One of: billing, audit, integration, data_request, other",
    )
    priority: str = Field(
        default="normal",
        description="One of: low, normal, high, urgent",
    )
    related_run_slug: str | None = None
    related_review_id: str | None = None
    related_workspace_id: str | None = None


@router.post(
    "/api/inspector/support-tickets",
    status_code=201,
    dependencies=[Depends(_require_support_ticket_endpoint_enabled)],
)
async def open_support_ticket(
    body: _SupportTicketCreateRequest,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Open a new support ticket bound to caller.org_id.

    Member+ role required. Categories and priorities are closed
    enums; invalid values return 400."""
    if caller.role not in {"member", "admin", "owner"}:
        raise HTTPException(
            status_code=403,
            detail=(
                f"caller role {caller.role!r} insufficient to open "
                "support tickets; member+ required"
            ),
        )
    try:
        category_enum = TicketCategory(body.category)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid category {body.category!r}; must be one of: "
                f"{', '.join(c.value for c in TicketCategory)}"
            ),
        )
    try:
        priority_enum = TicketPriority(body.priority)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                f"invalid priority {body.priority!r}; must be one of: "
                f"{', '.join(p.value for p in TicketPriority)}"
            ),
        )
    store = _get_support_ticket_store()
    try:
        ticket = store.open_ticket(
            org_id=caller.org_id,
            submitter_user_id=caller.user_id,
            title=body.title,
            description=body.description,
            category=category_enum,
            priority=priority_enum,
            related_run_slug=body.related_run_slug,
            related_review_id=body.related_review_id,
            related_workspace_id=body.related_workspace_id,
        )
    except SupportTicketStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SupportTicketError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return ticket_to_dict(ticket)


@router.get(
    "/api/inspector/support-tickets",
    dependencies=[Depends(_require_support_ticket_endpoint_enabled)],
)
async def list_support_tickets(
    status: str | None = None,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """List support tickets for caller's org. Optional `status`
    filter (open / in_progress / resolved / closed)."""
    status_enum: TicketStatus | None = None
    if status is not None:
        try:
            status_enum = TicketStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"invalid status {status!r}; must be one of: "
                    f"{', '.join(s.value for s in TicketStatus)}"
                ),
            )
    store = _get_support_ticket_store()
    tickets = store.list_by_org(
        org_id=caller.org_id, status=status_enum,
    )
    return {"tickets": [ticket_to_dict(t) for t in tickets]}


@router.get(
    "/api/inspector/support-tickets/{ticket_id}",
    dependencies=[Depends(_require_support_ticket_endpoint_enabled)],
)
async def get_support_ticket(
    ticket_id: str,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    store = _get_support_ticket_store()
    ticket = store.get_ticket(
        ticket_id=ticket_id, org_id=caller.org_id,
    )
    if ticket is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown ticket_id: {ticket_id}",
        )
    return ticket_to_dict(ticket)


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
async def route_query(
    req: RouteQueryRequest,
    caller: Caller | None = Depends(optional_caller),
) -> dict:
    """Classify a user query against the curated template catalog.

    Advisory only — does NOT enqueue a job. UI flow: call this, surface
    the verdict + rationale to the user, on confirmation call
    /api/inspector/jobs to actually enqueue.

    M-INT-0a (Phase E0): when the caller is authenticated, the
    classification result is also recorded via
    `decision_telemetry.record_decision(...)` for downstream
    M-D4 trust-gate calibration. Anonymous callers skip telemetry.
    Telemetry write failure is logged but does NOT gate the
    decision (returned to the user regardless).

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
    # M-INT-0a integration: record the scope-gate decision.
    # Best-effort: failure to write does NOT change the response.
    _record_scope_gate_decision(
        req.question, result,
        workspace_id=caller.org_id if caller else None,
    )
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


# ---------------------------------------------------------------------------
# Review store (M-23) — singleton, lazy-init, test-overridable
# ---------------------------------------------------------------------------


_REVIEW_DB_PATH = REPO_ROOT / "state" / "polaris_reviews.sqlite"
_review_store = None  # type: ignore[var-annotated]


def get_review_store():
    """Lazy-init the ReviewStore. Tests patch this with a tmp_path store."""
    from src.polaris_graph.audit_ir.review_store import ReviewStore
    global _review_store
    if _review_store is None:
        _review_store = ReviewStore(_REVIEW_DB_PATH)
    return _review_store


def _set_review_store_for_tests(store) -> None:
    global _review_store
    _review_store = store


# ---------------------------------------------------------------------------
# Workspace-memory store (M-21)
# ---------------------------------------------------------------------------


_WORKSPACE_MEMORY_DB_PATH = (
    REPO_ROOT / "state" / "polaris_workspace_memory.sqlite"
)
_workspace_memory_store = None  # type: ignore[var-annotated]


def get_workspace_memory_store():
    """Lazy-init the WorkspaceMemoryStore. Tests patch via tmp_path."""
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStore,
    )
    global _workspace_memory_store
    if _workspace_memory_store is None:
        _workspace_memory_store = WorkspaceMemoryStore(
            _WORKSPACE_MEMORY_DB_PATH
        )
    return _workspace_memory_store


def _set_workspace_memory_store_for_tests(store) -> None:
    global _workspace_memory_store
    _workspace_memory_store = store


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


# ---------------------------------------------------------------------------
# Workspace memory (M-21)
# ---------------------------------------------------------------------------


class AppendMemoryRequest(BaseModel):
    claim_text: str = Field(..., description="Concrete prose stored as memory")
    source_url: str = Field(..., description="Canonical URL for attribution")
    source_tier: str = Field(..., description="V30 tier (T1..T7 or UNKNOWN)")
    source_evidence_id: str | None = Field(
        default=None,
        description="Evidence ID this memory derives from, if any.",
    )


@router.post("/api/inspector/workspaces/{workspace_id}/memory")
async def append_workspace_memory(
    workspace_id: str,
    req: AppendMemoryRequest,
    caller: Caller = Depends(require_workspace_member),
) -> dict:
    """Append one memory entry to a workspace.

    Cross-workspace isolation: the workspace dep already validates
    caller.org_id matches the workspace's org_id. The entry is
    bound to workspace_id at the store level — it cannot leak
    into another workspace's retrieve() result.
    """
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStateError,
        memory_entry_to_dict,
    )
    store = get_workspace_memory_store()
    try:
        entry = store.append_entry(
            workspace_id=workspace_id,
            claim_text=req.claim_text,
            source_url=req.source_url,
            source_tier=req.source_tier,
            source_evidence_id=req.source_evidence_id,
        )
    except WorkspaceMemoryStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return memory_entry_to_dict(entry)


@router.get("/api/inspector/workspaces/{workspace_id}/memory")
async def list_workspace_memory(
    workspace_id: str,
    caller: Caller = Depends(require_workspace_viewer),
    max_age_days: float | None = None,
) -> dict:
    """List all memory entries for a workspace, newest first.

    `max_age_days` (optional) applies the freshness cutoff per
    FINAL_PLAN's freshness/staleness rules requirement.
    """
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStateError,
        memory_entry_to_dict,
    )
    store = get_workspace_memory_store()
    try:
        entries = store.list_entries(
            workspace_id=workspace_id, max_age_days=max_age_days,
        )
    except WorkspaceMemoryStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "count": len(entries),
        "entries": [memory_entry_to_dict(e) for e in entries],
    }


@router.post("/api/inspector/workspaces/{workspace_id}/memory/retrieve")
async def retrieve_workspace_memory(
    workspace_id: str,
    query: str,
    caller: Caller = Depends(require_workspace_viewer),
    top_k: int = 10,
    max_age_days: float | None = None,
) -> dict:
    """Active retrieval surface — returns ranked memory entries
    matching `query` keywords. The Inspector + the V30 runner both
    consume this; the runner labels matched entries as
    'memory-derived' in the rendered audit (per FINAL_PLAN
    attribution requirement).
    """
    from src.polaris_graph.audit_ir.workspace_memory import (
        WorkspaceMemoryStateError,
        memory_entry_to_dict,
    )
    store = get_workspace_memory_store()
    try:
        results = store.retrieve(
            workspace_id=workspace_id, query=query, top_k=top_k,
            max_age_days=max_age_days,
        )
    except WorkspaceMemoryStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "count": len(results),
        "results": [
            {"entry": memory_entry_to_dict(e), "score": round(score, 4)}
            for (e, score) in results
        ],
    }


@router.delete(
    "/api/inspector/workspaces/{workspace_id}/memory/{entry_id}"
)
async def delete_workspace_memory_entry(
    workspace_id: str,
    entry_id: str,
    caller: Caller = Depends(require_workspace_member),
) -> dict:
    """Hard-delete one memory entry. Per FINAL_PLAN, memory must
    be user-removable; deletion is irreversible (no soft-delete
    tombstone) so customers can guarantee data purge."""
    store = get_workspace_memory_store()
    deleted = store.delete_entry(
        workspace_id=workspace_id, entry_id=entry_id,
    )
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=(
                f"memory entry {entry_id!r} not found in workspace "
                f"{workspace_id!r}"
            ),
        )
    return {"deleted": True, "entry_id": entry_id}


# ---------------------------------------------------------------------------
# Review queue (M-23)
# ---------------------------------------------------------------------------


class CreateReviewRequest(BaseModel):
    run_slug: str = Field(..., description="audit slug being reviewed")
    run_id: str = Field(..., description="specific run_id under review")
    prior_review_id: str | None = Field(
        default=None,
        description=(
            "If this review chains from a prior NEEDS_CHANGES review "
            "(re-review of the same audit shape after re-running), "
            "pass the prior review_id; new review's version = prior + 1."
        ),
    )


class ReviewDecisionRequest(BaseModel):
    decision: str = Field(
        ...,
        description="One of: approved, rejected, needs_changes",
    )
    notes: str | None = Field(
        default=None,
        description="Reviewer notes; required for rejected/needs_changes.",
    )


@router.post("/api/inspector/reviews")
async def create_review(
    req: CreateReviewRequest,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict:
    """Enqueue a run for human review. Members and above can
    create; the new review is org-scoped to caller.org_id."""
    from src.polaris_graph.audit_ir.auth_middleware import (
        require_org_member_of,
    )
    require_org_member_of(caller, caller.org_id, "member")
    from src.polaris_graph.audit_ir.review_store import (
        ReviewStateError,
        review_to_dict,
    )
    store = get_review_store()
    try:
        item = store.enqueue(
            org_id=caller.org_id,
            run_slug=req.run_slug,
            run_id=req.run_id,
            prior_review_id=req.prior_review_id,
        )
    except ReviewStateError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return review_to_dict(item)


@router.get("/api/inspector/reviews")
async def list_reviews(
    caller: Caller = Depends(require_authenticated_caller),
    status: str | None = None,
) -> dict:
    """List reviews scoped to the caller's org. Optional `status`
    filter (case-sensitive enum value, e.g. 'pending')."""
    from src.polaris_graph.audit_ir.review_store import (
        ReviewStatus,
        review_to_dict,
    )
    status_filter: ReviewStatus | None = None
    if status:
        try:
            status_filter = ReviewStatus(status)
        except ValueError:
            valid = ", ".join(s.value for s in ReviewStatus)
            raise HTTPException(
                status_code=400,
                detail=f"unknown status {status!r}; expected one of {valid}",
            )
    store = get_review_store()
    items = store.list_by_org(org_id=caller.org_id, status=status_filter)
    return {
        "count": len(items),
        "reviews": [review_to_dict(i) for i in items],
    }


@router.get("/api/inspector/reviews/{review_id}")
async def get_review(
    review_id: str,
    caller: Caller = Depends(require_review_viewer),
) -> dict:
    from src.polaris_graph.audit_ir.review_store import review_to_dict
    item = get_review_store().get(
        review_id=review_id, org_id=caller.org_id,
    )
    if item is None:
        # Should never happen — require_review_viewer already 404'd.
        raise HTTPException(
            status_code=404, detail=f"unknown review_id: {review_id}",
        )
    return review_to_dict(item)


@router.post("/api/inspector/reviews/{review_id}/claim")
async def claim_review(
    review_id: str,
    caller: Caller = Depends(require_review_member),
) -> dict:
    from src.polaris_graph.audit_ir.review_store import (
        ReviewStateError,
        review_to_dict,
    )
    try:
        item = get_review_store().claim(
            review_id=review_id,
            org_id=caller.org_id,
            user_id=caller.user_id,
        )
    except ReviewStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return review_to_dict(item)


@router.post("/api/inspector/reviews/{review_id}/decision")
async def decide_review(
    review_id: str,
    req: ReviewDecisionRequest,
    caller: Caller = Depends(require_review_member),
) -> dict:
    from src.polaris_graph.audit_ir.review_store import (
        ReviewStateError,
        ReviewStatus,
        review_to_dict,
    )
    valid_decisions = {
        "approved": ReviewStatus.APPROVED,
        "rejected": ReviewStatus.REJECTED,
        "needs_changes": ReviewStatus.NEEDS_CHANGES,
    }
    if req.decision not in valid_decisions:
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown decision {req.decision!r}; expected one of "
                f"{', '.join(valid_decisions)}"
            ),
        )
    if req.decision in ("rejected", "needs_changes") and not (
        req.notes and req.notes.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"decision {req.decision!r} requires non-empty notes "
                f"explaining why"
            ),
        )

    store = get_review_store()
    try:
        if req.decision == "approved":
            item = store.approve(
                review_id=review_id, org_id=caller.org_id,
                user_id=caller.user_id, notes=req.notes,
            )
        elif req.decision == "rejected":
            item = store.reject(
                review_id=review_id, org_id=caller.org_id,
                user_id=caller.user_id, notes=req.notes,
            )
        else:  # needs_changes
            item = store.request_changes(
                review_id=review_id, org_id=caller.org_id,
                user_id=caller.user_id, notes=req.notes,
            )
    except ReviewStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return review_to_dict(item)


@router.get("/api/inspector/reviews/{review_id}/transitions")
async def list_review_transitions(
    review_id: str,
    caller: Caller = Depends(require_review_viewer),
) -> dict:
    """Append-only audit log for one review."""
    rows = get_review_store().list_transitions(
        review_id=review_id, org_id=caller.org_id,
    )
    return {"count": len(rows), "transitions": rows}


@router.get("/api/inspector/reviews/{review_id}/diff")
async def get_review_version_diff(
    review_id: str,
    caller: Caller = Depends(require_review_viewer),
) -> dict:
    """M-23: version diff between this review's run and the
    prior review's run (only meaningful if prior_review_id is set).

    Returns the M-16 RunDiff projection. 400 if the review has no
    prior version.
    """
    from src.polaris_graph.audit_ir.review_store import review_to_dict
    from src.polaris_graph.audit_ir.run_diff import (
        diff_runs, diff_to_dict,
    )
    store = get_review_store()
    item = store.get(review_id=review_id, org_id=caller.org_id)
    if item is None:
        raise HTTPException(
            status_code=404, detail=f"unknown review_id: {review_id}",
        )
    if item.prior_review_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "this review has no prior version; version diff is "
                "only defined for chained reviews (re-reviews of the "
                "same audit shape)"
            ),
        )
    prior = store.get(
        review_id=item.prior_review_id, org_id=caller.org_id,
    )
    if prior is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f"review {review_id!r} declares prior "
                f"{item.prior_review_id!r} but it cannot be loaded"
            ),
        )

    # Codex M-23 v1 review fix: look up runs by run_id, NOT
    # run_slug. v1's find_run_by_slug() returned the same run for
    # both versions because chained reviews must share run_slug —
    # so the diff was always between a run and itself, surfacing
    # an empty-deltas false-positive.
    from src.polaris_graph.audit_ir.registry import find_run_by_id
    summary_a = find_run_by_id(prior.run_id)
    summary_b = find_run_by_id(item.run_id)
    if summary_a is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f"underlying run artifact unavailable for diff: "
                f"prior review {prior.review_id!r} references run "
                f"{prior.run_id!r} which is not mounted"
            ),
        )
    if summary_b is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f"underlying run artifact unavailable for diff: "
                f"current review {item.review_id!r} references run "
                f"{item.run_id!r} which is not mounted"
            ),
        )
    try:
        ir_a = load_audit_ir(summary_a.artifact_dir)
        ir_b = load_audit_ir(summary_b.artifact_dir)
    except (FileNotFoundError, AuditIRSchemaError) as exc:
        raise HTTPException(
            status_code=500, detail=f"cannot load AuditIR: {exc}",
        )
    try:
        d = diff_runs(ir_a, ir_b)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "prior_review": review_to_dict(prior),
        "current_review": review_to_dict(item),
        "diff": diff_to_dict(d),
    }


# ════════════════════════════════════════════════════════════════════
# M-LIVE-3 — Operator dashboard (Inspector aggregates panel)
# ════════════════════════════════════════════════════════════════════
#
# Endpoints:
#   - GET /api/inspector/dashboard/decision-aggregates
#   - GET /api/inspector/dashboard/freshness-aggregates
#   - GET /api/inspector/dashboard/pin-trends
#
# All require authentication; all org-scoped via caller.org_id.
# Rollback: PG_USE_OPERATOR_DASHBOARD=0 returns 404 (default ON).
# ════════════════════════════════════════════════════════════════════


def _operator_dashboard_endpoint_enabled() -> bool:
    return os.environ.get(
        "PG_USE_OPERATOR_DASHBOARD", "1",
    ) != "0"


async def _require_operator_dashboard_endpoint_enabled() -> None:
    if not _operator_dashboard_endpoint_enabled():
        raise HTTPException(
            status_code=404,
            detail="operator dashboard endpoint disabled",
        )


def _freshness_db_path() -> Path:
    raw = os.environ.get("PG_FRESHNESS_DB_PATH")
    if raw:
        return Path(raw)
    base = Path(__file__).resolve().parents[3] / "state"
    base.mkdir(parents=True, exist_ok=True)
    return base / "freshness_alerts.sqlite"


_FRESHNESS_STORE: FreshnessAlertStore | None = None
_FRESHNESS_STORE_LOCK = threading.Lock()


def _get_freshness_store() -> FreshnessAlertStore:
    global _FRESHNESS_STORE
    with _FRESHNESS_STORE_LOCK:
        if _FRESHNESS_STORE is None:
            _FRESHNESS_STORE = FreshnessAlertStore(_freshness_db_path())
        return _FRESHNESS_STORE


def _reset_freshness_store_for_test() -> None:
    global _FRESHNESS_STORE
    with _FRESHNESS_STORE_LOCK:
        _FRESHNESS_STORE = None


def _decision_aggregates_to_dict(agg: DecisionAggregates) -> dict[str, Any]:
    return {
        "workspace_id": agg.workspace_id,
        "decision_kind": (
            agg.decision_kind.value
            if agg.decision_kind is not None
            else None
        ),
        "window_start": agg.window_start,
        "window_end": agg.window_end,
        "total_decisions": agg.total_decisions,
        "total_terminal": agg.total_terminal,
        "pending_count": agg.pending_count,
        "accepted_count": agg.accepted_count,
        "modified_count": agg.modified_count,
        "overridden_count": agg.overridden_count,
        "rejected_count": agg.rejected_count,
        "acceptance_rate": agg.acceptance_rate,
        "modification_rate": agg.modification_rate,
        "override_rate": agg.override_rate,
        "rejection_rate": agg.rejection_rate,
    }


def _freshness_aggregates_to_dict(
    agg: FreshnessAggregates,
) -> dict[str, Any]:
    return {
        "workspace_id": agg.workspace_id,
        "window_start": agg.window_start,
        "window_end": agg.window_end,
        "only_latest_per_source": agg.only_latest_per_source,
        "total_alerts": agg.total_alerts,
        "unchanged_count": agg.unchanged_count,
        "superseded_count": agg.superseded_count,
        "retracted_count": agg.retracted_count,
        "expression_of_concern_count":
            agg.expression_of_concern_count,
        "unreachable_count": agg.unreachable_count,
        "evicting_count": agg.evicting_count,
        "unique_source_count": agg.unique_source_count,
    }


def _pin_trend_report_to_dict(report: PinTrendReport) -> dict[str, Any]:
    return {
        "pin_count": report.pin_count,
        "window_start": report.window_start,
        "window_end": report.window_end,
        "verdict": (
            report.verdict.value
            if hasattr(report.verdict, "value")
            else str(report.verdict)
        ),
        "drift_event_count": len(report.drift_events),
        "drift_events": [
            {
                "captured_at": e.captured_at,
                "pin_index": e.pin_index,
                "dimension": (
                    e.dimension.value
                    if hasattr(e.dimension, "value")
                    else str(e.dimension)
                ),
                # v2 R1 P0 fix: PinDriftEvent uses `before`/`after`,
                # not `from_value`/`to_value`. v1 attribute name was
                # wrong → endpoint 500'd whenever the pin set had
                # any drift event. Repro: 2 pins with one model
                # change → AttributeError.
                "before": e.before,
                "after": e.after,
            }
            for e in report.drift_events
        ],
        "dimension_stats": [
            {
                "dimension": (
                    s.dimension.value
                    if hasattr(s.dimension, "value")
                    else str(s.dimension)
                ),
                "stability_score": s.stability_score,
                "change_count": s.change_count,
            }
            for s in report.dimension_stats
        ],
    }


@router.get(
    "/api/inspector/dashboard/decision-aggregates",
    dependencies=[Depends(_require_operator_dashboard_endpoint_enabled)],
)
async def get_decision_aggregates(
    decision_kind: str | None = None,
    since: float | None = None,
    until: float | None = None,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict[str, Any]:
    """Operator dashboard: decision aggregates for caller's org.

    Workspace is the caller's `org_id`. Time-windowed via
    `since` / `until` (UNIX epoch seconds; both inclusive).
    """
    kind: DecisionKind | None = None
    if decision_kind is not None:
        try:
            kind = DecisionKind(decision_kind)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"invalid decision_kind: {decision_kind!r}; "
                    f"expected one of "
                    f"{[k.value for k in DecisionKind]}"
                ),
            )
    store = _get_decision_store()
    try:
        agg = compute_aggregates(
            store,
            workspace_id=caller.org_id,
            decision_kind=kind,
            since=since,
            until=until,
        )
    except DecisionAggregatesError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _decision_aggregates_to_dict(agg)


@router.get(
    "/api/inspector/dashboard/freshness-aggregates",
    dependencies=[Depends(_require_operator_dashboard_endpoint_enabled)],
)
async def get_freshness_aggregates(
    since: float | None = None,
    until: float | None = None,
    only_latest_per_source: bool = False,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict[str, Any]:
    """Operator dashboard: freshness aggregates for caller's org."""
    store = _get_freshness_store()
    try:
        agg = compute_freshness_aggregates(
            store,
            workspace_id=caller.org_id,
            since=since,
            until=until,
            only_latest_per_source=only_latest_per_source,
        )
    except FreshnessAggregatesError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _freshness_aggregates_to_dict(agg)


@router.get(
    "/api/inspector/dashboard/pin-trends",
    dependencies=[Depends(_require_operator_dashboard_endpoint_enabled)],
)
async def get_pin_trends(
    out_root: str | None = None,
    caller: Caller = Depends(require_authenticated_caller),
) -> dict[str, Any]:
    """Operator dashboard: pin trends across recent runs.

    Pins are loaded by globbing `model_pin.json` files under
    `out_root` (default: `outputs/`). Org-scoping for v1 is
    best-effort: pin files do not currently carry an org_id;
    auth gates access but per-org pin filtering is deferred to
    when M-INT-0b adds org_id to the capture path.
    """
    repo_root = Path(__file__).resolve().parents[3]
    if out_root is None:
        scan_root = repo_root / "outputs"
    else:
        cand = Path(out_root)
        scan_root = (
            cand if cand.is_absolute() else (repo_root / cand)
        ).resolve()
        try:
            scan_root.relative_to(repo_root.resolve())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="out_root must be inside the repository",
            )
    if not scan_root.exists():
        raise HTTPException(
            status_code=404,
            detail=f"out_root does not exist: {scan_root}",
        )

    pin_files = sorted(
        scan_root.rglob("model_pin.json"),
        key=lambda p: p.stat().st_mtime,
    )
    pins = []
    for pf in pin_files:
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
            pins.append(pin_from_dict(data))
        except Exception:
            continue
    pins.sort(key=lambda p: p.captured_at)
    if not pins:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no valid model_pin.json files found under "
                f"{scan_root}"
            ),
        )
    try:
        report = analyze_pin_trends(pins)
    except PinTrendError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _pin_trend_report_to_dict(report)


# ════════════════════════════════════════════════════════════════════
# M-PROD-3 — Production observability (Prometheus-style metrics)
# ════════════════════════════════════════════════════════════════════
#
# Exposes a `/api/inspector/metrics` endpoint with substrate
# invocation counters + endpoint latency histograms. JSON format
# in v1; v2 may add a Prometheus text-format variant for direct
# scrape integration.
#
# Counters are in-memory + per-process. Production deployment
# should use a proper metrics backend (StatsD / Prometheus
# pushgateway / OTel) but this v1 surface is the minimum
# operator-visible signal for a dry-run.
#
# Rollback: PG_USE_METRICS_ENDPOINT=0 returns 404 (default ON).
# ════════════════════════════════════════════════════════════════════


_METRICS_LOCK = threading.Lock()
_SUBSTRATE_COUNTERS: dict[str, int] = {}
_ENDPOINT_COUNTERS: dict[str, int] = {}
_ENDPOINT_LATENCY_NS: dict[str, list[int]] = {}


def increment_substrate_counter(substrate_id: str) -> None:
    """Increment a per-substrate invocation counter. Called by
    Phase E substrates (M-INT-0a, M-INT-1, ..., M-INT-11) when
    they fire in production. Thread-safe."""
    if not isinstance(substrate_id, str) or not substrate_id.strip():
        return
    with _METRICS_LOCK:
        _SUBSTRATE_COUNTERS[substrate_id] = (
            _SUBSTRATE_COUNTERS.get(substrate_id, 0) + 1
        )


def record_endpoint_latency(
    endpoint: str, latency_ns: int,
) -> None:
    """Record one endpoint request + its latency. Thread-safe."""
    if not isinstance(endpoint, str) or not endpoint.strip():
        return
    with _METRICS_LOCK:
        _ENDPOINT_COUNTERS[endpoint] = (
            _ENDPOINT_COUNTERS.get(endpoint, 0) + 1
        )
        _ENDPOINT_LATENCY_NS.setdefault(endpoint, []).append(
            int(latency_ns),
        )


def _reset_metrics_for_test() -> None:
    """Test helper. Production code MUST NOT call this."""
    with _METRICS_LOCK:
        _SUBSTRATE_COUNTERS.clear()
        _ENDPOINT_COUNTERS.clear()
        _ENDPOINT_LATENCY_NS.clear()


def _percentile_ns(values: list[int], q: float) -> int:
    """Nearest-rank percentile.

    v2 R1 P1 fix: v1 used `int(q * len(s))` which selects the
    NEXT-higher element instead of the correct sorted-list
    index. Codex repro:
      _percentile_ns([10, 20], 0.50) returned 20 (should be 10)
      _percentile_ns(range(1, 101), 0.95) returned 96 (should be 95)
      _percentile_ns(range(1, 101), 0.99) returned 100 (should be 99)
    Correct nearest-rank formula: idx = ceil(q * n) - 1
    (1-indexed → 0-indexed conversion).
    """
    if not values:
        return 0
    s = sorted(values)
    n = len(s)
    import math
    idx = max(0, min(n - 1, math.ceil(q * n) - 1))
    return s[idx]


def _metrics_endpoint_enabled() -> bool:
    return os.environ.get("PG_USE_METRICS_ENDPOINT", "1") != "0"


async def _require_metrics_endpoint_enabled() -> None:
    if not _metrics_endpoint_enabled():
        raise HTTPException(
            status_code=404,
            detail="metrics endpoint disabled",
        )


@router.get(
    "/api/inspector/metrics",
    dependencies=[Depends(_require_metrics_endpoint_enabled)],
)
async def get_metrics(
    caller: Caller = Depends(require_authenticated_caller),
) -> dict[str, Any]:
    """Operator-visible metrics: substrate invocation counts +
    per-endpoint request count + latency p50/p95/p99.

    Auth required. Any authenticated caller in any role can
    read; per-org filtering is not applied because metrics are
    process-global (operator observability, not per-tenant
    billing). Production deployments using multi-tenant
    isolation should run separate FastAPI processes per tenant
    or wrap this endpoint behind an admin-role check.
    """
    with _METRICS_LOCK:
        substrates = dict(_SUBSTRATE_COUNTERS)
        endpoints = dict(_ENDPOINT_COUNTERS)
        latencies_snapshot = {
            k: list(v) for k, v in _ENDPOINT_LATENCY_NS.items()
        }
    endpoint_latency: dict[str, dict[str, float]] = {}
    for ep, ns_list in latencies_snapshot.items():
        if not ns_list:
            continue
        endpoint_latency[ep] = {
            "p50_ms": _percentile_ns(ns_list, 0.50) / 1_000_000,
            "p95_ms": _percentile_ns(ns_list, 0.95) / 1_000_000,
            "p99_ms": _percentile_ns(ns_list, 0.99) / 1_000_000,
            "max_ms": max(ns_list) / 1_000_000,
            "count": len(ns_list),
        }
    return {
        "substrate_invocations_total": substrates,
        "endpoint_requests_total": endpoints,
        "endpoint_latency": endpoint_latency,
        "metrics_version": "v1",
    }
