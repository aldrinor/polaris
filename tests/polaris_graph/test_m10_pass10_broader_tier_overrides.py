"""BUG-M-10 (Codex pass 10 content-audit blocker): broader tier
misclassification. Pass-9 fix (M-7) covered social platforms,
law-firm blogs, market-research firms, trade news. Pass-10 Codex
found 13 additional T1 hallucinations from:

- Clinical reference products (UpToDate, etc.)
- Policy think-tanks (KFF, Commonwealth Fund, AccessibleMeds)
- Government agencies (CMS.gov, IHS.gov)
- Business/general news (Fast Company)
- Web guides (Chitika)
- Guideline/explainer PMC content ("2025 Guidelines for DOACs",
  "Predetermined Change Control Plans: Guiding Principles")

These survive because R9_openalex_primary_study trusts
OpenAlex article+journal metadata regardless of domain or title
semantics. This test file pins the fix.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)


def _classify(url: str, title: str = "Generic Title", **openalex):
    """Worst-case OpenAlex metadata: peer-reviewed article in journal.
    Domain + title overrides must still win."""
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
# Clinical reference products → T4
# ─────────────────────────────────────────────────────────────────


def test_uptodate_is_t4_not_t1() -> None:
    """Codex pass 10 found uptodate.com x2 as T1 in the afib report.
    UpToDate is a clinical decision-support reference, not primary."""
    r = _classify(
        url="https://www.uptodate.com/contents/use-of-oral-anticoagulants-in-atrial-fibrillation",
        title="Use of oral anticoagulants in atrial fibrillation",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_dynamed_clinicalkey_bmj_bestpractice_are_t4() -> None:
    for domain in ("dynamed.com", "clinicalkey.com", "bestpractice.bmj.com"):
        r = _classify(url=f"https://{domain}/topics/af-management")
        assert r.tier.value == "T4", f"{domain}: expected T4, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Policy think-tanks → T4
# ─────────────────────────────────────────────────────────────────


def test_kff_is_t4_not_t1() -> None:
    """Codex pass 10: kff.org was T1 in the Medicare drug price report."""
    r = _classify(
        url="https://www.kff.org/health-costs/issue-brief/medicare-drug-price-negotiation/",
        title="Medicare Drug Price Negotiation Key Facts",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_commonwealth_fund_is_t4() -> None:
    """Codex pass 10: commonwealthfund.org was T1 in Medicare report."""
    r = _classify(url="https://www.commonwealthfund.org/publications/explainer/medicare-drug-prices")
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_accessiblemeds_is_t4_not_t1() -> None:
    """Codex pass 10: accessiblemeds.org industry/advocacy, was T1."""
    r = _classify(url="https://accessiblemeds.org/resources/report/medicare-drug-pricing")
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_brookings_rand_heritage_are_t4() -> None:
    """Major policy think-tanks."""
    for domain in ("brookings.edu", "rand.org", "heritage.org"):
        r = _classify(url=f"https://www.{domain}/research/health-policy-2026")
        assert r.tier.value == "T4", f"{domain}: expected T4, got {r.tier.value}"


def test_phrma_trade_assoc_is_t4() -> None:
    """Trade-association newsroom is advocacy, not research."""
    r = _classify(url="https://phrma.org/resources/medicare-negotiation-impact")
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Non-regulatory government agencies → T3
# ─────────────────────────────────────────────────────────────────


def test_cms_gov_is_t3_not_t1() -> None:
    """Codex pass 10: cms.gov was T1, should be T3 at most."""
    r = _classify(url="https://www.cms.gov/medicare/prescription-drug-coverage/drug-price-negotiation")
    assert r.tier.value == "T3", f"Expected T3, got {r.tier.value}"


def test_ihs_gov_is_t3_not_t1() -> None:
    """Codex pass 10: ihs.gov PDF was T1 in afib report."""
    r = _classify(
        url="https://www.ihs.gov/anticoagulation/doac-formulary-brief.pdf",
        title="DOAC Formulary Brief",
    )
    assert r.tier.value == "T3", f"Expected T3, got {r.tier.value}"


def test_hhs_va_are_t3() -> None:
    for domain in ("hhs.gov", "va.gov", "samhsa.gov", "hrsa.gov"):
        r = _classify(url=f"https://www.{domain}/report/health-2026")
        assert r.tier.value == "T3", f"{domain}: expected T3, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Business/general news → T6
# ─────────────────────────────────────────────────────────────────


def test_fastcompany_is_t6_not_t1() -> None:
    """Codex pass 10: fastcompany.com was T1 in the Novo DD report."""
    r = _classify(url="https://www.fastcompany.com/90123456/novo-nordisk-weight-loss")
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_forbes_businessinsider_fortune_are_t6() -> None:
    for domain in ("forbes.com", "businessinsider.com", "fortune.com"):
        r = _classify(url=f"https://www.{domain}/article/pharma-trends-2026")
        assert r.tier.value == "T6", f"{domain}: expected T6, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Web guides / SEO → T6
# ─────────────────────────────────────────────────────────────────


def test_chitika_is_t6_not_t1() -> None:
    """Codex pass 10: chitika.com was T1 in the RAG report."""
    r = _classify(url="https://www.chitika.com/blog/rag-architectures-2024")
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_pcmag_techradar_are_t6() -> None:
    for domain in ("pcmag.com", "techradar.com", "cnet.com"):
        r = _classify(url=f"https://www.{domain}/reviews/best-rag-tools-2026")
        assert r.tier.value == "T6", f"{domain}: expected T6, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Title-based demotion (guideline/explainer on legit journal host)
# ─────────────────────────────────────────────────────────────────


def test_pmc_guideline_title_demotes_to_t4() -> None:
    """Codex pass 10: PMC-hosted paper titled '2025 Guidelines for
    direct oral anticoagulants' was T1. Guideline content is T4
    regardless of journal host."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12345678/",
        title="2025 Guidelines for direct oral anticoagulants in atrial fibrillation",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_pmc_guiding_principles_title_demotes_to_t4() -> None:
    """Codex pass 10: PMC-hosted 'Predetermined Change Control Plans:
    Guiding Principles' was T1. Guiding-principles = policy analysis."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC11223344/",
        title="Predetermined Change Control Plans: Guiding Principles for AI-enabled Devices",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_pmc_explainer_title_demotes_to_t4() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC99887766/",
        title="An Explainer on Predetermined Change Control Plans",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_policy_brief_title_demotes() -> None:
    r = _classify(
        url="https://academic.oup.com/health-affairs/article/2025/policy-brief-negotiation",
        title="Medicare Drug Price Negotiation: A Policy Brief",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_key_facts_title_demotes() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC77665544/",
        title="Medicare Drug Price Negotiation: Key Facts 2025",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Regression: legitimate primary research still T1
# ─────────────────────────────────────────────────────────────────


def test_regression_pmc_primary_rct_still_t1() -> None:
    """Guard: real RCT papers in PMC without guideline/explainer
    markers in title must still classify as T1."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="Tirzepatide efficacy in type 2 diabetes: SURPASS-4 randomized trial",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1", f"Expected T1, got {r.tier.value}"


def test_regression_nejm_primary_still_t1() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide Versus Semaglutide for T2DM: Double-Blind Randomized Trial",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1", f"Expected T1, got {r.tier.value}"


def test_regression_pmc_systematic_review_still_t2() -> None:
    """Systematic reviews go to T2 via title detection; fix should
    not break that."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12345/",
        title="Semaglutide in obesity: a systematic review and meta-analysis",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T2", f"Expected T2, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Previously-fixed M-7 domains must still be correctly demoted
# ─────────────────────────────────────────────────────────────────


def test_regression_m7_facebook_still_t6() -> None:
    r = _classify(url="https://www.facebook.com/novo/posts/123")
    assert r.tier.value == "T6"


def test_regression_m7_delveinsight_still_t5() -> None:
    r = _classify(url="https://www.delveinsight.com/report/obesity-2030")
    assert r.tier.value == "T5"
