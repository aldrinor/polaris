"""Runs router — POST /runs, GET /runs/{id}.

I-phase0-005 (Codex APPROVE iter 4): persist runs to SQLite via
polaris_v6.queue.run_store and enqueue the Dramatiq actor on POST.
Replaces the previous in-memory `_run_table` dict.
"""

from __future__ import annotations

import sqlite3
import uuid

from fastapi import APIRouter, HTTPException

from polaris_v6.queue import run_store
from polaris_v6.queue.actors import enqueue_research_run
from polaris_v6.schemas.run_request import RunRequest
from polaris_v6.schemas.run_status import RunStatusResponse

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunStatusResponse, status_code=202)
def create_run(payload: RunRequest) -> RunStatusResponse:
    run_id = uuid.uuid4().hex
    try:
        run_store.insert_run(run_id, payload.template, payload.question)
    except sqlite3.IntegrityError as exc:
        # uuid4 collision is theoretically impossible but defensive
        raise HTTPException(status_code=409, detail=f"run {run_id!r} already exists") from exc
    except RuntimeError as exc:
        # init_db permission-denied or similar
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    enqueue_research_run.send(run_id, payload.model_dump())

    record = run_store.get_run(run_id)
    if record is None:  # pragma: no cover — insert just succeeded
        raise HTTPException(status_code=500, detail="run row vanished after insert")
    return record


@router.get("/{run_id}", response_model=RunStatusResponse)
def get_run(run_id: str) -> RunStatusResponse:
    record = run_store.get_run(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"run {run_id!r} not found")
    return record
