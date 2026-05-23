"""I-bug-771 (#812) — tier-classifier invariants.

The dominant #763-benchmark abort was `abort_corpus_inadequate`: the content-
based classifier mis-tiered authoritative cardiology sources (ahajournals->T7
stub, escardio guidelines->T4, jacc.org->T4) while over-crediting low-quality OA
(mdpi->T1). Codex DECIDED C+D and RECONCILED the MDPI conflict to option B
(discriminator): MDPI PRIMARY loses T1, but a genuine MDPI systematic review /
meta-analysis still routes to T2 (preserving the deliberate pass-12 distinction).

These assert Codex's required invariants. Each is claim-by-claim against the
exact domain/path the afib run actually retrieved.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    _is_low_quality_oa,
    classify_source_tier,
)


def _classify(url: str, title: str = "Generic study of X in Y", content_length: int = 8000, **openalex):
    sig = ClassificationSignals(
        url=url,
        title=title,
        publisher="",
        fetched_content_length=content_length,
        openalex_publication_type=openalex.get("pub_type", "article"),
        openalex_source_type=openalex.get("source_type", "journal"),
        openalex_is_peer_reviewed=openalex.get("is_peer_reviewed", True),
        source_type_hint="",
    )
    return classify_source_tier(sig)


# ── JACC: flagship cardiology journal, was demoted to T4 (not in allowlist) ──

def test_jacc_org_primary_is_t1() -> None:
    r = _classify(
        url="https://www.jacc.org/doi/10.1016/j.jacasi.2023.08.007",
        title="Anticoagulation outcomes in atrial fibrillation in Asia",
    )
    assert r.tier.value == "T1", f"JACC primary should be T1, got {r.tier.value}"


def test_jacc_org_systematic_review_is_t2() -> None:
    r = _classify(
        url="https://www.jacc.org/doi/10.1016/j.jacc.2024.01.001",
        title="Direct oral anticoagulants in AF: a systematic review and meta-analysis",
    )
    assert r.tier.value == "T2", f"JACC SR/MA should be T2, got {r.tier.value}"


# ── ESC / guideline-authority bodies → T2 (was T4 via unverified-host demote) ──

def test_escardio_guideline_is_t2() -> None:
    r = _classify(
        url="https://www.escardio.org/guidelines/scientific-documents/recommendations-af",
        title="2024 ESC Guidelines for the management of atrial fibrillation",
    )
    assert r.tier.value == "T2", f"ESC guideline should be T2, got {r.tier.value}"
    assert r.matched_rules[-1] == "R8c_guideline_authority"


def test_ahajournals_guideline_path_is_t2() -> None:
    r = _classify(
        url="https://www.ahajournals.org/doi/guidelines/10.1161/CIR.0000000000001193",
        title="2023 ACC/AHA Guideline for the Management of Atrial Fibrillation",
    )
    assert r.tier.value == "T2", f"AHA guideline-path should be T2, got {r.tier.value}"


def test_escardio_guideline_content_stub_stays_t7() -> None:
    """Stub guardrail: a 297-char fetch on a guideline body is NOT laundered to
    T2 — Rule 1 returns T7 first (Codex: never launder content-starved fetches)."""
    r = _classify(
        url="https://www.escardio.org/guidelines/recommendations-af",
        title="AF guidelines",
        content_length=297,
    )
    assert r.tier.value == "T7", f"Guideline stub should be T7, got {r.tier.value}"


# ── AHA journal: research article T1 when usable; 297-char stub T7 ──

def test_ahajournals_research_article_is_t1() -> None:
    r = _classify(
        url="https://www.ahajournals.org/doi/10.1161/CIRCOUTCOMES.124.011890",
        title="Outcomes after anticoagulation in atrial fibrillation: a cohort study",
    )
    assert r.tier.value == "T1", f"AHA research article should be T1, got {r.tier.value}"


def test_ahajournals_stub_stays_t7() -> None:
    r = _classify(
        url="https://www.ahajournals.org/doi/10.1161/JAHA.120.017559",
        title="AF outcomes",
        content_length=297,
    )
    assert r.tier.value == "T7", f"AHA 297-char stub should be T7, got {r.tier.value}"


# ── MDPI / low-quality OA: primary loses T1 (T4), but genuine SR/MA keeps T2 ──

def test_mdpi_primary_is_demoted_to_t4() -> None:
    """The demonstrated afib over-credit: an MDPI primary article got T1."""
    r = _classify(
        url="https://www.mdpi.com/2077-0383/14/22/8079",
        title="Anticoagulation strategies in atrial fibrillation",
    )
    assert r.tier.value == "T4", f"MDPI primary should be T4 ceiling, got {r.tier.value}"
    assert r.matched_rules[-1] == "R9_low_quality_oa_primary_demoted"


def test_mdpi_doi_prefix_primary_is_demoted_to_t4() -> None:
    """MDPI by URL-embedded DOI prefix (10.3390) also loses T1 primary credit."""
    r = _classify(
        url="https://doi.org/10.3390/jcm14228079",
        title="Anticoagulation strategies in atrial fibrillation",
    )
    assert r.tier.value == "T4", f"MDPI DOI primary should be T4, got {r.tier.value}"


def test_mdpi_systematic_review_stays_t2() -> None:
    """Codex reconcile B: a genuine full-title MDPI SR/MA is still secondary
    evidence (T2). The discriminator only denies the PRIMARY bucket."""
    r = _classify(
        url="https://www.mdpi.com/1424-8247/18/5/668",
        title="The Efficacy and Safety of Tirzepatide: Systematic Review and Meta-Analysis of Randomized Clinical Trials",
    )
    assert r.tier.value == "T2", f"MDPI SR/MA should stay T2, got {r.tier.value}"


# ── Society tool / dosing PDFs → T3, never T1/T2 (even with OpenAlex metadata) ──

def test_acc_org_dosing_tool_pdf_is_t3() -> None:
    r = _classify(
        url="https://www.acc.org/-/media/Non-Clinical/Tools-and-Practice-Support/DOAC-Dosing.pdf",
        title="DOAC Dosing in Atrial Fibrillation",
    )
    assert r.tier.value == "T3", f"ACC dosing tool PDF should be T3, got {r.tier.value}"
    assert r.matched_rules[-1] == "R8c_society_tool_demoted"


def test_jacc_tools_path_is_t3() -> None:
    r = _classify(
        url="https://www.jacc.org/tools/risk-calculator",
        title="AF Stroke Risk Calculator",
    )
    assert r.tier.value == "T3", f"JACC tools path should be T3, got {r.tier.value}"


# ── Precision guards: the fix must NOT start over-crediting low-quality hosts ──

def test_unknown_openalex_host_still_t4() -> None:
    """M-11 guard intact: OpenAlex article on an unknown host stays T4."""
    r = _classify(
        url="https://some-random-unknown-site.example/paper-2025",
        title="Effect of Drug X on Condition Y: A Study",
    )
    assert r.tier.value == "T4", f"Unknown host should stay T4, got {r.tier.value}"


def test_mdpi_news_style_not_laundered() -> None:
    """An MDPI page that is a stub is still T7 (Rule 1), not laundered."""
    r = _classify(
        url="https://www.mdpi.com/2077-0383/14/22/8079",
        title="Editorial note",
        content_length=300,
    )
    assert r.tier.value == "T7", f"MDPI stub should be T7, got {r.tier.value}"


# ── iter-2 (Codex P1): canonical ACC/AHA guidelines are DOI ARTICLES, no path ──

def test_aha_guideline_doi_article_is_t2() -> None:
    """Real ACC/AHA guideline: a DOI article (no /guidelines/ path) with a
    guideline title must reach T2, not fall to T4/T1."""
    r = _classify(
        url="https://www.ahajournals.org/doi/10.1161/CIR.0000000000001193",
        title="2023 ACC/AHA/ACCP/HRS Guideline for the Diagnosis and Management of Atrial Fibrillation",
    )
    assert r.tier.value == "T2", f"AHA guideline DOI article should be T2, got {r.tier.value}"
    assert r.matched_rules[-1] == "R8c_guideline_authority"


def test_jacc_consensus_statement_is_t2() -> None:
    r = _classify(
        url="https://www.jacc.org/doi/10.1016/j.jacc.2024.02.001",
        title="2024 Expert Consensus Statement on anticoagulation in AF",
    )
    assert r.tier.value == "T2", f"JACC consensus statement should be T2, got {r.tier.value}"


def test_aha_primary_rct_not_promoted_by_guideline_check() -> None:
    """A primary RCT on an authority domain (no guideline title) stays T1 — the
    narrow guideline-title detector must not catch primary studies."""
    r = _classify(
        url="https://www.ahajournals.org/doi/10.1161/CIRCULATIONAHA.124.012345",
        title="Apixaban versus warfarin in atrial fibrillation: a randomized controlled trial",
    )
    assert r.tier.value == "T1", f"AHA primary RCT should stay T1, got {r.tier.value}"


def test_authority_domain_explainer_title_not_promoted_to_t2() -> None:
    """An explainer/whitepaper title on an authority domain must NOT be promoted
    to T2 (the narrow guideline set deliberately excludes explainer markers)."""
    r = _classify(
        url="https://www.ahajournals.org/doi/10.1161/whitepaper.2024",
        title="An explainer on anticoagulation pricing trends",
    )
    assert r.tier.value != "T2", f"Explainer title should NOT be T2, got {r.tier.value}"


def test_gdmt_primary_study_not_promoted_to_t2() -> None:
    """iter-3 (Codex P1): 'Guideline-Directed Medical Therapy' (GDMT) is a
    therapy studied in PRIMARY studies, not a guideline document. The bare
    'guideline' substring must NOT promote it to T2 via Rule 8c. (It resolves to
    T4 via the pre-existing broad R9_openalex_guideline_explainer demotion — a
    separate, pre-#812 behavior; the #812 invariant is simply: NOT T2, NOT
    promoted by R8c.)"""
    r = _classify(
        url="https://www.jacc.org/doi/10.1016/j.jacc.2024.03.010",
        title="Guideline-Directed Medical Therapy in Heart Failure: A Prospective Cohort Study",
    )
    assert r.tier.value != "T2", f"GDMT primary should NOT be T2, got {r.tier.value}"
    assert r.matched_rules[-1] != "R8c_guideline_authority"


def test_guideline_adherence_study_not_promoted_to_t2() -> None:
    r = _classify(
        url="https://www.ahajournals.org/doi/10.1161/CIRCOUTCOMES.124.099999",
        title="Guideline Adherence and Outcomes in Atrial Fibrillation: A Registry Analysis",
    )
    assert r.tier.value != "T2", f"Guideline-adherence study should not be T2, got {r.tier.value}"


def test_guideline_comparison_commentary_not_promoted() -> None:
    """iter-4 (Codex P1): a guideline-COMPARISON/analysis article is commentary
    ABOUT guidelines, not an issued guideline document. Undated + 'guideline
    recommendations for' (not 'guideline for') -> must NOT be T2."""
    r = _classify(
        url="https://www.jacc.org/doi/abs/10.1016/j.jacc.2024.07.044",
        title="International Clinical Practice Guideline Recommendations for Acute Pulmonary Embolism: Harmony, Dissonance, and Silence",
    )
    assert r.tier.value != "T2", f"Guideline-comparison commentary should NOT be T2, got {r.tier.value}"
    assert r.matched_rules[-1] != "R8c_guideline_authority"


