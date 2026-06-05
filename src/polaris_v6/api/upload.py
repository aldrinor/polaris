"""POST /upload — F3b drag-drop document upload endpoint.

Per docs/carney_delivery_plan_v6_2.md F3b, the user can upload PDFs /
docx / md / txt to seed a research run. Phase 0 ships the contract:
returns a document_id + parse_status; Phase 1 wires actual parsing +
chunking + sovereignty router (CAN_REAL data must stay on Canadian
infra).

Per CLAUDE.md security posture: file content classification
(PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN) is set by
the caller; default is UNKNOWN and triggers conservative routing.

I-rdy-010 (#506): `get_upload_record` + `chunk_text` let POST /runs
resolve uploaded document_ids to content at run-creation time. The
upload table is an in-process dict — the Dramatiq worker is a separate
process and cannot read it — so /runs (which runs in the API process)
resolves the content and embeds it in the actor message.
"""

from __future__ import annotations

import hashlib
import html as _html
import os
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

# I-rdy-010 (#506): grounding-chunk parameters. CHUNK_SIZE matches the
# upload-endpoint preview chunking; MAX_GROUNDING_CHUNKS bounds how much
# uploaded text is embedded into a Dramatiq actor message — a .md/.txt
# upload can be up to MAX_BYTES, so the full document is NOT embedded.
CHUNK_SIZE = 280
MAX_GROUNDING_CHUNKS = 40

# I-ready-011 (#1077): document-ingest backend selector (LAW VI). `legacy` (DEFAULT) keeps the
# .md/.txt-only behavior byte-identical (PDF/DOCX still fail loud downstream). `local` routes
# PDF/DOCX through the EXISTING DocumentIngester (PyMuPDF text + Tesseract OCR fallback,
# python-docx) — deps already in requirements.txt. The VLM-OCR backends (figure/chart/table
# understanding via docling/surya/deepseek-ocr-2) are OPERATOR-GATED heavy open-weight deps and
# fail LOUD here until installed + signed off (never loaded in the autonomous loop, §8.4).
_VLM_BACKENDS = frozenset({"vlm", "docling", "surya", "deepseek-ocr", "deepseek-ocr-2", "marker"})
_LOCAL_PARSE_EXTENSIONS = frozenset({".pdf", ".docx"})
# All recognised backend values. An unrecognised value (operator typo) FAILS LOUD rather than
# silently falling back to legacy (Codex diff-gate P2 — no silent config degradation, LAW II).
_KNOWN_BACKENDS = frozenset({"legacy", "local"}) | _VLM_BACKENDS


def _doc_ingest_backend() -> str:
    return os.environ.get("PG_DOC_INGEST_BACKEND", "legacy").strip().lower()


async def _extract_text_local(content: bytes, ext: str) -> str:
    """Extract text from PDF/DOCX bytes via the EXISTING DocumentIngester (PyMuPDF/python-docx +
    Tesseract OCR fallback). I-ready-011 (#1077).

    DocumentIngester.ingest takes a file PATH, so the bytes are written to a temp file with the
    real extension (the ingester dispatches on suffix). The import is LAZY so a `legacy` upload
    never pulls fitz/document_ingester. A born-digital text PDF uses PyMuPDF text extraction with
    NO OCR model (Tesseract fires only when extracted text < threshold).
    """
    import tempfile
    from pathlib import Path

    from polaris_graph.document_ingester import DocumentIngester

    tmp_path: "Path | None" = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        result = await DocumentIngester().ingest(tmp_path)
        return str(result.get("content") or "")
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    bytes: int
    sha256: str
    classification: DataClassification
    parse_status: Literal["queued", "completed", "failed"]
    chunk_preview: list[str]
    content: str = ""
    html: str = ""


_UPLOAD_TABLE: dict[str, UploadResponse] = {}


def chunk_text(
    text: str,
    *,
    size: int = CHUNK_SIZE,
    max_chunks: int = MAX_GROUNDING_CHUNKS,
) -> list[str]:
    """Split text into fixed-size chunks, capped at ``max_chunks``.

    The cap bounds the embedded actor-message payload (I-rdy-010) — an
    uploaded .md/.txt document can be up to ``MAX_BYTES``, so only the
    leading ``max_chunks`` are used to ground a run.
    """
    text = text.strip()
    if not text:
        return []
    chunks = [text[i : i + size] for i in range(0, len(text), size)]
    return chunks[:max_chunks]


