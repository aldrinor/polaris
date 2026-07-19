"""Telemetry subpackage for the pipeline A / rebuild pipeline.

Local-only, spend-free observability helpers. The first member is the
per-tool utilization tracer (I-meta-007b), which records every external
tool/API invocation (Serper, Semantic Scholar, content fetch, ...) to an
in-memory buffer plus an optional per-run ``tool_trace.jsonl`` and exposes
a per-tool summary via :meth:`ToolTracer.manifest`.

Nothing in this package performs network I/O or LLM calls.
"""
from src.polaris_graph.telemetry.tool_tracer import (
    ToolCall,
    ToolTracer,
    attach_tool_utilization,
    get_tool_tracer,
    reset_tool_tracer,
    tool_tracker_enabled,
)

__all__ = [
    "ToolCall",
    "ToolTracer",
    "attach_tool_utilization",
    "get_tool_tracer",
    "reset_tool_tracer",
    "tool_tracker_enabled",
]
