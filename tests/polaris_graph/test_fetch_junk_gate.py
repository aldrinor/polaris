"""I-fetchclean-001 (2026-07-10) — fetch-junk leak gate tests (offline, real leak spans).

Proves the two-class fetch-junk fix against the REAL drb_72 replay leak spans:

  * Leak class 1 (WHOLE junk pages accepted) — the shared shell detector
    ``shell_detector.is_cited_span_shell`` now flags the SSRN/Cloudflare
    "Performing security verification…" wall (A2 seam + A4 frame_fetcher both call
    it) and the "Something went wrong. Wait a moment…" error page (A1 vocab).
  * Leak class 2 (chrome welded inside real articles) — the new pure
    ``strip_markdown_nav_chrome`` removes full-page nav / Cookiebot / skip-nav
    chrome while byte-preserving reference lists (the ev_037 guard) and real prose.

All pure / offline — no network, no backends. INPUT HYGIENE ONLY; the
strict_verify / NLI / 4-role / span-grounding faithfulness gates are untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.retrieval import shell_detector
from src.tools.access_bypass import clean_fetch_body, strip_markdown_nav_chrome

_FIX = Path(__file__).resolve().parent.parent / "fixtures" / "fetch_junk_leaks"


def _load(name: str) -> str:
    return (_FIX / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Fix A — whole-page shell vocabulary at the seam (leak class 1)
# ---------------------------------------------------------------------------


def test_a1_error_page_something_went_wrong_is_shell() -> None:
    """A1: the replay error_page ("Something went wrong. Wait a moment and try
    again.") is now a shell at ANY length via the new co-occurrence tuple."""
    assert shell_detector.is_cited_span_shell(
        "Something went wrong. Wait a moment and try again."
    ) is True
    # A real article that merely says "something went wrong" in prose (no retry CTA)
    # is NOT a shell — the ALL-of tuple needs the retry clause.
    prose = (
        "The authors note that something went wrong during the third trial arm, "
        "which reduced the effective sample size by roughly eleven percent, and "
        "they adjusted the analysis accordingly across every reported outcome."
    )
    assert shell_detector.is_cited_span_shell(prose) is False


def test_a2_a4_ssrn_security_wall_is_shell() -> None:
    """A2/A4: the ev_932 SSRN Cloudflare security wall is a fetch-shell (the exact
    ``is_cited_span_shell`` verdict both the refetch seam and frame_fetcher use)."""
    wall = _load("ev_932_ssrn_security_wall.txt")
    assert shell_detector.is_cited_span_shell(wall) is True


def test_seam_gate_default_on_and_off() -> None:
    """A2/A3: the seam gate helper defaults ON and honours the OFF value."""
    from src.polaris_graph.retrieval.live_retriever import (
        _fetch_shell_vocab_gate_enabled,
    )
    import os

    prev = os.environ.pop("PG_FETCH_SHELL_VOCAB_GATE", None)
    try:
        assert _fetch_shell_vocab_gate_enabled() is True  # default ON
        os.environ["PG_FETCH_SHELL_VOCAB_GATE"] = "0"
        assert _fetch_shell_vocab_gate_enabled() is False  # OFF ⇒ byte-identical path
    finally:
        os.environ.pop("PG_FETCH_SHELL_VOCAB_GATE", None)
        if prev is not None:
            os.environ["PG_FETCH_SHELL_VOCAB_GATE"] = prev


# ---------------------------------------------------------------------------
# Fix B — markdown nav/boilerplate line filter (leak class 2)
# ---------------------------------------------------------------------------


def test_b1_cookiebot_strip_prose_kept() -> None:
    """ev_954: the ACM Cookiebot consent-link strip is removed; surrounding prose kept."""
    out = strip_markdown_nav_chrome(_load("ev_954_cookiebot_strip.md"))
    assert "cookiebot.com" not in out
    assert "[Consent]" not in out and "[Details]" not in out
    assert "Large language models" in out
    assert "retrieval-augmented generation" in out


def test_b1_openai_nav_strip_prose_kept() -> None:
    """ev_878: the openai full-page nav line is removed; the article prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_878_openai_nav.md"))
    assert "openai.com/research" not in out
    assert "[Products]" not in out
    assert "alignment technique" in out


def test_b1_skip_nav_strip_prose_kept() -> None:
    """ev_1044: the deloitte skip-to-content link is removed; the prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_1044_skip_nav.md"))
    assert "Skip to main content" not in out
    assert "reskilling programs" in out


def test_b1_references_section_byte_identical_guard() -> None:
    """ev_037 GUARD: a references section with citation URLs survives BYTE-IDENTICAL —
    reference mode + per-line citation signals keep every entry, including a
    markdown-link reference that would otherwise trip the link-density drop."""
    text = _load("ev_037_bipartisanpolicy_references.md")
    out = strip_markdown_nav_chrome(text)
    assert out == text.strip()
    # The citation URLs / DOIs / markdown-link reference all survive.
    assert "10.1086/709228" in out
    assert "bipartisanpolicy.org/report/work-future" in out
    assert "[Preprint](https://arxiv.org/abs/2001.01234)" in out


def test_b1_prose_with_inline_links_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round-2 Fix 2 (RC2): a real sentence with incidental inline links keeps its ANCHOR TEXT
    while the URL chrome is unwrapped (the density-dilution leak fix — the URL inside a quote-body
    link is chrome; the real citation URL lives in evidence metadata, not the quote text). The
    OFF path (PG_FETCH_MD_NAV_STRIP_V2=0) is byte-identical to round-1 (links kept wrapped)."""
    text = _load("prose_with_inline_links.md")
    # Default-ON: links unwrapped to anchor text, URLs gone, every prose word preserved.
    on = strip_markdown_nav_chrome(text)
    assert "proposed method" in on
    assert "baseline approach" in on
    assert "https://example.org/m" not in on
    assert "https://example.org/b" not in on
    assert "improving recall without sacrificing precision" in on
    # OFF (V2 gate off): byte-identical to round-1 — the wrapped links survive.
    monkeypatch.setenv("PG_FETCH_MD_NAV_STRIP_V2", "0")
    off = strip_markdown_nav_chrome(text)
    assert off == text.strip()
    assert "[proposed method](https://example.org/m)" in off
    assert "[baseline approach](https://example.org/b)" in off


def test_b1_pure_nav_page_becomes_empty() -> None:
    """A page that is ONLY nav collapses to empty → the caller's existing
    empty_after_clean shell path refuses it (a failed fetch, not a source)."""
    nav_only = _load("ev_878_openai_nav.md").split("\n\n")[0]
    assert strip_markdown_nav_chrome(nav_only) == ""


def test_b1_no_chrome_body_unchanged() -> None:
    """A body with no chrome and no links is byte-preserved (no false drops)."""
    body = (
        "Mortality fell to 12.4% in the treatment arm.\n\n"
        "The reduction persisted at the twelve-month follow-up assessment."
    )
    assert strip_markdown_nav_chrome(body) == body


# ---------------------------------------------------------------------------
# OFF path — byte-identical guarantee
# ---------------------------------------------------------------------------


def test_flags_off_nav_preserved_byte_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    """BOTH B flags OFF ⇒ clean_fetch_body leaves the nav-bearing body byte-identical
    to its input; flag ON removes the nav and keeps the prose."""
    text = _load("ev_878_openai_nav.md")
    monkeypatch.setenv("PG_FETCH_MD_NAV_STRIP", "0")
    monkeypatch.setenv("PG_FETCH_COOKIE_CHROME_STRIP", "0")
    off = clean_fetch_body(text).cleaned_text
    assert "openai.com/research" in off  # nav preserved when flag OFF
    assert off == text.strip()  # byte-identical (no boilerplate patterns present)

    monkeypatch.setenv("PG_FETCH_MD_NAV_STRIP", "1")
    on = clean_fetch_body(text).cleaned_text
    assert "openai.com/research" not in on  # nav removed when flag ON
    assert "alignment technique" in on  # prose kept


# ---------------------------------------------------------------------------
# Fix round-1 (I-fetchclean-001, 2026-07-10) — the remaining 15 welded-chrome
# leaks. F1 welded-heading cap · F2 inline token removals · F3 consent-banner
# line rule · F4 nav-run token removal · F5 shell vocab. Each fixture is a
# realistic reproduction of the replay leak's junk mechanism; every guard
# fixture stays byte-identical (reference / footnote / prose / short heading).
# ---------------------------------------------------------------------------


def test_f5_uq_bot_wall_is_shell() -> None:
    """F5 (ev_688): the UQ 'solve a puzzle / confirm you are' PDF bot-wall is a shell at
    ANY length via the new CHALLENGE_PAGE_COOCCURRENCE tuples."""
    wall = _load("ev_688_uq_bot_wall.txt")
    assert shell_detector.is_cited_span_shell(wall) is True
    # A real article that merely designs a puzzle task is NOT a shell (needs both tokens).
    prose = (
        "The researchers designed a puzzle task to measure working memory across two "
        "hundred participants over twelve weeks and reported robust and replicable effects."
    )
    assert shell_detector.is_cited_span_shell(prose) is False


def test_f5_short_body_markers_added() -> None:
    """F5 (ev_688 short form): the transient-error and 'confirm you are human' stub copy are
    short-body shell markers now."""
    assert shell_detector.is_cited_span_shell("Temporary error. Please try again.") is True
    assert shell_detector.is_cited_span_shell("Let's confirm you are human.") is True


def test_f2_gov_banner_and_crossref_inline_stripped() -> None:
    """F2.1/F2.7 (ev_497): the welded US-gov site banner and the 'Crossref 0' citation-count
    widget are removed inline; the real prose survives on the same line."""
    out = strip_markdown_nav_chrome(_load("ev_497_bls_gov_banner.md"))
    assert "official website of the United States government" not in out
    assert "Here's how you know" not in out
    assert "Crossref 0" not in out
    assert "professional and business services" in out


def test_f2_reading_time_inline_stripped() -> None:
    """F2.2 (ev_957): the '10 Minute Read Time' widget welded inline with the article is removed;
    prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_957_cbreim_reading_time.md"))
    assert "Minute Read Time" not in out
    assert "Office vacancy rates" in out


def test_f2_skip_nav_paren_title_stripped() -> None:
    """F2.3 (ev_258): the paren-title skip-nav form ``(url "skip to main content")`` is removed;
    prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_258_growthlab_skip_nav.md"))
    assert "skip to main content" not in out
    assert "growthlab.hks.harvard.edu" not in out
    assert "Economic complexity" in out


def test_f2_tandfonline_cover_sheet_stripped() -> None:
    """F2.6 (ev_524): the Taylor & Francis PDF cover-sheet tokens (print/online ISSN pair,
    'Journal homepage:' URL) are removed; the article prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_524_tandfonline_cover_sheet.md"))
    assert "(Print)" not in out
    assert "1466-4402" not in out
    assert "Journal homepage:" not in out
    assert "tandfonline.com" not in out
    assert "funding formulas" in out


def test_f2_f3_iab_consent_stripped_prose_kept() -> None:
    """F2.5 + F3 (ev_954): the IAB TCF anchor is removed and the consent-banner line is dropped;
    the surrounding real prose on the other lines survives."""
    out = strip_markdown_nav_chrome(_load("ev_954_iab_tcf_consent.md"))
    assert "IABV2SETTINGS" not in out
    assert "This website uses cookies" not in out
    assert "Cookie Policy" not in out
    assert "Retrieval-augmented generation reduced unsupported claims" in out
    assert "improved factual precision" in out


def test_f3_ec_europa_consent_line_dropped_prose_kept() -> None:
    """F3 (ev_726): the 'This site uses cookies' banner line is dropped; the article prose above
    and below survives."""
    out = strip_markdown_nav_chrome(_load("ev_726_ec_europa_consent.md"))
    assert "This site uses cookies" not in out
    assert "browsing experience" not in out
    assert "Digital Services Act" in out
    assert "national digital services coordinators" in out


def test_f3_italian_consent_line_dropped_prose_kept() -> None:
    """F3 multilingual (ev_661): the Italian 'Nel nostro sito utilizziamo … il tuo consenso'
    banner line is dropped; the Italian article prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_661_unibo_consent_italian.md"))
    assert "Nel nostro sito utilizziamo" not in out
    assert "cookie di profilazione" not in out
    assert "politiche di coesione" in out
    assert "investimenti infrastrutturali" in out


def test_f1_f3_welded_heading_consent_dropped_prose_kept() -> None:
    """F1 + F3 (ev_244): the long ``## You control your data …`` welded heading no longer bypasses
    chrome rules (F1 cap) and is dropped as a consent banner (F3); real prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_244_appunite_consent_heading.md"))
    assert "You control your data" not in out
    assert "business partners use technologies" not in out
    assert "storage from compute" in out
    assert "schema registry" in out


def test_f4_hackernews_nav_run_stripped_prose_kept() -> None:
    """F4 (ev_255): the welded Hacker News header nav run is removed even though the line's prose
    tail carries a year; the real prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_255_hackernews_nav.md"))
    assert "news.ycombinator.com" not in out
    assert "[past]" not in out and "[comments]" not in out
    assert "asynchronous written communication" in out


def test_f4_repec_browse_nav_run_stripped_prose_kept() -> None:
    """F4 (ev_748): the welded RePEc browse-nav link run is removed even though the series tail
    carries a year (per-run guard, not whole-line); the prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_748_repec_browse_nav.md"))
    assert "ideas.repec.org/w.html" not in out
    assert "[Journal articles]" not in out and "[Books]" not in out
    assert "RePEc Biblio curated reading list" in out
    assert "2019" in out  # the real prose tail (with its year) is preserved


def test_f1_f2_video_chrome_after_heading_stripped() -> None:
    """F1 + F2.4 (ev_272): the inline video-player chrome welded after ``## Summary`` is removed
    (the long heading line falls through the F1 cap into F2); the wage prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_272_bls_video_chrome.md"))
    assert "enable javascript to play this video" not in out
    assert "Video transcript available" not in out
    assert "median annual wage" in out


# --- guards: every one stays byte-identical -------------------------------


def test_f2_crossref_reference_line_guard_byte_identical() -> None:
    """F2.7 GUARD: a reference line naming Crossref near a year/DOI is reference-like, so the
    Crossref widget rule is skipped and the whole line survives byte-identical."""
    text = _load("crossref_reference_line_guard.md")
    out = strip_markdown_nav_chrome(text)
    assert out == text.strip()
    assert "Crossref 12" in out
    assert "10.1086/709228" in out


def test_f4_footnote_marker_run_guard_byte_identical() -> None:
    """F4 GUARD: a run of pure-digit footnote markers is citation apparatus, not nav — kept
    byte-identical."""
    text = _load("footnote_marker_run_guard.md")
    out = strip_markdown_nav_chrome(text)
    assert out == text.strip()
    assert "[1](#fn1)" in out and "[4](#fn4)" in out


def test_f3_privacy_cookie_sentence_guard_byte_identical() -> None:
    """F3 GUARD: a real sentence that mentions cookies once but does NOT open with a consent
    anchor is kept byte-identical."""
    text = _load("privacy_cookie_sentence_guard.md")
    out = strip_markdown_nav_chrome(text)
    assert out == text.strip()
    assert "cookie consent banners" in out


def test_f1_short_heading_guard_byte_identical() -> None:
    """F1 GUARD: a short real heading (<= the char cap) is still kept byte-identical; the prose
    below survives."""
    text = _load("short_heading_guard.md")
    out = strip_markdown_nav_chrome(text)
    assert out == text.strip()
    assert "## Results" in out
    assert "primary endpoint" in out


# ---------------------------------------------------------------------------
# Fix round-2 (I-fetchclean-001, 2026-07-10) — the 15 residual welded-chrome leaks
# from the live retest. RC1 heading-line bypass · RC2 density-dilution (chrome welded
# inside a prose line, unwrapped to anchor text) · RC3 vocab gaps · RC4 span-window
# link-boundary snap (live_retriever). Every leak fixture must clean to junk-free; every
# round-2 guard stays byte-identical; the OFF path (PG_FETCH_MD_NAV_STRIP_V2=0) is
# byte-identical to round-1.
# ---------------------------------------------------------------------------


def test_r2_wharton_image_and_welded_heading_stripped() -> None:
    """RC1 (ev_880): the long welded heading's image markdown is removed (F1 fall-through + F2
    image delete); the article prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_880_wharton_image_heading.md"))
    assert "![Image" not in out
    assert "campus-banner-image.png" not in out
    assert "remote onboarding reduces first-year attrition" in out


