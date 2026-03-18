"""Analysis notebook — growing record of ReAct steps with provenance.

Each step records what tool was used, what it found, and which evidence
IDs produced the result. build_synthesis_context() outputs markdown with
[CITE:ev_xxx] tokens that point to ORIGINAL sources.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field

from src.polaris_graph.contracts_v3 import AnalysisEntry
from src.polaris_graph.tools.tool_registry import ToolResult

logger = logging.getLogger("polaris_graph")


@dataclass
class AnalysisStep:
    """One step in the ReAct loop."""

    step_number: int
    reasoning: str
    tool_name: str
    result: ToolResult
    elapsed_seconds: float


class AnalysisNotebook:
    """Accumulates analysis steps and produces synthesis context with provenance."""

    def __init__(self, query: str, evidence_ids: list[str]):
        self._query = query
        self._evidence_ids = evidence_ids
        self._steps: list[AnalysisStep] = []
        self._data_points: list[dict] = []
        self._started_at = time.monotonic()

    def add_step(self, step: AnalysisStep) -> None:
        """Add a completed step and accumulate its data points."""
        self._steps.append(step)
        if step.result.success and step.result.data_points_produced:
            self._data_points.extend(step.result.data_points_produced)

    @property
    def steps(self) -> list[AnalysisStep]:
        return list(self._steps)

    @property
    def data_points(self) -> list[dict]:
        return list(self._data_points)

    @property
    def has_data(self) -> bool:
        return len(self._data_points) > 0

    @property
    def step_count(self) -> int:
        return len(self._steps)

    @property
    def successful_steps(self) -> int:
        return sum(1 for s in self._steps if s.result.success)

    def get_all_source_evidence_ids(self) -> list[str]:
        """Collect all unique evidence IDs across all successful steps."""
        ids = []
        seen = set()
        for step in self._steps:
            if step.result.success:
                for eid in step.result.source_evidence_ids:
                    if eid not in seen:
                        ids.append(eid)
                        seen.add(eid)
        return ids

    def build_synthesis_context(self) -> str:
        """Build markdown context with [CITE:ev_xxx] tokens for synthesis.

        Priority rules:
        1. If interpret_results exists, lead with it (the analytical prose)
        2. Follow with extract_numeric_data (structured data for reference)
        3. Skip comparison_table and statistical_summary entirely —
           the interpretation already incorporates their findings, and
           raw pivot tables are unreadable noise for the section writer

        This ensures the section writer sees ANALYSIS first, then
        supporting data — never raw stat dumps or sparse pivot tables.
        """
        if not self._steps:
            return ""

        has_interpretation = any(
            s.tool_name == "interpret_results" and s.result.success
            for s in self._steps
        )

        # Tools to SKIP when interpretation exists (it supersedes them)
        skip_when_interpreted = {
            "comparison_table", "statistical_summary", "query_evidence_sql",
        }

        sections = []

        # Pass 1: interpretation first (if it exists)
        if has_interpretation:
            for step in self._steps:
                if step.tool_name == "interpret_results" and step.result.success:
                    sections.append("### Research Analysis")
                    sections.append("")
                    sections.append(step.result.markdown)
                    sections.append("")
                    break

        # Pass 2: supporting raw data (extraction only, skip stats/tables)
        for step in self._steps:
            if not step.result.success:
                continue
            if step.tool_name == "interpret_results":
                continue  # Already added above

            if has_interpretation and step.tool_name in skip_when_interpreted:
                continue  # Interpretation supersedes these

            tool_title = step.result.tool_name.replace("_", " ").title()
            sections.append(f"### {tool_title}")
            sections.append("")
            sections.append(step.result.markdown)

            if step.result.insights:
                sections.append("")
                for insight in step.result.insights:
                    sections.append(f"- {insight}")

            sections.append("")

        return "\n".join(sections)

    def summary_for_llm(self) -> str:
        """Compact summary for the ReAct planner's next decision."""
        lines = [
            f"Query: {self._query}",
            f"Evidence pool: {len(self._evidence_ids)} pieces",
            f"Steps completed: {self.step_count} "
            f"({self.successful_steps} successful)",
            f"Data points extracted: {len(self._data_points)}",
            "",
            "Steps so far:",
        ]

        for step in self._steps:
            status = "OK" if step.result.success else "FAILED"
            lines.append(
                f"  {step.step_number}. {step.tool_name} [{status}] "
                f"({step.elapsed_seconds:.1f}s) — {step.reasoning[:60]}"
            )

        return "\n".join(lines)

    def to_entries(self) -> list[AnalysisEntry]:
        """Convert successful steps to AnalysisEntry contracts."""
        entries = []
        for step in self._steps:
            if not step.result.success:
                continue

            entries.append(AnalysisEntry(
                entry_id=f"analysis_{uuid.uuid4().hex[:8]}",
                analysis_type=step.result.tool_name,
                title=step.reasoning[:100],
                markdown=step.result.markdown,
                source_evidence_ids=step.result.source_evidence_ids,
                statistics=step.result.statistics,
                image_base64=(
                    step.result.charts[0].get("image_base64", "")
                    if step.result.charts
                    else ""
                ),
                insights=step.result.insights,
            ))

        return entries
