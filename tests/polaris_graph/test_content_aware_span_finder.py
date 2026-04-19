"""BUG-M-2 (Codex pass 4 medium): content-aware span finder.

Root cause of the 83% strict_verify drop rate on the clinical smoke
(`outputs/m2_diag_clinical`): the rewriter used `(0, 200)` as the
span for no-decimal sentences, and a narrow ±30-char window around
decimals for numeric sentences. Both frequently hit evidence spans
that did not contain the sentence's content words, so strict_verify
dropped them with `no_content_word_overlap_any_cited_span`.

The new `_find_best_span_for_sentence` picks the window (default
500 chars) that satisfies the sentence's decimal hard-requirement
AND maximizes content-word overlap — the exact criteria strict_verify
uses.
"""

from __future__ import annotations

from src.polaris_graph.generator.live_deepseek_generator import (
    _find_best_span_for_sentence,
)


def test_no_decimal_sentence_picks_content_rich_window():
    """Sentence has no decimals; finder should pick the window with
    the most content-word overlap, not the first 200 chars."""
    sentence = (
        "Tirzepatide demonstrated significant reductions in "
        "HbA1c and body weight across clinical trials."
    )
    # First 400 chars are author metadata (no keywords).
    # Next 400 chars have the actual claim support.
    direct_quote = (
        "A" * 400  # filler that does NOT match the sentence
        + " Tirzepatide achieved significant reductions in HbA1c "
        "and improvements in body weight in clinical trials with "
        "type 2 diabetes patients. "
        + "B" * 200
    )

    span = _find_best_span_for_sentence(sentence, direct_quote)
    assert span is not None
    start, end = span
    # Best window must include the middle section with 'tirzepatide',
    # 'hba1c', 'body', 'weight', 'clinical', 'trials'.
    window_text = direct_quote[start:end]
    assert "tirzepatide" in window_text.lower()
    assert "hba1c" in window_text.lower()
    assert "body" in window_text.lower() and "weight" in window_text.lower()


def test_decimal_sentence_window_contains_all_decimals():
    """Sentence has multiple decimals; finder must pick a window
    that contains ALL of them (hard requirement)."""
    sentence = (
        "A1C reductions were -1.87% with 5 mg and -2.07% with 15 mg."
    )
    # The decimals are separated by 300 chars; a narrow ±30 window
    # would miss one. A 500-char window can capture both.
    direct_quote = (
        "Methods section: patients enrolled were... "
        + "B" * 300
        + " Primary outcome: A1C change from baseline was -1.87% in "
        "the 5 mg arm."
        + "C" * 100
        + " A1C change was -2.07% in the 15 mg arm at 40 weeks."
        + "D" * 100
    )

    span = _find_best_span_for_sentence(sentence, direct_quote)
    assert span is not None
    window_text = direct_quote[span[0]:span[1]]
    assert "-1.87" in window_text
    assert "-2.07" in window_text


def test_short_quote_returns_full_quote():
    """If the evidence direct_quote is smaller than the window, the
    finder should return (0, len(quote))."""
    sentence = "The drug reduced glucose levels."
    direct_quote = "Short evidence about glucose reduction."

    span = _find_best_span_for_sentence(sentence, direct_quote)
    assert span == (0, len(direct_quote))


def test_empty_quote_returns_none():
    """No direct_quote → cannot find a span."""
    span = _find_best_span_for_sentence("Anything.", "")
    assert span is None


def test_decimal_not_in_any_window_falls_back():
    """If no window contains all sentence-decimals, finder returns a
    best-effort span so strict_verify can drop with a clear failure
    reason, rather than the rewriter silently stripping the citation."""
    sentence = "The reduction was -9.99%."
    # direct_quote contains no -9.99
    direct_quote = "A" * 600 + " totally unrelated text " + "B" * 400

    span = _find_best_span_for_sentence(sentence, direct_quote)
    assert span is not None
    # Returned span is (0, window) by convention; the sentence will
    # drop at strict_verify with number_not_in_any_cited_span.
    assert span[0] == 0


def test_window_env_override(monkeypatch):
    """PG_PROVENANCE_SPAN_WINDOW lets operators tune the default."""
    monkeypatch.setenv("PG_PROVENANCE_SPAN_WINDOW", "150")
    sentence = "The drug is effective."
    direct_quote = "X" * 1000 + " drug effective results " + "Y" * 500

    span = _find_best_span_for_sentence(sentence, direct_quote)
    assert span is not None
    # 150-char window (not default 500).
    assert (span[1] - span[0]) <= 150


def test_prefers_higher_overlap_window_among_equal_decimal_windows():
    """Given two windows that both contain required decimals, the
    one with higher content-word overlap wins."""
    sentence = "A1C dropped 2.0% in weight-loss patients."
    # Two separate regions both contain 2.0 but only one has
    # 'a1c', 'weight', 'loss', 'patients' nearby.
    direct_quote = (
        "filler 2.0 filler "              # window A: has 2.0 but no keywords
        + "X" * 400
        + " patients showed A1C 2.0% in weight loss arm "  # window B: richer
        + "Y" * 300
    )

    span = _find_best_span_for_sentence(sentence, direct_quote)
    assert span is not None
    wt = direct_quote[span[0]:span[1]].lower()
    assert "a1c" in wt
    assert "weight" in wt
