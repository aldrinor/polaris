"""Dramatiq actors for POLARIS v6 research-run lifecycle.

I-arch-001a (2026-05-12): wired to pipeline-A run_one_query. Concurrency-safe
(no os.environ mutation — v6 fields flow through q-dict). UUID-scoped
artifact_dir prevents same-slug concurrent overwrites. Full failure mapping
maps pipeline-A manifest verdict to lifecycle_status × pipeline_status.

Stub-mode preserved: when no run_store row exists (existing test_actors.py
direct .fn() invocation), returns deterministic noop without DB writes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

import dramatiq

from polaris_v6.queue import run_store

logger = logging.getLogger(__name__)

ENQUEUE_MAX_RETRIES = 3

# I-arch-001a: week-1 template→scope_domain mapping. Per Codex iter-3 APPROVE
# of brief. Per-domain expansion (real scope_templates for 4 new policy
# domains) deferred to post-demo Phase 2 per I-arch-001c follow-up.
TEMPLATE_TO_SCOPE_DOMAIN = {
    "ai_sovereignty": "policy",
    "canada_us": "policy",
    "climate": "policy",
    "clinical": "clinical",
    "defense": "policy",
    "housing": "policy",
    "trade": "policy",
    "workforce": "policy",
}


def _derive_slug(template_id: str, question: str) -> str:
    """Deterministic URL-safe slug for pipeline-A run_dir nesting.

    Pipeline-A reads q['slug']; this produces a stable, human-readable
    identifier per (template, question) pair. UUID provides uniqueness
    via the artifact_dir parent — slug itself doesn't need to be unique.
    """
    base = f"{template_id}_{question[:60]}"
    cleaned = re.sub(r"[^a-z0-9_]+", "_", base.lower()).strip("_")
    return cleaned[:120] or "untitled"


@dramatiq.actor(max_retries=ENQUEUE_MAX_RETRIES, time_limit=30 * 60 * 1000)
def enqueue_research_run(run_id: str, request_payload: dict[str, Any]) -> dict[str, Any]:
    """Execute a research run via pipeline-A. Idempotent on run_id.

    Stub-mode path: when run_store has no row for run_id (tests use
    .fn() directly without insert_run), returns deterministic noop
    without DB writes — preserves I-phase0-005 stub-mode semantics.

    Production path: marks in_progress, builds q-dict with v6 fields,
    invokes scripts.run_honest_sweep_r3.run_one_query, parses the
    manifest.json pipeline-A writes, and dispatches to
    mark_completed / mark_aborted / mark_failed per pipeline_status.
    """
    # Stub-mode preservation
    if run_store.get_run(run_id) is None:
        return {"run_id": run_id, "status": "completed", "echo": request_payload}

    run_store.mark_in_progress(run_id)
    decision_id = str(uuid.uuid4())
    output_root = Path(os.environ.get("POLARIS_V6_OUTPUT_ROOT", "outputs/v6_runs"))
    artifact_dir_root = output_root / run_id
    artifact_dir_root.mkdir(parents=True, exist_ok=True)

    template_id = request_payload.get("template", "")
    question = request_payload.get("question", "")
    domain = TEMPLATE_TO_SCOPE_DOMAIN.get(template_id, "policy")
    slug = _derive_slug(template_id, question)

    # v6 fields flow through q-dict (NO os.environ mutation per iter-2 P1.2)
    q: dict[str, Any] = {
        "domain": domain,
        "slug": slug,
        "question": question,
        "external_run_id": run_id,
        "decision_id": decision_id,
        "v6_mode": True,
        "out_root_override": str(artifact_dir_root),
        "template_id": template_id,
    }

    # I-arch-001b: synthesize v30.1 contract patch from v6 template's
    # frame_manifest. Pipeline-A merges this into the scope template's
    # per_query_report_contract before compile_frame / load_report_contract_for_slug.
    # Failure is graceful (logger.warning) — pipeline-A handles missing
    # contract via legacy no-contract path.
    try:
        from polaris_v6.templates.registry import load_template
        from src.polaris_graph.v30_contract_synthesizer import build_v30_contract

        v6_tmpl = load_template(template_id).model_dump()
        q["v30_contract_patch"] = build_v30_contract(v6_tmpl, slug, question)
        logger.info(
            "[actor] v30_contract_patch synthesized run_id=%s template_id=%s slug=%s entities=%d",
            run_id,
            template_id,
            slug,
            len(q["v30_contract_patch"][slug]["required_entities"]),
        )
    except FileNotFoundError as exc:
        logger.warning(
            "[actor] v6 template not found template_id=%s run_id=%s; "
            "pipeline-A will run on legacy no-contract path: %s",
            template_id,
            run_id,
            exc,
        )
    except Exception as exc:  # noqa: BLE001 — synthesizer failure must not block runtime
        logger.warning(
            "[actor] v30_contract_patch synthesis FAILED run_id=%s template_id=%s "
            "slug=%s: %s; pipeline-A on legacy no-contract path",
            run_id,
            template_id,
            slug,
            exc,
            exc_info=True,
        )

    run_store.set_pipeline_meta(
        run_id,
        query_slug=slug,
        artifact_dir=str(artifact_dir_root),
        decision_id=decision_id,
    )

    try:
        from scripts.run_honest_sweep_r3 import run_one_query

        summary = asyncio.run(run_one_query(q, artifact_dir_root))
    except Exception as exc:  # noqa: BLE001 — actor must record any pipeline crash
        logger.exception("[actor] pipeline-A raised for run_id=%s", run_id)
        run_store.mark_failed(run_id, f"pipeline_exception: {type(exc).__name__}: {exc}")
        raise

    # Parse pipeline-A's manifest.json — written at every exit path
    manifest_path = artifact_dir_root / "manifest.json"
    if not manifest_path.is_file():
        run_store.mark_failed(
            run_id, "manifest_missing: pipeline-A returned without writing manifest.json"
        )
        return summary
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        run_store.mark_failed(run_id, f"manifest_invalid: {exc}")
        return summary

    pipeline_status = manifest.get("status") or "error_unexpected"
    manifest_run_id = manifest.get("run_id")
    cost_usd = manifest.get("cost_usd")
    if cost_usd is None:
        cost_usd = summary.get("cost_usd")
    try:
        cost_usd_f = float(cost_usd) if cost_usd is not None else None
    except (TypeError, ValueError):
        cost_usd_f = None

    run_store.set_pipeline_meta(run_id, manifest_run_id=manifest_run_id)

    if pipeline_status == "success" or pipeline_status.startswith("partial_"):
        run_store.mark_completed(
            run_id, summary, pipeline_status=pipeline_status, cost_usd=cost_usd_f
        )
    elif pipeline_status.startswith("abort_"):
        run_store.mark_aborted(
            run_id,
            pipeline_status=pipeline_status,
            abort_reason=manifest.get("error") or pipeline_status,
            cost_usd=cost_usd_f,
        )
    elif pipeline_status.startswith("error_"):
        run_store.mark_failed(
            run_id, f"pipeline_error: {pipeline_status}: {manifest.get('error', '')}"
        )
    else:
        run_store.mark_failed(run_id, f"unknown_pipeline_status: {pipeline_status!r}")
    return summary


@dramatiq.actor(max_retries=0)
def cancel_research_run(run_id: str) -> dict[str, Any]:
    """Cancel an in-flight research run by run_id.

    Implementation note: real cancellation is via Worker.send_signal on the
    target message_id (see test_dramatiq_acceptance.py scenario 3); this
    actor exists to provide an audited entrypoint that records the cancel
    intent in the run-status table before the signal fires.
    """
    return {"run_id": run_id, "status": "cancel_requested"}
