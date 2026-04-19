"""BUG-M-11 (Codex pass 11): R9 OpenAlex primary-study rule now
requires the domain to be on a peer-reviewed-journal allowlist
(PEER_REVIEWED_JOURNAL_DOMAINS or NIH_LITERATURE_HOSTS) before
granting T1. Otherwise demoted to T4.

Previously R9 granted T1 solely on OpenAlex article+journal
metadata, which let trade-association whitepapers, industry
insight pages, web explainers, and trade news pages through.
Codex pass 11 named 7 such hallucinations post-M-10.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)


def _classify(url: str, title: str = "Generic Title", **openalex):
    sig = ClassificationSignals(
        url=url,
        title=title,
        publisher="",
        fetched_content_length=8000,
        openalex_publication_type=openalex.get("pub_type", "article"),
        openalex_source_type=openalex.get("source_type", "journal"),
        openalex_is_peer_reviewed=openalex.get("is_peer_reviewed", True),
        source_type_hint="",
    )
    return classify_source_tier(sig)


# ─────────────────────────────────────────────────────────────────
# Pass-11 specific hallucinations — must all demote from T1
# ─────────────────────────────────────────────────────────────────


def test_vizientinc_insight_demoted_to_t5() -> None:
    """Codex pass 11: vizientinc.com 'Early impacts of IRA' was T1.
    vizientinc is in MARKET_RESEARCH_DOMAINS → T5."""
    r = _classify(
        url="https://www.vizientinc.com/insights/early-impacts-medicare-drug-pricing",
        title="Early impacts of the IRA's Medicare Drug Price Negotiation Program",
    )
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_seniorcarepharmacies_whitepaper_demoted_to_t4() -> None:
    """Codex pass 11: SCPC IRA Impact Whitepaper was T1.
    seniorcarepharmacies.org is in POLICY_THINK_TANK_DOMAINS → T4."""
    r = _classify(
        url="https://www.seniorcarepharmacies.org/SCPC-IRA-Impact-Whitepaper-ATI-final.pdf",
        title="SCPC IRA Impact Whitepaper",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_powderbulksolids_trade_news_demoted_to_t6() -> None:
    """Codex pass 11: powderbulksolids.com 'Lilly increases investment'
    was T1. Now in WEB_GUIDE_DOMAINS → T6."""
    r = _classify(
        url="https://www.powderbulksolids.com/material-handling/lilly-increases-investment",
        title="Lilly increases investment in manufacturing",
    )
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_emergentmind_web_explainer_demoted_to_t6() -> None:
    """Codex pass 11: emergentmind.com topic page was T1.
    Now in WEB_GUIDE_DOMAINS → T6."""
    r = _classify(
        url="https://www.emergentmind.com/topics/long-context-optimization",
        title="Long-Context Optimization in Transformers",
    )
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_checklist_title_demoted_to_t4() -> None:
    """Codex pass 11: 'Use of real-world evidence...: A checklist'
    was T1. New title marker 'checklist' → T4."""
    r = _classify(
        url="https://doi.org/10.1093/haschl/qxaf030",
        title="Use of real-world evidence in Medicare drug coverage: A checklist",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_whitepaper_title_demoted_to_t4() -> None:
    """New title marker 'whitepaper' demotes from T1."""
    r = _classify(
        url="https://academic.oup.com/policy/article/42/2025/whitepaper-impact",
        title="Whitepaper: Impact of Drug Price Negotiation",
        pub_type="article",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_early_impacts_title_demoted_to_t4() -> None:
    """New title marker 'early impacts' demotes from T1."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC98765432/",
        title="Early Impacts of Policy X on Market Dynamics",
        pub_type="article",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_industry_insights_title_demoted_to_t4() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMCABC/",
        title="Industry Insights on Drug Pricing Reform",
        pub_type="article",
    )
    assert r.tier.value == "T4"


# ─────────────────────────────────────────────────────────────────
# The core M-11 tightening: unknown-host article → T4 (not T1)
# ─────────────────────────────────────────────────────────────────


def test_unknown_domain_with_openalex_primary_demotes_to_t4() -> None:
    """Core M-11: if OpenAlex says peer-reviewed article+journal but
    the domain is NOT on the known-journal allowlist, route to T4
    narrative instead of T1 primary."""
    r = _classify(
        url="https://some-random-unknown-site.example/paper-2025",
        title="Effect of Drug X on Condition Y: A Study",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T4", (
        f"Unknown host with OpenAlex primary metadata should demote "
        f"to T4. Got {r.tier.value}"
    )


def test_unknown_domain_narrative_review_still_t4_explicit() -> None:
    """Guard: narrative review on an unknown host — still T4 via the
    narrative-flavor title path (not regressed by M-11)."""
    r = _classify(
        url="https://some-unknown.example/",
        title="A review of recent advances in diabetes care",
        pub_type="article",
    )
    assert r.tier.value == "T4"


# ─────────────────────────────────────────────────────────────────
# Regressions: known journal hosts still T1 with primary titles
# ─────────────────────────────────────────────────────────────────


def test_regression_pmc_primary_still_t1() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="SURPASS-4 randomized trial of tirzepatide",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_nejm_primary_still_t1() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide in type 2 diabetes",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_lancet_primary_still_t1() -> None:
    r = _classify(
        url="https://www.thelancet.com/journals/lancet/article/S0140-6736(24)00123-4",
        title="Semaglutide in Obesity",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_jamanetwork_primary_still_t1() -> None:
    r = _classify(
        url="https://jamanetwork.com/journals/jama/fullarticle/2812936",
        title="Continued tirzepatide treatment",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_pubmed_primary_still_t1() -> None:
    """PubMed is in NIH_LITERATURE_HOSTS."""
    r = _classify(
        url="https://pubmed.ncbi.nlm.nih.gov/40926359/",
        title="Phase 3 trial results",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T1"


def test_regression_frontiers_primary_still_t1_when_title_is_primary() -> None:
    """A genuine primary study on Frontiers should still be T1 when
    the title signals primary research (not a meta-analysis or
    narrative review)."""
    r = _classify(
        url="https://www.frontiersin.org/journals/medicine/articles/10.3389/fmed.2024.1234567",
        title="Randomized controlled trial of semaglutide in T2DM",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T1"


# ─────────────────────────────────────────────────────────────────
# Regressions for earlier M-7/M-10
# ─────────────────────────────────────────────────────────────────


def test_regression_m10_uptodate_still_t4() -> None:
    r = _classify(url="https://www.uptodate.com/contents/af-oac")
    assert r.tier.value == "T4"


def test_regression_m10_cms_still_t3() -> None:
    r = _classify(url="https://www.cms.gov/medicare/drug-pricing")
    assert r.tier.value == "T3"


def test_regression_m7_facebook_still_t6() -> None:
    r = _classify(url="https://www.facebook.com/novo/posts/123")
    assert r.tier.value == "T6"
