"""I-extract-001 Layer-A — flag-gated trafilatura precision profile at the
``_strip_html`` HTML->text seam in ``live_retriever``.

Deterministic + OFFLINE: the body-non-regression test reads a saved HTML sample
from ``outputs/audits/iextract001/raw_html/`` (CPU-only trafilatura; no network),
the wiring tests spy on ``safe_trafilatura_extract`` so no extractor actually runs.

Acceptance covered:
  - default profile (unset / "default") passes NO kwargs -> current behavior.
  - "trafilatura_precision" passes favor_precision=True to trafilatura.
  - an UNKNOWN flag value fails LOUD (warning) and falls back to default.
  - the precision profile does NOT regress body-anchor recall (faithfulness-
    neutral: it must not silently drop real findings -- CLAUDE.md SS-1.3).
  - the readability -> regex fallback chain is preserved when trafilatura yields
    nothing, even with the precision flag set.
"""

import os
from pathlib import Path

import pytest

from src.polaris_graph.retrieval import live_retriever as lr
from src.tools import access_bypass

_RAW_HTML_DIR = (
    Path(__file__).resolve().parents[2]
    / "outputs" / "audits" / "iextract001" / "raw_html"
)
# SAEB retraction page: body-bearing, the page where readability-lxml dropped the
# whole body via wrong-region selection -> the right faithfulness regression guard.
_BODY_SAMPLE = _RAW_HTML_DIR / "20_ev_230.html"
_BODY_ANCHORS = (
    "after consulting members of the editorial board",
    "the corresponding author has requested that this paper is retracted",
    "artificial intelligence and economic growth: a theoretical framework",
)


def _capture_kwargs(monkeypatch):
    """Replace safe_trafilatura_extract with a spy; return the captured-kwargs
    dict (populated when _strip_html invokes the extractor)."""
    captured: dict = {}

    def _spy(html, **kwargs):
        captured.update(kwargs)
        return "extracted body text"

    monkeypatch.setattr(access_bypass, "safe_trafilatura_extract", _spy)
    return captured


def test_default_profile_passes_no_kwargs(monkeypatch):
    monkeypatch.delenv(lr.PG_HTML_EXTRACTOR_ENV, raising=False)
    captured = _capture_kwargs(monkeypatch)
    lr._strip_html("<html><body><p>hello world body</p></body></html>")
    assert "favor_precision" not in captured


def test_explicit_default_value_passes_no_kwargs(monkeypatch):
    monkeypatch.setenv(lr.PG_HTML_EXTRACTOR_ENV, "default")
    captured = _capture_kwargs(monkeypatch)
    lr._strip_html("<html><body><p>hello world body</p></body></html>")
    assert "favor_precision" not in captured


def test_precision_profile_passes_favor_precision(monkeypatch):
    monkeypatch.setenv(
        lr.PG_HTML_EXTRACTOR_ENV, lr._HTML_EXTRACTOR_TRAFILATURA_PRECISION
    )
    captured = _capture_kwargs(monkeypatch)
    lr._strip_html("<html><body><p>hello world body</p></body></html>")
    assert captured.get("favor_precision") is True


def test_unknown_value_falls_back_to_default_and_warns(monkeypatch, caplog):
    monkeypatch.setenv(lr.PG_HTML_EXTRACTOR_ENV, "boilerpy3_typo")
    captured = _capture_kwargs(monkeypatch)
    with caplog.at_level("WARNING"):
        kwargs = lr._trafilatura_extract_kwargs()
    assert kwargs == {}
    assert lr.PG_HTML_EXTRACTOR_ENV in caplog.text
    lr._strip_html("<html><body><p>hello world body</p></body></html>")
    assert "favor_precision" not in captured


def test_fallback_chain_preserved_under_precision_flag(monkeypatch):
    """trafilatura yields nothing -> readability fallback still runs, even with
    the precision flag set. Regex tier remains the last resort below it."""
    monkeypatch.setenv(
        lr.PG_HTML_EXTRACTOR_ENV, lr._HTML_EXTRACTOR_TRAFILATURA_PRECISION
    )
    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")
    monkeypatch.setattr(
        access_bypass, "safe_trafilatura_extract", lambda html, **kw: None
    )
    monkeypatch.setattr(access_bypass, "_html_is_extract_safe", lambda html: True)
    monkeypatch.setattr(lr, "_readability_extract", lambda html: "READABILITY_BODY")
    out = lr._strip_html("<html><body><p>some body</p></body></html>")
    assert out == "READABILITY_BODY"


@pytest.mark.skipif(
    not _BODY_SAMPLE.exists(), reason="iextract001 raw_html sample not present"
)
def test_precision_does_not_regress_body_anchors(monkeypatch):
    """Faithfulness-neutral: every body anchor the default profile retains must
    survive under the precision profile (no silent drop of real findings)."""
    html = _BODY_SAMPLE.read_text(encoding="utf-8", errors="ignore")
    monkeypatch.setenv("PG_FETCH_TABLE_LINEARIZE", "0")

    monkeypatch.setenv(lr.PG_HTML_EXTRACTOR_ENV, "default")
    default_out = lr._strip_html(html).lower()
    monkeypatch.setenv(
        lr.PG_HTML_EXTRACTOR_ENV, lr._HTML_EXTRACTOR_TRAFILATURA_PRECISION
    )
    precision_out = lr._strip_html(html).lower()

    for anchor in _BODY_ANCHORS:
        assert anchor in default_out, f"anchor missing from default: {anchor!r}"
        assert anchor in precision_out, (
            f"precision profile dropped a real-body anchor: {anchor!r}"
        )