def get_upload_record(document_id: str) -> UploadResponse | None:
    """Look up an uploaded document by id, or None if absent.

    Used by POST /runs (I-rdy-010) to resolve document_ids → content at
    run-creation time, in the API process that owns ``_UPLOAD_TABLE``.
    """
    return _UPLOAD_TABLE.get(document_id)


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

    backend = _doc_ingest_backend()
    if backend not in _KNOWN_BACKENDS:
        # Codex diff-gate P2: a typo'd backend must FAIL LOUD, not silently behave as legacy
        # (which would unparse a PDF the operator believes they enabled). LAW II — no silent
        # config degradation.
        raise HTTPException(
            status_code=400,
            detail=(
                f"unknown PG_DOC_INGEST_BACKEND={backend!r}; valid values: "
                f"{sorted(_KNOWN_BACKENDS)}."
            ),
        )
    if ext in {".md", ".txt"}:
        # Text formats: decode directly on EVERY backend (no parser/model needed) — unchanged.
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = ""
    elif backend in _VLM_BACKENDS:
        # I-ready-011 (#1077): VLM-OCR (figure/chart/table understanding) is operator-gated — heavy
        # open-weight deps (docling/surya/deepseek-ocr-2) not installed + never loaded in the
        # autonomous loop (§8.4). Fail LOUD so the operator sees exactly what to enable, never a
        # silent empty parse.
        raise HTTPException(
            status_code=501,
            detail=(
                f"PG_DOC_INGEST_BACKEND={backend!r} (VLM-OCR) is not enabled: it requires "
                "operator-installed open-weight OCR deps (docling / surya / deepseek-ocr-2) plus "
                "sovereignty sign-off. Use PG_DOC_INGEST_BACKEND=local (PyMuPDF/Tesseract) or the "
                "default 'legacy'."
            ),
        )
    elif backend == "local" and ext in _LOCAL_PARSE_EXTENSIONS:
        # I-ready-011 (#1077): parse PDF/DOCX via the EXISTING DocumentIngester (PyMuPDF text +
        # Tesseract OCR fallback for scanned pages; python-docx). The extracted text flows through
        # the SAME chunk_text + evidence path as a .md/.txt upload — no new verification bypass
        # (Codex brief-gate confirmed faithfulness-safe). Fail LOUD on a parse error.
        try:
            text = await _extract_text_local(content, ext)
        except Exception as exc:  # noqa: BLE001 — surface the parse failure, never silent-empty
            raise HTTPException(
                status_code=422,
                detail=f"failed to parse {ext} document with the 'local' backend: {exc}",
            ) from exc
        if not text.strip():
            # Codex diff-gate P2: DocumentIngester can return BLANK without raising (e.g. a
            # scanned/figure-only PDF where text extraction yields nothing). Fail LOUD at upload
            # time (not a deferred /runs 400) with an actionable pointer — consistent with the
            # parse-error branch above.
            raise HTTPException(
                status_code=422,
                detail=(
                    f"the 'local' backend extracted no text from this {ext} (likely a "
                    "scanned / figure-only document). Enable the VLM-OCR backend "
                    "(PG_DOC_INGEST_BACKEND=vlm) once its open-weight deps are installed."
                ),
            )
    else:
        # legacy (DEFAULT): non-text formats are not parsed here -> downstream fail-loud 400.
        text = ""

    chunks = [text[i : i + 280] for i in range(0, min(len(text), 840), 280) if text]
    preview_text = text
    preview_html = f"<pre>{_html.escape(text)}</pre>" if text else ""

    response = UploadResponse(
        document_id=document_id,
        filename=file.filename,
        bytes=len(content),
        sha256=sha,
        classification=classification,
        parse_status="completed" if chunks else "queued",
        chunk_preview=chunks[:3],
        content=preview_text,
        html=preview_html,
    )
    _UPLOAD_TABLE[document_id] = response
    return response


@router.get("/{document_id}", response_model=UploadResponse)
def get_upload(document_id: str) -> UploadResponse:
    record = _UPLOAD_TABLE.get(document_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"document {document_id!r} not found")
    return record
