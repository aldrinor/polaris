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
