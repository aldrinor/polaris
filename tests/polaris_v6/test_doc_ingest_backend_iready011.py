"""I-ready-011 (#1077) — PG_DOC_INGEST_BACKEND selector on the v6 upload path.

The v6 HTTP upload path (`upload.py`) decoded only .md/.txt and returned chunks=[] for PDF/DOCX
(→ runs.py HTTP 400 "pdf/docx parsing is not yet available"). This adds PG_DOC_INGEST_BACKEND:
  * legacy (DEFAULT) — byte-identical (PDF/DOCX still unparsed → empty chunks);
  * local — PDF/DOCX parsed via the EXISTING DocumentIngester (PyMuPDF + Tesseract fallback);
  * vlm/docling/surya/... — operator-gated heavy-OCR stub that fails LOUD (501), no model load.

Offline / §8.4-clean: the PDF fixture is born-digital (a text layer inserted via fitz), so the
'local' path uses PyMuPDF text extraction with NO OCR model (Tesseract fires only when the
extracted text is below threshold). DocumentIngester persistence is redirected to tmp.
"""

from __future__ import annotations

import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile

import polaris_graph.document_ingester as document_ingester
from polaris_v6.api import upload as upload_mod
from polaris_v6.api.upload import _doc_ingest_backend, upload_document

_PDF_TEXT = (
    "Synthetic trial fixture (PUBLIC_SYNTHETIC). In the ZORBLAX-7 study the experimental compound "
    "reduced the fictional Quibble Score by 42 percent versus placebo."
)


def _born_digital_pdf_bytes() -> bytes:
    """A 1-page PDF with a real text layer (no scan) → PyMuPDF text extraction, NO Tesseract."""
    import fitz  # PyMuPDF (in requirements.txt)

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 144), _PDF_TEXT, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _uf(name: str, content: bytes) -> UploadFile:
    return UploadFile(file=BytesIO(content), filename=name)


@pytest.fixture()
def _hermetic_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(document_ingester, "DOCUMENT_STORAGE_DIR", tmp_path / "doc_store")
    return tmp_path


@pytest.fixture(autouse=True)
def _clear_upload_table():
    upload_mod._UPLOAD_TABLE.clear()
    yield
    upload_mod._UPLOAD_TABLE.clear()


# ── default + selector ──────────────────────────────────────────────────────

def test_backend_default_is_legacy(monkeypatch):
    monkeypatch.delenv("PG_DOC_INGEST_BACKEND", raising=False)
    assert _doc_ingest_backend() == "legacy"
    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "LOCAL")
    assert _doc_ingest_backend() == "local"  # normalized lower


# ── legacy: byte-identical (PDF unparsed) ───────────────────────────────────

def test_legacy_pdf_yields_no_chunks(monkeypatch):
    monkeypatch.delenv("PG_DOC_INGEST_BACKEND", raising=False)  # default legacy
    resp = asyncio.run(upload_document(file=_uf("trial.pdf", b"%PDF-1.4 fake"), classification="PUBLIC_SYNTHETIC"))
    assert resp.content == ""
    assert resp.chunk_preview == []
    assert resp.parse_status == "queued"  # downstream runs.py then 400s — unchanged behavior


def test_md_unchanged_under_every_backend(monkeypatch):
    for backend in ("legacy", "local", "vlm"):
        monkeypatch.setenv("PG_DOC_INGEST_BACKEND", backend)
        resp = asyncio.run(upload_document(file=_uf("note.md", b"# Title\n\nHello world."), classification="PUBLIC_SYNTHETIC"))
        assert "Hello world." in resp.content
        assert resp.chunk_preview  # non-empty
        assert resp.parse_status == "completed"


# ── local: PDF parsed via existing DocumentIngester (no OCR model) ──────────

def test_local_pdf_is_parsed_to_chunks(_hermetic_storage, monkeypatch):
    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "local")
    resp = asyncio.run(upload_document(file=_uf("trial.pdf", _born_digital_pdf_bytes()), classification="PUBLIC_SYNTHETIC"))
    assert "ZORBLAX-7" in resp.content
    assert resp.chunk_preview  # non-empty → downstream runs.py will chunk + ground, no 400
    assert resp.parse_status == "completed"


def test_local_parse_failure_fails_loud(_hermetic_storage, monkeypatch):
    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "local")
    # Not a real PDF → DocumentIngester raises → 422 fail-loud (never silent-empty).
    with pytest.raises(HTTPException) as exc:
        asyncio.run(upload_document(file=_uf("broken.pdf", b"not a pdf at all"), classification="PUBLIC_SYNTHETIC"))
    assert exc.value.status_code == 422


# ── vlm: operator-gated fail-loud stub, no heavy import ─────────────────────

def test_unknown_backend_fails_loud_400(monkeypatch):
    """Codex diff-gate P2: a typo'd PG_DOC_INGEST_BACKEND must fail loud (400), not silently
    fall back to legacy (which would unparse a PDF the operator thinks they enabled)."""
    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "locl")  # typo
    with pytest.raises(HTTPException) as exc:
        asyncio.run(upload_document(file=_uf("trial.pdf", b"%PDF fake"), classification="PUBLIC_SYNTHETIC"))
    assert exc.value.status_code == 400
    assert "unknown" in str(exc.value.detail).lower()


def test_local_blank_extraction_fails_loud_422(monkeypatch):
    """Codex diff-gate P2: DocumentIngester can return blank without throwing (scanned/figure-only
    PDF). The 'local' backend must fail loud at upload (422), not defer a confusing /runs 400."""
    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", "local")

    async def _blank(content, ext):
        return "   \n\t  "  # whitespace-only extraction

    monkeypatch.setattr(upload_mod, "_extract_text_local", _blank)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(upload_document(file=_uf("scanned.pdf", b"%PDF fake"), classification="PUBLIC_SYNTHETIC"))
    assert exc.value.status_code == 422
    assert "no text" in str(exc.value.detail).lower()


@pytest.mark.parametrize("backend", ["vlm", "docling", "surya", "deepseek-ocr-2"])
def test_vlm_backend_fails_loud_501(monkeypatch, backend):
    import sys
    monkeypatch.setenv("PG_DOC_INGEST_BACKEND", backend)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(upload_document(file=_uf("trial.pdf", _born_digital_pdf_bytes() if False else b"%PDF fake"), classification="PUBLIC_SYNTHETIC"))
    assert exc.value.status_code == 501
    assert "operator" in str(exc.value.detail).lower()
    # The stub must NOT import a heavy OCR engine.
    assert "docling" not in sys.modules
    assert "surya" not in sys.modules
