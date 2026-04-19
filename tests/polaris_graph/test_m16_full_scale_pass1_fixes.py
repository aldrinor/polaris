"""BUG-M-16 (Codex full-scale pass 1 CONDITIONAL): regression tests
for the 3 specific tier hallucinations Codex named plus the
conference-ID/case-report/post-hoc detection patterns.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    classify_source_tier,
    _detect_conference_abstract,
    _detect_narrative_flavor_from_title,
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
# Conference abstract detector — day-prefix IDs
# ─────────────────────────────────────────────────────────────────


def test_thu_id_prefix_detects_conference_abstract() -> None:
    """Codex pass 1 case [20]: JES supplement abstract
    'THU296: GADA-positive SURPASS 2-5 post hoc analysis'."""
    assert _detect_conference_abstract(
        "THU296 GADA-positive SURPASS 2-5 post hoc",
        "https://academic.oup.com/jes/article-pdf/...",
    ) is True


def test_thu_hyphen_id_detects() -> None:
    assert _detect_conference_abstract(
        "THU-0245: Some Abstract Title",
        "",
    ) is True


def test_mon_tue_wed_fri_sat_sun_prefixes_detect() -> None:
    for day in ("MON", "TUE", "WED", "FRI", "SAT", "SUN"):
        assert _detect_conference_abstract(
            f"{day}-123: Some Abstract", "",
        ) is True, f"{day} prefix failed to detect"


def test_or_number_hyphen_number_detects() -> None:
    """Oral-presentation supplement abstract IDs like OR30-04."""
    assert _detect_conference_abstract("OR30-04: Some Talk", "") is True
    assert _detect_conference_abstract("OR01-2: Another Talk", "") is True


def test_jes_article_pdf_supplement_url_detects() -> None:
    """JES article-pdf supplement URLs are always abstracts."""
    assert _detect_conference_abstract(
        "Some Generic Title",
        "https://academic.oup.com/jes/article-pdf/6/Supplement_1/A347/bvac150.722.pdf",
    ) is True


def test_normal_title_does_not_false_positive() -> None:
    """Guard: normal journal titles aren't mistakenly flagged as
    conference abstracts by the new detectors."""
    assert _detect_conference_abstract(
        "Tirzepatide in type 2 diabetes: a randomized trial",
        "https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
    ) is False


# ─────────────────────────────────────────────────────────────────
# Narrative flavor — case report / post-hoc / pooled / subgroup
# ─────────────────────────────────────────────────────────────────


def test_case_report_title_detects_narrative() -> None:
    assert _detect_narrative_flavor_from_title(
        "Efficacy and Safety of Tirzepatide in Refractory Hypoglycemia: A Case Report"
    ) is True


def test_a_case_of_title_detects() -> None:
    assert _detect_narrative_flavor_from_title(
        "A Case of Tirzepatide-Induced Pancreatitis"
    ) is True


def test_post_hoc_analysis_title_detects() -> None:
    assert _detect_narrative_flavor_from_title(
        "Body-weight outcomes: a post hoc analysis of SURPASS-4"
    ) is True


def test_pooled_analysis_title_detects() -> None:
    assert _detect_narrative_flavor_from_title(
        "Safety of tirzepatide: a pooled analysis of SURPASS trials"
    ) is True


def test_subgroup_analysis_title_detects() -> None:
    assert _detect_narrative_flavor_from_title(
        "Tirzepatide across baseline HbA1c: subgroup analysis"
    ) is True


# ─────────────────────────────────────────────────────────────────
# End-to-end classifier outcomes for the Codex-named URLs
# ─────────────────────────────────────────────────────────────────


def test_pmc_case_report_demotes_to_t4() -> None:
    """Codex pass 1 case [10]: PMC case report was T1."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC12345678/",
        title="Efficacy and Safety of Tirzepatide in Refractory Hypoglycemia: A Case Report",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


def test_thu296_conference_abstract_is_t7() -> None:
    """Codex pass 1 case [20]: JES supplement abstract was T4,
    should be T7."""
    r = _classify(
        url="https://academic.oup.com/jes/article-pdf/6/Supplement_1/A347/46734272/bvac150.722.pdf",
        title="THU296: GADA-positive SURPASS 2-5 post hoc analysis",
    )
    assert r.tier.value == "T7", f"Expected T7, got {r.tier.value}"


def test_pmc_perspective_primary_care_demotes_to_t4() -> None:
    """Codex pass 1 case [1]: PMC 'A Perspective for Primary Care
    Providers' was T1."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC10115620/",
        title="Efficacy and Safety of Tirzepatide in Adults With Type 2 Diabetes: A Perspective for Primary Care Providers",
    )
    assert r.tier.value == "T4", f"Expected T4, got {r.tier.value}"


# ─────────────────────────────────────────────────────────────────
# Regressions: legitimate primaries still T1
# ─────────────────────────────────────────────────────────────────


def test_regression_nejm_primary_still_t1() -> None:
    r = _classify(
        url="https://www.nejm.org/doi/full/10.1056/NEJMoa2107519",
        title="Tirzepatide in type 2 diabetes",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"


def test_regression_legitimate_primary_rct_on_pmc_still_t1() -> None:
    """Guard: a PMC paper whose title is a primary-study signal
    (not post-hoc/case-report/perspective) still reaches T1."""
    r = _classify(
        url="https://pmc.ncbi.nlm.nih.gov/articles/PMC99887766/",
        title="Tirzepatide in SURPASS-4: Phase 3 randomized trial",
        pub_type="article",
        source_type="journal",
        is_peer_reviewed=True,
    )
    assert r.tier.value == "T1"
