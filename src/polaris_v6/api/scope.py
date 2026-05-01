"""POST /scope/check — F1 scope discovery panel endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from polaris_v6.scope.decision import ScopeDecision, classify_scope
from polaris_v6.schemas.run_request import TemplateId

router = APIRouter(prefix="/scope", tags=["scope"])


class ScopeCheckRequest(BaseModel):
    template: TemplateId
    question: str = Field(..., min_length=1, max_length=2000)


@router.post("/check", response_model=ScopeDecision)
def check_scope(payload: ScopeCheckRequest) -> ScopeDecision:
    return classify_scope(payload.template, payload.question)
