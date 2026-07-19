"""
Structured pipeline tracer for polaris graph.

Emits JSONL events to logs/pg_trace_{vector_id}.jsonl alongside
regular Python logging. Every node, LLM call, fetch, and quality
decision gets a machine-parseable trace event.

OBS-1: Standalone tracing module with zero external dependencies.
Uses stdlib only: json, time, contextvars, dataclasses, pathlib.
"""

import json
import logging
import os
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)

PG_TRACING_ENABLED = resolve("PG_TRACING_ENABLED") == "1"

# Thread-safe vector_id propagation
_current_vector_id: ContextVar[str] = ContextVar("pg_vector_id", default="unknown")
_current_tracer: ContextVar[Optional["PipelineTracer"]] = ContextVar("pg_tracer", default=None)


@dataclass
class TraceEvent:
    """A single structured trace event."""

    timestamp: str
    vector_id: str
    node: str           # "plan", "search", "analyze", "verify", "evaluate", "synthesize"
    event_type: str     # "node_start", "node_end", "fetch", "llm_call", "quality_gate", etc.
    data: dict = field(default_factory=dict)
    duration_ms: float = 0.0


class PipelineTracer:
    """Structured JSONL tracer for pipeline observability.

    Creates a JSONL file at logs/pg_trace_{vector_id}.jsonl and writes
    one event per line. Also keeps events in memory for summary.

    Usage::

        tracer = PipelineTracer("V001")
        tracer.node_start("plan", iteration=1)
        # ... do work ...
        tracer.node_end("plan", query_count=50)
        print(tracer.summary())
    """

    def __init__(self, vector_id: str, output_dir: str = "logs"):
        self.vector_id = vector_id
        # W3.3: session_id disambiguates events when multiple runs append to
        # the same pg_trace_{vector_id}.jsonl. Readers can filter by sid to
        # isolate a single pipeline execution.
        self.session_id = uuid.uuid4().hex[:12]
        self._events: list[TraceEvent] = []
        self._node_timers: dict[str, float] = {}
        self._path = Path(output_dir) / f"pg_trace_{vector_id}.jsonl"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        _current_vector_id.set(vector_id)
        _current_tracer.set(self)
        # Mark the start of this session so a new file section is parseable.
        self._emit(
            event_type="session_start",
            node="pipeline",
            data={"session_id": self.session_id},
        )

    def node_start(self, node: str, **data: Any) -> None:
        """Record node entry."""
        self._node_timers[node] = time.monotonic()
        self._emit("node_start", node, data)

    def node_end(self, node: str, **data: Any) -> None:
        """Record node exit with wall-clock duration."""
        start = self._node_timers.pop(node, time.monotonic())
        duration_ms = (time.monotonic() - start) * 1000
        self._emit("node_end", node, {**data, "duration_ms": round(duration_ms, 1)})

    def fetch(
        self,
        node: str,
        url: str,
        status: str,
        content_len: int = 0,
        duration_ms: float = 0,
        **data: Any,
    ) -> None:
        """Record a URL fetch attempt."""
        self._emit("fetch", node, {
            "url": url[:200],
            "status": status,
            "content_len": content_len,
            "duration_ms": round(duration_ms, 1),
            **data,
        })

    def llm_call(
        self,
        node: str,
        call_type: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration_ms: float = 0,
        **data: Any,
    ) -> None:
        """Record an LLM API call."""
        self._emit("llm_call", node, {
            "call_type": call_type,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "duration_ms": round(duration_ms, 1),
            **data,
        })

    def evidence(self, node: str, action: str, count: int, **data: Any) -> None:
        """Record evidence flow (extracted, filtered, deduped, accumulated)."""
        self._emit("evidence", node, {"action": action, "count": count, **data})

    def quality_gate(self, node: str, gate: str, passed: bool, **data: Any) -> None:
        """Record a quality gate check."""
        self._emit("quality_gate", node, {"gate": gate, "passed": passed, **data})

    def query(self, node: str, action: str, queries: "list[str] | int", **data: Any) -> None:
        """Record query generation/amplification."""
        count = queries if isinstance(queries, int) else len(queries)
        self._emit("query", node, {"action": action, "count": count, **data})

    def search_result(
        self,
        node: str,
        engine: str,
        query: str,
        result_count: int,
        **data: Any,
    ) -> None:
        """Record search results per query."""
        self._emit("search_result", node, {
            "engine": engine,
            "query": query,
            "result_count": result_count,
            **data,
        })

    def reasoning_capture(
        self, node: str, call_type: str, reasoning_text: str,
        prompt_excerpt: str = "", **data: Any,
    ) -> None:
        """Record LLM reasoning content from any call."""
        self._emit("reasoning_capture", node, {
            "call_type": call_type,
            "reasoning_text": reasoning_text[:50000],
            "chars": len(reasoning_text or ""),
            "prompt_excerpt": prompt_excerpt[:500],
            **data,
        })

    def storm_transcript(
        self, persona: str, round_num: int,
        question: str, answer: str, sources: list[str],
        key_findings: list[str], **data: Any,
    ) -> None:
        """Record a full STORM interview Q&A round."""
        self._emit("storm_transcript", "storm_interviews", {
            "persona": persona,
            "round": round_num,
            "question": question[:2000],
            "answer": answer[:5000],
            "sources": sources[:20],
            "key_findings": key_findings[:10],
            **data,
        })

    def iteration_decision(
        self, iteration: int, decision: str, rationale: dict,
        **data: Any,
    ) -> None:
        """Record an iteration routing decision with full rationale."""
        self._emit("iteration_decision", "evaluate", {
            "iteration": iteration,
            "decision": decision,
            "rationale": rationale,
            **data,
        })

    def summary(self) -> dict[str, Any]:
        """Return a summary of all trace events for state storage."""
        node_durations: dict[str, float] = {}
        event_counts: dict[str, int] = {}
        for e in self._events:
            event_counts[e.event_type] = event_counts.get(e.event_type, 0) + 1
            if e.event_type == "node_end" and "duration_ms" in e.data:
                node_durations[e.node] = e.data["duration_ms"]

        return {
            "total_events": len(self._events),
            "nodes": list(set(e.node for e in self._events)),
            "event_counts": event_counts,
            "node_durations_ms": node_durations,
            "trace_file": str(self._path),
        }

    def log_event(
        self, event_type: str, data: dict | None = None, node: str = "pipeline"
    ) -> None:
        """Generic event logging — public API for components like SmartArt."""
        self._emit(event_type=event_type, node=node, data=data or {})

    def _emit(self, event_type: str, node: str, data: dict) -> None:
        """Write a trace event to JSONL and memory."""
        if not PG_TRACING_ENABLED:
            return
        event = TraceEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            vector_id=self.vector_id,
            node=node,
            event_type=event_type,
            data=data,
        )
        self._events.append(event)
        # Write to JSONL file
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": event.timestamp,
                    "vid": event.vector_id,
                    # W3.3: tag every event with the session_id so readers
                    # can filter to a single pipeline run in a shared trace.
                    "sid": self.session_id,
                    "node": event.node,
                    "type": event.event_type,
                    **event.data,
                }, default=str) + "\n")
        except Exception as exc:
            logger.warning("[polaris graph] Tracing write failed: %s", exc)


def get_tracer() -> Optional[PipelineTracer]:
    """Get the current pipeline tracer (if any)."""
    return _current_tracer.get(None)
