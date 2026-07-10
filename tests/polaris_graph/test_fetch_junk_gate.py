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


def test_b1_prose_with_inline_links_kept() -> None:
    """A real sentence with incidental inline links is KEPT byte-identical (prose-like)."""
    text = _load("prose_with_inline_links.md")
    out = strip_markdown_nav_chrome(text)
    assert out == text.strip()
    assert "[proposed method](https://example.org/m)" in out
    assert "[baseline approach](https://example.org/b)" in out


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
