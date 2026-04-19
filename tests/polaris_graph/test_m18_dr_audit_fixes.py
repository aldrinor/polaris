"""M-18 (DR audit pass 1): classifier fixes from tirzepatide v4 DR audit.

Fixes two specific misclassifications flagged by Codex DR output audit:

M-18a: NEJM head-to-head RCT "Tirzepatide as Compared with Semaglutide
       for the Treatment of Obesity" was labeled T4 (narrative review)
       because "for the treatment of" matched _NARRATIVE_FLAVOR_KEYWORDS
       and no primary-study marker counter-balanced. Fix: add "as
       compared with" to primary-study markers; have narrative flavor
       defer to primary signals when present.

M-18b: Facebook post about tirzepatide boxed warning was labeled T7
       via R1_stub_content_length because R1 ran before R2b social
       platform check. Fix: add new RP1_social_platform_early rule
       that fires BEFORE R1 to reject social domains by authority
       rather than by fetched content size.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
    _detect_narrative_flavor_from_title,
    _detect_primary_study_signal,
)


# ─────────────────────────────────────────────────────────────────
# M-18a: NEJM head-to-head RCT over-demotion fix
# ─────────────────────────────────────────────────────────────────


def test_m18a_nejm_head_to_head_rct_title_is_primary() -> None:
    """'Tirzepatide as Compared with Semaglutide for the Treatment of
    Obesity.' is the NEJM SURMOUNT-5 head-to-head RCT. DR audit found
    it classified T4 because 'for the treatment of' triggered
    narrative flavor. M-18a: 'as compared with' is now a primary-study
    marker AND narrative flavor defers to primary signals."""
    title = "Tirzepatide as Compared with Semaglutide for the Treatment of Obesity."
    assert _detect_primary_study_signal(title) is True
    assert _detect_narrative_flavor_from_title(title) is False


def test_m18a_nejm_rct_classifies_t1_not_t4() -> None:
    """End-to-end: NEJM URL + head-to-head RCT title + OpenAlex article
    + journal should classify T1."""
    r = classify_source_tier(ClassificationSignals(
        url="https://doi.org/10.1056/NEJMoa2416394",
        title="Tirzepatide as Compared with Semaglutide for the Treatment of Obesity.",
        publisher="",
        fetched_content_length=8000,
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
    ))
    assert r.tier.value == "T1"


def test_m18a_rct_with_narrative_flavor_keyword_still_primary() -> None:
    """A randomized trial titled with 'for the treatment of' should
    still be primary; primary signal wins over narrative flavor."""
    title = "A randomized placebo-controlled trial for the treatment of obesity."
    assert _detect_primary_study_signal(title) is True
    assert _detect_narrative_flavor_from_title(title) is False


def test_m18a_pure_narrative_review_without_primary_signal_still_demoted() -> None:
    """Sanity: a bare 'X for the Treatment of Y' title with no primary
    study signal remains narrative flavor."""
    title = "Tirzepatide for the Treatment of Type 2 Diabetes."
    assert _detect_primary_study_signal(title) is False
    assert _detect_narrative_flavor_from_title(title) is True


def test_m18a_as_compared_to_also_works() -> None:
    """Some journals use 'as compared to' instead of 'as compared with'."""
    title = "Drug X as Compared to Drug Y for the Treatment of Z."
    assert _detect_primary_study_signal(title) is True


# ─────────────────────────────────────────────────────────────────
# M-18b: Social platform short-circuit before R1 stub
# ─────────────────────────────────────────────────────────────────


def test_m18b_facebook_post_classified_t6_not_t7_stub() -> None:
    """Facebook post with 816-char body (stub-sized) should hit
    RP1_social_platform_early (T6) BEFORE R1_stub_content_length (T7).
    DR audit found Facebook was T7, meaning it was citable as if it
    were just a truncated article."""
    r = classify_source_tier(ClassificationSignals(
        url="https://www.facebook.com/clinicalpharmacyboard/posts/black-box-warning-of-tirzepatide/",
        title="Black Box Warning of Tirzepatide Risk of thyroid C-cell tumors",
        publisher="",
        fetched_content_length=816,
    ))
    assert r.tier.value == "T6"
    assert "RP1_social_platform_early" in r.matched_rules


def test_m18b_twitter_post_large_body_still_t6() -> None:
    """Even if Twitter/X post has large body (thread dump), it must
    remain T6 — social platform rule fires first regardless of
    content length."""
    r = classify_source_tier(ClassificationSignals(
        url="https://twitter.com/account/status/123456789",
        title="Long thread about tirzepatide safety",
        publisher="",
        fetched_content_length=50000,  # large thread dump
    ))
    assert r.tier.value == "T6"
    assert "RP1_social_platform_early" in r.matched_rules


def test_m18b_reddit_post_also_social() -> None:
    """Reddit.com medical discussion post — same rule applies."""
    r = classify_source_tier(ClassificationSignals(
        url="https://reddit.com/r/diabetes/comments/abc/tirzepatide_experience",
        title="My tirzepatide experience",
        publisher="",
        fetched_content_length=3000,
    ))
    assert r.tier.value == "T6"
    assert "RP1_social_platform_early" in r.matched_rules


def test_m18b_legitimate_journal_stub_still_t7() -> None:
    """Sanity: a real journal URL with stub-sized content must still
    be T7 (M-18b only short-circuits social platforms, not journals)."""
    r = classify_source_tier(ClassificationSignals(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa1234",
        title="Primary trial of tirzepatide",
        publisher="",
        fetched_content_length=500,  # stub
    ))
    assert r.tier.value == "T7"
    assert "R1_stub_content_length" in r.matched_rules


def test_m18b_non_social_non_stub_url_unaffected() -> None:
    """Ensure M-18b hasn't changed classification for non-social,
    non-stub URLs."""
    r = classify_source_tier(ClassificationSignals(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC9999/",
        title="A randomized placebo-controlled trial of tirzepatide",
        publisher="",
        fetched_content_length=15000,
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
    ))
    # Should classify T1 via R9 primary study (title has randomized
    # + placebo-controlled primary-study markers)
    assert r.tier.value == "T1"
