"""I-deepfix-001 U19 (#1344) — the docling-OOM gate + extractor telemetry.

Two defects fixed here, both faithfulness-neutral (they only choose WHICH
extractor produces the verbatim text that strict_verify later grounds):

1. **The gate never ran docling when its threshold was disabled.** The fanout
   run set ``PG_MAX_DOCLING_PDF_BYTES=0`` intending "no limit", but the code
   treated 0 as a LITERAL cap, so ``len(pdf_bytes) > 0`` was true for EVERY
   non-empty PDF -> docling was ALWAYS skipped and every clinical PDF fell to
   flat PyMuPDF text (which mangles tables). A ``<= 0`` threshold must now mean
   "unlimited" so docling actually runs (mirrors the mineru25 circuit-breaker
   escape-hatch idiom).

2. **Telemetry mislabeled the extractor.** When the gate skipped docling and
   PyMuPDF ran, the tool trace still reported ``docling``. The final extractor
   must be recorded truthfully.

Offline: no network, no GPU, no paid LLM. Docling is stubbed; PyMuPDF (fitz)
runs on a real in-memory single-page PDF.
"""

from __future__ import annotations

import asyncio

import pytest

from src.tools.access_bypass import AccessBypass
from src.polaris_graph.telemetry.tool_tracer import (
    get_tool_tracer,
    reset_tool_tracer,
)

_URL = "https://example.org/clinical_table_paper.pdf"


def _pdf_extractor_calls():
    """Recorded pdf_extract tool-trace rows, most recent last."""
    return [c for c in get_tool_tracer().get_calls() if c.tool_name == "pdf_extract"]


def test_docling_runs_when_byte_guard_disabled(monkeypatch):
    """PG_MAX_DOCLING_PDF_BYTES=0 must mean 'unlimited' -> docling RUNS.

    Reproduces the fanout misconfiguration (``bytes=...>0`` skip on every PDF).
    With the fix the 0 threshold disables the guard, docling is invoked, and
    the telemetry reports the REAL extractor (docling).
    """
    # docling is the selected extractor (mineru25 path skipped); both OOM
    # guards disabled with the <=0 escape hatch (the fanout misconfig).
    monkeypatch.setenv("PG_CLINICAL_PDF_EXTRACTOR", "docling")
    monkeypatch.setenv("PG_MAX_DOCLING_PDF_BYTES", "0")
    monkeypatch.setenv("PG_MAX_DOCLING_PDF_PAGES", "0")
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")

    docling_output = "CLINICAL TABLE | dose | outcome | p-value\n" * 40  # > 500 chars
    called = {"docling": False}

    def _fake_docling(pdf_bytes: bytes) -> str:
        called["docling"] = True
        return docling_output

    monkeypatch.setattr(AccessBypass, "_docling_extract", staticmethod(_fake_docling))

    reset_tool_tracer()
    ab = AccessBypass()
    pdf_bytes = b"%PDF-1.4\n" + b"x" * 4096  # non-empty -> old code would skip docling

    result = asyncio.run(ab._extract_pdf_text_from_bytes(_URL, pdf_bytes))

    # Docling ACTUALLY ran (gate no longer skips it on a 0/disabled threshold).
    assert called["docling"] is True
    assert result == docling_output.strip() or result == docling_output
    assert "CLINICAL TABLE" in result

    # Telemetry reports the REAL extractor = docling, status ok.
    calls = _pdf_extractor_calls()
    assert calls, "expected a pdf_extract telemetry row"
    last = calls[-1]
    assert last.backend_used == "docling"
    assert last.status == "ok"


def test_pymupdf_labeled_when_guard_trips(monkeypatch):
    """A positive byte cap still trips -> PyMuPDF runs AND is labeled pymupdf.

    Proves (a) the guard still works when configured > 0, and (b) the tool
    trace reports the ground-truth extractor (pymupdf), never a stale docling.
    """
    fitz = pytest.importorskip("fitz")

    # Build a real one-page PDF with known body text (offline, no network).
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "MAGNESIUM SUPPLEMENTATION REDUCED SYSTOLIC BP")
    pdf_bytes = doc.tobytes()
    doc.close()

    # Small positive byte cap: the real PDF exceeds it -> byte guard trips ->
    # docling skipped -> PyMuPDF fallback runs.
    monkeypatch.setenv("PG_CLINICAL_PDF_EXTRACTOR", "docling")
    monkeypatch.setenv("PG_MAX_DOCLING_PDF_BYTES", "100")
    monkeypatch.setenv("PG_MAX_DOCLING_PDF_PAGES", "40")
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")
    assert len(pdf_bytes) > 100

    def _fail_docling(pdf_bytes: bytes) -> str:
        raise AssertionError("docling must NOT be called when the byte guard trips")

    monkeypatch.setattr(AccessBypass, "_docling_extract", staticmethod(_fail_docling))

    reset_tool_tracer()
    ab = AccessBypass()
    result = asyncio.run(ab._extract_pdf_text_from_bytes(_URL, pdf_bytes))

    assert "MAGNESIUM" in result.upper()

    calls = _pdf_extractor_calls()
    assert calls, "expected a pdf_extract telemetry row"
    last = calls[-1]
    assert last.backend_used == "pymupdf"
    assert last.status == "ok"
