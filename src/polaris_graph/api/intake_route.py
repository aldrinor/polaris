"""FastAPI HTTP route for the intake pipeline.

Per slice 001 architecture proposal §"Module boundaries":
    api/intake.py      → process_intake() pure-function orchestrator
    api/intake_route.py → FastAPI APIRouter exposing it as POST /api/intake

The router is mountable into any FastAPI app:

    from fastapi import FastAPI
    from polaris_graph.api.intake_route import router as intake_router

    app = FastAPI()
    app.include_router(intake_router, prefix="/api")

Or run as a standalone server:

    python -m polaris_graph.api.intake_route  # if invoked directly

Tests use FastAPI TestClient (no real HTTP server required).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from polaris_graph.api.intake import IntakeError, process_intake
from polaris_graph.scope.scope_decision import ScopeDecision

router = APIRouter(tags=["intake"])


class IntakeRequest(BaseModel):
    """POST body for /api/intake."""

    question: str = Field(
        description="User-typed clinical research question",
        min_length=1,
        max_length=2000,  # outer cap; normalize() enforces 1000 internal limit
    )


class IntakeErrorResponse(BaseModel):
    """Returned when the intake produces an IntakeError (HTTP 400)."""

    error: bool = True
    code: str  # 'too_short' | 'too_long' | 'invalid_input'
    message: str
    raw: str


class IntakeSuccessResponse(BaseModel):
    """Returned when the intake produces a ScopeDecision (HTTP 200).

    Wraps ScopeDecision plus standard top-level metadata.
    """

    error: bool = False
    decision: dict  # ScopeDecision.model_dump(mode="json")
    server_time_utc: str


@router.post(
    "/intake",
    response_model=None,  # union response — let FastAPI emit either shape
)
def post_intake(req: IntakeRequest) -> IntakeSuccessResponse | IntakeErrorResponse:
    """Run a question through the BPEI front-half pipeline.

    Returns ScopeDecision on success (HTTP 200) or IntakeError shape
    (HTTP 400) when the question is malformed.
    """
    result = process_intake(req.question)

    if isinstance(result, IntakeError):
        # 400 with structured error body
        raise HTTPException(
            status_code=400,
            detail={
                "error": True,
                "code": result.code,
                "message": result.message,
                "raw": result.raw,
            },
        )

    # ScopeDecision success path
    assert isinstance(result, ScopeDecision)
    return IntakeSuccessResponse(
        decision=result.model_dump(mode="json"),
        server_time_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


@router.get("/intake/health")
def get_intake_health() -> dict[str, Any]:
    """Liveness probe + slice 001 backend version info."""
    return {
        "status": "ok",
        "slice": "slice_001_clinical_scope_discovery",
        "pipeline_stages": [
            "question_normalizer",
            "clinical_classifier",
            "ambiguity_detector_clinical",
            "scope_decision",
        ],
    }
