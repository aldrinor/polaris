"""W3 (I-deepfix-001) — FAIL-LOUD behavioral test that the per-citation credibility
WEIGHT is surfaced in the REAL rendered report, and that the legacy GOLD/SILVER
quality-tier vocabulary is reconciled onto ONE T1-T7 language.

These tests drive the real ``assemble_report`` render path (NOT a flag tautology):
they assemble a report from real schemas and assert the credibility annotation
appears in the returned ``report.md`` text. §-1.3 posture: the annotation is
advisory disclosure of state the tier/authority/genre stages ALREADY computed —
no source is dropped, no gate reads it, the faithfulness engine is untouched.

Default-OFF byte-identical revert (LAW VI) is asserted too: with the flag OFF the
References block is exactly the legacy output (no annotation).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.schemas import (
    CitationAudit,
    CitationMapping,
    ReportOutline,
    SectionDraft,
)
from src.polaris_graph.synthesis.report_assembler import (
    assemble_report,
    compute_quality_metrics,
    format_citation_credibility_annotation,
    resolve_credibility_tier,
)

_FLAG = "PG_RENDER_CITATION_CREDIBILITY"


def _outline() -> ReportOutline:
    return ReportOutline(
        title="Water Purification Methods",
        abstract=(
            "This report examines water purification methods drawing on 2 sources "
            "with 2 citations across 500 words."
        ),
        sections=[
            {
                "section_id": "s01",
                "title": "Filtration Techniques",
                "description": "Overview of filtration methods",
                "evidence_ids": ["ev_001", "ev_002"],
                "target_words": 400,
                "order": 1,
            },
        ],
    )


def _sections() -> list[SectionDraft]:
    return [
        SectionDraft(
            section_id="s01",
            title="Filtration Techniques",
            content=(
                "Activated carbon filters remove chlorine [CITE:ev_001]. "
                "Reverse osmosis removes dissolved salts [CITE:ev_002]. "
                "These methods are widely used in residential settings."
            ),
            claims_made=["Carbon removes chlorine", "RO removes salts"],
            evidence_ids=["ev_001", "ev_002"],
        ),
    ]


def _evidence_with_credibility() -> list[dict]:
    """Two sources carrying the ALREADY-COMPUTED credibility+genre signals the
    tier_classifier / credibility_pass / document_type_classifier produce."""
    return [
        {
            "evidence_id": "ev_001",
            "statement": "Activated carbon removes chlorine.",
            "source_url": "https://example.com/carbon",
            "source_title": "Carbon Filter Study",
            "direct_quote": "Carbon filters effectively remove chlorine.",
            "source_tier": "T1",
            "authority_score": 0.95,
            "source_class": "PRIMARY_SCHOLARLY",
            "document_type": "JOURNAL_ARTICLE",
        },
        {
            "evidence_id": "ev_002",
            "statement": "RO removes dissolved salts.",
            "source_url": "https://example.com/ro",
            "source_title": "RO Technology Review",
            "direct_quote": "Reverse osmosis removes dissolved salts.",
            "source_tier": "T6",
            "authority_score": 0.30,
            "source_class": "COMMENTARY",
            "document_type": "BLOG_COMMENTARY",
        },
    ]


def _citation_audit() -> CitationAudit:
    return CitationAudit(
        mappings=[
            CitationMapping(evidence_id="ev_001", citation_number=1, is_grounded=True),
            CitationMapping(evidence_id="ev_002", citation_number=2, is_grounded=True),
        ],
        ungrounded_claims=[],
        bibliography_entries=["[1] Carbon Filter Study", "[2] RO Technology Review"],
    )


def test_render_off_is_byte_identical_no_annotation(monkeypatch):
    """Default-OFF: the References block carries NO credibility annotation."""
    monkeypatch.delenv(_FLAG, raising=False)
    report, _, _ = assemble_report(
        _outline(), _sections(), _evidence_with_credibility(), _citation_audit(),
    )
    assert "[credibility:" not in report, (
        "flag OFF must be byte-identical — no credibility annotation may render"
    )


def test_render_on_surfaces_per_citation_credibility_weight(monkeypatch):
    """FLAG ON: the rendered report surfaces tier (T1-T7), authority_score,
    source_class, and genre for EACH cited source — the real render effect."""
    monkeypatch.setenv(_FLAG, "1")
    report, _, _ = assemble_report(
        _outline(), _sections(), _evidence_with_credibility(), _citation_audit(),
    )
    # The T1 peer-reviewed journal source.
    assert "[credibility:" in report, "credibility annotation did not render"
    assert "tier T1" in report, "T1 tier weight not surfaced in the render"
    assert "authority 0.95" in report, "authority_score not surfaced"
    assert "class PRIMARY_SCHOLARLY" in report, "source_class not surfaced"
    assert "genre JOURNAL_ARTICLE" in report, "document-type genre not surfaced"
    # The low-tier blog source is ALSO surfaced (WEIGHT-and-disclose, never dropped).
    assert "tier T6" in report, "low-tier source must still render (never dropped)"
    assert "genre BLOG_COMMENTARY" in report, "blog genre not surfaced"


def test_render_on_failopen_when_no_credibility_signal(monkeypatch):
    """A source with NO credibility fields renders exactly as before (fail-open —
    a weight is never fabricated)."""
    monkeypatch.setenv(_FLAG, "1")
    ev = _evidence_with_credibility()
    for row in ev:
        for k in ("source_tier", "tier", "quality_tier", "authority_score",
                  "source_class", "document_type"):
            row.pop(k, None)
    report, _, _ = assemble_report(_outline(), _sections(), ev, _citation_audit())
    assert "[credibility:" not in report, (
        "no credibility signal => no fabricated annotation (fail-open)"
    )


def test_annotation_helper_is_honest_per_source():
    """The annotation function surfaces exactly the present signals and nothing
    fabricated (unit-level guard for the render string)."""
    annot = format_citation_credibility_annotation(
        {"source_tier": "T2", "authority_score": 0.85, "document_type": "REVIEW_ARTICLE"}
    )
    assert "tier T2" in annot and "authority 0.85" in annot
    assert "genre REVIEW_ARTICLE" in annot
    # No class present => no class bit invented.
    assert "class" not in annot
    # Empty row => empty string (never a bare "[credibility: ]").
    assert format_citation_credibility_annotation({}) == ""


def test_legacy_gold_silver_reconciled_onto_t1_t7():
    """A source that only carries the legacy GOLD/SILVER/BRONZE vocabulary is
    reconciled onto the T1-T7 band so ONE credibility language shows."""
    gold, basis_g = resolve_credibility_tier({"quality_tier": "GOLD"})
    silver, _ = resolve_credibility_tier({"quality_tier": "SILVER"})
    bronze, _ = resolve_credibility_tier({"quality_tier": "BRONZE"})
    assert gold == "T2" and "legacy_reconcile" in basis_g
    assert silver == "T4"
    assert bronze == "T6"
    # A real T1-T7 tier wins over the legacy field (tier_classifier is authoritative).
    tier, basis = resolve_credibility_tier({"source_tier": "T1", "quality_tier": "GOLD"})
    assert tier == "T1" and "tier_classifier" in basis


def test_quality_metrics_emit_one_tier_language(monkeypatch):
    """compute_quality_metrics emits a reconciled T1-T7 ``tier_distribution`` so
    the metrics speak ONE credibility language even when only legacy tiers exist."""
    monkeypatch.delenv(_FLAG, raising=False)
    report, report_sections, bibliography = assemble_report(
        _outline(), _sections(), _evidence_with_credibility(), _citation_audit(),
    )
    metrics = compute_quality_metrics(
        evidence=_evidence_with_credibility(),
        claims=[],
        report_sections=report_sections,
        bibliography=bibliography,
        faithfulness_score=1.0,
    )
    dist = metrics["tier_distribution"]
    assert dist.get("T1") == 1, "T1 source not counted in the reconciled distribution"
    assert dist.get("T6") == 1, "T6 source not counted in the reconciled distribution"

    # Legacy-only evidence still reconciles onto the T1-T7 language.
    legacy_ev = [
        {"evidence_id": "ev_a", "quality_tier": "GOLD", "source_url": "https://a.test"},
        {"evidence_id": "ev_b", "quality_tier": "BRONZE", "source_url": "https://b.test"},
    ]
    legacy_metrics = compute_quality_metrics(
        evidence=legacy_ev, claims=[], report_sections=report_sections,
        bibliography=bibliography, faithfulness_score=1.0,
    )
    ldist = legacy_metrics["tier_distribution"]
    assert ldist.get("T2") == 1 and ldist.get("T6") == 1, (
        "legacy GOLD/BRONZE not reconciled onto the T1-T7 language"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