def test_r2_thehill_ticker_and_nav_stripped() -> None:
    """RC1/RC3 (ev_195): a short welded heading loses its nav-link URLs (unwrapped) and the
    'N hours ago' ticker token; the article prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_195_thehill_ticker_nav.md"))
    assert "thehill.com" not in out
    assert "hours ago" not in out
    assert "appropriations bill advanced out of committee" in out


def test_r2_appunite_welded_prose_consent_inline_stripped() -> None:
    """RC1/RC3 (ev_244): a CMP consent sentence welded MID-line after real prose is removed inline
    (F3, not a whole-line drop); the surrounding article prose on the SAME line survives."""
    out = strip_markdown_nav_chrome(_load("ev_244_appunite_welded_prose_consent.md"))
    assert "business partners use technologies" not in out
    assert "including cookies" not in out
    assert "storage from compute" in out
    assert "schema registry lets producers evolve message formats" in out


def test_r2_ama_empty_anchor_and_bare_url_stripped() -> None:
    """RC1/RC3 (ev_441): the welded heading's empty-anchor link and bare parenthesised URL echo are
    removed; the ethics prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_441_ama_empty_anchor_heading.md"))
    assert "journalofethics.ama-assn.org" not in out
    assert "[]" not in out
    assert "ethical obligation to disclose financial conflicts of interest" in out


