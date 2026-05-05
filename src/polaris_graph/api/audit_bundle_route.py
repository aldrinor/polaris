"""FastAPI route for slice 004 audit-bundle export.

POST /api/audit-bundle — accepts a {decision, pool, report} triple
(typically the slice 001 + 002 + 003 chain output) and streams back
a GPG-signed audit_<bundle_id>.tar.gz file.

Mounted alongside the other slice routes in polaris_v6.api.app.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from polaris_graph.audit_bundle.bundle_builder import (
    SignFn,
    build_audit_bundle,
)
from polaris_graph.generator2.verified_report import VerifiedReport
from polaris_graph.retrieval2.evidence_pool import EvidencePool
from polaris_graph.scope.scope_decision import ScopeDecision

router = APIRouter(tags=["audit-bundle"])


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_sign_fn() -> SignFn | None:
    """Returns the active GPG signer or None.

    None signals the orchestrator's sentinel default which raises and is
    caught by the route -> HTTP 503. Tests override this dep; production
    binds to a real GPGSigner via app.dependency_overrides at startup
    when POLARIS_GPG_KEY_ID is set.
    """
    return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AuditBundleRequest(BaseModel):
    """POST body for /api/audit-bundle.

    Carries the full BPEI chain (decision + pool + report). The route
    re-validates the FK chain consistency before building.
    """

    decision: ScopeDecision = Field(description="slice 001 ScopeDecision")
    pool: EvidencePool = Field(description="slice 002 EvidencePool")
    report: VerifiedReport = Field(
        description="slice 003 VerifiedReport (verdict=success required)"
    )


class AuditBundleErrorResponse(BaseModel):
    """Body returned with HTTP 4xx/5xx when bundle cannot be assembled."""

    error: bool = True
    code: str  # 'fk_chain_mismatch' | 'verdict_not_success' |
               # 'gpg_unavailable' | 'sign_failed'
    message: str
    report_id: str | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/audit-bundle")
def post_audit_bundle(
    req: AuditBundleRequest,
    sign_fn: SignFn | None = Depends(get_sign_fn),
) -> Any:
    """Build + return a GPG-signed audit bundle as application/gzip.

    Returns the .tar.gz file as a streaming download.
    """
    if sign_fn is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error": True,
                "code": "gpg_unavailable",
                "message": (
                    "GPG signer not configured. Set POLARIS_GPG_KEY_ID in env "
                    "and ensure the corresponding key is in the gpg keyring."
                ),
                "report_id": req.report.report_id,
            },
        )

    # Build into a temp dir; FileResponse copies it to the wire.
    tmp_dir = Path(tempfile.mkdtemp(prefix="polaris_audit_"))
    try:
        bundle_path = build_audit_bundle(
            req.decision,
            req.pool,
            req.report,
            output_dir=tmp_dir,
            sign_fn=sign_fn,
        )
    except ValueError as exc:
        # FK chain mismatch or verdict != success
        msg = str(exc)
        code = (
            "fk_chain_mismatch"
            if "FK chain" in msg or "pool_id" in msg or "decision_id" in msg
            else "verdict_not_success"
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": True,
                "code": code,
                "message": msg,
                "report_id": req.report.report_id,
            },
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error": True,
                "code": "sign_failed",
                "message": str(exc),
                "report_id": req.report.report_id,
            },
        )

    return FileResponse(
        path=str(bundle_path),
        filename=bundle_path.name,
        media_type="application/gzip",
    )


@router.get("/audit-bundle/health")
def get_audit_bundle_health(
    sign_fn: SignFn | None = Depends(get_sign_fn),
) -> dict[str, Any]:
    """Liveness probe + slice 004 backend version info.

    signing_backend reflects ACTUAL state via the Depends-injected sign_fn:
    - 'sentinel' if no signer is wired (POST will 503 — LAW II fail-loud)
    - 'gpg' if a real GPGSigner is bound via app.dependency_overrides
    """
    return {
        "status": "ok",
        "slice": "slice_004_audit_bundle_export",
        "pipeline_stages": [
            "validate_fk_chain",
            "build_manifest",
            "snapshot_sources",
            "serialize_yaml",
            "gpg_sign",
            "pack_tarball",
        ],
        "signing_backend": "gpg" if sign_fn is not None else "sentinel",
    }
