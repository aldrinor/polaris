"""GET /runs/{run_id}/charts/{chart_type} — Vega-Lite spec endpoint."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException

from polaris_v6.api.bundle import _GOLDEN_RUN_INDEX, _FIXTURE_DIR
from polaris_v6.api.live_run_adapter import live_run_evidence_contract
from polaris_v6.charts.from_bundle import chart_from_bundle
from polaris_v6.schemas.evidence_contract import EvidenceContract

router = APIRouter(prefix="/runs", tags=["charts"])

ChartType = Literal["forest_plot", "comparison_table", "timeline"]


@router.get("/{run_id}/charts/{chart_type}")
def get_chart(run_id: str, chart_type: ChartType) -> dict:
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
    spec = chart_from_bundle(bundle=bundle, chart_type=chart_type)
    return spec
