"""FastAPI HTTP route for the slice 002 clinical retrieval pipeline.

Per `.codex/slices/slice_002/architecture_proposal.md` §"api/retrieval_route".

Mirrors slice 001's `api/intake_route.py` pattern:

    api/intake_route.py     -> POST /api/intake
    api/retrieval_route.py  -> POST /api/retrieval (this module)

The route accepts a ScopeDecision (typically passed straight from the
slice 001 intake response) and returns either an EvidencePool (HTTP 200)
or a structured RetrievalError body (HTTP 400).

Mount into any FastAPI app:

    from fastapi import FastAPI
    from polaris_graph.api.retrieval_route import router as retrieval_router

    app = FastAPI()
    app.include_router(retrieval_router, prefix="/api")

Tests use FastAPI TestClient (no real HTTP server, no real network).
The fetch_fn is injected via FastAPI's dependency-override mechanism;
in production it will be the real Serper + Semantic-Scholar fetcher
shipped in PR 7.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from polaris_graph.clinical_retrieval.clinical_retriever import (
    FetchHttpFn,
    process_retrieval,
)
from polaris_graph.clinical_retrieval.evidence_pool import EvidencePool, RetrievalError
from polaris_graph.scope.scope_decision import ScopeDecision

router = APIRouter(tags=["retrieval"])


# ---------------------------------------------------------------------------
# Dependency: fetch_fn injection point
# ---------------------------------------------------------------------------

def get_fetch_fn() -> FetchHttpFn | None:
    """Returns the active fetch_fn or None.

    None signals process_retrieval() to use its default sentinel, which
    raises and is caught by the orchestrator -> RetrievalError(
    fetch_backend_unavailable). Tests override this dep to inject stubs.
    PR 7 will replace this default with the real Serper + Semantic-Scholar
    fetcher.
    """
    return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RetrievalRequest(BaseModel):
    """POST body for /api/retrieval.

    Accepts a ScopeDecision verbatim (as returned by /api/intake).
    Pydantic re-validates the structure on the way in so a malformed
    decision yields HTTP 422 before the orchestrator runs.
    """

    decision: ScopeDecision = Field(
        description="ScopeDecision from slice 001 intake (status=in_scope, scope_class=clinical_*)",
    )


class RetrievalErrorResponse(BaseModel):
    """Body returned with HTTP 400 when retrieval cannot proceed."""

    error: bool = True
    code: str  # 'wrong_status' | 'wrong_scope_class' | 'fetch_backend_unavailable'
    message: str
    decision_id: str | None = None


class RetrievalSuccessResponse(BaseModel):
    """Body returned with HTTP 200 wrapping a successful EvidencePool."""

    error: bool = False
    pool: dict  # EvidencePool.model_dump(mode="json")
    server_time_utc: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post(
    "/retrieval",
    response_model=None,  # union response: success-shape or 400-error
)
def post_retrieval(
    req: RetrievalRequest,
    fetch_fn: FetchHttpFn | None = Depends(get_fetch_fn),
) -> RetrievalSuccessResponse | RetrievalErrorResponse:
    """Run a slice 001 ScopeDecision through clinical retrieval.

    Returns EvidencePool (HTTP 200) on success — note that an EvidencePool
    with adequacy.is_adequate=False is still HTTP 200 (the request
    succeeded, the corpus just isn't strong enough for downstream
    generation; UI surfaces the failure_reason). HTTP 400 is reserved
    for structural failures: wrong status, wrong scope class, fetch
    backend down.
    """
    if fetch_fn is None:
        result = process_retrieval(req.decision)
    else:
        result = process_retrieval(req.decision, fetch_fn=fetch_fn)

    if isinstance(result, RetrievalError):
        raise HTTPException(
            status_code=400,
            detail={
                "error": True,
                "code": result.code,
                "message": result.message,
                "decision_id": result.decision_id,
            },
        )

    assert isinstance(result, EvidencePool)
    return RetrievalSuccessResponse(
        pool=result.model_dump(mode="json"),
        server_time_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


@router.get("/retrieval/health")
def get_retrieval_health() -> dict[str, Any]:
    """Liveness probe + slice 002 backend version info."""
    return {
        "status": "ok",
        "slice": "slice_002_clinical_retrieval",
        "pipeline_stages": [
            "validate_decision",
            "query_planner",
            "fetch_backend",
            "clinical_source_registry",
            "url_dedup",
            "corpus_adequacy_gate",
        ],
        "fetch_backend": "sentinel",  # replaced by 'serper+semantic_scholar' in PR 7
    }
