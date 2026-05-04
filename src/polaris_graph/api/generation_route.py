"""FastAPI HTTP route for slice 003 generation pipeline.

POST /api/generation — accepts an EvidencePool (typically the slice 002
response) and returns a VerifiedReport (HTTP 200) or GenerationError
detail (HTTP 400).

Mirrors slice 001 intake_route.py + slice 002 retrieval_route.py.

Mount:
    from polaris_graph.api.generation_route import router as generation_router
    app.include_router(generation_router, prefix="/api")
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from polaris_graph.generator2.generator import (
    GeneratorCompletionFn,
    process_generation,
)
from polaris_graph.generator2.verified_report import (
    GenerationError,
    VerifiedReport,
)
from polaris_graph.retrieval2.evidence_pool import EvidencePool

router = APIRouter(tags=["generation"])


# ---------------------------------------------------------------------------
# Dependency: completion_fn injection
# ---------------------------------------------------------------------------

def get_completion_fn() -> GeneratorCompletionFn | None:
    """Returns the active completion_fn or None.

    None signals process_generation() to use its default sentinel which
    triggers GenerationError(completion_backend_unavailable). Tests
    override this dep; PR 7 will replace the production default with the
    real OpenRouter-backed adapter.
    """
    return None


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class GenerationRequest(BaseModel):
    """POST body for /api/generation.

    Accepts an EvidencePool verbatim (as returned by /api/retrieval).
    Pydantic re-validates the structure on the way in so a malformed
    pool yields HTTP 422 before the orchestrator runs.

    `scope_class` is OPTIONAL but recommended; without it the generator
    falls back to the clinical_efficacy blueprint. Callers chaining
    intake -> retrieval -> generation should thread the slice 001
    ScopeDecision.scope_class through.
    """

    pool: EvidencePool = Field(
        description="EvidencePool from slice 002 retrieval (adequacy=True)"
    )
    scope_class: str | None = Field(
        default=None,
        description=(
            "Optional clinical_* scope class to select the section "
            "blueprint. Defaults to clinical_efficacy when omitted."
        ),
    )


class GenerationErrorResponse(BaseModel):
    """Body returned with HTTP 400 when generation cannot proceed."""

    error: bool = True
    code: str
    message: str
    pool_id: str | None = None
    decision_id: str | None = None


class GenerationSuccessResponse(BaseModel):
    """Body returned with HTTP 200 wrapping a VerifiedReport.

    Note: a VerifiedReport with verdict='abort_no_verified_sections' is
    still HTTP 200 (request succeeded; the corpus generated but every
    section failed strict-verify; UI surfaces the abort verdict).
    HTTP 400 is reserved for structural failures: inadequate input pool,
    completion backend down, malformed output.
    """

    error: bool = False
    report: dict
    server_time_utc: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/generation", response_model=None)
def post_generation(
    req: GenerationRequest,
    completion_fn: GeneratorCompletionFn | None = Depends(get_completion_fn),
) -> GenerationSuccessResponse | GenerationErrorResponse:
    """Run an EvidencePool through generator + strict-verify."""
    if completion_fn is None:
        result = process_generation(
            req.pool, scope_class=req.scope_class
        )
    else:
        result = process_generation(
            req.pool,
            completion_fn=completion_fn,
            scope_class=req.scope_class,
        )

    if isinstance(result, GenerationError):
        raise HTTPException(
            status_code=400,
            detail={
                "error": True,
                "code": result.code,
                "message": result.message,
                "pool_id": result.pool_id,
                "decision_id": result.decision_id,
            },
        )

    assert isinstance(result, VerifiedReport)
    return GenerationSuccessResponse(
        report=result.model_dump(mode="json"),
        server_time_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )


@router.get("/generation/health")
def get_generation_health() -> dict[str, Any]:
    """Liveness probe + slice 003 backend version info."""
    return {
        "status": "ok",
        "slice": "slice_003_generator_strict_verify",
        "pipeline_stages": [
            "validate_pool",
            "section_blueprint",
            "completion_fn",
            "sentence_split",
            "strict_verify",
            "section_pass_rate",
            "regeneration",
            "verdict",
        ],
        "completion_backend": "sentinel",  # PR 7 -> 'openrouter_deepseek'
    }
