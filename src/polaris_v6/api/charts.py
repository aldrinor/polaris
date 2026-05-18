"""GET /runs/{run_id}/charts/{chart_type} — Vega-Lite spec endpoint.

I-rdy-008 (#504) slice 8 (Codex architecture consult
`.codex/I-rdy-008/slice8_charts_arch_consult_verdict.txt`): the charts route
resolves a completed run via `run_store -> artifact_dir -> load_audit_ir()`
— the same path the inspector routes use — and derives the Vega-Lite spec
from the run's AuditIR (`chart_from_audit_ir`). It no longer reads the
golden-fixture `_GOLDEN_RUN_INDEX`; any completed run (golden or live) is
charted.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException

from polaris_graph.audit_ir.loader import load_audit_ir
from polaris_v6.api.run_resolver import resolve_completed_artifact_dir
from polaris_v6.charts.from_audit_ir import chart_from_audit_ir

router = APIRouter(prefix="/runs", tags=["charts"])

ChartType = Literal["forest_plot", "comparison_table", "timeline"]


@router.get("/{run_id}/charts/{chart_type}")
def get_chart(run_id: str, chart_type: ChartType) -> dict:
    """Return the Vega-Lite spec for one chart type of a completed run.

    Resolution mirrors the inspector route: unknown run -> 404 /
    not-completed -> 409 / abort_* / error_* -> 422 / missing artifact_dir
    -> 404 / artifact_dir present but unloadable -> 422 (fail loud). An
    unknown `chart_type` is rejected as 422 by the `ChartType` Literal.
    """
    artifact_dir = resolve_completed_artifact_dir(run_id)
    try:
        ir = load_audit_ir(artifact_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"run {run_id} artifact_dir failed AuditIR load: {exc}",
        ) from exc
    return chart_from_audit_ir(ir=ir, chart_type=chart_type)
