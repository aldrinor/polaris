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

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from polaris_v6.api.artifact_to_slice_chain import (
    SovereigntyFilterEmptiedReportError,
    build_slice_chain,
)
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
    sign_fn=Depends(  # I-arch-001d Codex iter-2 P1-004: explicit Depends
        # Lazy import: audit_bundle_route depends on polaris_graph; we don't
        # want bundle.py import to fail if that subtree has runtime issues
        # outside this endpoint.
        lambda: _resolve_sign_fn()
    ),
):
    """Resolve run_id → artifact_dir → signed audit bundle (tar.gz).

    Status codes:
        200: bundleable run; returns application/gzip
        404: run not found, not completed, or artifact_dir missing
        422: run aborted (pipeline_status=abort_*) or sovereignty cascade
             emptied the report
        503: GPG signer not configured (POLARIS_GPG_KEY_ID unset)
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

    try:
        decision, pool, report = build_slice_chain(artifact_dir)
    except SovereigntyFilterEmptiedReportError as exc:
        raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": f"artifact_dir incomplete: {exc}"},
        ) from exc

    # Lazy import keeps top-of-file imports clean of polaris_graph dependency.
    from polaris_graph.api.audit_bundle_route import (
        AuditBundleRequest,
        post_audit_bundle,
    )

    return post_audit_bundle(
        AuditBundleRequest(decision=decision, pool=pool, report=report),
        sign_fn=sign_fn,
    )


def _resolve_sign_fn():
    """Lazy import of audit_bundle_route.get_sign_fn for FastAPI Depends.

    The audit_bundle_route module imports polaris_graph; deferring keeps
    bundle.py loadable even when the polaris_graph subtree has an init
    issue (it doesn't today, but the lazy pattern is defensive).
    """
    from polaris_graph.api.audit_bundle_route import get_sign_fn
    return get_sign_fn()
