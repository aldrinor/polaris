"""I-deepfix-001 B2 (wave-2, 2026-07-08) — mineru25 page-SCALED timeout + gentler breaker.

Pure offline unit tests (no GPU / LLM / network). Two mechanisms:

1. ``_mineru25_timeout_seconds(pdf_bytes, floor)`` — page-scaled per-PDF timeout so a
   458-page report gets proportional time while a 4-page article keeps the fast floor,
   bounded above so a mangled page count can never produce an unbounded wall.
   ``PG_MINERU25_TIMEOUT_PER_PAGE_S`` UNSET => returns ``floor`` unchanged (BYTE-IDENTICAL).

2. Gentler breaker — ``PG_MINERU25_BREAKER_THRESHOLD`` / ``PG_MINERU25_BREAKER_COOLDOWN_S``
   take precedence when set, else fall through to the legacy
   ``PG_MINERU25_CIRCUIT_THRESHOLD`` / ``PG_MINERU25_CIRCUIT_COOLDOWN`` then the 3-fail /
   300s defaults (BYTE-IDENTICAL when the new flags are unset).

GREEN = ``python -m pytest tests/polaris_graph/test_deepfix_b2_mineru_page_scaled_timeout.py -q``.
"""
from __future__ import annotations

import pytest

from src.tools import access_bypass


_B2_TIMEOUT_ENVS = (
    "PG_MINERU25_TIMEOUT_PER_PAGE_S",
    "PG_MINERU25_TIMEOUT_MAX_S",
    "PG_MINERU25_BREAKER_THRESHOLD",
    "PG_MINERU25_BREAKER_COOLDOWN_S",
    "PG_MINERU25_CIRCUIT_THRESHOLD",
    "PG_MINERU25_CIRCUIT_COOLDOWN",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _B2_TIMEOUT_ENVS:
        monkeypatch.delenv(name, raising=False)
    yield


# ── 1. page-scaled timeout: OFF byte-identical ───────────────────────────────
def test_per_page_unset_returns_floor_unchanged():
    """PG_MINERU25_TIMEOUT_PER_PAGE_S unset => the flat floor is returned unchanged,
    the page probe never runs => byte-identical legacy behaviour."""
    assert access_bypass._mineru25_timeout_seconds(b"anything", 90.0) == 90.0
    assert access_bypass._mineru25_timeout_seconds(b"", 42.0) == 42.0


def test_per_page_invalid_or_nonpositive_returns_floor(monkeypatch):
    for bad in ("abc", "0", "-1", ""):
        monkeypatch.setenv("PG_MINERU25_TIMEOUT_PER_PAGE_S", bad)
        assert access_bypass._mineru25_timeout_seconds(b"x", 90.0) == 90.0


# ── 2. page-scaled timeout: ON scales by page count, bounded ─────────────────
def test_page_scaled_timeout_scales_and_bounds(monkeypatch):
    monkeypatch.setattr(access_bypass, "_mineru25_pdf_page_count", lambda _b: 458)
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_PER_PAGE_S", "2")
    # 458 * 2 = 916, bounded above by the 900s default cap.
    assert access_bypass._mineru25_timeout_seconds(b"x", 90.0) == 900.0


def test_page_scaled_timeout_midsize(monkeypatch):
    monkeypatch.setattr(access_bypass, "_mineru25_pdf_page_count", lambda _b: 200)
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_PER_PAGE_S", "2")
    # 200 * 2 = 400, under both floor-max and the cap.
    assert access_bypass._mineru25_timeout_seconds(b"x", 90.0) == 400.0


def test_small_pdf_keeps_floor(monkeypatch):
    monkeypatch.setattr(access_bypass, "_mineru25_pdf_page_count", lambda _b: 4)
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_PER_PAGE_S", "2")
    # 4 * 2 = 8 < floor 90 => the floor wins (small PDFs stay fast).
    assert access_bypass._mineru25_timeout_seconds(b"x", 90.0) == 90.0


def test_custom_max_bound(monkeypatch):
    monkeypatch.setattr(access_bypass, "_mineru25_pdf_page_count", lambda _b: 458)
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_PER_PAGE_S", "2")
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_MAX_S", "500")
    # 916 bounded to the custom 500s cap.
    assert access_bypass._mineru25_timeout_seconds(b"x", 90.0) == 500.0


def test_probe_failure_falls_back_to_floor(monkeypatch):
    """A failed page probe (0) must fall back to the floor (fail-open, no scaling)."""
    monkeypatch.setattr(access_bypass, "_mineru25_pdf_page_count", lambda _b: 0)
    monkeypatch.setenv("PG_MINERU25_TIMEOUT_PER_PAGE_S", "2")
    assert access_bypass._mineru25_timeout_seconds(b"x", 90.0) == 90.0


def test_page_probe_reads_real_pdf():
    """The real page probe returns the true count on a real PDF and 0 on garbage."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for _ in range(3):
        doc.new_page()
    pdf_bytes = doc.tobytes()
    doc.close()
    assert access_bypass._mineru25_pdf_page_count(pdf_bytes) == 3
    assert access_bypass._mineru25_pdf_page_count(b"not a pdf at all") == 0


# ── 3. gentler breaker: new flag precedence + legacy byte-identity ───────────
def test_breaker_threshold_unset_is_legacy_default():
    """Both new + legacy flags unset => the 3-fail default (byte-identical)."""
    assert access_bypass._mineru25_circuit_threshold() == 3


def test_breaker_threshold_new_flag_takes_precedence(monkeypatch):
    monkeypatch.setenv("PG_MINERU25_BREAKER_THRESHOLD", "8")
    assert access_bypass._mineru25_circuit_threshold() == 8


def test_breaker_threshold_falls_through_to_legacy(monkeypatch):
    """New flag unset + legacy set => legacy value (byte-identical fallback)."""
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_THRESHOLD", "5")
    assert access_bypass._mineru25_circuit_threshold() == 5


def test_breaker_threshold_new_beats_legacy(monkeypatch):
    monkeypatch.setenv("PG_MINERU25_BREAKER_THRESHOLD", "8")
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_THRESHOLD", "3")
    assert access_bypass._mineru25_circuit_threshold() == 8


def test_breaker_threshold_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("PG_MINERU25_BREAKER_THRESHOLD", "notanint")
    assert access_bypass._mineru25_circuit_threshold() == 3


def test_breaker_disable_sentinel_via_new_flag(monkeypatch):
    """The <=0 escape hatch still works through the new flag name."""
    monkeypatch.setenv("PG_MINERU25_BREAKER_THRESHOLD", "0")
    assert access_bypass._mineru25_circuit_threshold() == 0


def test_breaker_cooldown_unset_is_legacy_default():
    assert access_bypass._mineru25_circuit_cooldown() == 300.0


def test_breaker_cooldown_new_flag_takes_precedence(monkeypatch):
    monkeypatch.setenv("PG_MINERU25_BREAKER_COOLDOWN_S", "120")
    assert access_bypass._mineru25_circuit_cooldown() == 120.0


def test_breaker_cooldown_falls_through_to_legacy(monkeypatch):
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_COOLDOWN", "150")
    assert access_bypass._mineru25_circuit_cooldown() == 150.0


def test_breaker_cooldown_new_beats_legacy(monkeypatch):
    monkeypatch.setenv("PG_MINERU25_BREAKER_COOLDOWN_S", "120")
    monkeypatch.setenv("PG_MINERU25_CIRCUIT_COOLDOWN", "300")
    assert access_bypass._mineru25_circuit_cooldown() == 120.0
