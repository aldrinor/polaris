"""Runs router — POST /runs, GET /runs/{id}.

I-phase0-005 (Codex APPROVE iter 4): persist runs to SQLite via
polaris_v6.queue.run_store and enqueue the Dramatiq actor on POST.
Replaces the previous in-memory `_run_table` dict.

I-rdy-010 (#506): POST /runs resolves uploaded `document_ids` to content
BEFORE inserting/enqueuing the run, so a missing or unparsed upload fails
loud here rather than leaving a queued orphan run. The resolved content is
embedded in the actor message because the Dramatiq worker is a separate
process and cannot read the API process's in-memory upload table.
"""

from __future__ import annotations

import sqlite3
import uuid

from fastapi import APIRouter, HTTPException

from polaris_v6.api.upload import chunk_text, get_upload_record
from polaris_v6.queue import run_store
from polaris_v6.queue.actors import enqueue_research_run
from polaris_v6.schemas.run_request import RunRequest
from polaris_v6.schemas.run_status import RunStatusResponse

router = APIRouter(prefix="/runs", tags=["runs"])


def _resolve_uploaded_documents(document_ids: list[str]) -> list[dict]:
    """Resolve uploaded document_ids → content for actor-message embedding.

    Returns one dict per id: `{document_id, classification, filename,
    chunks}`. `chunks` is `chunk_text(record.content)` — the full document
    re-chunked (and capped), NOT the 3-chunk `chunk_preview`.

    Fails loud (HTTP 400) per LAW II on:
      * a document_id with no upload record;
      * an upload that yields no extractable text (e.g. an unparsed
        pdf/docx) — a silent zero-evidence run would mislead the operator.
    """
    resolved: list[dict] = []
    for document_id in document_ids:
        record = get_upload_record(document_id)
        if record is None:
            raise HTTPException(
                status_code=400,
                detail=f"uploaded document {document_id!r} not found",
            )
        chunks = chunk_text(record.content)
        if not chunks:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"uploaded document {document_id!r} ({record.filename}) "
                    "has no extractable text — pdf/docx parsing is not yet "
                    "available; upload a .md or .txt document to ground a run."
                ),
            )
        resolved.append(
            {
                "document_id": document_id,
                "classification": record.classification,
                "filename": record.filename,
                "chunks": chunks,
            }
        )
    return resolved


@router.post("", response_model=RunStatusResponse, status_code=202)
def create_run(payload: RunRequest) -> RunStatusResponse:
    # I-rdy-010: resolve uploads BEFORE insert_run/enqueue so a bad
    # document_id fails loud here instead of orphaning a queued run.
    uploaded_documents = _resolve_uploaded_documents(payload.document_ids)

    run_id = uuid.uuid4().hex
    try:
        run_store.insert_run(run_id, payload.template, payload.question)
    except sqlite3.IntegrityError as exc:
        # uuid4 collision is theoretically impossible but defensive
        raise HTTPException(status_code=409, detail=f"run {run_id!r} already exists") from exc
    except RuntimeError as exc:
        # init_db permission-denied or similar
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # The actor message carries the resolved upload content (the worker is
    # a separate process — it cannot read the API process's upload table).
    actor_payload = payload.model_dump()
    actor_payload["uploaded_documents"] = uploaded_documents
    enqueue_research_run.send(run_id, actor_payload)

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
