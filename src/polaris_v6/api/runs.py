"""Runs router — POST /runs, GET /runs/{id}.

I-phase0-005 (Codex APPROVE iter 4): persist runs to SQLite via
polaris_v6.queue.run_store and enqueue the Dramatiq actor on POST.
Replaces the previous in-memory `_run_table` dict.

I-rdy-013 (2026-05-16): POST /runs enforces the 1-concurrent-session
constraint via `run_store.insert_run_if_idle` — a 2nd concurrent request
is cleanly rejected with HTTP 409 (never enqueued) and a structured detail
the frontend renders as a link to the active run.
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
        active = run_store.insert_run_if_idle(
            run_id, payload.template, payload.question
        )
    except sqlite3.IntegrityError as exc:
        # uuid4 collision is theoretically impossible but defensive
        raise HTTPException(status_code=409, detail=f"run {run_id!r} already exists") from exc
    except RuntimeError as exc:
        # init_db permission-denied or similar
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if active is not None:
        # I-rdy-013: 1-concurrent-session constraint — a research run is
        # already queued or in progress. Reject cleanly; the rejected run is
        # never enqueued. The structured `detail` lets the frontend render a
        # specific UX with a link to the active run.
        raise HTTPException(
            status_code=409,
            detail={
                "code": "concurrent_run_active",
                "active_run_id": active.run_id,
                "active_status": active.lifecycle_status,
                "message": (
                    "POLARIS runs one research session at a time. "
                    f"Run {active.run_id[:8]} is currently {active.lifecycle_status}. "
                    "Wait for it to finish before starting a new run."
                ),
            },
        )

    try:
        enqueue_research_run.send(run_id, payload.model_dump())
    except Exception as exc:
        # I-rdy-013 (Codex diff P1-001): the queued row is already committed.
        # If enqueue fails it would never run yet would permanently hold the
        # single-session slot. Mark it failed (terminal → frees the slot),
        # then surface 503.
        run_store.mark_failed(run_id, f"enqueue failed: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"failed to enqueue run {run_id!r}: {exc}",
        ) from exc

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
