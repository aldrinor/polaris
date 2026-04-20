"""M-23 unit tests: Unpaywall + strip-before-paywall + quality-scored winner.

Covers iteration 6 access_bypass.py changes:
  M-23a: Unpaywall step 0 (DOI -> OA URL swap before concurrent fetch)
  M-23b: Strip navigation boilerplate BEFORE paywall detection
         (previously nav chrome with "sign in" triggered false positives
         on 45K-char NEJM/Lancet full-article bodies)
  M-23c: Quality-scored winner selection (length + structural markers +
         numeric density) replaces first-success-wins — fixes the
         "Jina 422-char stub beat Crawl4AI 45K NEJM fetch" bug from V7.

These tests are pure unit tests — no network, no real backends. They
exercise the scoring function, the strip-vs-paywall ordering, and the
winner-selection loop with synthetic AccessResult inputs.
"""

from __future__ import annotations

import re

import pytest

from src.tools.access_bypass import (
    AccessBypass,
    AccessResult,
    _score_content_quality,
    _strip_navigation_boilerplate,
)


# ---------------------------------------------------------------------------
# M-23c: quality scoring
# ---------------------------------------------------------------------------


def test_score_empty_content_is_zero() -> None:
    assert _score_content_quality("") == 0.0


def test_score_paywall_stub_is_near_zero() -> None:
    stub = "Please sign in to continue reading. Subscribe now."
    assert _score_content_quality(stub) < 0.05


def test_score_long_stub_stays_low_without_structural_markers() -> None:
    """Length alone must not win — a 10K-char paywall shell with no
    Abstract/Methods/Results has near-zero structural score."""
    stub = "Please subscribe to continue. " * 400
    score = _score_content_quality(stub)
    assert score < 0.3, (
        f"Long stub scored {score:.3f} — length alone should not dominate"
    )


def test_score_full_article_beats_stub_by_large_margin() -> None:
    """A real article body with structural sections and numeric data
    should easily beat any paywall stub at comparable length."""
    article = (
        "Abstract: In this phase 3 trial, 524 participants received "
        "tirzepatide 15 mg. Methods: randomized double-blind. Results: "
        "8.5% HbA1c reduction, 95% CI 7.9-9.1, p<0.001. Discussion: "
        "superior to semaglutide. Conclusion: tirzepatide is effective. "
        "Introduction. Background. References. Statistical analysis."
    ) * 80
    stub = "Please sign in. Subscribe to read." * 300
    a_score = _score_content_quality(article)
    s_score = _score_content_quality(stub)
    assert a_score > s_score + 0.3, (
        f"article={a_score:.3f} stub={s_score:.3f} — margin too small"
    )


def test_score_rewards_numeric_density() -> None:
    """Two articles of the same length, same structural markers: the
    one with p-values and percentages should win — that is the evidence
    the generator needs for quantitative claims."""
    with_numbers = (
        "Abstract Methods Results Discussion Conclusion. "
        "8.5% p<0.001 95% CI 524 participants 15 mg N=2,539 " * 20
    )
    without_numbers = (
        "Abstract Methods Results Discussion Conclusion. "
        "The study found benefits and risks were discussed. " * 20
    )
    assert (
        _score_content_quality(with_numbers)
        > _score_content_quality(without_numbers)
    )


# ---------------------------------------------------------------------------
# M-23b: strip-before-paywall ordering
# ---------------------------------------------------------------------------


def test_nav_chrome_sign_in_stripped_before_paywall_check() -> None:
    """A real NEJM-style article body often contains a footer-nav line
    'Sign In' / 'Subscribe' as a literal bullet. Under the OLD order,
    these fired paywall patterns and the full 45K article body was
    thrown away. After stripping boilerplate, the standalone 'Sign In'
    line is gone, and the real article text has no such patterns."""
    bypass = AccessBypass()
    raw = (
        "Sign In\n"
        "Subscribe\n"
        "# Tirzepatide once weekly in type 2 diabetes\n\n"
        "Abstract. In this phase 3 randomized trial of 524 patients, "
        "tirzepatide reduced HbA1c by 8.5 percent compared with placebo "
        "(95% CI 7.9 to 9.1, p<0.001). Methods described standard "
        "randomization. Results and Discussion follow.\n"
    )
    stripped = _strip_navigation_boilerplate(raw)
    # The standalone nav lines are gone; the real article text is intact.
    assert "# Tirzepatide once weekly" in stripped
    assert "HbA1c by 8.5 percent" in stripped
    # After stripping, no paywall signal fires.
    assert not bypass._detect_paywall(stripped), (
        "Stripped full-article text falsely flagged as paywall"
    )


