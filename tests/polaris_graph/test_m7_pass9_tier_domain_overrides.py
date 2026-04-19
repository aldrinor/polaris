"""BUG-M-7 (Codex pass 9 content-audit blocker): hard domain
overrides so social platforms, law-firm blogs, market-research /
consulting sites, and trade-news publications cannot be classified
as T1 regardless of OpenAlex metadata.

Codex pass 9 opened the 4 released reports from the 8-query sweep
and found that many shipped bibliographies listed Facebook, Reddit,
AOL, Knobbe (law firm), Statista, DelveInsight, MatrixBCG,
PortersFiveForce, PharmaVoice, and C&EN as T1. The user-facing
limitations section then underreported reliance on low-provenance
sources — a release-blocking honesty defect.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)


def _classify(url: str, title: str = "Some Title", **openalex):
    """Worst-case OpenAlex metadata: it says peer-reviewed article
    in a journal. The domain override must still downgrade."""
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
# Social platforms + general-interest portals → T6
# ─────────────────────────────────────────────────────────────────


def test_facebook_is_t6_even_with_openalex_primary() -> None:
    """Codex pass 9 found facebook.com classified as T1 in the Novo
    released bibliography. Must be T6."""
    r = _classify(url="https://www.facebook.com/novonordisk/posts/12345")
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_reddit_is_t6_even_with_openalex_primary() -> None:
    """Codex pass 9 found reddit.com in the RAG report bibliography
    as T1. Must be T6."""
    r = _classify(url="https://www.reddit.com/r/MachineLearning/comments/abc/rag_best_practices/")
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_aol_is_t6_even_with_openalex_primary() -> None:
    """Codex pass 9 found aol.com classified as T1 in Novo."""
    r = _classify(url="https://www.aol.com/news/novo-nordisk-earnings-123.html")
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_twitter_and_x_are_t6() -> None:
    for url in ("https://twitter.com/user/status/123",
                "https://x.com/user/status/123"):
        r = _classify(url=url)
        assert r.tier.value == "T6", f"{url}: expected T6, got {r.tier.value}"


def test_yahoo_msn_huffpost_are_t6() -> None:
    for url in ("https://www.yahoo.com/finance/news/lilly-q3.html",
                "https://www.msn.com/en-us/health/article",
                "https://www.huffpost.com/entry/obesity-drugs"):
        r = _classify(url=url)
        assert r.tier.value == "T6", f"{url}: expected T6, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Law-firm blogs → T6
# ─────────────────────────────────────────────────────────────────


def test_knobbe_law_firm_is_t6_even_with_openalex_primary() -> None:
    """Codex pass 9 found knobbe.com classified as T1 in the FDA
    released bibliography. Law-firm IP/regulatory blogs are T6."""
    r = _classify(
        url="https://www.knobbe.com/blog/fda-ai-device-pccp-guidance",
        title="FDA Finalizes AI-PCCP Guidance",
    )
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_additional_law_firm_blogs_are_t6() -> None:
    """Spot check of other common IP / pharma law firms added in
    the pass-9 expansion."""
    for domain in ("finnegan.com", "foley.com", "jonesday.com",
                   "goodwinlaw.com", "kirkland.com", "cooley.com"):
        r = _classify(url=f"https://www.{domain}/blog/post-123")
        assert r.tier.value == "T6", f"{domain}: expected T6, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Market research / consulting → T5
# ─────────────────────────────────────────────────────────────────


def test_delveinsight_is_t5_even_with_openalex_primary() -> None:
    """Codex pass 9 found delveinsight.com classified as T1 in the
    Lilly released bibliography. Market-research firms are T5."""
    r = _classify(
        url="https://www.delveinsight.com/report/obesity-market-forecast-2030",
        title="Obesity Drug Market Forecast 2030",
    )
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_statista_is_t5() -> None:
    """Statista data summaries are not primary research."""
    r = _classify(url="https://www.statista.com/statistics/obesity-drug-sales")
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_matrixbcg_is_t5() -> None:
    """Codex pass 9 found matrixbcg.com classified as T1."""
    r = _classify(url="https://matrixbcg.com/analysis/novo-portfolio")
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_portersfiveforce_is_t5() -> None:
    """Codex pass 9 found portersfiveforce.com classified as T1."""
    r = _classify(url="https://portersfiveforce.com/novo-nordisk-analysis")
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_pharmavoice_is_t5() -> None:
    """PharmaVoice trade publication. Codex pass 9 found it T1."""
    r = _classify(url="https://www.pharmavoice.com/news/lilly-obesity-pipeline")
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_mckinsey_bcg_bain_consulting_are_t5() -> None:
    for domain in ("mckinsey.com", "bcg.com", "bain.com", "deloitte.com"):
        r = _classify(url=f"https://www.{domain}/insights/pharma-trends-2026")
        assert r.tier.value == "T5", f"{domain}: expected T5, got {r.tier.value}"


def test_gartner_forrester_idc_are_t5() -> None:
    """Tech market research."""
    for domain in ("gartner.com", "forrester.com", "idc.com"):
        r = _classify(url=f"https://www.{domain}/research/report-123")
        assert r.tier.value == "T5", f"{domain}: expected T5, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Trade news → T6 (via NEWS_BLOG_DOMAINS)
# ─────────────────────────────────────────────────────────────────


def test_cen_acs_is_t6_not_t1_even_with_openalex_review() -> None:
    """Codex pass 9 found C&EN (cen.acs.org) classified as T1 in
    the Lilly report. C&EN is ACS trade press, not peer-reviewed."""
    r = _classify(
        url="https://cen.acs.org/pharmaceuticals/drug-discovery/Lilly-Zepbound-manufacturing/100/i42",
        title="Lilly Zepbound manufacturing expansion",
        pub_type="review",
    )
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Regression: legitimate T1 sources are still T1
# ─────────────────────────────────────────────────────────────────


def test_regression_pmc_article_is_still_t1() -> None:
    """Guard against over-aggressive blocklist: a real PMC paper
    with OpenAlex primary-study metadata must still be T1."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="Tirzepatide efficacy in type 2 diabetes: SURPASS-4 trial",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1", f"Expected T1, got {r.tier.value}"


def test_regression_nejm_article_is_still_t1() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide Versus Semaglutide for T2DM",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1", f"Expected T1, got {r.tier.value}"


def test_regression_arxiv_preprint_unaffected() -> None:
    """arxiv.org preprint should still route to T4 / T5 via the
    preprint rule, not incorrectly picked up by new blocklists."""
    r = _classify(
        url="https://arxiv.org/abs/2403.12345",
        title="FAIR-RAG: Factual Alignment in Retrieval-Augmented Generation",
    )
    # arxiv is T4 via PREPRINT_DOMAINS rule
    assert r.tier.value in ("T4", "T5"), (
        f"arxiv preprint should be T4/T5, got {r.tier.value}"
    )
