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

from polaris_v6.ambiguity_detector import (
    CandidateSnippet,
    detect_ambiguity,
)

router = APIRouter(prefix="/ambiguity", tags=["ambiguity"])


class CandidateIn(BaseModel):
    """One pre-fetched candidate snippet: its source id and text."""

    source_id: str
    text: str = Field(..., min_length=1, max_length=8000)


class AmbiguityCheckRequest(BaseModel):
    """Request body for `POST /ambiguity`.

    Carries the user `question`, caller-supplied candidate snippets (may be
    empty), and the clustering knobs `min_cluster_size` and
    `similarity_threshold` passed through to `detect_ambiguity`.
    """

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
    """One detected ambiguity cluster: its id, representative text, and members."""

    cluster_id: int
    representative_text: str
    member_source_ids: list[str]


class AmbiguityCheckResponse(BaseModel):
    """Response body for `POST /ambiguity`.

    `is_ambiguous` signals whether disambiguation is warranted, `clusters`
    enumerates the detected clusters, and `fallback_used` reports whether the
    detector fell back to its heuristic path.
    """

    is_ambiguous: bool
    clusters: list[AmbiguityClusterOut]
    fallback_used: bool


@router.post("", response_model=AmbiguityCheckResponse)
def check_ambiguity(payload: AmbiguityCheckRequest) -> AmbiguityCheckResponse:
    """Run F2 ambiguity detection over the request's candidate snippets.

    Converts the inbound candidates to detector snippets, runs
    `detect_ambiguity` with the request's clustering knobs, and returns the
    clusters and ambiguity verdict for the frontend disambiguation modal.
    """
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
