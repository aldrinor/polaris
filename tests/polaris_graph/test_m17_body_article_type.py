"""BUG-M-17b (Codex pass 3 BLOCKED fix): bounded body-text inspection
that REQUIRES context, not lone keywords.

Codex pass 3 flagged 6 false-positive risks (lone "systematic review",
"meta-analysis", "case report", "for clinicians" mentions in primary
papers citing prior literature). M-17b tightens: trust only explicit
publisher article-type metadata + declarative body patterns that
state the fetched article IS the given type.
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
# P1a: explicit meta / JSON-LD article-type tags
# ─────────────────────────────────────────────────────────────────


def test_meta_citation_article_type_systematic_review() -> None:
    content = (
        '<meta name="citation_article_type" content="Systematic Review">\n'
        'Some other text...'
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_meta_citation_article_type_reverse_attr_order() -> None:
    """Codex pass 3 recall gap: handle both attr orders."""
    content = (
        '<meta content="Systematic Review" name="citation_article_type">\n'
        'Abstract of the paper...'
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_meta_citation_article_type_case_report() -> None:
    content = (
        '<meta name="citation_article_type" content="Case Report">\n'
        'Hypothetical safety event.'
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


def test_jsonld_articletype_meta_analysis() -> None:
    content = '<script type="application/ld+json">{"articleType": "Meta-Analysis", "headline": "X"}</script>'
    assert _detect_article_type_from_body(content) == "SR_MA"


# ─────────────────────────────────────────────────────────────────
# P1b: publisher-embedded article-type headers
# ─────────────────────────────────────────────────────────────────


def test_frontiers_systematic_review_article_header() -> None:
    content = (
        "<html><body>"
        "SYSTEMATIC REVIEW article"
        " Front. Pharmacol., 2022 | https://doi.org/10.3389/fphar..."
        "Efficacy and safety of tirzepatide in patients with type 2 diabetes"
        "</body></html>"
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_nature_article_type_header_meta_analysis() -> None:
    content = (
        "Article type: Meta-Analysis\n"
        "Nature Medicine, 2025\n"
        "Weight-loss outcomes across GLP-1 agonists..."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_frontiers_case_report_article_header() -> None:
    content = (
        "CASE REPORT article\n"
        "Front. Endocrinol., 2024\n"
        "A patient with refractory hypoglycemia..."
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


# ─────────────────────────────────────────────────────────────────
# P2: declarative body patterns (require context, not lone keyword)
# ─────────────────────────────────────────────────────────────────


def test_objective_to_conduct_systematic_review() -> None:
    content = (
        "Abstract\n\nObjective: To conduct a systematic review and "
        "meta-analysis of tirzepatide efficacy trials."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_we_conducted_a_systematic_review() -> None:
    content = (
        "Abstract\n\nBackground: Tirzepatide is a novel GIP/GLP-1 agonist.\n"
        "Methods: We conducted a systematic review of randomized trials..."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_this_systematic_review_and_meta_analysis() -> None:
    content = (
        "Abstract\n\nThis systematic review and meta-analysis pools "
        "SURPASS trial safety data..."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_prisma_with_context_signals_sr_ma() -> None:
    content = (
        "Abstract\n\nMethods: Following PRISMA 2020 flow diagram, we "
        "performed literature search of MEDLINE..."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_cochrane_review_signals_sr_ma() -> None:
    content = "This Cochrane systematic review evaluates tirzepatide..."
    assert _detect_article_type_from_body(content) == "SR_MA"


def test_pooled_estimate_random_effects_signals_sr_ma() -> None:
    """Meta-analytic method signature: pooled estimate + random-effects."""
    content = (
        "Abstract\n\nResults: The pooled odds ratio using random-effects "
        "model was 0.82 (95% CI 0.74-0.91)."
    )
    assert _detect_article_type_from_body(content) == "SR_MA"


# ─────────────────────────────────────────────────────────────────
# Case report: declarative, not lone "case report"
# ─────────────────────────────────────────────────────────────────


def test_we_report_a_case_pattern() -> None:
    content = (
        "Abstract\n\nWe report a case of refractory hypoglycemia in a "
        "patient following Roux-en-Y..."
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


def test_here_we_describe_a_case() -> None:
    content = (
        "Abstract\n\nHere we describe a case of tirzepatide-induced "
        "pancreatitis..."
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


def test_we_report_a_65_year_old_patient() -> None:
    content = (
        "Abstract\n\nWe report a 65-year-old patient with refractory "
        "hypoglycemia..."
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


def test_opener_a_62_year_old_woman_presented() -> None:
    """Classic case report opener at start of abstract."""
    content = (
        "A 62-year-old woman presented with recurrent hypoglycemia "
        "after Roux-en-Y gastric bypass..."
    )
    assert _detect_article_type_from_body(content) == "CASE_REPORT"


# ─────────────────────────────────────────────────────────────────
# Guideline / perspective: declarative patterns
# ─────────────────────────────────────────────────────────────────


def test_this_clinical_practice_guideline() -> None:
    content = (
        "This clinical practice guideline provides evidence-based "
        "recommendations for tirzepatide use..."
    )
    assert _detect_article_type_from_body(content) == "GUIDELINE"


def test_consensus_statement_from() -> None:
    content = (
        "Consensus statement from the Endocrine Society on tirzepatide "
        "prescribing..."
    )
    assert _detect_article_type_from_body(content) == "GUIDELINE"


def test_in_this_perspective() -> None:
    content = (
        "Abstract\n\nIn this perspective, we examine the implications "
        "of tirzepatide approval..."
    )
    assert _detect_article_type_from_body(content) == "PERSPECTIVE"


# ─────────────────────────────────────────────────────────────────
# NEGATIVE: lone keywords in primary papers must NOT trigger
# (the exact false positives Codex pass 3 flagged)
# ─────────────────────────────────────────────────────────────────


def test_primary_paper_citing_prior_systematic_review_not_flagged() -> None:
    """Codex pass 3 reproducer #1: primary paper citing Wilding et al.
    systematic review in background should NOT flag as SR_MA."""
    content = (
        "Abstract\n\n"
        "Background: We compared tirzepatide to semaglutide in adults "
        "with obesity. Prior evidence includes the Wilding et al. "
        "systematic review for GLP-1 receptor agonists.\n"
        "Methods: Participants were randomized to tirzepatide 15 mg or "
        "semaglutide 2.4 mg for 72 weeks..."
    )
    assert _detect_article_type_from_body(content) == ""


def test_primary_paper_mentioning_meta_analysis_methodology_not_flagged() -> None:
    """Codex pass 3 reproducer #2: 'meta-analysis methodology' in a
    primary RCT should not flag."""
    content = (
        "Abstract\n\n"
        "Methods: This randomized trial compared tirzepatide with "
        "semaglutide. We discuss meta-analysis methodology used in "
        "prior evidence synthesis but the current study is a single "
        "trial..."
    )
    assert _detect_article_type_from_body(content) == ""


def test_primary_paper_excluding_case_reports_not_flagged() -> None:
    """Codex pass 3 reproducer #3: 'we excluded case reports' in a
    primary paper's eligibility criteria should not flag."""
    content = (
        "Abstract\n\n"
        "Methods: We enrolled adults with type 2 diabetes. We excluded "
        "case reports and case series from the literature search used "
        "for protocol development..."
    )
    assert _detect_article_type_from_body(content) == ""


