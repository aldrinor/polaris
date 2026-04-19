"""BUG-M-15 (Codex pass 15 CONDITIONAL): narrow targeted R10 guards
for the 5 false-T1 patterns Codex identified post-cycle-8. Avoids
the cycle-7 over-demotion failure mode by NOT applying a blanket
primary-signal requirement; instead guards specific patterns:

1. Truncated titles (ending with "..." / "…")
2. NIH literature aggregators (PMC, PubMed) without OpenAlex metadata
3. Professional-society tool/dosing URL paths (acc.org/tools/...)
4. Biomedical guidance/consensus/practice-guide title markers

Critically, bare NEJM/Lancet primary titles like "Tirzepatide in
type 2 diabetes" must STILL be T1 (they were over-demoted in cycle
7 when M-14 required primary signals universally).
"""

from __future__ import annotations

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
        openalex_publication_type=openalex.get("pub_type", ""),
        openalex_source_type=openalex.get("source_type", ""),
        openalex_is_peer_reviewed=openalex.get("is_peer_reviewed", False),
        source_type_hint="",
    )
    return classify_source_tier(sig)


# ─────────────────────────────────────────────────────────────────
# Guard 1: Truncated titles
# ─────────────────────────────────────────────────────────────────


def test_truncated_title_with_ellipsis_demotes_to_t4() -> None:
    """Codex pass 15: MDPI SR/MA title was truncated mid-title.
    Without full title, can't detect SR/MA — demote to T4 until
    full title can be fetched."""
    r = _classify(
        url="https://www.mdpi.com/1424-8247/18/5/668",
        title="The Efficacy and Safety of Tirzepatide in Patients with Diabetes and ...",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_truncated_title_with_unicode_ellipsis_demotes() -> None:
    """Alternative ellipsis character (Unicode …) also truncated."""
    r = _classify(
        url="https://www.nature.com/articles/abc",
        title="Some paper about drug effects and safety\u2026",
    )
    assert r.tier.value == "T4"


def test_non_truncated_title_not_demoted_by_guard1() -> None:
    """Regression: a full title without ellipsis must not be
    demoted by the truncation guard."""
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide in type 2 diabetes",
    )
    assert r.tier.value == "T1"


# ─────────────────────────────────────────────────────────────────
# Guard 2 REVERTED (cycle-9 over-demote): NIH aggregator tests removed.
# Replaced with regression guarantee that PMC/PubMed primaries stay T1
# when OpenAlex metadata is present, and fall back to R10 default T1
# when metadata is absent. Codex pass 16 will weigh in on whether the
# residual NIH hallucinations need a narrower (per-title-pattern) fix.
# ─────────────────────────────────────────────────────────────────


def test_pmc_without_openalex_still_r10_fallback_t1() -> None:
    """Guard 2 revert regression: PMC paper without OpenAlex metadata
    falls back to R10 presumed-primary T1. This preserves cycle-8
    release behavior (trading some false T1s for non-zero release
    rate)."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="Efficacy and Safety of Tirzepatide in Adults With Type 2 Diabetes",
    )
    assert r.tier.value == "T1", (
        f"PMC R10 fallback should default to T1 when title is untruncated "
        f"and no narrative/guideline markers fire. Got: {r.tier.value}"
    )


def test_pmc_with_openalex_primary_still_t1() -> None:
    """PMC paper with OpenAlex article+journal metadata routes via R9,
    not R10."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC99887766/",
        title="Tirzepatide in SURPASS-4: Phase 3 randomized trial",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


# ─────────────────────────────────────────────────────────────────
# Guard 3: Professional-society tool/dosing URL paths
# ─────────────────────────────────────────────────────────────────


def test_acc_dosing_tool_url_demoted_to_t3() -> None:
    """Codex pass 15: ACC.org DOAC dosing PDF is a clinical tool,
    not primary research. URL path contains 'dosing'."""
    r = _classify(
        url="https://www.acc.org/tools/doac-dosing-guide.pdf",
        title="DOAC Dosing Guide",
    )
    assert r.tier.value == "T3", f"Expected T3, got {r.tier.value}"


def test_acc_practice_support_url_demoted_to_t3() -> None:
    r = _classify(
        url="https://www.acc.org/practice-support/guidelines/af-care.pdf",
        title="AF Care Pathway",
    )
    assert r.tier.value == "T3"


def test_acc_clinical_research_article_not_demoted_by_guard3() -> None:
    """Regression: ACC.org article that is NOT a tool/practice-support
    path should not be affected by guard 3."""
    r = _classify(
        url="https://www.acc.org/latest-in-cardiology/articles/2024/trial-results",
        title="Some Trial Results",
    )
    # This hits the fallback T1 (or other R10 branches); not demoted by guard 3
    assert r.tier.value == "T1"


# ─────────────────────────────────────────────────────────────────
# Guard 4: Biomedical guidance/consensus markers
# ─────────────────────────────────────────────────────────────────


def test_practical_guidance_title_demoted_to_t4() -> None:
    """Codex pass 15 recommendation: 'practical guidance' is a
    guideline-adjacent marker."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12240022/",
        title="Practical Guidance for DOAC Management in Atrial Fibrillation",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4"


def test_consensus_statement_title_demoted_to_t4() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC999/",
        title="Expert Consensus Statement on Tirzepatide Prescribing",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4"


def test_position_paper_title_demoted_to_t4() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/10.1056/abc",
        title="Position Paper: Obesity Pharmacotherapy in 2026",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T4"


# ─────────────────────────────────────────────────────────────────
# Cycle-7 regression: bare NEJM/Lancet primary titles still T1
# (these were the ones M-14 part 2 over-demoted)
# ─────────────────────────────────────────────────────────────────


def test_regression_bare_nejm_title_still_t1() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide in type 2 diabetes",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_bare_lancet_title_still_t1() -> None:
    r = _classify(
        url="https://www.thelancet.com/journals/lancet/article/S0140",
        title="Semaglutide in Obesity",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_jama_plain_trial_still_t1() -> None:
    r = _classify(
        url="https://jamanetwork.com/journals/jama/fullarticle/2812936",
        title="Continued Tirzepatide Treatment",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T1"


# ─────────────────────────────────────────────────────────────────
# Earlier M-fix regressions still hold
# ─────────────────────────────────────────────────────────────────


def test_regression_m7_facebook_still_t6() -> None:
    r = _classify(url="https://www.facebook.com/post/123")
    assert r.tier.value == "T6"


def test_regression_m10_kff_still_t4() -> None:
    r = _classify(url="https://www.kff.org/issue-brief/abc")
    assert r.tier.value == "T4"


def test_regression_sr_ma_title_still_t2() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC333/",
        title="Semaglutide in obesity: a systematic review and meta-analysis",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T2"
