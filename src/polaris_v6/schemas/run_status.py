"""Run-status response schema."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RunStatus = Literal[
    "queued",
    "in_progress",
    "completed",
    "cancelled",
    "failed",
    "abort_scope_rejected",
    "abort_corpus_inadequate",
    "abort_corpus_approval_denied",
    "abort_no_verified_sections",
]


class RunStatusResponse(BaseModel):
    run_id: str = Field(..., description="Server-assigned run id.")
    status: RunStatus = Field(
        ...,
        description=(
            "Pipeline verdict per CLAUDE.md §9.3. abort_* statuses are pipeline "
            "verdicts (not errors); failed/cancelled are operational outcomes."
        ),
    )
    template: str
    question: str
    queued_at: str = Field(..., description="ISO8601 UTC.")
    started_at: str | None = None
    finished_at: str | None = None
    # I-phase0-005 fix: JSON-encoded actor return value when status='completed'.
    # Optional; default None preserves backward-compat for existing callers.
    result_json: str | None = None
