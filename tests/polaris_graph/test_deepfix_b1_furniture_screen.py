"""I-deepfix-001 B1 (wave-2, 2026-07-08) — extraction-time furniture screen + recovery.

Pure offline unit tests (no GPU / LLM / network). Three behaviours, all default-OFF:

1. ``shell_detector`` furniture-density detection (``furniture_density`` /
   ``is_furniture_dominant``) — reuses the shared render-side chrome predicate
   READ-ONLY, char-weighted, gated to a long body.
2. ``shell_detector.select_real_content_span`` — B1 step 3 span picker (a real-content
   span wins the direct_quote over a furniture span; all-furniture => keep first, never
   drop).
3. ``AccessBypass._extract_pdf_text_from_bytes`` wrapper — flag OFF byte-identical;
   flag ON marks a furniture-dominant body degraded and (with re-fetch on) recovers
   real content via a DIFFERENT extractor, else keeps + discloses (never drops).

GREEN = ``python -m pytest tests/polaris_graph/test_deepfix_b1_furniture_screen.py -q``.
"""
from __future__ import annotations

import asyncio

import pytest

from src.polaris_graph.retrieval import shell_detector as sd
from src.tools.access_bypass import AccessBypass


_B1_ENVS = (
    "PG_FURNITURE_DENSITY_SCREEN",
    "PG_FURNITURE_REFETCH",
    "PG_SPAN_SELECT_FURNITURE_AWARE",
    "PG_FURNITURE_DENSITY_THRESHOLD",
    "PG_FURNITURE_MIN_BODY_CHARS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _B1_ENVS:
        monkeypatch.delenv(name, raising=False)
    yield


# ── 1. flag helpers default OFF ──────────────────────────────────────────────
def test_flags_default_off():
    assert sd.furniture_density_screen_enabled() is False
    assert sd.furniture_refetch_enabled() is False
    assert sd.span_select_furniture_aware_enabled() is False


def test_flags_on_via_env(monkeypatch):
    monkeypatch.setenv("PG_FURNITURE_DENSITY_SCREEN", "1")
    monkeypatch.setenv("PG_FURNITURE_REFETCH", "true")
    monkeypatch.setenv("PG_SPAN_SELECT_FURNITURE_AWARE", "on")
    assert sd.furniture_density_screen_enabled() is True
    assert sd.furniture_refetch_enabled() is True
    assert sd.span_select_furniture_aware_enabled() is True


# ── 2. furniture_density char-weighted math (deterministic via monkeypatch) ───
def test_furniture_density_char_weighted(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    body = ("CHROME" + "x" * 94) + "\n\n" + ("y" * 100)  # 100 furniture + 100 real
    assert sd.furniture_density(body) == pytest.approx(0.5, abs=1e-6)


def test_furniture_density_empty_is_zero():
    assert sd.furniture_density("") == 0.0
    assert sd.furniture_density("   \n  ") == 0.0


# ── 3. is_furniture_dominant: threshold + min-body guard ──────────────────────
def test_dominant_true_when_dense_and_long(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    body = ("CHROME" + "x" * 794) + "\n\n" + ("y" * 500)  # 800 furniture / 1300 total >= 0.6
    assert len(body.strip()) >= 1200
    assert sd.is_furniture_dominant(body) is True


def test_dominant_false_when_short(monkeypatch):
    """A dense-but-SHORT body is not dominant — the short-body shell gates own stubs."""
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: True)
    assert sd.is_furniture_dominant("CHROME everywhere but short") is False


def test_dominant_false_for_real_prose(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: False)
    body = "y" * 3000
    assert sd.is_furniture_dominant(body) is False


def test_dominant_respects_threshold_env(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    body = ("CHROME" + "x" * 594) + "\n\n" + ("y" * 700)  # 600/1300 ~= 0.46
    assert sd.is_furniture_dominant(body) is False  # under default 0.6
    monkeypatch.setenv("PG_FURNITURE_DENSITY_THRESHOLD", "0.4")
    assert sd.is_furniture_dominant(body) is True    # 0.46 >= 0.4


# ── 4. real-predicate wiring (no monkeypatch) ────────────────────────────────
def test_real_predicate_wiring_furniture_vs_prose():
    """Proves the READ-ONLY reuse of is_render_chrome_or_unrenderable actually fires:
    a masthead/DOI/license furniture body scores high density; real prose scores ~0."""
    prose_unit = (
        "One more robot per thousand workers in the United States reduces the "
        "employment-to-population ratio by 0.2 percentage points and wages by 0.42 "
        "percent, according to the study of local labor markets across many regions."
    )
    real = "\n\n".join(prose_unit for _ in range(8))
    furniture_lines = [
        "## Abstract", "10.1093/qje/qjae044", "## Author Listed", "ISSN 0033-5533",
        "doi:10.1000/xyz", "## References", "## Acknowledgements", "## Introduction",
        "## Methods", "## Results", "## Discussion", "## Conclusion",
        "Terms of Use", "Privacy Policy", "## Supplementary Material", "## Funding",
    ]
    furn = "\n\n".join(furniture_lines * 6)
    assert sd.furniture_density(real) < 0.2
    assert sd.furniture_density(furn) >= 0.6
    assert sd.is_furniture_dominant(real) is False
    assert sd.is_furniture_dominant(furn) is True


# ── 5. select_real_content_span ──────────────────────────────────────────────
def test_span_pick_prefers_real_content(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: s.strip().startswith("CHROME"))
    spans = ["CHROME masthead", "CHROME nav", "Real article sentence about robots."]
    assert sd.select_real_content_span(spans) == (2, "Real article sentence about robots.")


def test_span_pick_all_furniture_keeps_first(monkeypatch):
    monkeypatch.setattr(sd, "_is_furniture_segment", lambda s: True)
    spans = ["CHROME a", "CHROME b"]
    assert sd.select_real_content_span(spans) == (0, "CHROME a")


def test_span_pick_empty():
    assert sd.select_real_content_span([]) == (0, "")
    assert sd.select_real_content_span(None) == (0, "")


# ── 6. AccessBypass wrapper: flag-OFF byte-identical + ON behaviours ──────────
_URL = "https://example.org/paper.pdf"
_PDF = b"%PDF-1.7 stub"


def _stub_impl(return_body):
    async def _impl(self, url, pdf_bytes):  # noqa: ANN001
        return return_body
    return _impl


def test_wrapper_flag_off_byte_identical(monkeypatch):
    """Screen OFF => wrapper returns the impl output UNCHANGED (byte-identical)."""
    monkeypatch.setattr(AccessBypass, "_extract_pdf_text_from_bytes_impl", _stub_impl("FURNITURE BODY"))
    # is_furniture_dominant must never even be consulted when the flag is off.
    monkeypatch.setattr(sd, "is_furniture_dominant", lambda b: (_ for _ in ()).throw(AssertionError("screen ran while OFF")))
    ab = AccessBypass()
    out = asyncio.run(ab._extract_pdf_text_from_bytes(_URL, _PDF))
    assert out == "FURNITURE BODY"


def test_wrapper_non_furniture_body_passes_through(monkeypatch):
    monkeypatch.setenv("PG_FURNITURE_DENSITY_SCREEN", "1")
    monkeypatch.setattr(AccessBypass, "_extract_pdf_text_from_bytes_impl", _stub_impl("CLEAN ARTICLE"))
    monkeypatch.setattr(sd, "is_furniture_dominant", lambda b: False)
    ab = AccessBypass()
    out = asyncio.run(ab._extract_pdf_text_from_bytes(_URL, _PDF))
    assert out == "CLEAN ARTICLE"


def test_wrapper_furniture_refetch_off_keeps_and_discloses(monkeypatch):
    """Screen ON, dominant, re-fetch OFF => keep the original body (never drop)."""
    monkeypatch.setenv("PG_FURNITURE_DENSITY_SCREEN", "1")
    monkeypatch.setattr(AccessBypass, "_extract_pdf_text_from_bytes_impl", _stub_impl("FURNITURE BODY"))
    monkeypatch.setattr(sd, "is_furniture_dominant", lambda b: True)
    ab = AccessBypass()
    out = asyncio.run(ab._extract_pdf_text_from_bytes(_URL, _PDF))
    assert out == "FURNITURE BODY"  # kept + disclosed, not dropped


def test_wrapper_refetch_recovers_real_content(monkeypatch):
    """Screen ON, dominant, re-fetch ON, alternate returns clean => recovered wins."""
    monkeypatch.setenv("PG_FURNITURE_DENSITY_SCREEN", "1")
    monkeypatch.setenv("PG_FURNITURE_REFETCH", "1")
    monkeypatch.setattr(AccessBypass, "_extract_pdf_text_from_bytes_impl", _stub_impl("FURNITURE BODY"))
    # Original body is furniture; recovered body is clean.
    monkeypatch.setattr(sd, "is_furniture_dominant", lambda b: b == "FURNITURE BODY")

    async def _recover(self, url, pdf_bytes):  # noqa: ANN001
        return "RECOVERED CLEAN ARTICLE"

    monkeypatch.setattr(AccessBypass, "_refetch_alternate_extractor", _recover)
    ab = AccessBypass()
    out = asyncio.run(ab._extract_pdf_text_from_bytes(_URL, _PDF))
    assert out == "RECOVERED CLEAN ARTICLE"


def test_wrapper_refetch_still_furniture_keeps_original(monkeypatch):
    """Re-fetch returns furniture too => keep the original + disclose (never drop)."""
    monkeypatch.setenv("PG_FURNITURE_DENSITY_SCREEN", "1")
    monkeypatch.setenv("PG_FURNITURE_REFETCH", "1")
    monkeypatch.setattr(AccessBypass, "_extract_pdf_text_from_bytes_impl", _stub_impl("FURNITURE BODY"))
    monkeypatch.setattr(sd, "is_furniture_dominant", lambda b: True)  # everything furniture

    async def _recover(self, url, pdf_bytes):  # noqa: ANN001
        return "STILL FURNITURE"

    monkeypatch.setattr(AccessBypass, "_refetch_alternate_extractor", _recover)
    ab = AccessBypass()
    out = asyncio.run(ab._extract_pdf_text_from_bytes(_URL, _PDF))
    assert out == "FURNITURE BODY"


def test_refetch_alternate_no_gpu_no_oom_safe_returns_empty(monkeypatch):
    """With no GPU and an OOM-unsafe PDF, the alternate re-fetch recovers nothing
    (returns "") — the caller then keeps + discloses the original."""
    monkeypatch.setattr(AccessBypass, "_gpu_available", staticmethod(lambda: False))
    monkeypatch.setattr(AccessBypass, "_docling_oom_safe", staticmethod(lambda b: False))
    ab = AccessBypass()
    out = asyncio.run(ab._refetch_alternate_extractor(_URL, _PDF))
    assert out == ""
