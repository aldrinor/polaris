"""POST /ambiguity — F2 ambiguity check endpoint.

Takes a question + optional candidate snippets, returns the
AmbiguityResult so the frontend can render a disambiguation modal
before any expensive retrieval / generator cost is incurred.

Phase 0 contract: candidates are passed in by the caller (typically a
cheap candidate-fetcher in the backend will populate them in Phase 1).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from polaris_v6.bpei.ambiguity_detector import (
    CandidateSnippet,
    detect_ambiguity,
)

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


class AmbiguityClusterOut(BaseModel):
    cluster_id: int
    representative_text: str
    member_source_ids: list[str]


class AmbiguityCheckResponse(BaseModel):
    is_ambiguous: bool
    clusters: list[AmbiguityClusterOut]
    fallback_used: bool


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
