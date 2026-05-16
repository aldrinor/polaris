"""GET /runs/{run_id}/bundle — F15 audit bundle export.

This is the artifact Carney's office receives. Per docs/blockers.md §5,
real bundle redistribution policy is gated on Phase 1/2 legal IP review;
for COPYRIGHTED sources the bundle exports citations + DOI links only,
not verbatim spans.

Phase 0 ships the endpoint contract that returns an EvidenceContract
v1.0 JSON. Phase 1 wires it to the actual run-storage backend; here we
serve a synthetic bundle from the golden corpus when a known run_id
matches, otherwise 404.

I-arch-001d (2026-05-13) adds GET /runs/{run_id}/bundle.tar.gz which
resolves run_id → artifact_dir via run_store and returns a real
GPG-signed audit bundle via the build_slice_chain bridge.
"""

from __future__ import annotations

import json  # noqa: F401 — used by release_allowed gate below
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

# I-arch-001d Codex diff iter-1 P1-001 fix: import get_sign_fn at module top
# so FastAPI Depends() identity matches what app.dependency_overrides keys on.
# A lambda Depends would be a DIFFERENT callable than get_sign_fn — the
# create_app() override wouldn't fire and the endpoint would always 503.
from polaris_graph.api.audit_bundle_route import (
    AuditBundleRequest,
    get_sign_fn,
    post_audit_bundle,
)
from polaris_v6.api.artifact_to_slice_chain import (
    SovereigntyFilterEmptiedReportError,
    build_slice_chain,
)
from polaris_v6.api.live_run_adapter import live_run_evidence_contract
from polaris_v6.queue import run_store
from polaris_v6.schemas.evidence_contract import EvidenceContract

router = APIRouter(prefix="/runs", tags=["bundle"])

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "v6" / "fixtures" / "evidence_contract_v1"

_GOLDEN_RUN_INDEX = {
    "golden_clinical_001": "golden_run_clinical.json",
    "golden_housing_002": "golden_run_with_contradiction.json",
    "golden_abort_003": "golden_run_abort_no_verified.json",
    "golden_defense_004": "golden_run_defense.json",
    "golden_climate_005": "golden_run_climate.json",
    "golden_ai_006": "golden_run_ai_sovereignty.json",
    "golden_with_drop_reason": "golden_run_with_drop_reason.json",
}


@router.get("/{run_id}/bundle", response_model=EvidenceContract)
def get_bundle(run_id: str) -> EvidenceContract:
    # I-rdy-008: a live completed run resolves through the live_run adapter;
    # only fall back to the golden fixture index when no run_store row exists.
    live = live_run_evidence_contract(run_id)
    if live is not None:
        return live
    fixture_name = _GOLDEN_RUN_INDEX.get(run_id)
    if fixture_name is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bundle for run {run_id!r} not found. Available golden runs: {list(_GOLDEN_RUN_INDEX)}",
        )
    raw = json.loads((_FIXTURE_DIR / fixture_name).read_text())
    return EvidenceContract.model_validate(raw)


@router.get("/{run_id}/bundle.tar.gz")
def get_run_bundle_targz(
    run_id: str,
    sign_fn=Depends(get_sign_fn),
):
    """Resolve run_id → artifact_dir → signed audit bundle (tar.gz).

    I-arch-001d Codex diff iter-1 P1-001: `Depends(get_sign_fn)` MUST use
    the actual `get_sign_fn` callable from audit_bundle_route — the
    create_app() registers `app.dependency_overrides[get_sign_fn]` to
    inject the real GPGSigner when POLARIS_GPG_KEY_ID is set. A lambda
    Depends would be a different callable; the override would never fire.

    Status codes:
        200: bundleable run; returns application/gzip
        404: run not found, not completed, or artifact_dir missing
        422: run aborted (pipeline_status=abort_*) or sovereignty cascade
             emptied the report
        503: GPG signer not configured (POLARIS_GPG_KEY_ID unset) — surfaced
             by the inner post_audit_bundle when sign_fn is None.
    """
    info = run_store.get_run(run_id)
    if info is None:
        raise HTTPException(status_code=404, detail={"error": "run not found"})
    if info.lifecycle_status != "completed":
        raise HTTPException(
            status_code=404,
            detail={"error": f"run not completed: lifecycle_status={info.lifecycle_status}"},
        )
    if info.pipeline_status and info.pipeline_status.startswith("abort_"):
        raise HTTPException(
            status_code=422,
            detail={"error": f"run aborted: pipeline_status={info.pipeline_status}", "bundleable": False},
        )
    if not info.artifact_dir:
        raise HTTPException(
            status_code=404, detail={"error": "run has no artifact_dir recorded"}
        )

    artifact_dir = Path(info.artifact_dir)
    if not artifact_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail={"error": f"artifact_dir does not exist on disk: {artifact_dir}"},
        )

    # I-arch-001d Codex diff iter-2 P1-002 fix: release_allowed gate.
    # The slice-chain pipeline_verdict collapses partial_* into "success",
    # but a release-blocked partial (e.g. partial_qwen_advisory with
    # release_allowed=false) MUST NOT ship as a clean bundle. Read the raw
    # manifest.release_allowed flag and refuse with 422 when False.
    try:
        manifest_raw = json.loads((artifact_dir / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": f"manifest.json missing or invalid: {exc}"},
        ) from exc
    if not manifest_raw.get("release_allowed", False):
        raise HTTPException(
            status_code=422,
            detail={
                "error": (
                    f"run release-blocked: pipeline_status={info.pipeline_status!r}, "
                    f"release_allowed=False. Bundle cannot ship until release gate clears."
                ),
                "bundleable": False,
                "pipeline_status": info.pipeline_status,
            },
        )

    try:
        decision, pool, report = build_slice_chain(artifact_dir)
    except SovereigntyFilterEmptiedReportError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": f"artifact_dir incomplete: {exc}"},
        ) from exc

    return post_audit_bundle(
        AuditBundleRequest(decision=decision, pool=pool, report=report),
        sign_fn=sign_fn,
    )
