"""BUG-M-12 (Codex pass 12): fix truncated-title T1 hallucinations
via OpenAlex full-title enrichment + expanded narrative markers.

Codex pass 12 named 4 false T1s caused by Serper snippet titles
being truncated mid-title, losing "systematic review and
meta-analysis" / "perspective for primary care providers" suffixes.

Fix approach:
1. live_retriever._openalex_enrich preserves OpenAlex display_name
   (full title) and live_retriever passes it to the classifier as
   the primary title.
2. Expanded _NARRATIVE_FLAVOR_KEYWORDS to catch "perspective for",
   "for clinicians", "primary care providers", "prescribing
   information", etc.

The original idea of requiring a positive primary-study marker was
too strict — bare "Tirzepatide in type 2 diabetes" / "Semaglutide
in Obesity" NEJM/Lancet titles are legitimate primary research
without containing "randomized" / "phase 3" / "cohort" etc.
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
# Full-title captures the SR/MA / perspective suffix
# ─────────────────────────────────────────────────────────────────


def test_full_mdpi_title_with_sr_ma_suffix_is_t2() -> None:
    """When the full OpenAlex title contains 'Systematic Review and
    Meta-Analysis', classifier routes to T2 correctly — the fix is
    upstream (preserve full title), not in the classifier itself."""
    r = _classify(
        url="https://www.mdpi.com/1424-8247/18/5/668",
        title="The Efficacy and Safety of Tirzepatide in Patients with Diabetes and/or Obesity: Systematic Review and Meta-Analysis of Randomized Clinical Trials",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T2", f"Expected T2, got {r.tier.value}"


def test_full_frontiers_title_with_sr_ma_suffix_is_t2() -> None:
    r = _classify(
        url="https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2022.1016639/full",
        title="Efficacy and safety of tirzepatide in patients with type 2 diabetes: A systematic review and meta-analysis",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T2", f"Expected T2, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Expanded narrative markers ("perspective for", "for clinicians")
# ─────────────────────────────────────────────────────────────────


def test_perspective_for_primary_care_title_demotes_to_t4() -> None:
    """Codex pass 12 case 1: full PMC10115620 title includes
    'A Perspective for Primary Care Providers'. Expanded narrative
    markers demote to T4."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="Efficacy and Safety of Tirzepatide in Adults With Type 2 Diabetes: A Perspective for Primary Care Providers",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_for_clinicians_title_demotes_to_t4() -> None:
    """Generic 'for clinicians' narrative marker."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC99887766/",
        title="Tirzepatide dosing: what clinicians need to know",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4"


def test_prescribing_recommendations_demotes_to_t4() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMCABC/",
        title="Tirzepatide Prescribing Recommendations for Adults with Diabetes",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4"


# ─────────────────────────────────────────────────────────────────
# Regressions: primary papers with bare titles on allowlisted hosts
# remain T1 (these are the legitimate primaries M-12 must not break)
# ─────────────────────────────────────────────────────────────────


def test_regression_bare_nejm_title_still_t1() -> None:
    """Bare 'Tirzepatide in type 2 diabetes' on NEJM is a legitimate
    primary trial. Must still be T1."""
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide in type 2 diabetes",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_bare_lancet_title_still_t1() -> None:
    """Bare 'Semaglutide in Obesity' on Lancet is the STEP-1 trial."""
    r = _classify(
        url="https://www.thelancet.com/journals/lancet/article/S0140-6736",
        title="Semaglutide in Obesity",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


# ─────────────────────────────────────────────────────────────────
# Regressions from prior M fixes still hold
# ─────────────────────────────────────────────────────────────────


def test_regression_m11_unknown_domain_still_demoted() -> None:
    r = _classify(
        url="https://unknown-domain.example/paper",
        title="Effect of X on Y: A Randomized Controlled Trial",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4"


def test_regression_m10_kff_still_t4() -> None:
    r = _classify(url="https://www.kff.org/issue-brief/abc")
    assert r.tier.value == "T4"


def test_regression_m7_facebook_still_t6() -> None:
    r = _classify(url="https://www.facebook.com/post/123")
    assert r.tier.value == "T6"


def test_regression_sr_ma_via_title_still_t2() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC333/",
        title="Semaglutide in obesity: a systematic review and meta-analysis",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T2"
