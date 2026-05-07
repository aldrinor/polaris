"""POST /upload — F3b drag-drop document upload endpoint.

Per docs/carney_delivery_plan_v6_2.md F3b, the user can upload PDFs /
docx / md / txt to seed a research run. Phase 0 ships the contract:
returns a document_id + parse_status; Phase 1 wires actual parsing +
chunking + sovereignty router (CAN_REAL data must stay on Canadian
infra).

Per CLAUDE.md security posture: file content classification
(PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN) is set by
the caller; default is UNKNOWN and triggers conservative routing.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Literal

from fastapi import APIRouter, Form, HTTPException, UploadFile
from pydantic import BaseModel

router = APIRouter(prefix="/upload", tags=["upload"])

DataClassification = Literal[
    "PUBLIC_SYNTHETIC",
    "CAN_REAL",
    "PRIVATE",
    "CLIENT",
    "UNKNOWN",
]

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
MAX_BYTES = 50 * 1024 * 1024  # 50 MB per upload (I-f3-005 frontend dropzone)


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    bytes: int
    sha256: str
    classification: DataClassification
    parse_status: Literal["queued", "completed", "failed"]
    chunk_preview: list[str]


_UPLOAD_TABLE: dict[str, UploadResponse] = {}


@router.post("", response_model=UploadResponse, status_code=201)
async def upload_document(
    file: UploadFile,
    classification: DataClassification = Form("UNKNOWN"),
) -> UploadResponse:
    if file.filename is None:
        raise HTTPException(status_code=400, detail="filename required")

    ext = "." + file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported extension {ext!r}. Allowed: {sorted(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {MAX_BYTES // (1024 * 1024)} MB limit",
        )
    if len(content) == 0:
        raise HTTPException(status_code=422, detail="empty file")

    sha = hashlib.sha256(content).hexdigest()
    document_id = uuid.uuid4().hex

    if ext in {".md", ".txt"}:
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
        chunks = [text[i : i + 280] for i in range(0, min(len(text), 840), 280) if text]
    else:
        chunks = []

    response = UploadResponse(
        document_id=document_id,
        filename=file.filename,
        bytes=len(content),
        sha256=sha,
        classification=classification,
        parse_status="completed" if chunks else "queued",
        chunk_preview=chunks[:3],
    )
    _UPLOAD_TABLE[document_id] = response
    return response


@router.get("/{document_id}", response_model=UploadResponse)
def get_upload(document_id: str) -> UploadResponse:
    record = _UPLOAD_TABLE.get(document_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"document {document_id!r} not found")
    return record
