"""
R-5 Fix A regression tests: tier-classifier denylist expansions from R-3 sweep.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)


def _classify(url: str, title: str = "", **oa):
    sig = ClassificationSignals(
        url=url, title=title, publisher="",
        fetched_content_length=8000,
        openalex_publication_type=oa.get("pub_type", ""),
        openalex_source_type=oa.get("source_type", ""),
        openalex_is_peer_reviewed=oa.get("is_peer_reviewed", False),
        source_type_hint="",
    )
    return classify_source_tier(sig)


# Vendor blog domains
def test_r5_morphik_ai_is_t5() -> None:
    r = _classify(
        url="https://www.morphik.ai/blog/rag-strategies-2025",
        title="RAG in 2025",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value == "T5", f"expected T5, got {r.tier.value}"


def test_r5_glean_vendor_blog_is_t5() -> None:
    r = _classify(
        url="https://www.glean.com/blog/rag-retrieval",
        title="What is RAG in 2025",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value == "T5"


def test_r5_intellectia_is_t5() -> None:
    r = _classify(
        url="https://intellectia.ai/news/stock/novo-nordisk-competition",
        title="Novo Nordisk faces competition",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value == "T5"


def test_r5_medcrypt_vendor_blog_is_t5() -> None:
    r = _classify(
        url="https://www.medcrypt.com/blog/fda-pccp-guidance",
        title="Understanding FDA's PCCP guidance",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value == "T5"


# Legal / consulting
def test_r5_mcdermottplus_is_t6() -> None:
    """mcdermottplus is a healthcare regulatory consulting firm."""
    r = _classify(
        url="https://www.mcdermottplus.com/insights/fda-pccp-guidance",
        title="FDA issues final PCCP guidance",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    # Legal commentary rule fires → T6
    assert r.tier.value == "T6"


# Self-publish platforms (URL path match)
def test_r5_linkedin_pulse_is_t6() -> None:
    r = _classify(
        url="https://www.linkedin.com/pulse/rag-architectural-review-2025-user/",
        title="RAG architectural review",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value == "T6"


def test_r5_yahoo_finance_is_t6() -> None:
    r = _classify(
        url="https://finance.yahoo.com/sectors/healthcare/articles/eli-lilly-vs-novo-nordisk",
        title="Eli Lilly vs Novo Nordisk stock comparison",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value in {"T5", "T6"}, \
        f"vendor/news-wire should not be T1, got {r.tier.value}"


# Legitimate sources must still classify correctly
def test_r5_nejm_still_t1() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2032183",
        title="Effect of Semaglutide on Weight Loss in Adults",
        pub_type="article", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_r5_pubmed_meta_analysis_still_t2() -> None:
    r = _classify(
        url="https://pubmed.ncbi.nlm.nih.gov/40859897/",
        title="Semaglutide for Weight Loss: A Systematic Review and Meta-Analysis",
        pub_type="review", source_type="journal", is_peer_reviewed=True,
    )
    assert r.tier.value == "T2"


def test_r5_fda_still_t3() -> None:
    r = _classify(
        url="https://www.fda.gov/regulatory-information/search-fda-guidance-documents",
        title="FDA Final Guidance PCCP",
    )
    assert r.tier.value == "T3"
