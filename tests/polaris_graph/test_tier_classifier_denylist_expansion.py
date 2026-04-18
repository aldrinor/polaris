"""
Regression tests for Fix-2 denylist expansion (2026-04-18 live-run FPs).

Live honest-rebuild cycle exposed:
  - novonordiskmedical.com PDF got tier_classifier T1 via R9 OpenAlex
    primary. Expected T5 (industry).
  - prnewswire.com press release got tier_classifier T4 via R9 OpenAlex
    review. Expected T6 (news/wire).

These tests pin the fixed behavior so a future refactor of the
INDUSTRY_MARKETING_DOMAINS / NEWS_BLOG_DOMAINS sets can't silently
re-introduce the false positive.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)


def _classify(url: str, title: str, **openalex):
    sig = ClassificationSignals(
        url=url,
        title=title,
        publisher="",
        fetched_content_length=8000,
        openalex_publication_type=openalex.get("pub_type", ""),
        openalex_source_type=openalex.get("source_type", ""),
        openalex_is_peer_reviewed=openalex.get("is_peer_reviewed", False),
        source_type_hint="",
    )
    return classify_source_tier(sig)


def test_fix2_novonordiskmedical_is_t5_even_with_openalex_primary() -> None:
    """novonordiskmedical.com must not be lifted to T1 by OpenAlex."""
    r = _classify(
        url="https://www.novonordiskmedical.com/some-trial-data.pdf",
        title="STEP Program Trial Data",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_fix2_sciencehub_novonordisk_is_t5() -> None:
    r = _classify(
        url="https://sciencehub.novonordisk.com/obesity/step-up-full.pdf",
        title="Efficacy and Safety of Semaglutide 7.2 mg in Obesity",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T5", f"Expected T5, got {r.tier.value}"


def test_fix2_lillymedical_is_t5() -> None:
    r = _classify(
        url="https://www.lillymedical.com/resource/tirzepatide-program",
        title="Tirzepatide Clinical Trial Summary",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T5"


def test_fix2_prnewswire_is_t6_even_with_openalex_review() -> None:
    """prnewswire.com must not be lifted to T4 by OpenAlex."""
    r = _classify(
        url="https://www.prnewswire.com/news-releases/semaglutide-2-4-mg-injection.html",
        title="Semaglutide 2.4 mg injection demonstrated significant weight loss",
        pub_type="review",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_fix2_businesswire_and_globenewswire_are_t6() -> None:
    for host in (
        "https://www.businesswire.com/news/home/xxxxx/en/",
        "https://www.globenewswire.com/news-release/2026/xxx.html",
        "https://www.prweb.com/releases/2026/xxxxx.htm",
    ):
        r = _classify(url=host, title="Clinical Trial Press Release")
        assert r.tier.value == "T6", f"Host {host!r} expected T6, got {r.tier.value}"


def test_fix2_endocrinologyadvisor_is_t6_not_t4() -> None:
    """endocrinologyadvisor.com was tiered T4 by OpenAlex via R9; it's
    actually a news/commentary site, not a peer-reviewed review venue."""
    r = _classify(
        url="https://www.endocrinologyadvisor.com/news/step-up-trial-higher-dose.html",
        title="STEP UP Trial: Significant Weight Loss Observed With Higher Dose",
        pub_type="review",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T6", f"Expected T6, got {r.tier.value}"


def test_fix2_legitimate_pubmed_article_still_t1() -> None:
    """Don't break pubmed.ncbi.nlm.nih.gov T1 classification."""
    r = _classify(
        url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        title="Effect of Semaglutide on Weight Loss: A Randomized Controlled Trial",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_fix2_legitimate_nejm_article_still_t1() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2032183",
        title="Once-Weekly Semaglutide in Adults with Overweight or Obesity",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_fix2_fda_accessdata_still_t3() -> None:
    """Don't break the FDA regulatory classification."""
    r = _classify(
        url="https://www.accessdata.fda.gov/drugsatfda_docs/label/2021/215256s000lbl.pdf",
        title="Wegovy Prescribing Information",
    )
    assert r.tier.value == "T3"
