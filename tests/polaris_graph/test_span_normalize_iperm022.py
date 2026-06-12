"""I-perm-022 (#1214) — LIGATURE-ONLY cited-span normalization for the four-role seam.

Ligature decomposition is the ONLY §-1.1-safe span repair: a single presentation-form
codepoint -> its fixed letters, with NO word-boundary change. De-hyphenation and zero-width
handling were dropped as §-1.1-unsafe (any join/split can fabricate support — Codex
brief-gate iter-2 P1). These tests prove the safe behavior AND that the unsafe joins/splits
do NOT happen.

All non-ASCII chars are built with chr() so the test source stays pure ASCII.
"""
from __future__ import annotations

import os

import pytest

from src.polaris_graph.roles.native_gate_b_inputs import _normalize_span_text

FI = chr(0xFB01)   # fi ligature
FL = chr(0xFB02)   # fl ligature
FFI = chr(0xFB03)  # ffi ligature
ZWSP = chr(0x200B)
ZWJ = chr(0x200D)
NBSP = chr(0x00A0)


@pytest.fixture
def _norm_on():
    prev = os.environ.get("PG_GATE_B_SPAN_NORMALIZE")
    os.environ["PG_GATE_B_SPAN_NORMALIZE"] = "1"
    try:
        yield
    finally:
        if prev is None:
            os.environ.pop("PG_GATE_B_SPAN_NORMALIZE", None)
        else:
            os.environ["PG_GATE_B_SPAN_NORMALIZE"] = prev


def test_flag_off_byte_identical(monkeypatch):
    # Codex diff-gate P2: use monkeypatch so the env var is auto-restored (no test pollution).
    monkeypatch.delenv("PG_GATE_B_SPAN_NORMALIZE", raising=False)
    raw = "bio" + FI + "lms re-\nsigned not" + ZWSP + "able 20-\n30"
    assert _normalize_span_text(raw) == raw


def test_ligatures_repaired_when_on(_norm_on):
    assert _normalize_span_text("bio" + FI + "lms") == "biofilms"
    assert _normalize_span_text("in" + FL + "ammatory") == "inflammatory"
    assert _normalize_span_text("e" + FFI + "cacy") == "efficacy"


def test_full_ligature_table_matches_unicode_nfkd(_norm_on):
    # Codex brief-gate iter-3 P1: the map is NFKD-derived, so U+FB05 (LONG S T) -> "st"
    # (NOT "ft"). "lo<FB05>" must read as "lost", never "loft".
    import unicodedata
    from src.polaris_graph.roles.native_gate_b_inputs import _LIGATURE_MAP
    for cp in range(0xFB00, 0xFB07):
        ch = chr(cp)
        assert _LIGATURE_MAP[ch] == unicodedata.normalize("NFKD", ch)
    assert _normalize_span_text("lo" + chr(0xFB05)) == "lost"
    assert "loft" not in _normalize_span_text("lo" + chr(0xFB05))
    assert _normalize_span_text("be" + chr(0xFB06)) == "best"  # FB06 ST


# ── adversarial: the §-1.1-unsafe JOINS/SPLITS must NOT happen ─────────────

def test_line_break_hyphen_is_NOT_joined(_norm_on):
    # "re-signed" (signed again) must NOT become "resigned" (quit) — a hard hyphen is kept.
    assert _normalize_span_text("re-\nsigned") == "re-\nsigned"
    assert "resigned" not in _normalize_span_text("re-\nsigned")
    assert _normalize_span_text("well-\nknown drug") == "well-\nknown drug"


def test_zero_width_is_NOT_joined_negation_safe(_norm_on):
    # "not<ZWSP>able" must NOT become "notable"; the negation/space stays intact (untouched).
    assert _normalize_span_text("not" + ZWSP + "able") == "not" + ZWSP + "able"
    assert "notable" not in _normalize_span_text("not" + ZWSP + "able")
    # "in<ZWJ>effective" must NOT be split into "in effective" (the original-bug direction).
    assert "in effective" not in _normalize_span_text("in" + ZWJ + "effective")


def test_digits_and_nbsp_untouched(_norm_on):
    # ZERO digit modification; non-ligature content is byte-preserved (ligature-only scope).
    assert _normalize_span_text("range 20-\n30") == "range 20-\n30"
    assert _normalize_span_text("reduced by 2 percent") == "reduced by 2 percent"
    assert _normalize_span_text("HR " + chr(0x2212) + "1.07") == "HR " + chr(0x2212) + "1.07"
    assert _normalize_span_text("natural" + NBSP + "killer") == "natural" + NBSP + "killer"


def test_genuine_negative_span_gains_no_content(_norm_on):
    span = "the registry recorded outcomes in adults"
    out = _normalize_span_text(span)
    assert out == span                  # no ligature present -> unchanged; nothing invented
    assert "killer" not in out


def test_empty_safe(_norm_on):
    assert _normalize_span_text("") == ""
