"""Runs router — POST /runs, GET /runs/{id}.

Phase 0 stub: enqueue + status flow only. Real run execution wires up in
Phase 1 once requirements-v6.txt is installed in the dev cluster (Task
0.3) and the pipeline-A bridge in adapters/ is implemented.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from polaris_v6.schemas.run_request import RunRequest
from polaris_v6.schemas.run_status import RunStatusResponse

router = APIRouter(prefix="/runs", tags=["runs"])

_run_table: dict[str, RunStatusResponse] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("", response_model=RunStatusResponse, status_code=202)
def create_run(payload: RunRequest) -> RunStatusResponse:
    run_id = uuid.uuid4().hex
    record = RunStatusResponse(
        run_id=run_id,
        status="queued",
        template=payload.template,
        question=payload.question,
        queued_at=_now_iso(),
    )
    _run_table[run_id] = record
    # Phase 0 stub: real enqueue happens in Phase 1 once Dramatiq broker
    # is wired in production (acceptance test scenarios 1-8 verified).
    # from polaris_v6.queue.actors import enqueue_research_run
    # enqueue_research_run.send(run_id, payload.model_dump())
    return record


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str) -> RunStatusResponse:
    record = _run_table.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    return record
