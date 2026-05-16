"""GET /runs/{left}/compare/{right} — F12 side-by-side compare endpoint."""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from polaris_v6.api.bundle import _FIXTURE_DIR, _GOLDEN_RUN_INDEX
from polaris_v6.api.live_run_adapter import live_run_evidence_contract
from polaris_v6.compare.differ import compare_reports
from polaris_v6.schemas.evidence_contract import EvidenceContract

router = APIRouter(prefix="/runs", tags=["compare"])


def _load(run_id: str) -> EvidenceContract:
    # I-rdy-008: live completed run first; fall back to the golden fixture index.
    live = live_run_evidence_contract(run_id)
    if live is not None:
        return live
    fixture_name = _GOLDEN_RUN_INDEX.get(run_id)
    if fixture_name is None:
        raise HTTPException(
            status_code=404, detail=f"Bundle for run {run_id!r} not found."
        )
    raw = json.loads((_FIXTURE_DIR / fixture_name).read_text())
    return EvidenceContract.model_validate(raw)


@router.get("/{left_run_id}/compare/{right_run_id}")
def get_compare(left_run_id: str, right_run_id: str) -> dict:
    if left_run_id == right_run_id:
        raise HTTPException(
            status_code=400, detail="compare requires two distinct run ids"
        )
    left = _load(left_run_id)
    right = _load(right_run_id)
    return asdict(compare_reports(left, right))
