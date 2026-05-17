"""Tests for clinical_source_registry — T1/T2/T3 domain classifier."""

from __future__ import annotations

import pytest

from polaris_graph.clinical_retrieval.clinical_source_registry import (
    classify_url,
    deny_domains,
    filter_allowed,
    is_allowed,
    known_t1_domains,
    known_t2_domains,
    known_t3_domains,
)
from polaris_graph.clinical_retrieval.evidence_pool import SourceTier


# ---------- T1 (regulatory + systematic reviews) ----------

@pytest.mark.parametrize(
    "url",
    [
        "https://www.cochrane.org/CD123456",
        "https://www.cochranelibrary.com/cdsr/doi/10.1002/abc",
        "https://www.fda.gov/drugs/drug-approvals-and-databases/fda-approved-drug-products",
        "https://www.fda.gov/medical-devices/recalls",
        "https://www.fda.gov/safety/medwatch",
        "https://www.fda.gov/vaccines/safety",
        "https://www.ema.europa.eu/en/medicines/human/EPAR/example",
        "https://www.hc-sc.gc.ca/dhp-mps/index-eng.php",
        "https://www.canada.ca/en/health/medications-vaccines/oral-anticoagulants.html",
        "https://www.canada.ca/en/services/health/diseases.html",
        "https://www.who.int/publications/i/item/9789241550000",
        "https://www.who.int/news-room/fact-sheets/detail/diabetes",
        "https://www.nice.org.uk/guidance/ng28",
        "https://pubmed.ncbi.nlm.nih.gov/?term=aspirin&filter=pubt.systematicreview",
        "https://pubmed.ncbi.nlm.nih.gov/?term=aspirin+meta-analysis",
        "https://pubmed.ncbi.nlm.nih.gov/?term=cochrane+review",
    ],
)
def test_t1_urls_classify_as_t1(url: str):
    assert classify_url(url) is SourceTier.T1


# ---------- T2 (peer-reviewed primary research) ----------

@pytest.mark.parametrize(
    "url",
    [
        "https://www.nejm.org/doi/10.1056/NEJMoa1234567",
        "https://www.thelancet.com/journals/lancet/article/PIIS0140-6736",
        "https://jamanetwork.com/journals/jama/fullarticle/123",
        "https://www.bmj.com/content/123/bmj.abc",
        "https://journals.plos.org/plosmedicine/article?id=10.1371/abc",
        "https://bmcmedicine.biomedcentral.com/articles/10.1186/s12916-024",
        "https://link.springer.com/article/10.1007/abc",
        "https://www.sciencedirect.com/science/article/pii/S0140-6736",
        "https://onlinelibrary.wiley.com/doi/10.1002/abc",
        "https://www.nature.com/articles/s41591-024-1234",
        "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC1234567",
        # PubMed without a systematic-review filter falls through to T2
        "https://pubmed.ncbi.nlm.nih.gov/12345678/",
    ],
)
def test_t2_urls_classify_as_t2(url: str):
    assert classify_url(url) is SourceTier.T2


# ---------- T3 (registries + guidelines + agencies) ----------

@pytest.mark.parametrize(
    "url",
    [
        "https://clinicaltrials.gov/study/NCT01234567",
        "https://www.who.int/ictrp/search/en/",
        "https://www.cdc.gov/diabetes/data-research/research/index.html",
        "https://www.nih.gov/health-information/diabetes",
        "https://www.phac-aspc.gc.ca/cd-mc/diabetes-diabete/index-eng.php",
    ],
)
def test_t3_urls_classify_as_t3(url: str):
    assert classify_url(url) is SourceTier.T3


# ---------- Out-of-bounds (denylist + unknown domains) ----------

