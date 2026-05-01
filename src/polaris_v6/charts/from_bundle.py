"""Build chart specs from an EvidenceContract bundle.

Bridges the existing spec_builder + bundle endpoints. Each chart type
extracts the right slice of the bundle (verified sentences, contradictions,
or per-source numbers) and feeds it to the matching builder.

Phase 0/1 stub: deterministic mapping from bundle structure to chart
inputs. Phase 2B will swap in LLM-extracted numeric values when we have
real-pipeline data with per-source structured numerics.
"""

from __future__ import annotations

from typing import Literal

from polaris_v6.charts.spec_builder import (
    ComparisonRow,
    ForestPlotPoint,
    TimelinePoint,
    build_comparison_table,
    build_forest_plot,
    build_timeline,
)
from polaris_v6.schemas.evidence_contract import EvidenceContract

ChartType = Literal["forest_plot", "comparison_table", "timeline"]


def chart_from_bundle(*, bundle: EvidenceContract, chart_type: ChartType) -> dict:
    """Generate a chart spec from a bundle.

    For Phase 0, the chart is a deterministic synthetic mapping:
    - forest_plot: each contradiction → one point at estimate=0 with
      ci_low/ci_high reflecting claim_a vs claim_b spread
    - comparison_table: each frame_coverage → one bar per frame with
      coverage_percent value
    - timeline: each verified_sentence → one point ordered by section
    """
    if chart_type == "forest_plot":
        if not bundle.contradictions:
            return build_forest_plot(
                title=f"Frame coverage for {bundle.template}",
                points=[
                    ForestPlotPoint(
                        label=f.frame_name[:40],
                        estimate=f.coverage_percent / 100.0,
                        ci_low=max(0.0, (f.coverage_percent - 5) / 100.0),
                        ci_high=min(1.0, (f.coverage_percent + 5) / 100.0),
                        evidence_id=f.frame_id,
                    )
                    for f in bundle.frame_coverage
                ]
                or [
                    ForestPlotPoint(
                        label="(no frames)",
                        estimate=0.0,
                        ci_low=0.0,
                        ci_high=0.0,
                        evidence_id="placeholder",
                    )
                ],
            )
        points = []
        for c in bundle.contradictions:
            evidence_a_id = c.evidence_a[0] if c.evidence_a else "?"
            points.append(
                ForestPlotPoint(
                    label=c.contradiction_id,
                    estimate=0.0,
                    ci_low=-1.0,
                    ci_high=1.0,
                    evidence_id=evidence_a_id,
                )
            )
        return build_forest_plot(
            title=f"Contradictions in {bundle.template} run", points=points
        )

    if chart_type == "comparison_table":
        if not bundle.frame_coverage:
            return build_comparison_table(
                title=f"{bundle.template} run — sources by tier",
                rows=[
                    ComparisonRow(
                        entity=f"tier {span.source_tier}",
                        metric="span_chars",
                        value=float(span.span_end - span.span_start),
                        evidence_id=span.evidence_id,
                    )
                    for span in bundle.evidence_pool
                ]
                or [
                    ComparisonRow(
                        entity="(empty pool)",
                        metric="-",
                        value=0.0,
                        evidence_id="placeholder",
                    )
                ],
            )
        return build_comparison_table(
            title=f"Frame coverage — {bundle.template}",
            rows=[
                ComparisonRow(
                    entity=f.frame_name[:40],
                    metric="coverage_pct",
                    value=f.coverage_percent,
                    evidence_id=f.frame_id,
                )
                for f in bundle.frame_coverage
            ],
        )

    if chart_type == "timeline":
        if not bundle.verified_sentences:
            return build_timeline(
                title=f"{bundle.template} run timeline",
                points=[
                    TimelinePoint(
                        period="2026-Q2",
                        value=0.0,
                        series="(no sentences)",
                        evidence_id="placeholder",
                    )
                ],
                period_kind="quarter",
            )
        points = []
        for idx, s in enumerate(bundle.verified_sentences):
            ev_id = (
                s.provenance_tokens[0].split(":")[1]
                if s.provenance_tokens
                else "unknown"
            )
            points.append(
                TimelinePoint(
                    period=f"step-{idx + 1:02d}",
                    value=float(idx + 1),
                    series=s.section_id,
                    evidence_id=ev_id,
                )
            )
        return build_timeline(
            title=f"{bundle.template} verified-sentence timeline",
            points=points,
            period_kind="quarter",
        )

    raise ValueError(f"unknown chart_type: {chart_type}")
