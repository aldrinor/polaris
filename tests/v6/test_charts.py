"""Tests for the Vega-Lite chart spec builders."""

from __future__ import annotations

import json

import pytest

from polaris_v6.charts.spec_builder import (
    ComparisonRow,
    ForestPlotPoint,
    TimelinePoint,
    build_comparison_table,
    build_forest_plot,
    build_timeline,
)


def test_forest_plot_basic_shape():
    spec = build_forest_plot(
        title="SELECT trial cardiovascular outcomes",
        points=[
            ForestPlotPoint("MACE", -0.20, -0.27, -0.13, "ev_clin_001"),
            ForestPlotPoint("MI", -0.18, -0.28, -0.06, "ev_clin_002"),
            ForestPlotPoint("Stroke", -0.07, -0.19, 0.05, "ev_clin_003"),
        ],
    )
    assert spec["$schema"].startswith("https://vega.github.io/schema/vega-lite/v5")
    assert spec["polaris_provenance"]["chart_type"] == "forest_plot"
    assert spec["polaris_provenance"]["evidence_ids"] == [
        "ev_clin_001",
        "ev_clin_002",
        "ev_clin_003",
    ]
    json.dumps(spec)  # serializable


def test_forest_plot_empty_raises():
    with pytest.raises(ValueError):
        build_forest_plot(title="empty", points=[])


def test_comparison_table_basic_shape():
    spec = build_comparison_table(
        title="Q3 2025 housing starts by province",
        rows=[
            ComparisonRow("Ontario", "starts_thousands", 18.4, "ev_house_on"),
            ComparisonRow("Quebec", "starts_thousands", 9.7, "ev_house_qc"),
            ComparisonRow("BC", "starts_thousands", 7.2, "ev_house_bc"),
        ],
    )
    assert spec["mark"]["type"] == "bar"
    assert spec["polaris_provenance"]["chart_type"] == "comparison_table"
    assert len(spec["polaris_provenance"]["evidence_ids"]) == 3
    json.dumps(spec)


def test_timeline_quarter_kind():
    spec = build_timeline(
        title="Oil-sands GHG intensity per barrel",
        points=[
            TimelinePoint("2010-Q1", 0.080, "Suncor", "ev_oil_010"),
            TimelinePoint("2015-Q1", 0.075, "Suncor", "ev_oil_015"),
            TimelinePoint("2020-Q1", 0.070, "Suncor", "ev_oil_020"),
            TimelinePoint("2023-Q4", 0.066, "Suncor", "ev_oil_023"),
        ],
        period_kind="quarter",
    )
    assert spec["mark"]["type"] == "line"
    assert spec["encoding"]["x"]["type"] == "ordinal"
    assert spec["polaris_provenance"]["period_kind"] == "quarter"
    json.dumps(spec)


def test_timeline_date_kind_uses_temporal():
    spec = build_timeline(
        title="ECCC monthly emissions",
        points=[
            TimelinePoint("2024-01-01", 14.2, "ECCC", "ev_eccc_jan"),
            TimelinePoint("2024-02-01", 13.8, "ECCC", "ev_eccc_feb"),
        ],
        period_kind="date",
    )
    assert spec["encoding"]["x"]["type"] == "temporal"


def test_forest_plot_meta_analysis_with_negative_estimates():
    """I-f10-002: SELECT-trial-style meta-analysis with negative effect
    estimates and asymmetric CIs (e.g., MACE -0.20 [-0.27, -0.13]) MUST
    produce a two-layer rule+point Vega-Lite spec where every point row
    carries its evidence_id in tooltip metadata. Locks the meta-analysis
    use case the I-f10-002 acceptance criterion calls out beyond the
    basic-shape coverage."""
    spec = build_forest_plot(
        title="SELECT trial cardiovascular outcomes",
        points=[
            ForestPlotPoint("MACE", -0.20, -0.27, -0.13, "ev_clin_001"),
            ForestPlotPoint("MI", -0.18, -0.28, -0.06, "ev_clin_002"),
            ForestPlotPoint("Stroke", -0.07, -0.19, 0.05, "ev_clin_003"),
        ],
    )
    # Two-layer structure (rule for CI bars, point for estimates) preserved.
    assert "layer" in spec
    assert len(spec["layer"]) == 2
    rule_layer, point_layer = spec["layer"]
    assert rule_layer["mark"]["type"] == "rule"
    assert point_layer["mark"]["type"] == "point"
    # Each point's tooltip carries the evidence_id (click-through-to-source
    # contract for F10b).
    tooltip_fields = {f["field"] for f in point_layer["encoding"]["tooltip"]}
    assert "evidence_id" in tooltip_fields
    # Negative effect estimates serialize correctly.
    data = spec["data"]["values"]
    assert data[0]["estimate"] == -0.20
    assert data[0]["ci_low"] == -0.27
    assert data[0]["ci_high"] == -0.13
    # Asymmetric CI: stroke crosses zero (effect estimate negative, ci_high
    # positive) — meta-analysis "no effect" boundary case.
    assert data[2]["ci_low"] < 0 < data[2]["ci_high"]


