"""POST /ambiguity — F2 ambiguity check endpoints.

Two routes:

* ``POST /ambiguity`` — caller supplies candidate snippets directly
  (e.g. the dashboard builds them from uploaded-document chunks).
* ``POST /ambiguity/scan`` (I-rdy-009 / #505) — *question-only*. The
  backend fetches candidate snippets via one cheap web search before
  running ``detect_ambiguity``, so an ambiguous bare question triggers
  the disambiguation modal in the main create-run flow. On a
  candidate-fetch failure it returns HTTP 503
  ``candidate_fetch_unavailable`` — never a silent false-unambiguous
  result.

Both return the same ``AmbiguityCheckResponse`` so the frontend can
render a disambiguation modal before any expensive retrieval / generator
cost is incurred.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from polaris_v6.ambiguity_detector import (
    CandidateFetchError,
    CandidateSnippet,
    detect_ambiguity,
    fetch_candidate_snippets,
)
from polaris_v6.ambiguity_detector.ambiguity_detector import AmbiguityResult

router = APIRouter(prefix="/ambiguity", tags=["ambiguity"])


class CandidateIn(BaseModel):
    source_id: str
    text: str = Field(..., min_length=1, max_length=8000)


class AmbiguityCheckRequest(BaseModel):
    question: str = Field(..., min_length=4, max_length=2000)
    candidates: list[CandidateIn] = Field(
        ...,
        min_length=0,
        description=(
            "Pre-fetched candidate snippets. Phase 0: caller supplies. "
            "Phase 1: backend fetches via cheap retrieval before this call."
        ),
    )
    min_cluster_size: int = Field(default=2, ge=1)
    similarity_threshold: float = Field(default=0.5, ge=0.0, le=1.0)


class AmbiguityScanRequest(BaseModel):
    """POST body for /ambiguity/scan — a question with no caller-supplied
    candidates. The backend fetches candidates itself."""

    question: str = Field(..., min_length=4, max_length=2000)


class AmbiguityClusterOut(BaseModel):
    cluster_id: int
    representative_text: str
    member_source_ids: list[str]


class AmbiguityCheckResponse(BaseModel):
    is_ambiguous: bool
    clusters: list[AmbiguityClusterOut]
    fallback_used: bool


def _to_check_response(result: AmbiguityResult) -> AmbiguityCheckResponse:
    """Map a detector ``AmbiguityResult`` onto the HTTP response shape."""
    return AmbiguityCheckResponse(
        is_ambiguous=result.is_ambiguous,
        clusters=[
            AmbiguityClusterOut(
                cluster_id=c.cluster_id,
                representative_text=c.representative_text,
                member_source_ids=c.member_source_ids,
            )
            for c in result.clusters
        ],
        fallback_used=result.fallback_used,
    )


@router.post("", response_model=AmbiguityCheckResponse)
def check_ambiguity(payload: AmbiguityCheckRequest) -> AmbiguityCheckResponse:
    snippets = [
        CandidateSnippet(source_id=c.source_id, text=c.text) for c in payload.candidates
    ]
    result = detect_ambiguity(
        snippets,
        min_cluster_size=payload.min_cluster_size,
        similarity_threshold=payload.similarity_threshold,
    )
    return _to_check_response(result)


@router.post("/scan", response_model=AmbiguityCheckResponse)
async def scan_ambiguity(payload: AmbiguityScanRequest) -> AmbiguityCheckResponse:
    """Question-only ambiguity check for the main create-run flow.

    Fetches candidate snippets server-side via one cheap web search (the
    "Phase 1" candidate retrieval the ``/ambiguity`` docstring
    anticipated), then runs ``detect_ambiguity``. A candidate-fetch
    failure (no ``SERPER_API_KEY``, search unreachable, zero results)
    returns HTTP 503 ``candidate_fetch_unavailable`` rather than a
    silent false-unambiguous result.
    """
    try:
        snippets = await fetch_candidate_snippets(payload.question)
    except CandidateFetchError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": True,
                "code": "candidate_fetch_unavailable",
                "message": str(exc),
            },
        ) from exc
    result = detect_ambiguity(snippets)
    return _to_check_response(result)