def test_short_stub_still_detected_as_paywall_after_strip() -> None:
    """Stripping must NOT break the short-stub detection — a 500-char
    paywall shell with auth prompts is still correctly rejected."""
    bypass = AccessBypass()
    stub = (
        "# Article Title\n"
        "To continue reading, please sign in or create an account. "
        "Subscribers have full access to our content."
    )
    stripped = _strip_navigation_boilerplate(stub)
    assert bypass._detect_paywall(stripped), (
        "Short stub with auth prompt should still be flagged as paywall"
    )


# ---------------------------------------------------------------------------
# M-23d: HTTP error stub detection
# ---------------------------------------------------------------------------


def test_jina_403_forbidden_stub_rejected() -> None:
    """Jina proxies 403 Forbidden pages with success=True. Without
    M-23d these slipped past _detect_paywall and won as the only
    candidate. Exposed by live test on figshare OA landing page."""
    bypass = AccessBypass()
    jina_403 = (
        "Title: 403 Forbidden\n\n"
        "URL Source: https://figshare.com/articles/foo\n\n"
        "Warning: Target URL returned error 403: Forbidden\n\n"
        "Markdown Content:\n# 403 Forbidden\n\n# 403 Forbidden\n"
    )
    assert bypass._detect_paywall(jina_403), (
        "Jina 403-Forbidden stub must be treated as failed fetch"
    )


def test_404_not_found_stub_rejected() -> None:
    bypass = AccessBypass()
    not_found = (
        "Title: 404 Not Found\n\nThe requested page could not be found.\n"
    )
    assert bypass._detect_paywall(not_found)


def test_access_denied_short_page_rejected() -> None:
    bypass = AccessBypass()
    denied = "Access Denied\n\nYour IP has been blocked by Cloudflare."
    assert bypass._detect_paywall(denied)


def test_server_error_stub_rejected() -> None:
    bypass = AccessBypass()
    err_503 = "503 Service Unavailable\n\nThe server is temporarily unable."
    assert bypass._detect_paywall(err_503)


def test_long_article_with_incidental_403_not_rejected() -> None:
    """A 30K-char medical paper that *mentions* 'returned error 403'
    in one sentence (e.g., in a Methods section discussing HTTP
    robustness) must NOT be treated as a paywall stub — the length
    floor of 2K chars prevents over-triggering."""
    bypass = AccessBypass()
    long_article = (
        "Abstract. Randomized trial. Methods: we retried failed fetches "
        "(those that returned error 403 were excluded). Results: 8.5% "
        "HbA1c reduction (p<0.001). Discussion. Conclusion. "
    ) * 400
    assert not bypass._detect_paywall(long_article), (
        "Long article with incidental HTTP-error phrase should NOT fire M-23d"
    )


# ---------------------------------------------------------------------------
# M-23f: paywall-regex false-positive regression (live test finding)
# ---------------------------------------------------------------------------


def test_m23f_long_article_with_sign_and_access_not_flagged() -> None:
    """REGRESSION: live test on NEJM SURPASS-2 revealed the old greedy
    regex `sign.*in.*to.*access` matched a 50K-char article body saying
    '...the investigators worked under confidentiality agreements with
    the sponsor, and all the authors had full access to the trial
    data...' because `.*` spans arbitrary text. Fixed by requiring
    tight whitespace-adjacent tokens and length-gating the loose
    patterns."""
    bypass = AccessBypass()
    nejm_methods_excerpt = (
        "Abstract. Methods. In an open-label 40-week trial 1879 "
        "participants with type 2 diabetes were randomly assigned to "
        "once-weekly subcutaneous tirzepatide or semaglutide. "
        "The investigators worked under confidentiality agreements "
        "with the sponsor, and all the authors had full access to "
        "the trial data. The manuscript was signed off by all authors. "
        "Results: tirzepatide reduced HbA1c by 8.5 percent at 40 weeks "
        "(95 percent CI 7.9 to 9.1, p<0.001). Conclusion: superior. "
    ) * 60  # ~30K chars
    assert not bypass._detect_paywall(nejm_methods_excerpt), (
        "Long article with 'sign(ed)' and 'access' as separate tokens "
        "in normal body prose must NOT match the paywall regex"
    )


