"""BUG-19 (I-arch-006, #1262) — pre-gate web-crawl-chrome / non-assertional filter.

Regression coverage for wiring the two allowlist-only helpers from
``src.tools.access_bypass`` into ``provenance_generator.strict_verify``:

  * ``strip_web_boilerplate``            — crawl-marker LINES are removed from the
    section text BEFORE sentence-splitting.
  * ``is_boilerplate_or_nonassertional`` — a pure-chrome / error-page-stub /
    bare-DOI / table-number "sentence" is EXCLUDED from the gate's INPUT, so it
    can never be COUNTED as a verified claim.

The forensic found 17-34% of ENTAILED verdicts were chrome and a literal NTSB
"Page not found" 404 body self-entailed through the gate ("Page not found" ⊨
"Page not found"). These tests prove the chrome / 404 stub is dropped BEFORE the
gate while a genuine clinical sentence passes through untouched and verifies.

Faithfulness: this is INPUT hygiene — no gate verdict/threshold/strictness
changes. The MANDATORY regression test asserts the 404 string + a "URL Source:
... Markdown Content:" line never count as verified, AND that a real cited
clinical sentence is still verified normally.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.provenance_generator import (
    strict_verify,
)


# A genuine clinical sentence whose printed span contains the number AND >=2
# content words — the positive control that MUST keep verifying untouched.
_CLINICAL_QUOTE = (
    "At week 68, adults receiving semaglutide achieved a mean weight loss of 14.9%."
)
_CLINICAL_POOL = {
    "ev_step1": {
        "direct_quote": _CLINICAL_QUOTE,
        "statement": "STEP 1 weight loss result.",
    }
}
# Span 49-77 inside the quote = "mean weight loss of 14.9%": contains "14.9" and
# the content words "weight"/"loss".
_CLINICAL_SENTENCE = "Mean weight loss was 14.9% [#ev:ev_step1:49-77]."


def _verified_texts(report) -> list[str]:
    return [sv.sentence for sv in report.kept_sentences]


def test_clinical_sentence_alone_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    """Positive control: a genuine cited clinical sentence verifies (flag ON)."""
    monkeypatch.setenv("PG_PREGATE_STRIP_BOILERPLATE", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")  # mechanical checks only
    report = strict_verify(_CLINICAL_SENTENCE, _CLINICAL_POOL)
    assert report.total_kept == 1, report
    assert report.total_in == 1, report
    assert _CLINICAL_SENTENCE in _verified_texts(report)


def test_ntsb_404_stub_dropped_before_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """MANDATORY regression (BUG-19): the literal NTSB '404 Page not found' body
    is EXCLUDED before the gate — it is NEVER counted as a verified claim, and a
    genuine clinical sentence in the same draft still verifies normally."""
    monkeypatch.setenv("PG_PREGATE_STRIP_BOILERPLATE", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    # The 404 stub carries a syntactically-valid provenance token pointing at a
    # pool row whose direct_quote IS the same error text — so absent the BUG-19
    # filter it would SELF-ENTAIL and the mechanical checks would PASS it as a
    # "verified" finding. The filter must drop it at the input.
    pool = dict(_CLINICAL_POOL)
    pool["ev_404"] = {"direct_quote": "Page not found", "statement": "404"}
    draft = (
        f"{_CLINICAL_SENTENCE} "
        "Page not found [#ev:ev_404:0-14]."
    )
    report = strict_verify(draft, pool)
    kept = _verified_texts(report)
    # The 404 stub is neither kept NOR dropped — it never entered the gate.
    assert not any("Page not found" in k for k in kept), kept
    assert not any(
        "Page not found" in sv.sentence for sv in report.dropped_sentences
    ), report.dropped_sentences
    # The genuine clinical sentence still verifies.
    assert _CLINICAL_SENTENCE in kept, kept
    # Denominator excludes the non-claim: only the real sentence counts.
    assert report.total_in == 1, report
    assert report.total_kept == 1, report


def test_url_source_markdown_content_lines_stripped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MANDATORY regression (BUG-19): 'URL Source: ...' and 'Markdown Content:'
    crawl-marker lines are stripped from the section text BEFORE splitting, so
    they never become candidate sentences or count as verified."""
    monkeypatch.setenv("PG_PREGATE_STRIP_BOILERPLATE", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    draft = (
        "URL Source: https://example.org/article\n"
        "Markdown Content:\n"
        f"{_CLINICAL_SENTENCE}"
    )
    report = strict_verify(draft, _CLINICAL_POOL)
    kept = _verified_texts(report)
    all_units = kept + [sv.sentence for sv in report.dropped_sentences]
    assert not any("URL Source" in u for u in all_units), all_units
    assert not any("Markdown Content" in u for u in all_units), all_units
    # The real sentence survives the strip and verifies.
    assert _CLINICAL_SENTENCE in kept, kept
    assert report.total_kept == 1, report


def test_genuine_sentence_with_not_found_phrase_is_not_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Faithfulness floor: a REAL sentence that merely CONTAINS an error token as
    prose (here 'not found') is NOT a stub — it has real content words — so it is
    never flagged by the input filter and reaches the gate normally."""
    monkeypatch.setenv("PG_PREGATE_STRIP_BOILERPLATE", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    quote = (
        "The variant was not found in any of the 14.9% of treated participants "
        "who achieved remission."
    )
    pool = {"ev_x": {"direct_quote": quote, "statement": "result"}}
    # Span 0-93 (= len(quote)) covers the prose incl. "14.9" and many content words.
    sentence = (
        "The variant was not found in 14.9% of treated participants "
        "[#ev:ev_x:0-93]."
    )
    report = strict_verify(sentence, pool)
    # It must reach the gate (be counted), not be silently excluded as a stub.
    assert report.total_in == 1, report
    assert report.total_kept == 1, _verified_texts(report)


def test_flag_off_is_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """OFF-path (PG_PREGATE_STRIP_BOILERPLATE=0): the filter is inert. The 404
    stub reaches the gate exactly as before #1262 (it has a self-entailing token
    so under the mechanical-only checks it would be KEPT) — proving the change is
    gated and the default-ON behavior is what removes the hole."""
    monkeypatch.setenv("PG_PREGATE_STRIP_BOILERPLATE", "0")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    pool = dict(_CLINICAL_POOL)
    pool["ev_404"] = {"direct_quote": "Page not found", "statement": "404"}
    draft = (
        f"{_CLINICAL_SENTENCE} "
        "Page not found [#ev:ev_404:0-14]."
    )
    report = strict_verify(draft, pool)
    # With the filter OFF the 404 stub is NOT excluded; it enters the gate and is
    # counted in total_in (the pre-#1262 hole). This documents that the default-ON
    # filter is exactly what closes it.
    assert report.total_in == 2, report