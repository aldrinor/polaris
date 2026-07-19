"""POST /runs/{run_id}/followup — F11 report-scoped follow-up agent endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from polaris_v6.api.bundle import load_evidence_contract_for_run
from polaris_v6.followup.agent import answer_followup
from polaris_v6.followup.schema import FollowUpAnswer

router = APIRouter(prefix="/runs", tags=["followup"])


class FollowUpHttpRequest(BaseModel):
    """Request body for `POST /runs/{run_id}/followup`: the follow-up question."""

    question: str = Field(..., min_length=4, max_length=2000)


@router.post("/{run_id}/followup", response_model=FollowUpAnswer)
def post_followup(run_id: str, payload: FollowUpHttpRequest) -> FollowUpAnswer:
    """Answer a report-scoped follow-up question against a run's evidence bundle.

    Resolves the run's EvidenceContract (golden fixture or real completed run)
    and returns the follow-up agent's answer scoped to that parent report.
    404/422 propagate from `load_evidence_contract_for_run`.
    """
    # I-cd-680: resolves golden fixtures AND real completed runs (was
    # fixture-only → real runs 404).
    bundle = load_evidence_contract_for_run(run_id)
    return answer_followup(parent=bundle, question=payload.question)
