"""
Real-time Rich terminal dashboard for polaris graph pipeline.

Displays live progress during pipeline execution using Rich library.
Updates on every astream() event from LangGraph.
"""

import logging
import time
from typing import Any, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


class PipelineDashboard:
    """Real-time terminal dashboard for polaris graph runs.

    Usage:
        dashboard = PipelineDashboard(vector_id="V001", budget=150.0)
        with dashboard:
            async for event in app.astream(state, ...):
                dashboard.update_from_event(event)
    """

    # Node display order and pretty names
    NODE_ORDER = [
        "plan", "search", "storm_interviews", "analyze", "verify",
        "evaluate", "synthesize", "search_gaps",
    ]
    NODE_LABELS = {
        "plan": "Plan",
        "search": "Search",
        "storm_interviews": "STORM",
        "analyze": "Analyze",
        "verify": "Verify",
        "evaluate": "Evaluate",
        "synthesize": "Synthesize",
        "search_gaps": "Gap Search",
    }

    def __init__(
        self,
        vector_id: str = "",
        budget: float = 150.0,
        console: Optional[Console] = None,
    ):
        self.vector_id = vector_id
        self.budget = budget
        self.console = console or Console()
        self._live: Optional[Live] = None
        self._start_time = time.monotonic()

        # State tracking
        self._current_node: str = ""
        self._completed_nodes: set[str] = set()
        self._node_details: dict[str, str] = {}
        self._iteration: int = 0
        self._cost: float = 0.0
        self._evidence_count: int = 0
        self._claims_count: int = 0
        self._faithfulness: float = -1.0
        self._word_count: int = 0
        self._citation_count: int = 0
        self._source_count: int = 0
        self._status: str = "initializing"
        self._custom_messages: list[str] = []
        self._search_details: dict[str, int] = {}

    def __enter__(self):
        self._start_time = time.monotonic()
        self._live = Live(
            self._build_display(),
            console=self.console,
            refresh_per_second=2,
            transient=False,
        )
        self._live.__enter__()
        return self

    def __exit__(self, *args):
        if self._live:
            self._live.__exit__(*args)

    def update_from_event(self, event: dict[str, Any]) -> None:
        """Update dashboard from an astream() event.

        astream(stream_mode="updates") yields dicts like:
        {"node_name": {"key": value, ...}}

        astream(stream_mode=["updates", "custom"]) can also yield
        custom writer events.
        """
        if not event or not isinstance(event, dict):
            return

        for node_name, node_output in event.items():
            if not isinstance(node_output, dict):
                continue

            # Track node completion
            self._completed_nodes.add(node_name)
            self._current_node = node_name

            # Extract metrics from node output
            self._extract_metrics(node_name, node_output)

        self._refresh()

    def update_custom(
        self,
        phase: str = "",
        progress: int = 0,
        message: str = "",
        **kwargs,
    ) -> None:
        """Update from a custom stream writer event."""
        if phase:
            self._current_node = phase
        if message:
            self._custom_messages.append(message)
            # Keep last 5 messages
            if len(self._custom_messages) > 5:
                self._custom_messages = self._custom_messages[-5:]
        for key, value in kwargs.items():
            if key == "cost":
                self._cost = float(value)
            elif key == "evidence_count":
                self._evidence_count = int(value)
            elif key == "faithfulness":
                self._faithfulness = float(value)
        self._refresh()

    def node_start(self, node_name: str, **details) -> None:
        """Mark a node as currently running."""
        self._current_node = node_name
        detail_parts = [f"{k}={v}" for k, v in details.items()]
        if detail_parts:
            self._node_details[node_name] = ", ".join(detail_parts)
        self._refresh()

    def node_end(self, node_name: str, **details) -> None:
        """Mark a node as complete."""
        self._completed_nodes.add(node_name)
        detail_parts = [f"{k}={v}" for k, v in details.items()]
        if detail_parts:
            self._node_details[node_name] = ", ".join(detail_parts)
        self._refresh()

    def _extract_metrics(self, node: str, output: dict) -> None:
        """Extract relevant metrics from node output."""
        # Evidence count
        if "evidence" in output:
            ev = output["evidence"]
            if isinstance(ev, list):
                self._evidence_count = len(ev)

        # Claims
        if "claims" in output:
            claims = output["claims"]
            if isinstance(claims, list):
                self._claims_count = len(claims)

        # Faithfulness
        if "faithfulness_score" in output:
            self._faithfulness = output["faithfulness_score"]

        # Quality metrics
        qm = output.get("quality_metrics")
        if isinstance(qm, dict):
            self._word_count = qm.get("total_words", self._word_count)
            self._citation_count = qm.get("total_citations", self._citation_count)
            self._source_count = qm.get("unique_sources", self._source_count)

        # LLM usage / cost
        usage = output.get("llm_usage")
        if isinstance(usage, dict):
            self._cost = usage.get("total_cost_usd", self._cost)

        # Iteration
        if "iteration_count" in output:
            self._iteration = output["iteration_count"]

        # Status
        if "status" in output:
            self._status = output["status"]

        # Search details
        if node == "search":
            if "web_results" in output:
                wr = output["web_results"]
                self._search_details["web"] = len(wr) if isinstance(wr, list) else 0
            if "academic_results" in output:
                ar = output["academic_results"]
                self._search_details["academic"] = len(ar) if isinstance(ar, list) else 0
            if "agentic_search_rounds" in output:
                self._search_details["rounds"] = output["agentic_search_rounds"]

    def _refresh(self) -> None:
        """Refresh the live display."""
        if self._live:
            self._live.update(self._build_display())

    def _build_display(self) -> Panel:
        """Build the full dashboard panel."""
        elapsed = time.monotonic() - self._start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        # Header
        header = f"POLARIS GRAPH -- {self.vector_id} -- LIVE"

        # Node status table
        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("Phase", style="bold", width=14)
        table.add_column("Status", width=8, justify="center")
        table.add_column("Details", ratio=1)

        for node in self.NODE_ORDER:
            label = self.NODE_LABELS.get(node, node)
            details = self._node_details.get(node, "")

            if node in self._completed_nodes and node != self._current_node:
                status = Text("DONE", style="bold green")
            elif node == self._current_node:
                status = Text("LIVE", style="bold yellow")
            else:
                status = Text("--", style="dim")

            # Add search sub-details
            if node == "search" and self._search_details:
                parts = []
                if "web" in self._search_details:
                    parts.append(f"web={self._search_details['web']}")
                if "academic" in self._search_details:
                    parts.append(f"acad={self._search_details['academic']}")
                if "rounds" in self._search_details:
                    parts.append(f"rounds={self._search_details['rounds']}")
                if parts:
                    details = ", ".join(parts)

            table.add_row(label, status, details)

        # Metrics row
        metrics_table = Table(show_header=False, expand=True, box=None)
        metrics_table.add_column(ratio=1)
        metrics_table.add_column(ratio=1)
        metrics_table.add_column(ratio=1)
        metrics_table.add_column(ratio=1)

        faith_str = f"{self._faithfulness:.1%}" if self._faithfulness >= 0 else "N/A"
        budget_remaining = self.budget - self._cost

        metrics_table.add_row(
            f"Evidence: {self._evidence_count}",
            f"Claims: {self._claims_count}",
            f"Faith: {faith_str}",
            f"Iter: {self._iteration}",
        )
        metrics_table.add_row(
            f"Words: {self._word_count:,}",
            f"Citations: {self._citation_count}",
            f"Sources: {self._source_count}",
            f"Status: {self._status}",
        )

        # Footer
        footer_table = Table(show_header=False, expand=True, box=None)
        footer_table.add_column(ratio=1)
        footer_table.add_column(ratio=1)
        footer_table.add_column(ratio=1)
        footer_table.add_row(
            f"Cost: ${self._cost:.2f}",
            f"Time: {minutes}:{seconds:02d}",
            f"Budget: ${budget_remaining:.2f} remaining",
        )

        # Custom messages
        msg_text = ""
        if self._custom_messages:
            msg_text = "\n".join(f"  > {m}" for m in self._custom_messages[-3:])

        # Compose
        from rich.console import Group
        parts = [table, Text(""), metrics_table]
        if msg_text:
            parts.append(Text(msg_text, style="dim italic"))
        parts.append(Text(""))
        parts.append(footer_table)

        return Panel(
            Group(*parts),
            title=header,
            border_style="bright_blue",
        )