def test_all_charts_carry_evidence_ids():
    forest = build_forest_plot(
        title="t",
        points=[ForestPlotPoint("a", 0.0, -0.1, 0.1, "ev1")],
    )
    table = build_comparison_table(
        title="t",
        rows=[ComparisonRow("e", "m", 1.0, "ev2")],
    )
    timeline = build_timeline(
        title="t",
        points=[TimelinePoint("2025-Q1", 1.0, "s", "ev3")],
    )
    for spec in (forest, table, timeline):
        assert "polaris_provenance" in spec
        assert "evidence_ids" in spec["polaris_provenance"]
        assert len(spec["polaris_provenance"]["evidence_ids"]) >= 1


# Coverage gap fixes — exercise the from_bundle.py fallback paths that
# only fire on edge-case bundles (no frame_coverage, no verified_sentences,
# unknown chart_type). Closes the 3 uncovered lines (81, 116, 149).


def _make_bundle(**overrides):
    """Build a minimal valid EvidenceContract for from_bundle tests."""
    from polaris_v6.schemas.evidence_contract import (
        EvidenceContract,
        SourceSpan,
        VerifiedSentence,
    )

    base = dict(
        contract_version="1.0",
        run_id="test_bundle",
        template="clinical",
        question="q?",
        queued_at="2026-05-01T10:00:00Z",
        finished_at="2026-05-01T10:01:00Z",
        pipeline_status="success",
        evidence_pool=[
            SourceSpan(
                evidence_id="ev_x",
                source_url="https://example.gov",
                source_tier="T1",
                span_start=0,
                span_end=100,
                span_text="x",
            )
        ],
        verified_sentences=[
            VerifiedSentence(
                section_id="summary",
                sentence_text="x [#ev:ev_x:0-100].",
                provenance_tokens=["[#ev:ev_x:0-100]"],
                verifier_local_pass=True,
                verifier_global_pass=True,
                drop_reason=None,
            )
        ],
        frame_coverage=[],
        contradictions=[],
        cost_usd=0.1,
        generator_model="deepseek-v4-flash",
        verifier_model="gemma-4-31b-it",
        family_segregation_passed=True,
    )
    base.update(overrides)
    return EvidenceContract.model_validate(base)


def test_from_bundle_comparison_table_falls_back_to_evidence_pool():
    """Cover from_bundle.py:81 — comparison_table with no frame_coverage
    falls back to per-source-tier rows from the evidence_pool."""
    from polaris_v6.charts.from_bundle import chart_from_bundle

    bundle = _make_bundle(frame_coverage=[])
    spec = chart_from_bundle(bundle=bundle, chart_type="comparison_table")
    assert spec["polaris_provenance"]["chart_type"] == "comparison_table"
    # Should use the evidence_pool fallback (entity = "tier T1" etc).
    assert any("tier" in str(d) for d in spec["data"]["values"])


def test_from_bundle_timeline_falls_back_when_no_verified_sentences():
    """Cover from_bundle.py:116 — timeline placeholder when bundle has
    no verified_sentences."""
    from polaris_v6.charts.from_bundle import chart_from_bundle

    bundle = _make_bundle(verified_sentences=[])
    spec = chart_from_bundle(bundle=bundle, chart_type="timeline")
    assert spec["polaris_provenance"]["chart_type"] == "timeline"
    # Placeholder series.
    assert any(
        "no sentences" in str(d.get("series", "")).lower()
        for d in spec["data"]["values"]
    )


def test_from_bundle_unknown_chart_type_raises():
    """Cover from_bundle.py:149 — ValueError on unknown chart_type."""
    from polaris_v6.charts.from_bundle import chart_from_bundle

    bundle = _make_bundle()
    with pytest.raises(ValueError, match=r"unknown chart_type"):
        chart_from_bundle(bundle=bundle, chart_type="bogus")  # type: ignore[arg-type]