def test_revascularization_guideline_main_title_only_is_t2() -> None:
    """iter-4 (Codex P2): a real issued guideline whose title lacks 'for the'
    ('2021 ACC/AHA/SCAI Guideline for Coronary Artery Revascularization') must
    still reach T2 via the year-anchored 'guideline for' pattern."""
    r = _classify(
        url="https://www.jacc.org/doi/10.1016/j.jacc.2021.09.006",
        title="2021 ACC/AHA/SCAI Guideline for Coronary Artery Revascularization",
    )
    assert r.tier.value == "T2", f"Revascularization guideline should be T2, got {r.tier.value}"
    assert r.matched_rules[-1] == "R8c_guideline_authority"


def test_doi_prefix_exact_no_false_positive() -> None:
    """iter-2 (Codex P2): low-quality-OA DOI matching is exact-prefix, so a
    longer prefix beginning with 10.3390 (e.g. 10.33901) is NOT treated as MDPI."""
    assert _is_low_quality_oa("", "https://doi.org/10.3390/jcm14228079") is True
    assert _is_low_quality_oa("", "https://example.org/10.3390/abc") is True
    assert _is_low_quality_oa("", "https://doi.org/10.33901/xyz") is False
    assert _is_low_quality_oa("", "https://example.org/10.33901/abc") is False
    assert _is_low_quality_oa("", "https://doi.org/10.1056/NEJMoa2107519") is False