def test_r2_commerce_prose_inline_links_unwrapped() -> None:
    """RC2 (ev_011): inline absolute-URL study links welded into real prose are unwrapped to their
    anchor text (density-dilution leak); the URL chrome is gone, every prose word preserved."""
    out = strip_markdown_nav_chrome(_load("ev_011_commerce_prose_study_links.md"))
    assert "commerce.nc.gov" not in out
    assert "](http" not in out
    assert "recent study" in out and "follow-up analysis" in out
    assert "broadband expansion in rural counties increased small-business formation" in out


def test_r2_oamg_related_posts_run_stripped() -> None:
    """RC2 (ev_896): a welded related-posts link RUN after the article prose is removed; the
    conclusion prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_896_oamg_related_posts.md"))
    assert "oa.mg" not in out
    assert "[Scaling laws revisited]" not in out
    assert "transformer models scale predictably with data and compute" in out


def test_r2_oecd_toc_share_run_stripped() -> None:
    """RC2 (ev_045): the welded TOC/share link RUN is removed; the labour-market prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_045_oecd_toc_share.md"))
    assert "oecd.org/share" not in out
    assert "[Print]" not in out and "[Cite]" not in out
    assert "active labour-market policies improve reemployment rates" in out


def test_r2_oska_download_cta_unwrapped() -> None:
    """RC2 (ev_191): a single welded download-CTA link is unwrapped to anchor text (URL gone); the
    retraining prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_191_oska_download_cta.md"))
    assert "oska.example.org" not in out
    assert ".pdf)" not in out
    assert "vocational retraining raises median wages" in out


def test_r2_punku_relative_related_links_deleted() -> None:
    """RC2 (ev_891): welded related-posts links with RELATIVE (/blog/…) targets are deleted whole
    (site nav, not prose); the payment-rails prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_891_punku_related_list.md"))
    assert "/blog/" not in out
    assert "[Onboarding merchants]" not in out and "[Dispute handling]" not in out
    assert "staged rollout of new payment rails to limit settlement risk" in out


