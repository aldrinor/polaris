"""I-wire-003 B3 (#1317): offline unit test for the clinical-PDF winner (W4
mineru25) degradation flag derived from ``pdf_extract`` tool-trace rows.

The flag is PURE (derived from recorded rows, never a process global) so this
test needs NO network / NO LLM / NO GPU / NO unittest.mock — it records the same
``pdf_extract`` rows the access layer's ``_record`` writes on each branch and
asserts the manifest-surfaced ``clinical_pdf_winner_degraded`` shape.

Covers:
* a mineru25 WIN row -> degraded False, win_count 1, requested True.
* a mineru25 FALLBACK row (each of the 4 reasons) -> degraded True with the
  reason histogram + the CPU extractor that actually ran.
* NO pdf_extract rows (docling default — selector never called) -> degraded
  False, requested False (the legit baseline is NOT a degradation).
* per-query reset isolates the flag (no leak across a sweep).
* attach_tool_utilization stamps the top-level manifest key (ON), and OFF-mode
  never adds it (byte-identity).
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.telemetry.tool_tracer import (
    ToolTracer,
    attach_tool_utilization,
    get_tool_tracer,
    reset_tool_tracer,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_tool_tracer()
    yield
    reset_tool_tracer()


def _win(tracer: ToolTracer) -> None:
    tracer.record(
        "pdf_extract", target="https://a/x.pdf", status="ok", latency_ms=900.0,
        backend_used="mineru25", selected_extractor="mineru25", chars=4096,
    )


def _fallback(tracer: ToolTracer, reason: str, selected: str = "docling") -> None:
    tracer.record(
        "pdf_extract", target="https://a/y.pdf", status="retry", latency_ms=12.0,
        backend_used=selected, selected_extractor=selected,
        requested_extractor="mineru25", fallback_reason=reason,
    )


def test_win_only_is_not_degraded():
    tracer = ToolTracer()
    _win(tracer)
    s = tracer.clinical_pdf_winner_status()
    assert s["requested"] is True
    assert s["degraded"] is False
    assert s["win_count"] == 1
    assert s["fallback_count"] == 0
    assert s["reasons"] == {}
    assert s["source"] == "tool_trace.pdf_extract"


@pytest.mark.parametrize(
    "reason", ["no_gpu", "mineru25_empty", "mineru25_timeout", "mineru25_error"]
)
def test_each_fallback_reason_flags_degraded(reason):
    tracer = ToolTracer()
    _fallback(tracer, reason)
    s = tracer.clinical_pdf_winner_status()
    assert s["requested"] is True
    assert s["degraded"] is True
    assert s["fallback_count"] == 1
    assert s["win_count"] == 0
    assert s["reasons"] == {reason: 1}
    assert s["selected_extractors"] == ["docling"]


def test_mixed_win_and_fallback_is_degraded_with_histogram():
    tracer = ToolTracer()
    _win(tracer)
    _fallback(tracer, "mineru25_error")
    _fallback(tracer, "mineru25_error")
    _fallback(tracer, "no_gpu", selected="pymupdf")
    s = tracer.clinical_pdf_winner_status()
    assert s["degraded"] is True
    assert s["win_count"] == 1
    assert s["fallback_count"] == 3
    assert s["reasons"] == {"mineru25_error": 2, "no_gpu": 1}
    assert s["selected_extractors"] == ["docling", "pymupdf"]


def test_docling_default_no_rows_is_not_degraded():
    """When PG_CLINICAL_PDF_EXTRACTOR is unset/docling the selector is never
    called, so there is no pdf_extract row — the baseline is NOT a degradation."""
    tracer = ToolTracer()
    # An unrelated tool row must not trip the flag.
    tracer.record("serper", target="q", status="ok", latency_ms=10.0)
    s = tracer.clinical_pdf_winner_status()
    assert s["requested"] is False
    assert s["degraded"] is False
    assert s["fallback_count"] == 0
    assert s["win_count"] == 0


def test_reset_isolates_flag_across_queries():
    reset_tool_tracer()
    t1 = get_tool_tracer()
    _fallback(t1, "mineru25_error")
    assert t1.clinical_pdf_winner_status()["degraded"] is True
    # Query N+1: fresh tracer must NOT inherit N's degraded flag.
    reset_tool_tracer()
    t2 = get_tool_tracer()
    assert t2.clinical_pdf_winner_status()["degraded"] is False


def test_attach_stamps_top_level_manifest_key_when_on(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")
    reset_tool_tracer()
    tracer = get_tool_tracer(tmp_path)
    _fallback(tracer, "mineru25_timeout")
    manifest: dict = {}
    attach_tool_utilization(manifest, tmp_path)
    assert "clinical_pdf_winner_degraded" in manifest
    cpd = manifest["clinical_pdf_winner_degraded"]
    assert cpd["degraded"] is True
    assert cpd["reasons"] == {"mineru25_timeout": 1}


def test_attach_off_mode_omits_key(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    reset_tool_tracer()
    tracer = get_tool_tracer(tmp_path)
    _fallback(tracer, "mineru25_error")
    manifest: dict = {}
    attach_tool_utilization(manifest, tmp_path)
    # OFF-mode is a pure no-op: the key must NOT appear (byte-identity).
    assert "clinical_pdf_winner_degraded" not in manifest
