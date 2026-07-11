"""Analysis notebook — growing record of ReAct steps with provenance.

Each step records what tool was used, what it found, and which evidence
IDs produced the result. build_synthesis_context() outputs markdown with
[CITE:ev_xxx] tokens that point to ORIGINAL sources.
"""

import logging
import os
import time
import uuid
from dataclasses import dataclass, field

from src.polaris_graph.contracts_v3 import AnalysisEntry
from src.polaris_graph.tools.tool_registry import ToolResult

logger = logging.getLogger("polaris_graph")

# LAW VI: every knob env-tunable. Per-step character budget for the result digest that
# ``summary_for_llm(include_results=True)`` hands the planner. 0 disables the digest.
PG_NOTEBOOK_SUMMARY_RESULT_CHARS_DEFAULT = 600


def _summary_result_chars() -> int:
    raw = os.getenv(
        "PG_NOTEBOOK_SUMMARY_RESULT_CHARS",
        str(PG_NOTEBOOK_SUMMARY_RESULT_CHARS_DEFAULT),
    )
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        logger.warning(
            "[analysis_notebook] PG_NOTEBOOK_SUMMARY_RESULT_CHARS=%r is not an int; "
            "using default %d",
            raw, PG_NOTEBOOK_SUMMARY_RESULT_CHARS_DEFAULT,
        )
        return PG_NOTEBOOK_SUMMARY_RESULT_CHARS_DEFAULT


def _scalar(value) -> str:
    """Render a statistic VERBATIM — never reformat a number.

    ``str(1234567.89)`` -> ``'1234567.89'``. (``f'{v:g}'`` would emit ``1.23457e+06``
    and silently mangle the very value the planner needs; strict numeric verification
    downstream compares digits.)
    """
    return str(value)


def _result_digest_lines(result: ToolResult, budget: int) -> list[str]:
    """Planner-facing digest of ONE successful step's payload, capped at ``budget`` chars.

    Priority order = information density: statistics (the numbers) -> insights -> markdown
    fills the remainder. Nothing is dropped by KIND (weight-and-consolidate, not filter);
    when the budget runs out the omission is DISCLOSED inline ("+N more") rather than
    silently swallowed, because a silently-dropped computed number is exactly the failure
    this digest exists to end.
    """
    out: list[str] = []
    spent = 0

    def _emit(line: str) -> bool:
        """Emit if it fits. Returns False once the budget is exhausted."""
        nonlocal spent
        if spent + len(line) > budget:
            return False
        out.append(line)
        spent += len(line)
        return True

    stats = result.statistics if isinstance(result.statistics, dict) else {}
    if stats:
        pairs = [f"{k}={_scalar(v)}" for k, v in stats.items()]
        shown: list[str] = []
        for i, pair in enumerate(pairs):
            candidate = ", ".join([*shown, pair])
            if len(f"stats: {candidate}") > budget and shown:
                out.append(
                    f"stats: {', '.join(shown)} (+{len(pairs) - i} more omitted for length)"
                )
                spent += budget  # budget is spent; markdown/insights yield to the numbers
                break
            shown.append(pair)
        else:
            if shown:
                _emit(f"stats: {', '.join(shown)}")

    for insight in (result.insights or []):
        if not _emit(f"insight: {insight}"):
            break

    md = (result.markdown or "").strip()
    if md:
        remaining = budget - spent
        if remaining > 0:
            flat = " ".join(md.split())
            if len(flat) > remaining:
                flat = flat[:remaining] + "…"
            out.append(f"result: {flat}")

    return out


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
        # PQ-4: Keep comparison_table — it provides supplementary
        # context the writer can use for structured comparisons
        skip_when_interpreted = {
            "statistical_summary", "query_evidence_sql",
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

    def summary_for_llm(self, include_results: bool = False) -> str:
        """Compact summary for the ReAct planner's next decision.

        W4 (2026-07-11): ``include_results`` is OPT-IN and defaults to False, so the
        long-standing consumer (``react_agent.py``:7875) keeps its byte-identical string.
        With ``include_results=True`` (the OutlineAgent decide prompt,
        ``outline_agent.py``:1163) each SUCCESSFUL step also emits a RESULT DIGEST.

        Why: before this, ``summary_for_llm()`` was the ONLY notebook accessor fed to the
        outline decide LLM, and it printed only ``{n}. {tool} [{status}] ({elapsed}s) —
        {reasoning[:60]}``. A successful ``execute_python`` therefore recorded no gap (so
        nothing was disclosed) while its computed value — present in ``.statistics``,
        ``.insights`` AND ``.markdown`` — was unreachable by the planner: an UNDISCLOSED
        UNREACHABLE RESULT, and a tool that was strictly net-negative (it burned a turn and
        an OpenRouterClient for zero observable effect).

        WEIGHT-AND-CONSOLIDATE, never filter (docs/agentic_outline_redesign.md): nothing is
        dropped by kind. Statistics come first (they are the numbers), then insights, then
        markdown fills whatever character budget is left. The per-step budget is env-tunable
        (LAW VI) via ``PG_NOTEBOOK_SUMMARY_RESULT_CHARS`` (default 600); set it to 0 to
        suppress the digest entirely.

        This digest is PLANNER-FACING ONLY. It does not create a render path: exploratory
        ``execute_python`` output remains BARRED from the report, which renders computed
        numbers only through the verified ``[#calc:]`` / ``ModelSpec`` lane.
        """
        lines = [
            f"Query: {self._query}",
            f"Evidence pool: {len(self._evidence_ids)} pieces",
            f"Steps completed: {self.step_count} "
            f"({self.successful_steps} successful)",
            f"Data points extracted: {len(self._data_points)}",
            "",
            "Steps so far:",
        ]

        budget = _summary_result_chars() if include_results else 0

        for step in self._steps:
            status = "OK" if step.result.success else "FAILED"
            lines.append(
                f"  {step.step_number}. {step.tool_name} [{status}] "
                f"({step.elapsed_seconds:.1f}s) — {step.reasoning[:60]}"
            )
            if budget > 0 and step.result.success:
                lines.extend(
                    f"     {ln}" for ln in _result_digest_lines(step.result, budget)
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
