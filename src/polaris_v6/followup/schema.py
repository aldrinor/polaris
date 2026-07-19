"""Follow-up agent schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

FollowUpStatus = Literal[
    "answered",
    "out_of_scope",
    "needs_new_run",
    "evidence_insufficient",
]


class FollowUpRequest(BaseModel):
    """Request to answer a follow-up question against a prior run.

    Names the ``parent_run_id`` whose evidence pool bounds retrieval and the
    ``question`` to answer (4-2000 chars).
    """

    parent_run_id: str
    question: str = Field(..., min_length=4, max_length=2000)


class FollowUpAnswer(BaseModel):
    parent_run_id: str
    question: str
    status: FollowUpStatus
    answer_text: str | None = Field(
        default=None,
        description="None when status != 'answered'.",
    )
    used_evidence_ids: list[str] = Field(default_factory=list)
    provenance_tokens: list[str] = Field(default_factory=list)
    rationale: str = Field(
        ...,
        min_length=8,
        description="Why this answer / why this status.",
    )
