"""GET /api/inspector/runs/{run_id} — v6 live-inspector AuditIR resolver.

I-rdy-008 (#504) slice 1, Option A (Codex architecture-decision consult,
`.codex/I-rdy-008/arch_decision_verdict.txt`): the rich UI surfaces migrate
onto the canonical completed-run path
`run_id -> artifact_dir -> load_audit_ir() -> AuditIR`.

This is the demo-scoped v6 facade route — it exposes ONE completed-run read.
It deliberately does NOT mount `polaris_graph.audit_ir.inspector_router`, which
in current HEAD also carries non-demo surfaces (jobs, workspaces, operator
dashboards, metrics) per the consult's stale-correction.

Per `docs/live_run_artifact_contract.md` (#503) §2.3: `abort_*` / `error_*`
runs are pipeline-verdict artifacts, NOT AuditIR-loadable — rejected before
the loader is called.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from polaris_graph.audit_ir.loader import load_audit_ir
from polaris_graph.audit_ir.serializer import to_json_dict
from polaris_v6.queue import run_store

router = APIRouter(prefix="/api/inspector", tags=["inspector"])


@router.get("/runs/{run_id}")
def get_inspector_run(run_id: str) -> dict[str, Any]:
    """Return the full faithful AuditIR for a completed run as a JSON dict.

    The canonical data source for the Evidence Inspector and every derivative
    rich surface (I-rdy-008 #504, Option A). Resolution:

    - unknown run -> 404
    - run not completed -> 409
    - abort_* / error_* run -> 422 (no AuditIR-loadable artifacts)
    - missing / absent artifact_dir -> 404
    - artifact_dir present but unloadable -> 422 (fail loud, no zero-fill)
    - completed loadable run -> 200, full AuditIR JSON
    """
    record = run_store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")

    if record.lifecycle_status != "completed":
        raise HTTPException(
            status_code=409,
            detail=(
                f"run {run_id} is not completed "
                f"(lifecycle_status={record.lifecycle_status!r})"
            ),
        )

    status = record.pipeline_status or ""
    if status.startswith("abort_") or status.startswith("error_"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"run {run_id} produced no AuditIR-loadable artifacts "
                f"(pipeline_status={status!r}); it is a pipeline-verdict "
                f"artifact, not a renderable run"
            ),
        )

    if not record.artifact_dir:
        raise HTTPException(
            status_code=404,
            detail=f"run {run_id} has no artifact_dir recorded",
        )
    artifact_dir = Path(record.artifact_dir)
    if not artifact_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail=f"artifact_dir does not exist on disk: {artifact_dir}",
        )

    try:
        ir = load_audit_ir(artifact_dir)
    except (FileNotFoundError, NotADirectoryError, ValueError, TypeError) as exc:
        # AuditIRSchemaError and json.JSONDecodeError are both ValueError
        # subclasses; plain ValueError / TypeError also catch malformed
        # numeric fields (Codex brief iter-2 P2). Fail loud per audit-grade
        # discipline — no silent zero-fill of canonical structures.
        raise HTTPException(
            status_code=422,
            detail=f"run {run_id} artifact_dir failed AuditIR load: {exc}",
        ) from exc

    return to_json_dict(ir)