def test_primary_paper_citing_guidelines_as_background_not_flagged() -> None:
    """Codex pass 3 reproducer #4: guidelines as cited background."""
    content = (
        "Abstract\n\n"
        "Background: Current guidelines recommend GLP-1 receptor agonists "
        "for patients with established cardiovascular disease. We tested..."
    )
    assert _detect_article_type_from_body(content) == ""


def test_lone_for_clinicians_audience_phrase_not_flagged() -> None:
    """Codex pass 3: audience phrases without declarative framing
    should not flag. The concluding paragraph of a primary trial may
    say 'these findings have implications for clinicians.'"""
    content = (
        "Abstract\n\n"
        "Background: Tirzepatide efficacy.\n"
        "Methods: Randomized trial.\n"
        "Conclusion: These findings have important implications for "
        "clinicians managing type 2 diabetes."
    )
    assert _detect_article_type_from_body(content) == ""


def test_lone_primary_care_phrase_not_flagged() -> None:
    content = (
        "Abstract\n\n"
        "Background: Tirzepatide is available in primary care settings. "
        "Our objective is to test efficacy in a randomized trial of "
        "400 adults with type 2 diabetes."
    )
    assert _detect_article_type_from_body(content) == ""


def test_lone_case_series_in_exclusion_criteria_not_flagged() -> None:
    content = (
        "Eligibility: adults 18-75. We excluded patients with prior "
        "case series documentation of severe hypoglycemia."
    )
    assert _detect_article_type_from_body(content) == ""


