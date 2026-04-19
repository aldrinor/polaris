"""BUG-M-17 (Codex pass 2): bounded body-text inspection for
article-type signals.

Covers the 3 unfixed Codex pass-1 hallucinations by detecting
article-type from high-signal body regions (meta tags, JSON-LD,
Frontiers section header, PRISMA reference, "we report a case"
pattern) — catches cases where the title is truncated or doesn't
contain the discriminating phrase.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.live_retriever import (
    _detect_article_type_from_body,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
)


# ─────────────────────────────────────────────────────────────────
# Body inspector: article-type detection
# ─────────────────────────────────────────────────────────────────


def test_frontiers_systematic_review_article_header() -> None:
    """Frontiers prominently displays 'SYSTEMATIC REVIEW article' on
    the landing page for SR/MA papers."""
    content = (
        "<html><body>"
        "SYSTEMATIC REVIEW article"
        " Front. Pharmacol., 2022 | https://doi.org/10.3389/fphar..."
        "Efficacy and safety of tirzepatide in patients with type 2 diabetes"
        "</body></html>"
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_meta_citation_article_type_systematic_review() -> None:
    content = (
        '<meta name="citation_article_type" content="Systematic Review">\n'
        'Some other text...'
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_meta_citation_article_type_case_report() -> None:
    content = (
        '<meta name="citation_article_type" content="Case Report">\n'
        'Hypothetical safety event.'
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


def test_prisma_reference_in_body_signals_sr_ma() -> None:
    """PRISMA flow diagram reference in the first 4KB signals SR/MA."""
    content = (
        "Abstract\n\nObjective: To systematically review the literature.\n"
        "Methods: We followed the PRISMA 2020 reporting guidelines.\n"
        "Results: ..."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_we_report_a_case_pattern_signals_case_report() -> None:
    """Case report lead text."""
    content = (
        "Abstract\n\nWe report a case of refractory hypoglycemia in a "
        "65-year-old man following Roux-en-Y..."
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


def test_a_62_year_old_patient_signals_case_report() -> None:
    content = (
        "A 62-year-old woman presented with recurrent hypoglycemia..."
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


def test_perspective_for_signals_perspective() -> None:
    content = (
        "A Perspective for Primary Care Providers\n\n"
        "Tirzepatide is a dual GIP/GLP-1 receptor agonist..."
    )
    assert _detect_article_type_from_body(content) == "PERSPECTIVE"


def test_clinical_practice_guideline_signals_guideline() -> None:
    content = (
        "Clinical practice guideline: management of type 2 diabetes.\n\n"
        "This guideline provides evidence-based recommendations..."
    )
    assert _detect_article_type_from_body(content) == "GUIDELINE"


def test_consensus_statement_signals_guideline() -> None:
    content = (
        "Consensus statement from the Endocrine Society on tirzepatide..."
    )
    assert _detect_article_type_from_body(content) == "GUIDELINE"


def test_nature_article_type_header_meta_analysis() -> None:
    content = (
        "Article type: Meta-Analysis\n"
        "Nature Medicine, 2025\n"
        "Weight-loss outcomes across GLP-1 agonists..."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_meta_analysis_in_abstract_lead() -> None:
    """Oxford Academic 'Adverse Events Related to Tirzepatide' case:
    title doesn't say SR/MA but body lead says 'meta-analysis'."""
    content = (
        "Abstract\n\n"
        "Context: Tirzepatide is a novel GIP/GLP-1 agonist.\n"
        "Objective: To pool safety data from SURPASS trials via "
        "meta-analysis.\n"
        "Methods: Systematic search of MEDLINE..."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_bounded_scan_ignores_late_false_signals() -> None:
    """Scan is bounded to first 8KB. A false signal in the body
    after 8KB should NOT trigger. Fill first 8KB with irrelevant
    content; put 'meta-analysis' at position 10K → NOT detected."""
    filler = "x" * 10000
    content = filler + "\n\nThis is actually a meta-analysis paper."
    assert _detect_article_type_from_body(content) == ""


def test_empty_content_returns_empty() -> None:
    assert _detect_article_type_from_body("") == ""
    assert _detect_article_type_from_body(None) == ""


# ─────────────────────────────────────────────────────────────────
# End-to-end: body signal overrides R9/R10 title decisions
# ─────────────────────────────────────────────────────────────────


def _classify(url, title, body_type="", **oa):
    sig = ClassificationSignals(
        url=url,
        title=title,
        publisher="",
        fetched_content_length=8000,
        openalex_publication_type=oa.get("pub_type", "article"),
        openalex_source_type=oa.get("source_type", "journal"),
        openalex_is_peer_reviewed=oa.get("is_peer_reviewed", True),
        source_type_hint="",
        body_article_type=body_type,
    )
    return classify_source_tier(sig)


def test_pmc_truncated_title_body_case_report_goes_to_t4() -> None:
    """Codex pass 1 case [10]: truncated title doesn't say 'case
    report', but body inspection found it. Body signal wins → T4."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12547409/",
        title="Efficacy and Safety of Tirzepatide in Refractory Hypoglycemia ... - PMC",
        body_type="CASE_REPORT",
    )
    assert r.tier.value == "T4"


def test_pmc_truncated_title_body_perspective_goes_to_t4() -> None:
    """Codex pass 1 case [1]: truncated PMC title, body = Perspective
    for Primary Care Providers."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="Efficacy and Safety of Tirzepatide in Adults With Type 2 Diabetes",
        body_type="PERSPECTIVE",
    )
    assert r.tier.value == "T4"


def test_oxford_non_diagnostic_title_body_sr_ma_goes_to_t2() -> None:
    """Codex pass 1 case [8]: Oxford 'Adverse Events Related to
    Tirzepatide' title says nothing about SR/MA, but body inspection
    found meta-analysis marker."""
    r = _classify(
        url="https://academic.oup.com/jes/article-abstract/7/4/bvad016/7005432",
        title="Adverse Events Related to Tirzepatide - Oxford Academic",
        body_type="SR_MA",
    )
    assert r.tier.value == "T2"


def test_body_empty_signal_falls_through_to_title_rules() -> None:
    """Regression: no body signal → classifier falls through to
    existing R9/R10 title-based rules. Bare NEJM primary stays T1."""
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide in type 2 diabetes",
        body_type="",  # no body signal
    )
    assert r.tier.value == "T1"


def test_body_signal_overrides_even_strong_openalex_primary() -> None:
    """If OpenAlex says article+journal+peer-reviewed but body says
    CASE_REPORT, body wins (honest-by-construction: don't ship a
    case report as T1 primary)."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC999/",
        title="Tirzepatide reduces hypoglycemia",  # no marker in title
        body_type="CASE_REPORT",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T4"


def test_body_guideline_overrides_title() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC777/",
        title="Tirzepatide in adults",
        body_type="GUIDELINE",
    )
    assert r.tier.value == "T4"


# ─────────────────────────────────────────────────────────────────
# Regressions: prior M-fixes still hold
# ─────────────────────────────────────────────────────────────────


def test_regression_m7_facebook_still_t6() -> None:
    r = _classify(url="https://www.facebook.com/post/123", title="x")
    assert r.tier.value == "T6"


def test_regression_sr_ma_title_still_t2_without_body() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC333/",
        title="Tirzepatide in obesity: a systematic review and meta-analysis",
        body_type="",
        pub_type="article",
        source_type="journal",
    )
    assert r.tier.value == "T2"
