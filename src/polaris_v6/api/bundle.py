"""GET /runs/{run_id}/bundle — F15 audit bundle export.

This is the artifact Carney's office receives. Per docs/blockers.md §5,
real bundle redistribution policy is gated on Phase 1/2 legal IP review;
for COPYRIGHTED sources the bundle exports citations + DOI links only,
not verbatim spans.

Phase 0 ships the endpoint contract that returns an EvidenceContract
v1.0 JSON. Phase 1 wires it to the actual run-storage backend; here we
serve a synthetic bundle from the golden corpus when a known run_id
matches, otherwise 404. This is enough to wire the frontend "Export
bundle" button end-to-end.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from polaris_v6.schemas.evidence_contract import EvidenceContract

router = APIRouter(prefix="/runs", tags=["bundle"])

_FIXTURE_DIR = Path(__file__).resolve().parents[3] / "tests" / "v6" / "fixtures" / "evidence_contract_v1"

_GOLDEN_RUN_INDEX = {
    "golden_clinical_001": "golden_run_clinical.json",
    "golden_housing_002": "golden_run_with_contradiction.json",
    "golden_abort_003": "golden_run_abort_no_verified.json",
}


@router.get("/{run_id}/bundle", response_model=EvidenceContract)
def get_bundle(run_id: str) -> EvidenceContract:
    fixture_name = _GOLDEN_RUN_INDEX.get(run_id)
    if fixture_name is None:
        raise HTTPException(
            status_code=404,
            detail=f"Bundle for run {run_id!r} not found. Available golden runs: {list(_GOLDEN_RUN_INDEX)}",
        )
    raw = json.loads((_FIXTURE_DIR / fixture_name).read_text())
    return EvidenceContract.model_validate(raw)