@pytest.mark.parametrize(
    "url",
    [
        "https://en.wikipedia.org/wiki/Aspirin",
        "https://www.reddit.com/r/Health/comments/abc",
        "https://twitter.com/user/status/12345",
        "https://x.com/user/status/12345",
        "https://www.facebook.com/page/posts/12345",
        "https://medium.com/@author/article-name-abc",
        "https://substack.com/p/clinical-takes",
        "https://www.youtube.com/watch?v=abc",
    ],
)
def test_deny_listed_domains_return_none(url: str):
    assert classify_url(url) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://my-personal-blog.com/post/aspirin-cures-everything",
        "https://www.somerandomnews.com/article/medical-thoughts",
        "http://example.com/medical",
        "https://www.alternativemedicine-cures.org/articles",
    ],
)
def test_unknown_domains_return_none(url: str):
    assert classify_url(url) is None


# ---------- Subdomains ----------

def test_subdomain_match():
    """journals.plos.org should match the plos.org rule."""
    assert classify_url("https://journals.plos.org/plosmedicine/article?id=abc") is SourceTier.T2


def test_exact_domain_match():
    assert classify_url("https://nejm.org/doi/abc") is SourceTier.T2


# ---------- Path filters ----------

def test_fda_root_path_does_not_match():
    """FDA root or non-clinical paths should NOT classify."""
    assert classify_url("https://www.fda.gov/about-fda/contact-fda") is None


def test_canada_ca_non_health_path_does_not_match():
    """canada.ca only matches /health/ paths."""
    assert classify_url("https://www.canada.ca/en/services/taxes/income-tax.html") is None


def test_who_int_general_news_does_not_match_t1():
    """WHO general news pages don't match T1's path filter."""
    assert classify_url("https://www.who.int/news/item/random-news") is None


def test_who_int_ictrp_matches_t3():
    """WHO ICTRP path matches T3 trial-registry rule."""
    assert classify_url("https://www.who.int/ictrp/search/en/") is SourceTier.T3


def test_pubmed_systematic_review_filter_is_t1():
    assert (
        classify_url("https://pubmed.ncbi.nlm.nih.gov/?term=aspirin&filter=pubt.systematicreview")
        is SourceTier.T1
    )


def test_pubmed_no_filter_falls_through_to_t2():
    assert classify_url("https://pubmed.ncbi.nlm.nih.gov/12345/") is SourceTier.T2


# ---------- Malformed / edge inputs ----------

def test_empty_url_returns_none():
    assert classify_url("") is None


def test_garbage_url_returns_none():
    assert classify_url("not-a-real-url") is None


def test_url_with_no_scheme_returns_none():
    """urlparse(www.x.com) yields hostname=None when no scheme; should fail safe."""
    assert classify_url("www.cochrane.org/CD123") is None


def test_https_uppercase_host():
    """Hostname casing should not affect classification."""
    assert classify_url("https://WWW.NEJM.ORG/doi/abc") is SourceTier.T2


# ---------- Convenience helpers ----------

def test_is_allowed_true_for_known_t1():
    assert is_allowed("https://www.cochrane.org/CD123") is True


def test_is_allowed_false_for_unknown():
    assert is_allowed("https://unknownblog.com/post") is False


def test_filter_allowed_keeps_only_known():
    urls = [
        "https://www.nejm.org/doi/abc",
        "https://en.wikipedia.org/wiki/Aspirin",
        "https://clinicaltrials.gov/study/NCT001",
        "https://random-blog.com/post",
    ]
    kept = filter_allowed(urls)
    assert kept == [
        "https://www.nejm.org/doi/abc",
        "https://clinicaltrials.gov/study/NCT001",
    ]


# ---------- Introspection ----------

def test_known_domain_lists_non_empty():
    assert len(known_t1_domains()) > 0
    assert len(known_t2_domains()) > 0
    assert len(known_t3_domains()) > 0


def test_deny_domains_returns_sorted_tuple():
    deny = deny_domains()
    assert "wikipedia.org" in deny
    assert "reddit.com" in deny
    assert deny == tuple(sorted(deny))  # alphabetized for diagnostics


def test_t1_includes_cochrane_and_fda():
    t1 = known_t1_domains()
    assert "cochrane.org" in t1
    assert "fda.gov" in t1


def test_t2_includes_canonical_journals():
    t2 = known_t2_domains()
    for journal in ("nejm.org", "thelancet.com", "bmj.com", "jamanetwork.com"):
        assert journal in t2
