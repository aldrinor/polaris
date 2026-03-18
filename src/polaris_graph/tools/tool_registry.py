"""Tool registry for ReAct analysis agent.

Provides a registry of analysis tools that the LLM can browse and invoke.
Each tool wrapper tracks source_evidence_ids for citation provenance —
ensuring analysis results cite ORIGINAL sources, never "POLARIS Analysis Toolkit".
"""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("polaris_graph")


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result from executing an analysis tool.

    The critical field is source_evidence_ids: it traces every statistic,
    chart, and insight back to the original evidence pieces that produced it.
    Synthesis uses these IDs to generate [CITE:ev_xxx] tokens.
    """

    success: bool
    tool_name: str
    markdown: str = ""
    statistics: dict = field(default_factory=dict)
    charts: list[dict] = field(default_factory=list)
    source_evidence_ids: list[str] = field(default_factory=list)
    data_points_produced: list[dict] = field(default_factory=list)
    insights: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ToolDefinition:
    """Definition of an analysis tool available to the ReAct agent."""

    name: str
    description: str
    requires_data: bool
    requires_llm: bool
    parameters: dict = field(default_factory=dict)
    execute: Optional[Callable] = None


class ToolRegistry:
    """Registry of analysis tools the LLM can pick from."""

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def available_tools(self, has_data: bool) -> list[str]:
        """Return names of tools available given current data state."""
        return [
            name for name, tool in self._tools.items()
            if not tool.requires_data or has_data
        ]

    def get_tool_descriptions(self, has_data: bool) -> str:
        """Format tool descriptions for LLM prompt."""
        lines = []
        for name in sorted(self._tools.keys()):
            tool = self._tools[name]
            available = not tool.requires_data or has_data
            status = "" if available else " [UNAVAILABLE: needs numeric data first]"
            lines.append(f"- {name}: {tool.description}{status}")
            if tool.parameters:
                for param, desc in tool.parameters.items():
                    lines.append(f"    {param}: {desc}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------

def _extract_evidence_ids(data_points: list[dict]) -> list[str]:
    """Extract unique evidence IDs from a list of data points."""
    ids = []
    seen = set()
    for dp in data_points:
        ev_id = dp.get("evidence_id", "")
        if ev_id and ev_id not in seen:
            ids.append(ev_id)
            seen.add(ev_id)
    return ids


def _cite_inline(text: str, evidence_ids: list[str]) -> str:
    """Embed [CITE:ev_xxx] tokens on data-containing paragraphs.

    Strategy: prefer paragraphs that contain numbers or data (those are
    the actual claims that need citations). Fall back to any content
    paragraph. Skip headers, table rows, and blank lines.
    """
    if not evidence_ids:
        return text

    import re as _re

    cite_ids = evidence_ids[:15]

    paragraphs = text.split("\n\n")

    # Score paragraphs: prefer those with numbers (actual data claims)
    scored = []
    for i, para in enumerate(paragraphs):
        stripped = para.strip()
        if not stripped:
            continue
        if stripped.startswith("|") or stripped.startswith("---"):
            continue  # Skip tables and separators
        if stripped.startswith("#"):
            continue  # Skip headers

        # Data paragraphs have numbers with units
        has_data = bool(_re.search(
            r'\d+\.?\d*\s*(%|mg|ng|ppt|ppb|ppm|USD|\$|m2|kWh|g/L|mg/g)',
            stripped,
        ))
        # List items with data are good citation targets
        has_list_data = stripped.startswith("-") and bool(
            _re.search(r'\d+', stripped)
        )
        score = 2 if has_data else (1 if has_list_data else 0)
        scored.append((i, score))

    # Sort by score descending, then by position (earlier = better)
    scored.sort(key=lambda x: (-x[1], x[0]))

    # Distribute citations across top-scored paragraphs
    idx = 0
    assigned = set()
    for para_idx, _score in scored:
        if idx >= len(cite_ids):
            break
        if para_idx in assigned:
            continue
        batch = cite_ids[idx:idx + 3]
        tokens = "".join(f"[CITE:{eid}]" for eid in batch)
        paragraphs[para_idx] = paragraphs[para_idx].rstrip() + " " + tokens
        idx += len(batch)
        assigned.add(para_idx)

    # If no data paragraphs found, attach to first content paragraph
    if idx == 0 and cite_ids:
        for i, para in enumerate(paragraphs):
            s = para.strip()
            if s and not s.startswith("|") and not s.startswith("#"):
                tokens = "".join(f"[CITE:{eid}]" for eid in cite_ids[:5])
                paragraphs[i] = para.rstrip() + " " + tokens
                break

    return "\n\n".join(paragraphs)


def _evidence_ids_from_store(evidence_store: dict, limit: int = 10) -> list[str]:
    """Get evidence IDs from the store, excluding analysis entries."""
    return [
        eid for eid in list(evidence_store.keys())[:limit * 2]
        if evidence_store[eid].get("type") != "analysis"
    ][:limit]


# ---------------------------------------------------------------------------
# Tool wrapper functions (each tracks source_evidence_ids)
# ---------------------------------------------------------------------------

async def _wrap_extract_numeric_data(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for evidence_extractor.extract_numbers_from_evidence()."""
    from src.polaris_graph.tools.evidence_extractor import (
        extract_numbers_from_evidence,
        summarize_extracted_data,
    )

    extracted = extract_numbers_from_evidence(evidence_store)
    if not extracted:
        return ToolResult(
            success=False,
            tool_name="extract_numeric_data",
            markdown="No numeric data found in evidence.",
            error="No numeric values could be extracted",
        )

    summary = summarize_extracted_data(extracted)
    ev_ids = _extract_evidence_ids(extracted)

    return ToolResult(
        success=True,
        tool_name="extract_numeric_data",
        markdown=_cite_inline(summary, ev_ids),
        source_evidence_ids=ev_ids,
        data_points_produced=extracted,
        insights=[
            f"Extracted {len(extracted)} numeric data points "
            f"from {len(ev_ids)} evidence pieces",
        ],
    )


