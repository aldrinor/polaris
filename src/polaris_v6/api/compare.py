"""GET /runs/{left}/compare/{right} — F12 side-by-side compare endpoint."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from polaris_v6.api.bundle import load_evidence_contract_for_run
from polaris_v6.compare.differ import compare_reports

router = APIRouter(prefix="/runs", tags=["compare"])


@router.get("/{left_run_id}/compare/{right_run_id}")
def get_compare(left_run_id: str, right_run_id: str) -> dict:
    if left_run_id == right_run_id:
        raise HTTPException(
            status_code=400, detail="compare requires two distinct run ids"
        )
    # I-cd-680: resolves golden fixtures AND real completed runs.
    left = load_evidence_contract_for_run(left_run_id)
    right = load_evidence_contract_for_run(right_run_id)
    return asdict(compare_reports(left, right))