def test_m23f_long_article_with_subscribe_read_words_separated() -> None:
    """A paper mentioning 'subscribers to a newsletter' and 'read by'
    should not be falsely flagged — the old `subscribe.*to.*read`
    regex matched any text with those words anywhere."""
    bypass = AccessBypass()
    long_body = (
        "Abstract. Background: subscribers to diabetes-care newsletters "
        "often read recent trial updates, but primary peer-reviewed "
        "evidence remains essential. Methods. Results: 8.5% reduction. "
    ) * 200
    assert not bypass._detect_paywall(long_body)


def test_m23f_short_paywall_stub_still_rejected() -> None:
    """Confirm that genuine short paywall stubs STILL fire the
    detection after the tightening — M-23f must not regress real
    paywall rejection."""
    bypass = AccessBypass()
    for stub in [
        "Please subscribe to read the full article",
        "Sign in to access this content",
        "Members only. Log in required.",
        "Purchase this article to continue",
    ]:
        assert bypass._detect_paywall(stub), (
            f"Genuine paywall stub not detected: {stub!r}"
        )


# ---------------------------------------------------------------------------
# M-23c: winner selection logic (synthetic)
# ---------------------------------------------------------------------------


def test_winner_selection_prefers_quality_over_first_arrival() -> None:
    """Simulate the concurrent-fetch bug from V7: Jina returns a tiny
    paywall stub first, Crawl4AI returns a real 20K-char article
    second. The high-quality result must win regardless of order."""
    jina_stub = AccessResult(
        url="https://nejm.org/doi/full/10.1056/NEJMoa2416394",
        content="# Article\nAccess this article. Subscribe to NEJM.",
        access_method="jina",
        legal_alternative=None,
        success=True,
        metadata={},
    )
    article_body = (
        "Abstract. In this phase 3 trial, 524 patients received "
        "tirzepatide 15 mg weekly. Methods: randomized double-blind. "
        "Results: HbA1c fell 8.5% (95% CI 7.9-9.1, p<0.001). "
        "Discussion: superior to semaglutide. Conclusion: effective. "
        "Introduction. Background. References."
    ) * 50
    crawl4ai_full = AccessResult(
        url="https://nejm.org/doi/full/10.1056/NEJMoa2416394",
        content=article_body,
        access_method="crawl4ai",
        legal_alternative=None,
        success=True,
        metadata={},
    )

    # In the V7 ordering bug, jina arrived first — list order matters.
    candidates = [jina_stub, crawl4ai_full]
    # Simulate M-23c selection
    scored = [(c, _score_content_quality(c.content)) for c in candidates]
    scored.sort(key=lambda x: x[1], reverse=True)
    winner, winner_score = scored[0]

    assert winner.access_method == "crawl4ai", (
        f"Wrong winner: {winner.access_method} (scores: "
        f"{[(c.access_method, round(s, 3)) for c, s in scored]})"
    )
    assert winner_score > _score_content_quality(jina_stub.content) + 0.3


def test_winner_selection_handles_single_candidate() -> None:
    """When only one backend returns successfully, it wins uncontested."""
    only = AccessResult(
        url="https://example.org/paper",
        content=(
            "Abstract. Methods. Results. Discussion. Conclusion. "
            "8.5% p<0.001 524 patients."
        ) * 20,
        access_method="trafilatura",
        legal_alternative=None,
        success=True,
        metadata={},
    )
    scored = [(only, _score_content_quality(only.content))]
    winner, _ = scored[0]
    assert winner is only


# ---------------------------------------------------------------------------
# M-23a: Unpaywall shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_try_unpaywall_returns_none_when_no_email(monkeypatch) -> None:
    """Without UNPAYWALL_EMAIL set, the method must bail early with
    None rather than making a malformed API call."""
    monkeypatch.delenv("UNPAYWALL_EMAIL", raising=False)
    bypass = AccessBypass()
    result = await bypass._try_unpaywall("10.1056/NEJMoa2416394")
    assert result is None


def test_extract_doi_finds_nejm_doi() -> None:
    """Sanity-check the DOI extraction the Unpaywall step depends on."""
    bypass = AccessBypass()
    doi = bypass._extract_doi(
        "https://www.nejm.org/doi/full/10.1056/NEJMoa2416394"
    )
    assert doi == "10.1056/NEJMoa2416394"


def test_extract_doi_finds_lancet_doi() -> None:
    bypass = AccessBypass()
    doi = bypass._extract_doi(
        "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736(21)01324-6"
    )
    # Lancet PII URLs may not contain a canonical DOI; this just asserts
    # no crash. The resolver handles PII->DOI via _resolve_academic_url.
    assert doi is None or re.match(r"10\.\d{4,9}/.+", doi)