def test_prisma_without_context_not_flagged() -> None:
    """PRISMA alone isn't enough — needs search/selection/extraction
    co-occurrence."""
    content = (
        "Methods: We followed PRISMA reporting principles generally "
        "but this is a single trial."
    )
    assert _detect_article_type_from_body(content) == ""


# ─────────────────────────────────────────────────────────────────
# Bounded-scan regression
# ─────────────────────────────────────────────────────────────────


def test_bounded_scan_ignores_late_false_signals() -> None:
    filler = "x" * 10000
    content = filler + "\n\nThis is actually a systematic review and meta-analysis."
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
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12547409/",
        title="Efficacy and Safety of Tirzepatide in Refractory Hypoglycemia ... - PMC",
        body_type="CASE_REPORT",
    )
    assert r.tier.value == "T4"


def test_pmc_truncated_title_body_perspective_goes_to_t4() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="Efficacy and Safety of Tirzepatide in Adults With Type 2 Diabetes",
        body_type="PERSPECTIVE",
    )
    assert r.tier.value == "T4"


def test_oxford_non_diagnostic_title_body_sr_ma_goes_to_t2() -> None:
    r = _classify(
        url="https://academic.oup.com/jes/article-abstract/7/4/bvad016/7005432",
        title="Adverse Events Related to Tirzepatide - Oxford Academic",
        body_type="SR_MA",
    )
    assert r.tier.value == "T2"


def test_body_empty_signal_falls_through_to_title_rules() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide in type 2 diabetes",
        body_type="",
    )
    assert r.tier.value == "T1"


def test_body_signal_overrides_even_strong_openalex_primary() -> None:
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC999/",
        title="Tirzepatide reduces hypoglycemia",
        body_type="CASE_REPORT",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T4"


# ─────────────────────────────────────────────────────────────────
# Classifier-level false-positive regression (Codex pass 3 required)
# ─────────────────────────────────────────────────────────────────


def test_primary_paper_no_body_signal_stays_t1() -> None:
    """Codex pass 3 required test: a primary paper that mentions prior
    systematic reviews in its background must NOT be demoted because
    the detector now returns '' (empty) for that case. Classifier then
    falls through to R9 primary-article path → T1."""
    # Detector returns "" for this content:
    body = (
        "Background: Prior Wilding et al. systematic review summarized "
        "GLP-1 efficacy. Methods: Randomized trial of 1000 adults."
    )
    detector_signal = _detect_article_type_from_body(body)
    assert detector_signal == ""

    # When classifier receives body_article_type="", it falls through
    # to R9 which grants T1 on known-journal host.
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2025001",
        title="Tirzepatide vs semaglutide in adults with obesity",
        body_type=detector_signal,  # empty
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


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
