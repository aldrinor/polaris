"""Behavioral tests for the deterministic PDF front-matter (masthead) stripper.

Regression: ev_461 — a PDF extractor (mineru25 / docling / PyMuPDF) pulled the
journal masthead as the FIRST run of content, so it became a provenance span and
rendered as a "finding":

  "PERSPECTIVE Toward understanding the impact of artificial intelligence on labor
   Morgan R. Franka, David Autorb, ... Edited by Jose A. Scheinkman, ..., and
   approved February 28, 2019 (received for review January 18, 2019) Rapid advances
   in artificial intelligence (AI) ..."

Ground truth (the real extracted text in
outputs/audits/iextract001/raw_html/vm_substrate/24_ev_461.txt) is SPACE-COLLAPSED
onto a single physical line — masthead and body share one line with no newline
between them. The stripper therefore anchors on the editorial submission-date
clause (the canonical LAST masthead element) and cuts at its END, removing ONLY
the contiguous leading masthead block. It is offset-based (not line-based), so it
works on both the collapsed single-line form and a line-wrapped form.

Offline, no LLM, no network. Pure string fixtures.
"""
from src.tools.access_bypass import strip_pdf_frontmatter

# Single-line (space-collapsed) masthead, matching the real ev_461 extraction.
_EV461_MASTHEAD = (
    "PERSPECTIVE Toward understanding the impact of artificial intelligence on labor "
    "Morgan R. Franka, David Autorb, and Erik Brynjolfssonc "
    "Edited by Jose A. Scheinkman, Columbia University, New York, NY, and "
    "approved February 28, 2019 (received for review January 18, 2019) "
)
_EV461_BODY = (
    "Rapid advances in artificial intelligence are raising concerns about the "
    "future of human labor in a wide range of occupations."
)


def test_masthead_plus_body_strips_leading_only():
    """Masthead + body (collapsed single line): the masthead is stripped, the body
    is intact and a verbatim suffix, nothing after the body start is touched."""
    text = _EV461_MASTHEAD + _EV461_BODY
    out = strip_pdf_frontmatter(text)
    assert "PERSPECTIVE" not in out, "running-head masthead survived"
    assert "Morgan R. Frank" not in out, "author/affiliation list survived"
    assert "received for review" not in out, "submission-date clause survived"
    assert "Edited by" not in out, "editor byline survived"
    assert out == _EV461_BODY, "body altered or lost"


def test_pure_body_unchanged():
    """A clean body (no masthead) is returned byte-identical."""
    body = (
        "Tirzepatide reduced HbA1c by 2.1 percentage points versus placebo "
        "over 40 weeks in the SURPASS-2 trial. "
        "Adverse events were predominantly gastrointestinal and mild."
    )
    assert strip_pdf_frontmatter(body) == body, "clean body must be byte-identical"


def test_masthead_only_no_body_loss_panic():
    """Masthead-only fetch (cut leaves no body): returned UNCHANGED — there is no
    body to protect, so we never delete the whole thing (downstream thin/shell
    gates handle it). No crash, no surprise empty."""
    assert strip_pdf_frontmatter(_EV461_MASTHEAD.rstrip()) == _EV461_MASTHEAD.rstrip()


def test_body_sentence_containing_a_date_is_not_stripped():
    """A REAL body sentence that merely CONTAINS a date (no editorial '(received
    for review ...)' clause) must NOT be stripped — faithfulness."""
    text = (
        "The trial protocol was approved February 28, 2019, and subsequently "
        "enrolled 200 patients across twelve sites. Median follow-up was 18 months."
    )
    assert strip_pdf_frontmatter(text) == text, "date-bearing prose wrongly stripped"


def test_wrapped_body_no_overstrip():
    """Line-wrapped masthead + body where the body's OPENING sentence wraps across
    short physical lines: every body byte must survive (the over-strip guard)."""
    text = (
        "PERSPECTIVE\n"
        "Toward understanding the impact of\n"
        "Morgan R. Franka, David Autorb, and Erik Brynjolfssonc\n"
        "Edited by Jane Doe, approved February 28, 2019 "
        "(received for review January 18, 2019)\n"
        "Rapid advances in artificial intelligence are\n"
        "raising concerns about the future of human\n"
        "labor over many occupations and sectors.\n"
        "We use job vacancy data to study the labor question here."
    )
    body_expected = (
        "Rapid advances in artificial intelligence are\n"
        "raising concerns about the future of human\n"
        "labor over many occupations and sectors.\n"
        "We use job vacancy data to study the labor question here."
    )
    out = strip_pdf_frontmatter(text)
    assert "PERSPECTIVE" not in out
    assert "Morgan R. Frank" not in out
    assert "received for review" not in out
    assert out == body_expected, "body bytes dropped on wrapped input"


def test_multiclause_intl_paren_stripped():
    """A multi-clause editorial parenthetical with international "D Month YYYY"
    dates is recognized and the masthead stripped; the body is intact. Recall add
    is precision-safe (the paren still disambiguates from prose)."""
    text = (
        "RESEARCH ARTICLE A study of metal ions Jane A. Smithab, John Doec "
        "Edited by R. Roe (received for review 18 January 2019; accepted 3 Mar 2019) "
        "Serum copper levels were elevated in 42% of cardiovascular patients."
    )
    out = strip_pdf_frontmatter(text)
    assert "RESEARCH ARTICLE" not in out
    assert "received for review" not in out
    assert out == "Serum copper levels were elevated in 42% of cardiovascular patients."


def test_body_with_own_parens_after_terminator_intact():
    """The bounded clause-run stops at the first ')', so a body sentence that
    carries its OWN parentheses after the terminator is left fully intact (the
    precision guard against the [^)] run eating prose)."""
    text = (
        "ARTICLE T Smithab Edited by X (received for review January 1, 2020) "
        "Findings indicate a strong correlation (p < 0.001) between exposure and outcome."
    )
    out = strip_pdf_frontmatter(text)
    assert out == (
        "Findings indicate a strong correlation (p < 0.001) between exposure and outcome."
    )


def test_noneditorial_prose_paren_not_stripped():
    """A parenthetical date that is NOT the editorial 'received for review' clause
    is prose and must not trigger a strip."""
    text = "The dataset (reviewed January 18, 2019) showed a 12% increase across all sites here."
    assert strip_pdf_frontmatter(text) == text


def test_editorial_clause_without_anchor_not_stripped():
    """An editorial-form clause with NO masthead anchor (running-head / author /
    edited-by) before it must NOT trigger a strip (precision-first)."""
    text = (
        "This methods note records that the dataset was received for review "
        "March 3, 2021) and we analyzed it thoroughly across regions."
    )
    assert strip_pdf_frontmatter(text) == text


def test_flag_off_returns_input():
    """Flag off => no-op, even on a clear masthead."""
    import os

    text = _EV461_MASTHEAD + _EV461_BODY
    prev = os.environ.get("PG_PDF_FRONTMATTER_STRIP")
    os.environ["PG_PDF_FRONTMATTER_STRIP"] = "0"
    try:
        assert strip_pdf_frontmatter(text) == text, "flag off must be a no-op"
    finally:
        if prev is None:
            os.environ.pop("PG_PDF_FRONTMATTER_STRIP", None)
        else:
            os.environ["PG_PDF_FRONTMATTER_STRIP"] = prev


def test_empty_and_none_safe():
    assert strip_pdf_frontmatter("") == ""
    assert strip_pdf_frontmatter(None) == ""