def test_r2_bipartisanpolicy_backlink_deleted_citation_kept() -> None:
    """RC2/RC4 (ev_037): a reference-like endnote keeps its DOI + citation text byte-preserved; ONLY
    the empty-anchor same-page footnote back-link (the sole ref-mode exception) is deleted."""
    out = strip_markdown_nav_chrome(_load("ev_037_backlink_endnote.md"))
    assert "#4468eeee-endnote-link" not in out
    assert "bipartisanpolicy.org/report/work-future" not in out
    assert "10.1353/eca.2018.0000" in out
    assert "Is automation labor-displacing?" in out


def test_r2_nationalacademies_login_wall_stripped() -> None:
    """RC3 (ev_117): the login-wall sentence and the 'Download as guest' CTA link are removed (the
    line collapses and drops); the report prose on the next line survives."""
    out = strip_markdown_nav_chrome(_load("ev_117_nationalacademies_loginwall.md"))
    assert "You must be logged in" not in out
    assert "Download as guest" not in out
    assert "federal research funding yields measurable long-term economic returns" in out


def test_r2_scale_stanford_empty_anchor_and_bare_urls_stripped() -> None:
    """RC3/RC4 (ev_933): an empty-anchor link and the bare parenthesised same-page URL echoes are
    removed; the RL-curriculum prose survives."""
    out = strip_markdown_nav_chrome(_load("ev_933_scale_stanford_bare_urls.md"))
    assert "scale.stanford.edu" not in out
    assert "#site-content" not in out and "#page-footer" not in out
    assert "curriculum ordering improves sample efficiency" in out


