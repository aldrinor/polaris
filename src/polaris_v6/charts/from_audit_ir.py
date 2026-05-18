"""Build chart specs from a faithful AuditIR.

I-rdy-008 (#504) slice 8 (Codex architecture consult
`.codex/I-rdy-008/slice8_charts_arch_consult_verdict.txt`, Option A). The
golden-fixture charts (`from_bundle.chart_from_bundle`) derived the 3
Vega-Lite chart types from an `EvidenceContract`; the live charts route
resolves a completed run's `artifact_dir` and `load_audit_ir()`s it
instead. AuditIR carries NO `coverage_percent`, so this is a redesign, not
a port: every chart derives only from AuditIR-native quantities —

- forest_plot   : contradiction value spreads (the real min/mean/max of the
                  values disagreeing sources reported), or — when a run has
                  no contradictions — per-section verification rate
                  (`kept / total_in`, a genuine 0-1 rate).
- comparison_table : the source-tier mix (count of bibliography entries per
                  tier).
- timeline      : the report-order series of cited verified sentences.

No fabricated magnitudes and no pseudo confidence interval: the forest-plot
`ci_low`/`ci_high` carry the actual min/max of reported values (the title
says so), never an invented statistical band.
"""

from __future__ import annotations

from collections import Counter
from typing import Literal

from polaris_graph.audit_ir.loader import AuditIR, ContradictionCluster
from polaris_v6.charts.spec_builder import (
    ComparisonRow,
    ForestPlotPoint,
    TimelinePoint,
    build_comparison_table,
    build_forest_plot,
    build_timeline,
)

ChartType = Literal["forest_plot", "comparison_table", "timeline"]


def _cluster_label(cluster: ContradictionCluster) -> str:
    """A non-empty y-axis label — loader defaults `subject` to ''."""
    return cluster.subject or cluster.predicate or f"cluster-{cluster.cluster_id}"


def _forest_plot(ir: AuditIR) -> dict:
    """Contradiction value spreads, else per-section verification rate.

    A contradiction cluster's `claims[].value` are the real numbers the
    disagreeing sources reported; the point is their mean and the bar is
    their min–max (a true range, not a statistical CI — the title says so).
    A run with no contradictions falls back to one point per section with a
    genuine `kept / total_in` verification rate.
    """
    if ir.contradictions:
        points = []
        for cluster in ir.contradictions:
            values = [claim.value for claim in cluster.claims]
            points.append(
                ForestPlotPoint(
                    label=_cluster_label(cluster),
                    estimate=sum(values) / len(values),
                    ci_low=min(values),
                    ci_high=max(values),
                    evidence_id=cluster.claims[0].evidence_id,
                )
            )
        return build_forest_plot(
            title=(
                "Contradictions — point = mean of reported values, "
                "bar = min–max across disagreeing sources"
            ),
            points=points,
            x_label="Reported value across disagreeing sources",
        )

    # No contradictions: per-section verification rate. Skip sections with
    # total_in <= 0 — the loader defaults a missing total_in to 0, and
    # kept_count / total_in would then ZeroDivisionError (Codex brief
    # iter-1 P1-2); a section with no inbound count has no honest rate.
    rate_points = [
        ForestPlotPoint(
            label=section.title or "(untitled section)",
            estimate=section.kept_count / section.total_in,
            ci_low=section.kept_count / section.total_in,
            ci_high=section.kept_count / section.total_in,
            evidence_id=f"section:{section.title}",
        )
        for section in ir.verified_report.sections
        if section.total_in > 0
    ]
    if rate_points:
        return build_forest_plot(
            title="Section verification rate",
            points=rate_points,
            x_label="Section verification rate (verified / total)",
        )

    return build_forest_plot(
        title="No contradictions or verifiable sections in this run",
        points=[
            ForestPlotPoint(
                label="(no data)",
                estimate=0.0,
                ci_low=0.0,
                ci_high=0.0,
                evidence_id="placeholder",
            )
        ],
    )


def _comparison_table(ir: AuditIR) -> dict:
    """The source-tier mix — count of bibliography entries per tier."""
    if not ir.bibliography:
        return build_comparison_table(
            title="Source tier mix",
            rows=[
                ComparisonRow(
                    entity="(no sources)",
                    metric="source_count",
                    value=0.0,
                    evidence_id="placeholder",
                )
            ],
        )
    counts: Counter[str] = Counter(entry.tier for entry in ir.bibliography)
    first_evidence_id: dict[str, str] = {}
    for entry in ir.bibliography:
        first_evidence_id.setdefault(entry.tier, entry.evidence_id)
    rows = [
        ComparisonRow(
            entity=f"Tier {tier}",
            metric="source_count",
            value=float(counts[tier]),
            evidence_id=first_evidence_id[tier],
        )
        for tier in sorted(counts)
    ]
    return build_comparison_table(title="Source tier mix", rows=rows)


def _timeline(ir: AuditIR) -> dict:
    """The report-order series of cited verified sentences.

    Zero-token sentences are skipped (Codex brief iter-2 P2): a sentence
    with no `[#ev:...]` token has no evidence to click through to, so
    putting its `claim_id` in the `evidence_id` field would be misleading.
    `value` is the 1-based report position — a real ordinal, not an
    invented magnitude.
    """
    points = []
    position = 0
    for section in ir.verified_report.sections:
        for sentence in section.sentences:
            if not sentence.tokens:
                continue
            position += 1
            points.append(
                TimelinePoint(
                    period=f"step-{position:02d}",
                    value=float(position),
                    series=section.title or "(untitled section)",
                    evidence_id=sentence.tokens[0].evidence_id,
                )
            )
    if not points:
        return build_timeline(
            title="Verified-sentence timeline (report order)",
            points=[
                TimelinePoint(
                    period="step-01",
                    value=0.0,
                    series="(no cited sentences)",
                    evidence_id="placeholder",
                )
            ],
            period_kind="quarter",
        )
    return build_timeline(
        title="Verified-sentence timeline (report order)",
        points=points,
        period_kind="quarter",
    )


def chart_from_audit_ir(*, ir: AuditIR, chart_type: ChartType) -> dict:
    """Generate a Vega-Lite chart spec for `chart_type` from a run's AuditIR."""
    if chart_type == "forest_plot":
        return _forest_plot(ir)
    if chart_type == "comparison_table":
        return _comparison_table(ir)
    if chart_type == "timeline":
        return _timeline(ir)
    raise ValueError(f"unknown chart_type: {chart_type}")
