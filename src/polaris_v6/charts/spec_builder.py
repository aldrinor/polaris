"""Vega-Lite v5 chart spec builders for the 3 supported chart types.

Each builder returns a dict that can be JSON-serialised and rendered by
any Vega-Lite v5 client. The `polaris_provenance` extension is
non-standard but ignored by Vega-Lite renderers; it carries the
evidence_id mapping for the F10b click-through-to-source UX.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

VEGA_LITE_SCHEMA_URL = "https://vega.github.io/schema/vega-lite/v5.json"


@dataclass
class ForestPlotPoint:
    """One row of a forest plot: a point estimate with its 95% CI.

    ``evidence_id`` ties the row back to its source span for the
    click-through-to-source UX.
    """

    label: str
    estimate: float
    ci_low: float
    ci_high: float
    evidence_id: str


@dataclass
class ComparisonRow:
    """One bar of a comparison table: a metric ``value`` for an ``entity``.

    ``evidence_id`` ties the row back to its source span for click-through.
    """

    entity: str
    metric: str
    value: float
    evidence_id: str


@dataclass
class TimelinePoint:
    """One point on a timeline: a ``value`` for a ``series`` at a ``period``.

    ``period`` is an ISO 8601 date or a ``YYYY-Qn`` quarter string;
    ``evidence_id`` ties the point back to its source span for click-through.
    """

    period: str  # ISO 8601 date or YYYY-Qn
    value: float
    series: str
    evidence_id: str


def build_forest_plot(
    *,
    title: str,
    points: list[ForestPlotPoint],
    x_label: str = "Effect estimate (95% CI)",
) -> dict[str, Any]:
    """Build a Vega-Lite v5 forest-plot spec from CI point estimates.

    Args:
        title: Chart title.
        points: Rows to plot; must be non-empty.
        x_label: Axis title for the estimate/CI axis.

    Returns:
        A JSON-serialisable Vega-Lite spec (rule + point layers) carrying a
        ``polaris_provenance`` block that maps points to their evidence_ids.

    Raises:
        ValueError: If ``points`` is empty.
    """
    if not points:
        raise ValueError("forest plot requires at least one point")
    data_values = [
        {
            "label": p.label,
            "estimate": p.estimate,
            "ci_low": p.ci_low,
            "ci_high": p.ci_high,
            "evidence_id": p.evidence_id,
        }
        for p in points
    ]
    return {
        "$schema": VEGA_LITE_SCHEMA_URL,
        "title": title,
        "data": {"values": data_values},
        "layer": [
            {
                "mark": {"type": "rule"},
                "encoding": {
                    "y": {"field": "label", "type": "nominal", "sort": None, "axis": {"title": None}},
                    "x": {"field": "ci_low", "type": "quantitative", "title": x_label},
                    "x2": {"field": "ci_high"},
                },
            },
            {
                "mark": {"type": "point", "filled": True, "size": 100},
                "encoding": {
                    "y": {"field": "label", "type": "nominal"},
                    "x": {"field": "estimate", "type": "quantitative"},
                    "tooltip": [
                        {"field": "label"},
                        {"field": "estimate"},
                        {"field": "ci_low"},
                        {"field": "ci_high"},
                        {"field": "evidence_id"},
                    ],
                },
            },
        ],
        "polaris_provenance": {
            "chart_type": "forest_plot",
            "evidence_ids": [p.evidence_id for p in points],
        },
    }


def build_comparison_table(
    *,
    title: str,
    rows: list[ComparisonRow],
) -> dict[str, Any]:
    """Build a Vega-Lite v5 grouped-bar comparison spec.

    Args:
        title: Chart title.
        rows: Rows to plot; must be non-empty. Bars are grouped by entity and
            coloured by metric.

    Returns:
        A JSON-serialisable Vega-Lite spec carrying a ``polaris_provenance``
        block that maps rows to their evidence_ids.

    Raises:
        ValueError: If ``rows`` is empty.
    """
    if not rows:
        raise ValueError("comparison table requires at least one row")
    data_values = [
        {
            "entity": r.entity,
            "metric": r.metric,
            "value": r.value,
            "evidence_id": r.evidence_id,
        }
        for r in rows
    ]
    return {
        "$schema": VEGA_LITE_SCHEMA_URL,
        "title": title,
        "data": {"values": data_values},
        "mark": {"type": "bar"},
        "encoding": {
            "y": {"field": "entity", "type": "nominal", "axis": {"title": None}},
            "x": {"field": "value", "type": "quantitative"},
            "color": {"field": "metric", "type": "nominal"},
            "tooltip": [
                {"field": "entity"},
                {"field": "metric"},
                {"field": "value"},
                {"field": "evidence_id"},
            ],
        },
        "polaris_provenance": {
            "chart_type": "comparison_table",
            "evidence_ids": [r.evidence_id for r in rows],
        },
    }


def build_timeline(
    *,
    title: str,
    points: list[TimelinePoint],
    period_kind: Literal["date", "quarter", "year"] = "quarter",
) -> dict[str, Any]:
    """Build a Vega-Lite v5 multi-series line-timeline spec.

    Args:
        title: Chart title.
        points: Points to plot; must be non-empty. Lines are split by series.
        period_kind: Controls the x-axis encoding — ``"date"`` renders a
            temporal axis; ``"quarter"`` and ``"year"`` render an ordinal axis.

    Returns:
        A JSON-serialisable Vega-Lite spec carrying a ``polaris_provenance``
        block with ``period_kind`` and the points' evidence_ids.

    Raises:
        ValueError: If ``points`` is empty.
    """
    if not points:
        raise ValueError("timeline requires at least one point")
    temporal_type = "temporal" if period_kind == "date" else "ordinal"
    data_values = [
        {
            "period": p.period,
            "value": p.value,
            "series": p.series,
            "evidence_id": p.evidence_id,
        }
        for p in points
    ]
    return {
        "$schema": VEGA_LITE_SCHEMA_URL,
        "title": title,
        "data": {"values": data_values},
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "period", "type": temporal_type, "axis": {"title": "Period"}},
            "y": {"field": "value", "type": "quantitative"},
            "color": {"field": "series", "type": "nominal"},
            "tooltip": [
                {"field": "period"},
                {"field": "value"},
                {"field": "series"},
                {"field": "evidence_id"},
            ],
        },
        "polaris_provenance": {
            "chart_type": "timeline",
            "period_kind": period_kind,
            "evidence_ids": [p.evidence_id for p in points],
        },
    }
