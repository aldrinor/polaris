"""I-deepfix-001 U10 (scam / commercial demote leg): the tier classifier
mis-rated sources BOTH ways —

  * a retracted / withdrawn paper whose retraction is recorded only in its
    TITLE (OpenAlex ``is_retracted`` unset) was re-deposited on a preprint host
    and earned R7 T4 instead of being excluded; and
  * a commercial medical-tourism / clinic-marketing sales page was promoted to
    an authoritative / abstract-eligible tier via an OpenAlex article+journal
    MISLABEL.

The fix (a) extends R0 to exclude a paper carrying an explicit leading
retraction / withdrawal / expression-of-concern title marker, and (b) adds R8d
to demote an unambiguous commercial clinic-marketing / medical-tourism
call-to-action page to T6 (low commercial weight) BEFORE R9/R10 can promote it.

Both are per-citation WEIGHT decisions (CLAUDE.md §-1.3): retraction exclusion
mirrors the pre-existing ``openalex_is_retracted`` behaviour; the commercial
page is parked at T6, never dropped. The faithfulness engine is untouched, and
neither leg touches the U10 venue-authority exemption.

Two false-positive guards prove the fix does NOT over-demote a legitimate study
whose SUBJECT is retraction or medical tourism.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    TierLevel,
    classify_source_tier,
)

# Tiers a source must NOT reach to be "authoritative" / abstract-eligible.
# T4 (narrative review) is abstract-eligible, so a demoted commercial / scam
# source must sit strictly below it (T5-T7 or UNKNOWN-excluded).
_AUTHORITATIVE_OR_ABSTRACT_TIERS = {
    TierLevel.T1,
    TierLevel.T2,
    TierLevel.T3,
    TierLevel.T4,
}


# ─────────────────────────────────────────────────────────────────────
# Part A — retracted / withdrawn page excluded below T4
# ─────────────────────────────────────────────────────────────────────


def test_retracted_title_on_preprint_host_excluded_below_t4() -> None:
    """A retracted paper re-deposited on protocols.io (a preprint host) with a
    leading 'RETRACTED:' title but no OpenAlex flag. Pre-fix it earned R7 T4;
    post-fix R0 excludes it (UNKNOWN) — strictly below T4."""
    sig = ClassificationSignals(
        url="https://www.protocols.io/view/retracted-stem-cell-protocol-abcd1234",
        title="RETRACTED: Autologous stem cell therapy reverses Parkinson's disease",
        fetched_content_length=8000,
        openalex_is_retracted=False,
    )
    result = classify_source_tier(sig)
    assert result.tier == TierLevel.UNKNOWN, result.tier
    assert "R0_retracted" in result.matched_rules, result.matched_rules
    assert result.tier not in _AUTHORITATIVE_OR_ABSTRACT_TIERS


def test_expression_of_concern_title_excluded() -> None:
    """An 'Expression of Concern:' prefixed title is also excluded."""
    sig = ClassificationSignals(
        url="https://medrxiv.org/content/10.1101/2024.01.01.24300000v1",
        title="Expression of Concern: Ivermectin for COVID-19 outcomes",
        fetched_content_length=8000,
    )
    result = classify_source_tier(sig)
    assert result.tier == TierLevel.UNKNOWN, result.tier
    assert "R0_retracted" in result.matched_rules


def test_openalex_retraction_flag_still_excluded() -> None:
    """Regression: the pre-existing OpenAlex-flag retraction path is unchanged."""
    sig = ClassificationSignals(
        url="https://www.nature.com/articles/s41586-024-00000-0",
        title="A perfectly ordinary looking title",
        fetched_content_length=8000,
        openalex_is_retracted=True,
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
    )
    result = classify_source_tier(sig)
    assert result.tier == TierLevel.UNKNOWN
    assert "R0_retracted" in result.matched_rules


def test_paper_about_retraction_not_excluded() -> None:
    """False-positive guard: a legitimate meta-research paper whose SUBJECT is
    retraction must NOT be excluded — the title marker is a leading prefix only."""
    sig = ClassificationSignals(
        url="https://www.nejm.org/doi/full/10.1056/NEJMra2400000",
        title="Retraction of COVID-19 papers: a meta-research review",
        fetched_content_length=8000,
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
        openalex_is_retracted=False,
    )
    result = classify_source_tier(sig)
    assert result.tier != TierLevel.UNKNOWN, result.reasons
    assert "R0_retracted" not in result.matched_rules


# ─────────────────────────────────────────────────────────────────────
# Part B — commercial medical-tourism page not promoted to authoritative
# ─────────────────────────────────────────────────────────────────────


def test_medical_tourism_marketing_page_not_promoted_to_authoritative() -> None:
    """A clinic sales page with a treatment-packages URL and a 'Book Now' title,
    mislabelled by OpenAlex as a peer-reviewed journal article. Pre-fix the R9
    path landed it at T4 (abstract-eligible); post-fix R8d demotes it to T6."""
    sig = ClassificationSignals(
        url="https://premier-stemcell-clinic.com/treatment-packages/parkinsons",
        title="Stem Cell Treatment Packages for Parkinson's — Book Now",
        fetched_content_length=8000,
        # Worst-case OpenAlex mislabel: says peer-reviewed article in a journal.
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
    )
    result = classify_source_tier(sig)
    assert result.tier == TierLevel.T6, (result.tier, result.matched_rules)
    assert "R8d_commercial_marketing" in result.matched_rules
    assert result.tier not in _AUTHORITATIVE_OR_ABSTRACT_TIERS


def test_medical_tourism_cta_in_url_only() -> None:
    """A free-consultation CTA in the URL alone is enough to demote to T6."""
    sig = ClassificationSignals(
        url="https://cancer-clinic-abroad.example/free-consultation",
        title="Advanced Immunotherapy Abroad",
        fetched_content_length=8000,
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
    )
    result = classify_source_tier(sig)
    assert result.tier == TierLevel.T6, (result.tier, result.matched_rules)
    assert "R8d_commercial_marketing" in result.matched_rules


def test_study_about_medical_tourism_keeps_earned_tier() -> None:
    """False-positive guard: a genuine peer-reviewed study ABOUT medical tourism
    (no sales CTA) on a known journal domain must keep its earned T1 tier — the
    neutral topic 'medical tourism' alone must NOT trip R8d."""
    sig = ClassificationSignals(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2400001",
        title="Medical tourism for stem cell therapy: a prospective cohort study",
        fetched_content_length=8000,
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
    )
    result = classify_source_tier(sig)
    assert "R8d_commercial_marketing" not in result.matched_rules, result.matched_rules
    assert result.tier == TierLevel.T1, (result.tier, result.reasons)
