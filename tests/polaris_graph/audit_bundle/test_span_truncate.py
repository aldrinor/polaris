"""Tests for span_truncate (I-f15-002)."""

from __future__ import annotations

from src.polaris_graph.audit_bundle.span_truncate import (
    ELLIPSIS,
    MAX_SPAN_CHARS,
    ZWJ,
    truncate_span,
)

FAMILY = "\U0001F468" + ZWJ + "\U0001F469" + ZWJ + "\U0001F467"  # 5 codepoints
SHADDA = "ّ"


def test_short_text_passthrough():
    text = "a" * 500
    out = truncate_span(text)
    assert out == text
    assert not out.endswith(ELLIPSIS)


def test_ascii_truncation_total_500():
    text = "a" * 600
    out = truncate_span(text)
    assert len(out) == 500
    assert out.endswith(ELLIPSIS)
    assert out[:-1] == "a" * 499


def test_cjk_truncation_total_500():
    text = "中" * 600
    out = truncate_span(text)
    assert len(out) == 500
    assert out.endswith(ELLIPSIS)


def test_arabic_combining_walk_back():
    text = ("a" * 499) + SHADDA + ("b" * 100)
    out = truncate_span(text, max_chars=500)
    assert len(out) <= 500
    assert out.endswith(ELLIPSIS)
    assert SHADDA not in out[-2:]


def test_zwj_emoji_cut_after_zwj():
    text = ("a" * 499) + ZWJ + ("b" * 100)
    out = truncate_span(text, max_chars=500)
    assert len(out) <= 500
    assert out.endswith(ELLIPSIS)
    assert ZWJ not in out


def test_zwj_emoji_cut_before_zwj():
    text = ("a" * 498) + ZWJ + ("b" * 100)
    out = truncate_span(text, max_chars=500)
    assert len(out) <= 500
    assert out.endswith(ELLIPSIS)
    assert ZWJ not in out


def test_compound_emoji_not_split():
    text = ("a" * 497) + FAMILY + ("z" * 100)
    out = truncate_span(text, max_chars=500)
    assert len(out) <= 500
    assert out.endswith(ELLIPSIS)
    assert ZWJ not in out


def test_max_chars_zero():
    assert truncate_span("abc", max_chars=0) == ""


def test_max_chars_one():
    assert truncate_span("abc", max_chars=1) == ELLIPSIS


def test_utf8_byte_safe():
    samples = [
        "a" * 600,
        "中" * 600,
        ("a" * 499) + SHADDA + ("b" * 100),
        ("a" * 498) + ZWJ + FAMILY + ("z" * 100),
    ]
    for s in samples:
        out = truncate_span(s, max_chars=500)
        out.encode("utf-8")
        assert len(out) <= 500


def test_module_constants():
    assert MAX_SPAN_CHARS == 500
    assert ELLIPSIS == "…"
    assert ZWJ == "‍"