def test_r2_repec_serial_index_is_shell() -> None:
    """RC3 (ev_748): a RePEc serial INDEX page (not an article) is a whole-source fetch-shell via
    the new any-length co-occurrence tuple, so it is refused at the is_cited_span_shell fetch seam."""
    wall = _load("ev_748_repec_serial_index.txt")
    assert shell_detector.is_cited_span_shell(wall) is True
    # A real economics article that merely cites a RePEc URL once is NOT a shell (needs both tokens).
    prose = (
        "The working paper, archived at https://ideas.repec.org/p/example, estimates that minimum "
        "wage increases raised earnings for low-tenure workers without measurable employment loss."
    )
    assert shell_detector.is_cited_span_shell(prose) is False


# --- round-2 guards: byte-identical / OFF-path ----------------------------


def test_r2_reference_line_inline_link_guard_byte_identical() -> None:
    """RC2 GUARD: a reference-like citation line (year + author) keeps its inline absolute-URL link
    WRAPPED byte-identical — the unwrap policy never touches a reference/citation line."""
    text = _load("reference_line_inline_link_guard.md")
    out = strip_markdown_nav_chrome(text)
    assert out == text.strip()
    assert "[Full text](https://www.brookings.edu/bpea/2018/autor-salomons)" in out


def test_r2_v2_off_is_byte_identical_to_round1(monkeypatch: pytest.MonkeyPatch) -> None:
    """OFF path: with PG_FETCH_MD_NAV_STRIP_V2=0 the round-2 unwrap/vocab is never applied, so a
    prose line with incidental inline links is byte-identical to its (round-1 prose-like KEEP)
    input; ON, the links are unwrapped."""
    text = _load("ev_011_commerce_prose_study_links.md")
    monkeypatch.setenv("PG_FETCH_MD_NAV_STRIP_V2", "0")
    off = strip_markdown_nav_chrome(text)
    assert off == text.strip()
    assert "commerce.nc.gov" in off  # links preserved when V2 OFF
    monkeypatch.delenv("PG_FETCH_MD_NAV_STRIP_V2", raising=False)
    on = strip_markdown_nav_chrome(text)
    assert "commerce.nc.gov" not in on  # links unwrapped when V2 ON