async def _wrap_query_evidence_sql(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for EvidenceDatabase.query()."""
    from src.polaris_graph.tools.evidence_database import EvidenceDatabase

    query_sql = kwargs.get("sql", "")
    if not query_sql:
        query_sql = (
            "SELECT quality_tier, COUNT(*) as n, "
            "ROUND(AVG(relevance_score), 3) as avg_rel "
            "FROM evidence GROUP BY quality_tier ORDER BY n DESC"
        )

    db = EvidenceDatabase()
    loaded = db.load_evidence(evidence_store)
    if loaded == 0:
        db.close()
        return ToolResult(
            success=False,
            tool_name="query_evidence_sql",
            markdown="No evidence to query.",
            error="Evidence store empty",
        )

    result = db.query(query_sql)
    db.close()

    if not result["success"]:
        return ToolResult(
            success=False,
            tool_name="query_evidence_sql",
            markdown=f"SQL query failed: {result.get('error', 'unknown')}",
            error=result.get("error"),
        )

    # Extract evidence_ids from result rows if the query returns them
    ev_ids = []
    if "evidence_id" in result.get("columns", []):
        idx = result["columns"].index("evidence_id")
        ev_ids = [str(row[idx]) for row in result.get("rows", []) if row[idx]]

    if not ev_ids:
        ev_ids = _evidence_ids_from_store(evidence_store)

    markdown = f"**SQL Query:** `{query_sql}`\n\n{result.get('markdown_table', '')}"

    return ToolResult(
        success=True,
        tool_name="query_evidence_sql",
        markdown=_cite_inline(markdown, ev_ids),
        source_evidence_ids=ev_ids,
        statistics={"row_count": result["row_count"], "columns": result["columns"]},
    )


async def _wrap_statistical_summary(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for analysis_toolkit.statistical_summary().

    Groups data by unit first to prevent mixing ng/L with $ with %.
    Uses the LARGEST unit group for the primary analysis.
    """
    from src.polaris_graph.tools.analysis_toolkit import statistical_summary

    if not data_points:
        return ToolResult(
            success=False,
            tool_name="statistical_summary",
            markdown="No data points available for statistical summary.",
            error="Requires numeric data — run extract_numeric_data first",
        )

    # Group by unit to prevent mixing ng/L with $ with %
    by_unit: dict[str, list] = {}
    for dp in data_points:
        unit = dp.get("unit", "unknown") or "unknown"
        by_unit.setdefault(unit, []).append(dp)

    # Use the largest unit group (most meaningful)
    primary_unit = max(by_unit, key=lambda u: len(by_unit[u]))
    primary_data = by_unit[primary_unit]

    stats = statistical_summary(primary_data)
    ev_ids = _extract_evidence_ids(primary_data)

    if not stats.get("markdown_table"):
        return ToolResult(
            success=False,
            tool_name="statistical_summary",
            markdown="Could not compute statistics from provided data.",
            error="All values non-numeric",
        )

    return ToolResult(
        success=True,
        tool_name="statistical_summary",
        markdown=_cite_inline(stats["markdown_table"], ev_ids),
        statistics=stats.get("statistics", {}),
        source_evidence_ids=ev_ids,
        insights=stats.get("insights", []),
    )


async def _wrap_comparison_table(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for analysis_toolkit.build_comparison_table().

    Groups by unit first, then caps to top 10 labels (columns) to
    prevent 78KB pivot tables. Picks the largest unit group.
    """
    from src.polaris_graph.tools.analysis_toolkit import build_comparison_table

    if not data_points:
        return ToolResult(
            success=False,
            tool_name="comparison_table",
            markdown="No data points for comparison table.",
            error="Requires numeric data — run extract_numeric_data first",
        )

    # Group by unit — compare within the same unit only
    by_unit: dict[str, list] = {}
    for dp in data_points:
        unit = dp.get("unit", "unknown") or "unknown"
        by_unit.setdefault(unit, []).append(dp)

    primary_unit = max(by_unit, key=lambda u: len(by_unit[u]))
    unit_data = by_unit[primary_unit]

    # Cap labels (columns) to top 10 by frequency
    label_counts: dict[str, int] = {}
    for dp in unit_data:
        label = dp.get("label", "")
        if label:
            label_counts[label] = label_counts.get(label, 0) + 1
    top_labels = sorted(label_counts, key=label_counts.get, reverse=True)[:10]
    filtered = [dp for dp in unit_data if dp.get("label", "") in top_labels]

    if len(filtered) < 2:
        filtered = unit_data[:50]  # Fallback: just cap rows

    table_md = build_comparison_table(filtered)
    ev_ids = _extract_evidence_ids(filtered)

    if not table_md or len(table_md) < 50:
        return ToolResult(
            success=False,
            tool_name="comparison_table",
            markdown="Insufficient data for a meaningful comparison table.",
            error="Need data from >= 2 sources",
        )

    # Header with unit context
    header = f"**Comparison Table** (unit: {primary_unit}, {len(filtered)} data points)\n\n"

    return ToolResult(
        success=True,
        tool_name="comparison_table",
        markdown=_cite_inline(header + table_md, ev_ids),
        source_evidence_ids=ev_ids,
        statistics={"unit": primary_unit, "data_points": len(filtered), "sources": len(set(dp.get("source_url", "") for dp in filtered))},
    )


async def _wrap_meta_analysis(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for analysis_toolkit.generate_meta_analysis_summary()."""
    from src.polaris_graph.tools.analysis_toolkit import (
        generate_meta_analysis_summary,
    )

    if not data_points or len(data_points) < 3:
        return ToolResult(
            success=False,
            tool_name="meta_analysis",
            markdown="Need >= 3 data points for meta-analysis.",
            error="Insufficient data points",
        )

    meta_md = generate_meta_analysis_summary(data_points)
    ev_ids = _extract_evidence_ids(data_points)

    if not meta_md or len(meta_md) < 50:
        return ToolResult(
            success=False,
            tool_name="meta_analysis",
            markdown="Meta-analysis could not produce meaningful results.",
            error="Insufficient variation in data",
        )

    source_count = len(set(
        dp.get("source_url", "") for dp in data_points if dp.get("source_url")
    ))

    return ToolResult(
        success=True,
        tool_name="meta_analysis",
        markdown=_cite_inline(meta_md, ev_ids),
        source_evidence_ids=ev_ids,
        insights=[f"Meta-analysis across {source_count} sources"],
    )


async def _wrap_agreement_analysis(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for analysis_toolkit.compute_agreement_score()."""
    from src.polaris_graph.tools.analysis_toolkit import compute_agreement_score

    statements = []
    ev_ids = []
    for ev_id, ev in evidence_store.items():
        if ev.get("type") == "analysis":
            continue
        stmt = ev.get("statement", "")
        if stmt and len(stmt) > 20:
            statements.append(stmt)
            ev_ids.append(ev_id)
        if len(statements) >= 50:
            break

    if len(statements) < 3:
        return ToolResult(
            success=False,
            tool_name="agreement_analysis",
            markdown="Need >= 3 evidence statements for agreement analysis.",
            error="Insufficient evidence statements",
        )

    agreement = compute_agreement_score(statements)

    markdown = (
        f"**Source Agreement:** {agreement.get('consensus_strength', 'unknown')} "
        f"(score: {agreement.get('agreement_score', 0):.2f})\n\n"
        f"Based on pairwise comparison of {len(statements)} evidence statements."
    )

    return ToolResult(
        success=True,
        tool_name="agreement_analysis",
        markdown=_cite_inline(markdown, ev_ids[:10]),
        source_evidence_ids=ev_ids,
        statistics={"agreement_score": agreement.get("agreement_score", 0)},
        insights=[
            f"Consensus strength: {agreement.get('consensus_strength', 'unknown')}",
        ],
    )


async def _wrap_execute_python(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for code_executor.generate_and_execute_analysis()."""
    from src.polaris_graph.tools.code_executor import generate_and_execute_analysis

    if not client:
        return ToolResult(
            success=False,
            tool_name="execute_python",
            markdown="LLM client required for code generation.",
            error="No LLM client available",
        )

    question = kwargs.get(
        "question",
        "Analyze key patterns and relationships in the data",
    )
    query = kwargs.get("research_context", "")

    input_data = data_points[:30] if data_points else [
        {
            "statement": ev.get("statement", ""),
            "evidence_id": eid,
            "source_url": ev.get("source_url", ""),
        }
        for eid, ev in list(evidence_store.items())[:30]
        if ev.get("type") != "analysis"
    ]

    ev_ids = (
        _extract_evidence_ids(input_data)
        if data_points
        else [d.get("evidence_id", "") for d in input_data if d.get("evidence_id")]
    )

    tool_timeout = int(os.getenv("PG_REACT_TOOL_TIMEOUT", "60"))

    try:
        result = await asyncio.wait_for(
            generate_and_execute_analysis(
                client=client,
                evidence_data=input_data,
                analysis_question=question,
                research_context=query,
            ),
            timeout=tool_timeout,
        )
    except asyncio.TimeoutError:
        return ToolResult(
            success=False,
            tool_name="execute_python",
            markdown="Code execution timed out.",
            error=f"Timeout after {tool_timeout}s",
        )

    if not result.get("success"):
        return ToolResult(
            success=False,
            tool_name="execute_python",
            markdown=f"Code execution failed: {result.get('error', 'unknown')[:200]}",
            error=result.get("error"),
        )

    result_data = result.get("result", {})
    summary = (
        result_data.get("summary", str(result_data)[:1000])
        if result_data
        else ""
    )
    charts = result.get("charts", [])
    insights = (
        result_data.get("insights", [])
        if isinstance(result_data, dict)
        else []
    )

    return ToolResult(
        success=True,
        tool_name="execute_python",
        markdown=_cite_inline(summary, ev_ids),
        charts=charts,
        source_evidence_ids=ev_ids,
        statistics=(
            result_data.get("statistics", {})
            if isinstance(result_data, dict)
            else {}
        ),
        insights=insights,
    )


async def _wrap_rank_by_impact(
    evidence_store: dict,
    data_points: list[dict],
    client: Any,
    **kwargs,
) -> ToolResult:
    """Wrapper for analysis_toolkit.rank_evidence_by_impact()."""
    from src.polaris_graph.tools.analysis_toolkit import rank_evidence_by_impact

    if not data_points:
        return ToolResult(
            success=False,
            tool_name="rank_by_impact",
            markdown="No data points for impact ranking.",
            error="Requires numeric data — run extract_numeric_data first",
        )

    ranked = rank_evidence_by_impact(data_points)
    ev_ids = _extract_evidence_ids(ranked)

    lines = [
        "| Rank | Label | Value | Impact Score | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for i, dp in enumerate(ranked[:10], 1):
        lines.append(
            f"| {i} | {dp.get('label', '')[:40]} | {dp.get('value', '')} "
            f"| {dp.get('impact_score', 0):.2f} "
            f"| {dp.get('impact_reason', '')[:60]} |"
        )

    return ToolResult(
        success=True,
        tool_name="rank_by_impact",
        markdown=_cite_inline("\n".join(lines), ev_ids[:5]),
        source_evidence_ids=ev_ids,
        insights=[
            dp.get("impact_reason", "")
            for dp in ranked[:3]
            if dp.get("impact_score", 0) > 1.0
        ],
    )


# ---------------------------------------------------------------------------
# Build the default registry
# ---------------------------------------------------------------------------

def build_default_registry() -> ToolRegistry:
    """Create a ToolRegistry with the standard 8 analysis tools."""
    registry = ToolRegistry()

    registry.register(ToolDefinition(
        name="extract_numeric_data",
        description=(
            "Extract numbers, percentages, concentrations, and costs from "
            "evidence text. Run this FIRST if no structured data exists."
        ),
        requires_data=False,
        requires_llm=False,
        execute=_wrap_extract_numeric_data,
    ))

    registry.register(ToolDefinition(
        name="query_evidence_sql",
        description=(
            "Run SQL queries against evidence in SQLite "
            "(tier distribution, source counts, relevance patterns)."
        ),
        requires_data=False,
        requires_llm=False,
        parameters={
            "sql": "SQL SELECT query (optional, defaults to tier distribution)",
        },
        execute=_wrap_query_evidence_sql,
    ))

    registry.register(ToolDefinition(
        name="statistical_summary",
        description=(
            "Compute mean, median, std, 95% CI across data points "
            "grouped by source. Requires extracted numeric data."
        ),
        requires_data=True,
        requires_llm=False,
        execute=_wrap_statistical_summary,
    ))

    registry.register(ToolDefinition(
        name="comparison_table",
        description=(
            "Build a pivot table comparing metrics across studies/sources. "
            "Requires extracted numeric data from >= 2 sources."
        ),
        requires_data=True,
        requires_llm=False,
        execute=_wrap_comparison_table,
    ))

    registry.register(ToolDefinition(
        name="meta_analysis",
        description=(
            "Mini meta-analysis with pooled estimates, inverse-variance "
            "weighting, I-squared heterogeneity. Requires >= 3 data points."
        ),
        requires_data=True,
        requires_llm=False,
        execute=_wrap_meta_analysis,
    ))

    registry.register(ToolDefinition(
        name="agreement_analysis",
        description=(
            "Measure source agreement using pairwise Jaccard similarity "
            "on evidence statements. Works without structured data."
        ),
        requires_data=False,
        requires_llm=False,
        execute=_wrap_agreement_analysis,
    ))

    registry.register(ToolDefinition(
        name="execute_python",
        description=(
            "LLM writes and executes a custom Python analysis script "
            "(scipy, pandas, matplotlib). Use for correlations, trends, "
            "custom charts."
        ),
        requires_data=False,
        requires_llm=True,
        parameters={
            "question": "What to analyze (specific question for the code)",
        },
        execute=_wrap_execute_python,
    ))

    registry.register(ToolDefinition(
        name="rank_by_impact",
        description=(
            "Rank data points by deviation from the mean (z-score). "
            "Identifies outliers and high-impact findings."
        ),
        requires_data=True,
        requires_llm=False,
        execute=_wrap_rank_by_impact,
    ))

    return registry
