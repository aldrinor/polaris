"""I-wire-013 (#1327) — TRUNCATION-AT-SOURCE behavioural tests (pure, no models).

Two surgical fixes, verified here without any LLM / network / model load:

1. FETCH-LAYER de-hyphenation (``src.tools.access_bypass.dehyphenate_line_wraps``):
   a PDF/HTML line-wrap hyphen ("patent-\\ning activity") is joined to
   "patenting activity", while a legitimate intra-word hyphen ("co-author",
   "GLP-1") and multilingual prose are preserved BYTE-FOR-BYTE.

2. SPAN-START snap (``provenance_generator._snap_start_to_word_boundary`` /
   ``_reanchor_candidate_spans``): a re-anchor candidate whose START lands
   mid-token ("...September 2025" sliced inside "September") is snapped back to
   the head of the word so the recovered fragment opens at "September".

The faithfulness engine (strict_verify / NLI / span-grounding) is FROZEN; these
fixes only change the stored quote text / the candidate-span offsets, never a
verdict.
"""

from src.tools.access_bypass import dehyphenate_line_wraps
from src.polaris_graph.generator import provenance_generator as _pg


# ── Fix 1: fetch-layer de-hyphenation ────────────────────────────────────────

def test_line_wrap_hyphen_is_joined():
    """A trailing hyphen at a hard line break between two letters is removed."""
    assert dehyphenate_line_wraps("patent-\ning activity") == "patenting activity"
    # CRLF line endings repair identically.
    assert dehyphenate_line_wraps("devel-\r\nopment") == "development"


def test_legitimate_intra_word_hyphen_preserved():
    """A real hyphen ("co-author", "GLP-1") has no following newline -> untouched."""
    assert dehyphenate_line_wraps("co-author") == "co-author"
    assert dehyphenate_line_wraps("GLP-1 receptor agonist") == "GLP-1 receptor agonist"


def test_hyphen_before_digit_and_paragraph_break_not_joined():
    """A hyphen+newline before a DIGIT (GLP-1 split) is NOT joined; a blank-line
    paragraph break is never crossed."""
    assert dehyphenate_line_wraps("GLP-\n1 receptor") == "GLP-\n1 receptor"
    assert dehyphenate_line_wraps("end-\n\nNew para") == "end-\n\nNew para"


def test_multilingual_preserved_and_repaired():
    """Multilingual content is byte-for-byte preserved; its OWN line-wrap repairs."""
    # Legitimate accented hyphenation with no line break: preserved exactly.
    assert dehyphenate_line_wraps("café-bar") == "café-bar"
    # A line-wrap inside an accented word IS repaired (Unicode letter class).
    assert dehyphenate_line_wraps("rétro-\nactif") == "rétroactif"
    # No hyphen at all -> identity (byte-for-byte).
    text = "中文内容与 français mixed, no wraps."
    assert dehyphenate_line_wraps(text) == text


def test_empty_input_is_safe():
    assert dehyphenate_line_wraps("") == ""
    assert dehyphenate_line_wraps(None) == ""


# ── Fix 2: span-start snap to a word boundary ────────────────────────────────

def test_snap_start_lands_on_word_head():
    """A start INSIDE a word snaps back to the head of that word."""
    text = "Approved in September 2025 by the agency."
    mid = text.index("September") + 3  # lands inside "September" ("...tember")
    snapped = _pg._snap_start_to_word_boundary(text, mid)
    assert text[snapped:].startswith("September 2025"), (
        f"expected fragment to open at 'September'; got {text[snapped:][:20]!r}"
    )


def test_snap_is_noop_at_existing_boundaries():
    """A start at index 0 / whitespace / punctuation is unchanged (no over-reach)."""
    text = "Alpha beta gamma."
    assert _pg._snap_start_to_word_boundary(text, 0) == 0          # index 0
    sp = text.index(" ")
    assert _pg._snap_start_to_word_boundary(text, sp) == sp        # on the space
    assert _pg._snap_start_to_word_boundary(text, len(text)) == len(text)  # end


def test_reanchor_candidate_spans_open_at_word_boundary(monkeypatch):
    """End-to-end: every sliding-window candidate emitted by _reanchor_candidate_spans
    opens at a whole word (its first char is not a continuation of a prior token)."""
    # Force the sliding-window branch with a small window over a long single-line row
    # (no sentence terminators -> branch (a) yields only the trailing segment, so the
    # window candidates dominate and would otherwise land mid-token).
    monkeypatch.setattr(_pg, "PG_PROVENANCE_REANCHOR_WINDOW", 12)
    row = "alpha bravo charlie delta echo foxtrot golf hotel india juliet"
    spans = _pg._reanchor_candidate_spans(row)
    assert spans, "expected candidate spans"
    for s, e in spans:
        # The invariant: no span begins STRICTLY INSIDE a token (both the char
        # before and the char at the start being word chars). A start at index 0
        # or at a whitespace/punctuation boundary is fine — it opens at a word once
        # rendered.
        opens_mid_token = (
            s > 0 and _pg._is_word_char(row[s - 1]) and _pg._is_word_char(row[s])
        )
        assert not opens_mid_token, (
            f"candidate span ({s},{e}) opens mid-token: ...{row[max(0, s - 3):e][:12]!r}"
        )
