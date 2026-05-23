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
