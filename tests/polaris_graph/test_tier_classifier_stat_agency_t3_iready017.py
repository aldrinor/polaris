"""I-ready-017 (#1133): statistical / data agencies must classify as T3.

RERUN-BUG context (drb_72 workforce run):
    The workforce protocol (config/scope_templates/workforce.yaml) requires
    T3 (statistical-agency outputs: StatCan / BLS / OECD / ILO / Eurostat)
    at 35-65% as the PRIMARY quantitative evidence. In the live corpus dump
    bls.gov rows were classified T4 and oecd.org UNKNOWN, driving T3 to 0% ->
    abort_corpus_approval_denied.

Root cause (verified against the live dump):
    * bls.gov congressional-report URL -> R11_openalex_preprint_or_repo (T4)
      because OpenAlex returned publication_type="preprint" /
      source_type="repository".
    * bls.gov MLR article URL -> R9_openalex_narrative_review (T4) because
      OpenAlex said article+journal and the title tripped a narrative-flavor
      marker.
    * oecd.org / ilo.org (.org, on no domain set) -> no_rule_matched (UNKNOWN).

Fix: STATISTICAL_AGENCY_DOMAINS frozenset + R2b_statistical_agency rule placed
adjacent to R2b_gov_agency / R2c / R2d (BEFORE R9/R10/R11, AFTER the denylist
demotions). Always-on correctness fix.

These tests intentionally include the TWO signal-bearing cases from the live
dump (preprint/repository and article+journal-with-narrative-title) so they
prove the new rule fires BEFORE R9 / R11 — a bare-domain-only test would pass
even if the rule were mis-placed at the end of the function.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    TierLevel,
    classify_source_tier,
)


# ── The two signal-bearing cases reproduced verbatim from the live drb_72
# corpus dump (LAW II: the case that failed now passes). These are the ones
# that prove precedence over R9 / R11.

def test_bls_congressional_report_preprint_signal_is_t3_not_r11_t4():
    """Live-dump row 1: OpenAlex preprint/repository signal previously ->
    R11_openalex_preprint_or_repo (T4). Must now be T3 via the stat-agency
    rule, which fires BEFORE R11."""
    sig = ClassificationSignals(
        url=(
            "https://www.bls.gov/bls/congressional-reports/"
            "assessing-the-impact-of-new-technologies-on-the-labor-market.htm"
        ),
        title="Assessing the Impact of New Technologies on the Labor Market",
        fetched_content_length=8000,
        openalex_publication_type="preprint",
        openalex_source_type="repository",
    )
    res = classify_source_tier(sig)
    assert res.tier == TierLevel.T3, res.reasons
    assert "R2b_statistical_agency" in res.matched_rules
    assert "R11_openalex_preprint_or_repo" not in res.matched_rules


def test_bls_mlr_article_narrative_signal_is_t3_not_r9_t4():
    """Live-dump row 2: OpenAlex article+journal + narrative-flavor title
    previously -> R9_openalex_narrative_review (T4). Must now be T3 via the
    stat-agency rule, which fires BEFORE R9."""
    sig = ClassificationSignals(
        url=(
            "https://www.bls.gov/opub/mlr/2025/article/"
            "incorporating-ai-impacts-in-bls-employment-projections.htm"
        ),
        title="Incorporating AI impacts in BLS employment projections",
        fetched_content_length=12000,
        openalex_publication_type="article",
        openalex_source_type="journal",
        openalex_is_peer_reviewed=True,
    )
    res = classify_source_tier(sig)
    assert res.tier == TierLevel.T3, res.reasons
    assert "R2b_statistical_agency" in res.matched_rules
    assert "R9_openalex_narrative_review" not in res.matched_rules


def test_oecd_no_signals_was_unknown_now_t3():
    """Live-dump oecd.org row: previously no_rule_matched (UNKNOWN). Now T3."""
    sig = ClassificationSignals(
        url=(
            "https://www.oecd.org/en/publications/2021/01/"
            "the-impact-of-artificial-intelligence-on-the-labour-market_"
            "a4b9cac2.html"
        ),
        title="The impact of Artificial Intelligence on the labour market - OECD",
        fetched_content_length=15000,
    )
    res = classify_source_tier(sig)
    assert res.tier == TierLevel.T3, res.reasons
    assert "R2b_statistical_agency" in res.matched_rules


# ── Bare-domain coverage for the named protocol agencies + extensions.

def test_named_statistical_agencies_are_t3():
    urls = [
        "https://www.bls.gov/news.release/empsit.nr0.htm",
        "https://www.oecd.org/employment-outlook/",
        "https://www.ilo.org/global/research/global-reports/weso/lang--en/index.htm",
        "https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410028701",
        "https://www.federalreserve.gov/releases/h6/current/",
        "https://fred.stlouisfed.org/series/UNRATE",
        "https://data.worldbank.org/indicator/SL.UEM.TOTL.ZS",
        "https://www.imf.org/en/Publications/WEO",
        "https://www.census.gov/topics/employment.html",
    ]
    for u in urls:
        res = classify_source_tier(
            ClassificationSignals(url=u, fetched_content_length=8000)
        )
        assert res.tier == TierLevel.T3, (u, res.tier, res.reasons)


def test_eurostat_is_t3():
    """Eurostat is hosted under ec.europa.eu, which already parent-matches
    europa.eu in REGULATORY_DOMAINS. Assert tier == T3 only (the matched
    rule may legitimately be R2d_regulatory_domain, not the new rule)."""
    res = classify_source_tier(
        ClassificationSignals(
            url="https://ec.europa.eu/eurostat/web/lfs/data/database",
            fetched_content_length=8000,
        )
    )
    assert res.tier == TierLevel.T3, res.reasons


# ── Regression guards: pre-existing behaviour must be unchanged.

def test_clinical_regulatory_domains_still_t3():
    """fda.gov and ema.europa.eu must remain T3 (unregressed)."""
    for u in [
        "https://www.fda.gov/drugs/drug-approvals-and-databases",
        "https://www.ema.europa.eu/en/medicines/human/EPAR/example",
    ]:
        res = classify_source_tier(
            ClassificationSignals(url=u, fetched_content_length=8000)
        )
        assert res.tier == TierLevel.T3, (u, res.tier, res.reasons)


def test_generic_org_is_not_forced_to_t3():
    """A generic .org with no other signals must NOT be promoted to T3 by the
    new rule — it stays UNKNOWN (honest no-match)."""
    res = classify_source_tier(
        ClassificationSignals(
            url="https://www.example.org/some-page",
            fetched_content_length=8000,
        )
    )
    assert res.tier != TierLevel.T3, res.reasons
    assert "R2b_statistical_agency" not in res.matched_rules


def test_stat_agency_stub_still_t7():
    """A <1000-char stat-agency page must stay T7 (R1 stub fires before the
    stat-agency rule — consistent with REGULATORY_DOMAINS handling)."""
    res = classify_source_tier(
        ClassificationSignals(
            url="https://www.bls.gov/some-tiny-page.htm",
            fetched_content_length=300,
        )
    )
    assert res.tier == TierLevel.T7, res.reasons
