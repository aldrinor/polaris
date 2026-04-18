"""
Tests for Phase 2f — OpenAlexWork.authority_tier_t7() routing through
the new tier_classifier.
"""
from __future__ import annotations

from src.polaris_graph.tools.openalex_client import OpenAlexWork


def _mk(type_: str, source_type: str, title: str = "Test", is_retracted: bool = False) -> OpenAlexWork:
    return OpenAlexWork(
        work_id="https://openalex.org/W123",
        doi="",
        title=title,
        type=type_,
        source_type=source_type,
        source_name="Test Journal",
        publication_year=2024,
        is_retracted=is_retracted,
    )


def test_retracted_returns_unknown() -> None:
    w = _mk("article", "journal", is_retracted=True)
    assert w.authority_tier_t7() == "UNKNOWN"


def test_erratum_returns_unknown() -> None:
    w = _mk("erratum", "journal")
    assert w.authority_tier_t7() == "UNKNOWN"


def test_peer_reviewed_systematic_review_title_is_t2() -> None:
    w = _mk(
        "review", "journal",
        title="A Systematic Review and Meta-Analysis of Semaglutide",
    )
    assert w.authority_tier_t7(
        url="https://example.com/paper",
    ) == "T2"


def test_peer_reviewed_narrative_review_title_is_t4() -> None:
    w = _mk(
        "article", "journal",
        title="Semaglutide for the Treatment of Obesity",
    )
    assert w.authority_tier_t7(
        url="https://example.com/paper",
    ) == "T4"


def test_peer_reviewed_primary_study_is_t1() -> None:
    w = _mk(
        "article", "journal",
        title="Effect of Semaglutide on Weight Loss in Adults: A Randomized Controlled Trial",
    )
    assert w.authority_tier_t7(
        url="https://example.com/paper",
    ) == "T1"


def test_openalex_pubtype_review_defaults_to_t4() -> None:
    # OpenAlex says 'review' but the title is a bare drug-condition phrase
    w = _mk("review", "journal", title="Semaglutide 2.4 Mg for Obesity")
    assert w.authority_tier_t7(url="https://example.com/paper") == "T4"


def test_fda_url_is_t3_even_with_openalex_type() -> None:
    # URL overrides OpenAlex metadata for regulatory content
    w = _mk("other", "", title="Drug Label")
    tier = w.authority_tier_t7(
        url="https://www.accessdata.fda.gov/drugsatfda_docs/label/2021/215256s000lbl.pdf",
    )
    assert tier == "T3"


def test_scribd_url_drops_to_t6_regardless_of_content_hint() -> None:
    w = _mk("other", "", title="Product Monograph Mirror")
    tier = w.authority_tier_t7(
        url="https://scribd.com/document/978060740/wegovy",
        source_type_hint="government_report",  # would elevate naively
    )
    assert tier == "T6"


def test_touchendocrinology_is_t5_physician_portal() -> None:
    w = _mk("article", "journal", title="Once-Weekly Semaglutide: A Game Changer")
    tier = w.authority_tier_t7(
        url="https://touchendocrinology.com/obesity/journal-articles/once-weekly",
    )
    assert tier == "T5"
