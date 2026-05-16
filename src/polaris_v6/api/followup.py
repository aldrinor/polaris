"""POST /runs/{run_id}/followup — F11 report-scoped follow-up agent endpoint."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from polaris_v6.api.bundle import _FIXTURE_DIR, _GOLDEN_RUN_INDEX
from polaris_v6.api.live_run_adapter import live_run_evidence_contract
from polaris_v6.followup.agent import answer_followup
from polaris_v6.followup.schema import FollowUpAnswer
from polaris_v6.schemas.evidence_contract import EvidenceContract

router = APIRouter(prefix="/runs", tags=["followup"])


class FollowUpHttpRequest(BaseModel):
    question: str = Field(..., min_length=4, max_length=2000)


@router.post("/{run_id}/followup", response_model=FollowUpAnswer)
def post_followup(run_id: str, payload: FollowUpHttpRequest) -> FollowUpAnswer:
    # I-rdy-008: live completed run first; fall back to the golden fixture index.
    bundle = live_run_evidence_contract(run_id)
    if bundle is None:
        fixture_name = _GOLDEN_RUN_INDEX.get(run_id)
        if fixture_name is None:
            raise HTTPException(
                status_code=404,
                detail=f"Bundle for run {run_id!r} not found.",
            )
        raw = json.loads((_FIXTURE_DIR / fixture_name).read_text())
        bundle = EvidenceContract.model_validate(raw)
    return answer_followup(parent=bundle, question=payload.question)