def test_r2_span_window_link_boundary_snap() -> None:
    """RC4 Fix 5: _build_provenance_quote trims a leading dangling link URL tail and a trailing
    incomplete link token off a windowed span; OFF ⇒ byte-identical. Never eats a decimal/word."""
    from src.polaris_graph.retrieval.live_retriever import (
        _trim_span_link_fragments,
        _span_window_link_snap_enabled,
    )
    import os

    # leading dangling URL tail (no '[' before the first ')') is trimmed.
    assert _trim_span_link_fragments(
        'work-future/#4468eeee-link) the study reports a 12.4 percent reduction in mortality.'
    ) == 'the study reports a 12.4 percent reduction in mortality.'
    # trailing incomplete '[anchor](partial' token is trimmed.
    assert _trim_span_link_fragments(
        'Mortality fell to 12.4 percent in the treatment arm [Read more](https://example.org/rea'
    ) == 'Mortality fell to 12.4 percent in the treatment arm'
    # a clean span (a complete link, a decimal, no dangling fragment) is byte-identical.
    clean = 'The reduction was 12.4 percent, per the [trial report](https://example.org/t).'
    assert _trim_span_link_fragments(clean) == clean
    # gate default-ON, honours OFF.
    prev = os.environ.pop("PG_SPAN_WINDOW_LINK_SNAP", None)
    try:
        assert _span_window_link_snap_enabled() is True
        os.environ["PG_SPAN_WINDOW_LINK_SNAP"] = "0"
        assert _span_window_link_snap_enabled() is False
    finally:
        os.environ.pop("PG_SPAN_WINDOW_LINK_SNAP", None)
        if prev is not None:
            os.environ["PG_SPAN_WINDOW_LINK_SNAP"] = prev
