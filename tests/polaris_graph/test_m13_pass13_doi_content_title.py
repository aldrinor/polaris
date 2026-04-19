"""BUG-M-13 (Codex pass 13): DOI-based OpenAlex lookup + content-title
extraction + pharmacytimes blocklist.

Pass 13 found M-12's full-title path wasn't reaching the classifier
for MDPI / Frontiers SR/MA papers. Root causes:
- OpenAlex title-search with the Serper-truncated title didn't find
  the right paper or returned an empty display_name.
- MDPI URLs don't embed a DOI in the path, so DOI lookup can't fire.
- Frontiers URLs DO embed DOI; the DOI lookup path needed to be added.

Plus pharmacytimes.com was missing from NEWS_BLOG_DOMAINS (distinct
from pharmatimes.com which was already there), allowing OpenAlex to
lift it to T2 via SR/MA-adjacent metadata.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.live_retriever import (
    _extract_doi_from_url,
    _extract_title_from_content,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)


def _classify(url, title="Generic Title", **openalex):
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
# DOI extraction from URLs
# ─────────────────────────────────────────────────────────────────


def test_frontiers_url_yields_doi() -> None:
    """Frontiers URL embeds DOI; DOI lookup fires."""
    url = "https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2022.1016639/full"
    assert _extract_doi_from_url(url) == "10.3389/fphar.2022.1016639"


def test_nejm_url_yields_doi() -> None:
    url = "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519"
    assert _extract_doi_from_url(url) == "10.1056/NEJMoa2107519"


def test_doi_org_url_yields_doi() -> None:
    url = "https://doi.org/10.1093/haschl/qxaf030"
    assert _extract_doi_from_url(url) == "10.1093/haschl/qxaf030"


def test_mdpi_url_yields_no_doi() -> None:
    """MDPI URLs don't embed DOI in path; falls back to content/title."""
    url = "https://www.mdpi.com/1424-8247/18/5/668"
    assert _extract_doi_from_url(url) == ""


def test_pmc_url_yields_no_doi() -> None:
    """PMC URLs use PMC IDs not DOIs in path."""
    url = "https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/"
    assert _extract_doi_from_url(url) == ""


# ─────────────────────────────────────────────────────────────────
# Content-based title extraction
# ─────────────────────────────────────────────────────────────────


def test_jina_title_markdown() -> None:
    content = (
        "Title: The Efficacy and Safety of Tirzepatide in Patients "
        "with Diabetes and/or Obesity: Systematic Review and "
        "Meta-Analysis of Randomized Clinical Trials\n"
        "URL Source: https://www.mdpi.com/abc\n"
        "Published: 2025\n"
    )
    t = _extract_title_from_content(content)
    assert "systematic review" in t.lower()
    assert "meta-analysis" in t.lower()


def test_html_title_tag() -> None:
    content = (
        "<html><head>"
        "<title>Efficacy and safety of tirzepatide in patients with type 2 "
        "diabetes: A systematic review and meta-analysis | Frontiers</title>"
        "</head><body>..."
    )
    t = _extract_title_from_content(content)
    assert "systematic review" in t.lower()
    assert "meta-analysis" in t.lower()
    # Publisher suffix stripped
    assert "frontiers" not in t.lower()


def test_markdown_h1() -> None:
    content = (
        "# Efficacy and Safety of Tirzepatide: A Systematic Review\n"
        "\n"
        "Abstract: This systematic review..."
    )
    t = _extract_title_from_content(content)
    assert "systematic review" in t.lower()


def test_empty_content_returns_empty() -> None:
    assert _extract_title_from_content("") == ""
    assert _extract_title_from_content(None) == ""


def test_too_short_title_rejected() -> None:
    content = "<title>Home</title>"
    assert _extract_title_from_content(content) == ""


# ─────────────────────────────────────────────────────────────────
# pharmacytimes.com → T6 (previously missing from NEWS_BLOG_DOMAINS)
# ─────────────────────────────────────────────────────────────────


def test_pharmacytimes_is_t6_not_t2() -> None:
    """Codex pass 13: pharmacytimes.com was lifted to T2 via OpenAlex
    SR/MA metadata. Now in NEWS_BLOG_DOMAINS → T6."""
    r = _classify(
        url="https://www.pharmacytimes.com/view/tirzepatide-shows-significant-improvements-in-glycemic-control",
        title="Tirzepatide Shows Significant Improvements in Glycemic Control",
    )
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_pharmatimes_distinct_from_pharmacytimes() -> None:
    """Regression: pharmatimes.com (existing) and pharmacytimes.com
    (M-13 addition) are DIFFERENT domains but both should be T6."""
    r1 = _classify(url="https://www.pharmatimes.com/article/abc")
    assert r1.tier.value == "T6"
    r2 = _classify(url="https://www.pharmacytimes.com/view/abc")
    assert r2.tier.value == "T6"
