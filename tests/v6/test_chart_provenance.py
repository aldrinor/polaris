"""I-f10-005: Tests for the ChartProvenance Pydantic schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from polaris_v6.charts.provenance import (
    ChartProvenance,
    validate_chart_provenance,
)
from polaris_v6.charts.spec_builder import (
    ComparisonRow,
    ForestPlotPoint,
    TimelinePoint,
    build_comparison_table,
    build_forest_plot,
    build_timeline,
)


def test_validate_forest_plot_provenance():
    spec = build_forest_plot(
        title="t",
        points=[ForestPlotPoint("a", 0.0, -0.1, 0.1, "ev1")],
    )
    prov = validate_chart_provenance(spec)
    assert isinstance(prov, ChartProvenance)
    assert prov.chart_type == "forest_plot"
    assert prov.evidence_ids == ["ev1"]
    assert prov.period_kind is None


def test_validate_comparison_table_provenance():
    spec = build_comparison_table(
        title="t",
        rows=[ComparisonRow("e", "m", 1.0, "ev_x")],
    )
    prov = validate_chart_provenance(spec)
    assert prov.chart_type == "comparison_table"
    assert prov.evidence_ids == ["ev_x"]
    assert prov.period_kind is None


def test_validate_timeline_provenance():
    spec = build_timeline(
        title="t",
        points=[TimelinePoint("2025-Q1", 1.0, "s", "ev_t")],
        period_kind="quarter",
    )
    prov = validate_chart_provenance(spec)
    assert prov.chart_type == "timeline"
    assert prov.period_kind == "quarter"
    assert prov.evidence_ids == ["ev_t"]


def test_missing_polaris_provenance_raises():
    with pytest.raises(ValueError, match="missing polaris_provenance"):
        validate_chart_provenance({})


def test_polaris_provenance_not_dict_raises():
    with pytest.raises(ValueError, match="must be a dict"):
        validate_chart_provenance({"polaris_provenance": "not-a-dict"})


def test_empty_evidence_ids_raises():
    with pytest.raises(ValidationError):
        ChartProvenance(chart_type="forest_plot", evidence_ids=[])


def test_blank_evidence_id_raises():
    with pytest.raises(ValidationError, match="blank"):
        ChartProvenance(chart_type="forest_plot", evidence_ids=["ev1", "  "])


def test_unknown_chart_type_raises():
    with pytest.raises(ValidationError):
        ChartProvenance(chart_type="scatter_plot", evidence_ids=["ev1"])  # type: ignore[arg-type]


def test_timeline_without_period_kind_raises():
    with pytest.raises(ValidationError, match="requires period_kind"):
        ChartProvenance(chart_type="timeline", evidence_ids=["ev1"])


def test_non_timeline_with_period_kind_raises():
    with pytest.raises(ValidationError, match="only valid for timeline"):
        ChartProvenance(
            chart_type="forest_plot",
            evidence_ids=["ev1"],
            period_kind="quarter",
        )


def test_extra_field_forbidden():
    with pytest.raises(ValidationError):
        ChartProvenance(
            chart_type="forest_plot",
            evidence_ids=["ev1"],
            unknown_field="oops",  # type: ignore[call-arg]
        )
