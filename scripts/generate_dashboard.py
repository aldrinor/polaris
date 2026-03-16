"""
POLARIS Research Observatory Dashboard Generator.

Reads a JSONL trace file produced by PipelineTracer and generates
a self-contained HTML file with a modern three-panel layout inspired by
Consensus.app, Perplexity, and ChatGPT Deep Research.

Layout:
  LEFT:   Pipeline navigator sidebar (220px fixed)
  CENTER: Report & analysis (scrollable, all sections visible)
  RIGHT:  Evidence panel (320px fixed, independently scrollable)

All CSS and JS are inline. Only external dependency: Google Fonts (Inter).

CLI: python scripts/generate_dashboard.py \
       --trace logs/pg_trace_V001.jsonl \
       --output outputs/dashboard_V001.html
"""

import argparse
import html
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def _load_events(trace_path: str) -> list[dict]:
    """Load all JSONL events from trace file."""
    events = []
    with open(trace_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError as exc:
                print(f"  WARN: Skipping malformed line {line_num}: {exc}")
    return events


def _group_by_type(events: list[dict]) -> dict[str, list[dict]]:
    """Group events by their 'type' field."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        grouped[ev.get("type", "unknown")].append(ev)
    return grouped


def _esc(text) -> str:
    """HTML-escape text for safe embedding."""
    return html.escape(str(text)) if text else ""


def _format_duration(ms: float) -> str:
    """Format milliseconds as human-readable duration."""
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60000:
        return f"{ms / 1000:.1f}s"
    minutes = ms / 60000
    if minutes < 60:
        return f"{minutes:.1f}min"
    hours = minutes / 60
    return f"{hours:.1f}h"


def _format_cost(cost: float) -> str:
    """Format cost as USD string."""
    if cost < 0.01:
        return f"${cost:.4f}"
    return f"${cost:.2f}"


def _truncate(text: str, limit: int = 200) -> str:
    """Truncate text with ellipsis."""
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _extract_domain(url: str) -> str:
    """Extract domain from URL for display."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or url[:40]
    except Exception:
        return url[:40] if url else "unknown"


# ---------------------------------------------------------------------------
# Key metrics extraction
# ---------------------------------------------------------------------------

def _extract_key_metrics(grouped: dict) -> dict:
    """Extract key pipeline metrics from grouped events.

    Returns a dict with: faithfulness, final_evidence, total_words,
    total_citations, unique_sources, gate_passed, cost, total_duration,
    gold, silver, bronze, query, vector_id, iterations.
    """
    # --- Pipeline start metadata ---
    pipeline_starts = grouped.get("pipeline_start", [])
    query = ""
    vector_id = "unknown"
    if pipeline_starts:
        ps = pipeline_starts[0]
        query = ps.get("query", "")
        vector_id = ps.get("vector_id", ps.get("vid", "unknown"))

    # --- Quality gate metrics ---
    gate_events = grouped.get("quality_gate", [])
    final_gate = None
    for g in reversed(gate_events):
        if g.get("gate") in ("post_synthesis_final", "post_synthesis"):
            final_gate = g
            break

    total_words = final_gate.get("total_words", 0) if final_gate else 0
    total_citations = final_gate.get("total_citations", 0) if final_gate else 0
    unique_sources = final_gate.get("unique_sources", 0) if final_gate else 0
    gate_passed = final_gate.get("passed", False) if final_gate else False

    # --- Faithfulness from iteration_decision ---
    faithfulness = 0.0
    iter_decisions = grouped.get("iteration_decision", [])
    faith_history = []
    for d in iter_decisions:
        rationale = d.get("rationale", {})
        fs = rationale.get("faithfulness_score", 0)
        if fs > 0:
            faith_history.append(fs)
    if faith_history:
        faithfulness = faith_history[-1]

    # --- Evidence counts and tiers ---
    evidence_events = grouped.get("evidence", [])
    final_evidence = 0
    gold = 0
    silver = 0
    bronze = 0
    for e in evidence_events:
        action = e.get("action", "")
        if action in ("report_assembled", "accumulated", "verified",
                       "extracted", "relevance_scored"):
            final_evidence = max(final_evidence, e.get("count", 0))
        if action == "extracted":
            gold = max(gold, e.get("gold", 0))
            silver = max(silver, e.get("silver", 0))
            bronze = max(bronze, e.get("bronze", 0))

    # --- Duration ---
    node_ends = grouped.get("node_end", [])
    total_duration = sum(e.get("duration_ms", 0) for e in node_ends)

    # --- Cost ---
    llm_calls = grouped.get("llm_call", [])
    reasoning_evts = grouped.get("reasoning_capture", [])

    # Try cumulative_cost from llm_calls first
    cumulative_costs = [c.get("cumulative_cost_usd", 0) for c in llm_calls if c.get("cumulative_cost_usd", 0) > 0]
    if cumulative_costs:
        cost = max(cumulative_costs)
    else:
        # Fallback: estimate from tokens
        tok_in = max(
            sum(e.get("input_tokens", 0) for e in reasoning_evts),
            sum(e.get("input_tokens", 0) for e in llm_calls),
        )
        tok_out = max(
            sum(e.get("output_tokens", 0) for e in reasoning_evts),
            sum(e.get("output_tokens", 0) for e in llm_calls),
        )
        cost = (tok_in * 1.50 + tok_out * 6.00) / 1_000_000

    # --- Iterations ---
    iterations = len(iter_decisions)

    # --- LLM stats ---
    total_tokens_in = sum(c.get("input_tokens", 0) for c in llm_calls)
    total_tokens_out = sum(c.get("output_tokens", 0) for c in llm_calls)

    return {
        "faithfulness": faithfulness,
        "faith_history": faith_history,
        "final_evidence": final_evidence,
        "total_words": total_words,
        "total_citations": total_citations,
        "unique_sources": unique_sources,
        "gate_passed": gate_passed,
        "cost": cost,
        "total_duration": total_duration,
        "gold": gold,
        "silver": silver,
        "bronze": bronze,
        "query": query,
        "vector_id": vector_id,
        "iterations": iterations,
        "llm_calls": len(llm_calls),
        "total_tokens_in": total_tokens_in,
        "total_tokens_out": total_tokens_out,
    }


# ---------------------------------------------------------------------------
# Phase timeline data extraction
# ---------------------------------------------------------------------------

_PHASE_ORDER = [
    "plan", "search", "storm_interviews", "analyze",
    "verify", "evaluate", "synthesize", "report",
]

_PHASE_LABELS = {
    "plan": "Plan",
    "search": "Search",
    "storm_interviews": "STORM",
    "analyze": "Analyze",
    "verify": "Verify",
    "evaluate": "Evaluate",
    "synthesize": "Synthesize",
    "report": "Report",
}

_PHASE_ICONS = {
    "plan": "&#9881;",       # gear
    "search": "&#128269;",   # magnifying glass
    "storm_interviews": "&#9889;",  # lightning
    "analyze": "&#128200;",  # chart
    "verify": "&#9989;",     # check
    "evaluate": "&#9878;",   # balance
    "synthesize": "&#9998;", # pencil
    "report": "&#128196;",   # page
}


def _get_phase_status(grouped: dict) -> dict[str, str]:
    """Determine status (done/active/pending) for each pipeline phase."""
    node_starts = {e.get("node") for e in grouped.get("node_start", [])}
    node_ends = {e.get("node") for e in grouped.get("node_end", [])}

    status = {}
    for phase in _PHASE_ORDER:
        if phase in node_ends:
            status[phase] = "done"
        elif phase in node_starts:
            status[phase] = "active"
        else:
            status[phase] = "pending"
    return status


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

def _build_css() -> str:
    """Modern dark-mode CSS with three-panel layout."""
    return """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --bg-primary: #0a0a0a;
  --bg-secondary: #141414;
  --bg-tertiary: #1a1a1a;
  --bg-hover: #1f1f1f;
  --bg-card: #141414;
  --text-primary: #e5e5e5;
  --text-secondary: #a3a3a3;
  --text-tertiary: #737373;
  --accent: #22c55e;
  --accent-dim: rgba(34, 197, 94, 0.15);
  --accent-blue: #3b82f6;
  --accent-blue-dim: rgba(59, 130, 246, 0.15);
  --accent-amber: #f59e0b;
  --accent-amber-dim: rgba(245, 158, 11, 0.15);
  --accent-red: #ef4444;
  --accent-red-dim: rgba(239, 68, 68, 0.15);
  --border: #262626;
  --border-active: #404040;
  --gold: #eab308;
  --gold-dim: rgba(234, 179, 8, 0.15);
  --silver: #94a3b8;
  --silver-dim: rgba(148, 163, 184, 0.15);
  --bronze: #d97706;
  --bronze-dim: rgba(217, 119, 6, 0.15);
  --font-sans: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
  --font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'Menlo', monospace;
  --radius: 8px;
  --radius-sm: 6px;
  --radius-lg: 12px;
  --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 1px 2px rgba(0,0,0,0.2);
  --shadow-lg: 0 4px 12px rgba(0,0,0,0.4);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html { scroll-behavior: smooth; }

body {
  font-family: var(--font-sans);
  background: var(--bg-primary);
  color: var(--text-primary);
  line-height: 1.6;
  font-size: 14px;
  display: flex;
  min-height: 100vh;
  overflow: hidden;
}

/* ---- LEFT SIDEBAR ---- */
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: 220px;
  height: 100vh;
  background: var(--bg-tertiary);
  border-right: 1px solid var(--border);
  padding: 20px 0;
  overflow-y: auto;
  z-index: 100;
  display: flex;
  flex-direction: column;
}

.sidebar-logo {
  padding: 0 16px 16px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
}

.sidebar-logo h1 {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: -0.02em;
}

.sidebar-logo .subtitle {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 2px;
}

.sidebar-section {
  padding: 8px 12px 4px;
}

.sidebar-section-title {
  font-size: 10px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-weight: 600;
  padding: 0 4px;
  margin-bottom: 4px;
}

.sidebar a {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  color: var(--text-secondary);
  text-decoration: none;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 1px;
  transition: background 0.15s, color 0.15s;
  cursor: pointer;
}

.sidebar a:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.sidebar a.active {
  background: var(--accent-dim);
  color: var(--accent);
}

.sidebar a .nav-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}

.nav-dot-done { background: var(--accent); }
.nav-dot-active { background: var(--accent-blue); animation: pulse 1.5s infinite; }
.nav-dot-pending { background: var(--text-tertiary); opacity: 0.4; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.sidebar-query {
  padding: 12px 16px;
  margin-top: auto;
  border-top: 1px solid var(--border);
}

.sidebar-query-label {
  font-size: 10px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.sidebar-query-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* ---- CENTER PANEL ---- */
.center {
  margin-left: 220px;
  margin-right: 320px;
  min-height: 100vh;
  overflow-y: auto;
  height: 100vh;
  padding: 24px 32px 64px;
}

/* ---- RIGHT PANEL ---- */
.evidence-panel {
  position: fixed;
  top: 0;
  right: 0;
  width: 320px;
  height: 100vh;
  background: var(--bg-tertiary);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.evidence-panel-header {
  padding: 16px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.evidence-panel-header h2 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.evidence-filter {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-family: var(--font-sans);
  cursor: pointer;
  outline: none;
}

.evidence-filter:focus { border-color: var(--accent); }

.evidence-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.evidence-card {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px;
  margin-bottom: 8px;
  transition: border-color 0.15s;
}

.evidence-card:hover { border-color: var(--border-active); }

.evidence-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.tier-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  flex-shrink: 0;
}

.tier-gold { background: var(--gold-dim); color: var(--gold); }
.tier-silver { background: var(--silver-dim); color: var(--silver); }
.tier-bronze { background: var(--bronze-dim); color: var(--bronze); }

.evidence-card .domain {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.evidence-card .quote {
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 8px;
}

.signal-bars {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.signal-bar {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  color: var(--text-tertiary);
}

.signal-bar-track {
  width: 32px;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}

.signal-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.3s;
}

.evidence-card .perspective-tag {
  font-size: 10px;
  color: var(--accent-blue);
  background: var(--accent-blue-dim);
  padding: 1px 6px;
  border-radius: 3px;
  margin-left: auto;
}

.evidence-count-badge {
  font-size: 11px;
  color: var(--text-tertiary);
  background: var(--bg-primary);
  padding: 2px 8px;
  border-radius: 10px;
}

/* ---- HERO SECTION ---- */
.hero-header {
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}

.hero-header h1 {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 4px;
}

.hero-header .vector-id {
  font-size: 13px;
  color: var(--text-secondary);
}

.hero-header .query-text {
  font-size: 14px;
  color: var(--text-secondary);
  margin-top: 8px;
  line-height: 1.5;
  max-width: 700px;
}

.hero-metrics {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 12px;
  margin-bottom: 24px;
}

.hero-metrics-row2 {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.metric-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  transition: border-color 0.15s;
}

.metric-card:hover { border-color: var(--border-active); }

.metric-card .label {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
  margin-bottom: 6px;
}

.metric-card .value {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

.metric-card .sub {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.metric-card-faith {
  display: flex;
  align-items: center;
  gap: 20px;
}

.faith-gauge {
  flex-shrink: 0;
}

.faith-details .value {
  font-size: 36px;
  font-weight: 700;
}

/* ---- EVIDENCE STRENGTH METER ---- */
.strength-meter {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  margin-bottom: 24px;
}

.strength-meter h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.strength-label {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
}

.strength-strong { background: var(--accent-dim); color: var(--accent); }
.strength-moderate { background: var(--accent-amber-dim); color: var(--accent-amber); }
.strength-weak { background: var(--accent-red-dim); color: var(--accent-red); }
.strength-insufficient { background: rgba(115,115,115,0.15); color: var(--text-tertiary); }

.meter-bar-container {
  height: 24px;
  border-radius: 12px;
  background: var(--bg-primary);
  display: flex;
  overflow: hidden;
  margin-bottom: 10px;
}

.meter-segment {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: rgba(0,0,0,0.7);
  min-width: 0;
  transition: width 0.4s ease;
}

.meter-gold { background: var(--gold); }
.meter-silver { background: var(--silver); }
.meter-bronze { background: var(--bronze); }

.meter-legend {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

.meter-legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.meter-legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ---- PIPELINE FLOW ---- */
.pipeline-flow {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px 20px;
  margin-bottom: 24px;
  overflow-x: auto;
}

.pipeline-flow h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 14px;
}

.flow-container {
  display: flex;
  align-items: center;
  gap: 0;
  min-width: fit-content;
}

.flow-phase {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.flow-phase:hover { border-color: var(--border-active); }

.flow-phase-done {
  border-color: rgba(34,197,94,0.3);
  background: rgba(34,197,94,0.06);
}

.flow-phase-active {
  border-color: rgba(59,130,246,0.4);
  background: rgba(59,130,246,0.08);
  animation: pulse-border 2s infinite;
}

@keyframes pulse-border {
  0%, 100% { border-color: rgba(59,130,246,0.4); }
  50% { border-color: rgba(59,130,246,0.15); }
}

.flow-phase-pending { opacity: 0.4; }

.flow-phase .phase-icon { font-size: 14px; }

.flow-phase .phase-name {
  font-size: 12px;
  font-weight: 600;
}

.flow-phase .phase-status {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.phase-status-done { background: var(--accent); }
.phase-status-active { background: var(--accent-blue); animation: pulse 1.5s infinite; }
.phase-status-pending { background: var(--text-tertiary); opacity: 0.4; }

.flow-arrow {
  color: var(--text-tertiary);
  font-size: 14px;
  padding: 0 6px;
  flex-shrink: 0;
}

/* ---- SECTION STYLES ---- */
.section {
  margin-bottom: 28px;
  scroll-margin-top: 20px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
}

.section-header h2 {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.section-badge {
  font-size: 11px;
  background: var(--bg-secondary);
  color: var(--text-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

/* ---- FUNNEL ---- */
.funnel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 650px;
}

.funnel-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.funnel-label {
  min-width: 110px;
  font-size: 12px;
  color: var(--text-secondary);
  text-align: right;
  font-weight: 500;
}

.funnel-bar-track {
  flex: 1;
  height: 28px;
  background: var(--bg-secondary);
  border-radius: 6px;
  overflow: hidden;
  position: relative;
}

.funnel-bar-fill {
  height: 100%;
  border-radius: 6px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  font-size: 12px;
  font-weight: 600;
  color: white;
  min-width: fit-content;
  transition: width 0.5s ease;
}

.funnel-pct {
  font-size: 11px;
  color: var(--text-tertiary);
  min-width: 40px;
  text-align: right;
}

/* ---- QUALITY GATE CARDS ---- */
.gate-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.gate-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
}

.gate-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.gate-card-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
}

.gate-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}

.gate-pass { background: var(--accent-dim); color: var(--accent); }
.gate-fail { background: var(--accent-red-dim); color: var(--accent-red); }

.gate-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.gate-bar-track {
  height: 6px;
  background: var(--bg-primary);
  border-radius: 3px;
  position: relative;
  overflow: hidden;
}

.gate-bar-fill {
  height: 100%;
  border-radius: 3px;
  position: absolute;
  left: 0;
  top: 0;
}

.gate-threshold {
  position: absolute;
  top: -2px;
  width: 2px;
  height: 10px;
  background: var(--text-tertiary);
  border-radius: 1px;
}

.gate-sub {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 6px;
}

/* ---- STORM CHAT ---- */
.storm-personas {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.storm-persona-tab {
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.storm-persona-tab:hover { border-color: var(--border-active); color: var(--text-primary); }

.storm-persona-tab.active {
  border-color: var(--accent-blue);
  background: var(--accent-blue-dim);
  color: var(--accent-blue);
}

.storm-conversation { display: none; }
.storm-conversation.active { display: block; }

.storm-round { margin-bottom: 16px; }

.storm-q, .storm-a {
  padding: 10px 14px;
  border-radius: 12px;
  margin-bottom: 6px;
  max-width: 88%;
  font-size: 13px;
  line-height: 1.5;
}

.storm-q {
  background: var(--accent-blue);
  color: white;
  margin-left: auto;
  text-align: right;
  border-bottom-right-radius: 4px;
}

.storm-a {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.storm-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.storm-failed {
  border: 1px solid var(--accent-red);
}

/* ---- TABLES ---- */
table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

thead th {
  text-align: left;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-tertiary);
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

tbody td {
  padding: 6px 10px;
  border-bottom: 1px solid rgba(38,38,38,0.5);
  vertical-align: top;
}

tbody tr:nth-child(even) { background: rgba(20,20,20,0.3); }
tbody tr:hover { background: rgba(34,197,94,0.04); }

/* ---- TAGS / BADGES ---- */
.tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}

.tag-success { background: var(--accent-dim); color: var(--accent); }
.tag-error { background: var(--accent-red-dim); color: var(--accent-red); }
.tag-warning { background: var(--accent-amber-dim); color: var(--accent-amber); }
.tag-info { background: var(--accent-blue-dim); color: var(--accent-blue); }

/* ---- DETAILS (sub-items only) ---- */
details {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 8px;
  overflow: hidden;
}

details > summary {
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 500;
  font-size: 13px;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 8px;
  user-select: none;
  transition: background 0.15s;
  color: var(--text-secondary);
}

details > summary:hover { background: var(--bg-hover); }

details > summary::before {
  content: '\\25B6';
  font-size: 9px;
  transition: transform 0.2s;
  color: var(--accent);
}

details[open] > summary::before { transform: rotate(90deg); }

details .detail-body {
  padding: 12px 14px;
  border-top: 1px solid var(--border);
}

/* ---- CODE / PRE ---- */
pre, code {
  font-family: var(--font-mono);
  font-size: 12px;
}

pre {
  background: var(--bg-primary);
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 300px;
  overflow-y: auto;
  line-height: 1.5;
  border: 1px solid var(--border);
  color: var(--text-secondary);
}

/* ---- REASONING CARDS ---- */
.reasoning-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px;
  margin-bottom: 10px;
}

.reasoning-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.reasoning-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-blue);
}

/* ---- FAITH TREND ---- */
.faith-trend {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  height: 60px;
  margin-bottom: 12px;
}

.faith-bar {
  flex: 1;
  border-radius: 4px 4px 0 0;
  min-width: 30px;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  color: var(--text-primary);
  padding-top: 4px;
  transition: height 0.3s;
}

/* ---- VERDICT BREAKDOWN ---- */
.verdict-bar-container {
  display: flex;
  height: 20px;
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-primary);
  margin-bottom: 8px;
  max-width: 400px;
}

.verdict-seg { height: 100%; min-width: 0; }
.verdict-supported { background: var(--accent); }
.verdict-partial { background: var(--accent-amber); }
.verdict-not-supported { background: var(--accent-red); }

.verdict-legend {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 16px;
}

/* ---- LLM CALL TABLE ---- */
.llm-table { table-layout: auto; }
.llm-table td { white-space: nowrap; }
.llm-table td:nth-child(2) { white-space: normal; max-width: 250px; word-break: break-word; }

/* ---- RESPONSIVE ---- */
@media (max-width: 1280px) {
  .evidence-panel { display: none; }
  .center { margin-right: 0; }
}

@media (max-width: 900px) {
  .sidebar { display: none; }
  .center { margin-left: 0; padding: 16px; }
  .hero-metrics { grid-template-columns: 1fr; }
  .hero-metrics-row2 { grid-template-columns: repeat(2, 1fr); }
}

/* ---- SCROLLBAR ---- */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--border-active); }
"""


# ---------------------------------------------------------------------------
# JavaScript
# ---------------------------------------------------------------------------

def _build_js() -> str:
    """JS for scroll spy, evidence filtering, STORM tab switching."""
    return """
document.addEventListener('DOMContentLoaded', function() {
  // --- Scroll spy ---
  var sections = document.querySelectorAll('.section[id]');
  var navLinks = document.querySelectorAll('.sidebar a[data-section]');
  var centerPanel = document.querySelector('.center');

  if (centerPanel && sections.length > 0) {
    centerPanel.addEventListener('scroll', function() {
      var scrollPos = centerPanel.scrollTop + 80;
      var current = '';
      sections.forEach(function(s) {
        if (s.offsetTop <= scrollPos) {
          current = s.id;
        }
      });
      navLinks.forEach(function(a) {
        a.classList.remove('active');
        if (a.getAttribute('data-section') === current) {
          a.classList.add('active');
        }
      });
    });
  }

  // --- Sidebar nav click ---
  navLinks.forEach(function(a) {
    a.addEventListener('click', function(e) {
      e.preventDefault();
      var target = document.getElementById(this.getAttribute('data-section'));
      if (target && centerPanel) {
        centerPanel.scrollTo({ top: target.offsetTop - 20, behavior: 'smooth' });
      }
    });
  });

  // --- Evidence filter ---
  var filterSelect = document.getElementById('evidence-filter');
  if (filterSelect) {
    filterSelect.addEventListener('change', function() {
      var val = this.value;
      var cards = document.querySelectorAll('.evidence-card[data-tier]');
      cards.forEach(function(card) {
        if (val === 'all' || card.getAttribute('data-tier') === val) {
          card.style.display = '';
        } else {
          card.style.display = 'none';
        }
      });
      // Update count
      var visible = document.querySelectorAll('.evidence-card[data-tier]:not([style*="display: none"])').length;
      var countEl = document.getElementById('evidence-visible-count');
      if (countEl) countEl.textContent = visible;
    });
  }

  // --- STORM persona tabs ---
  var personaTabs = document.querySelectorAll('.storm-persona-tab');
  personaTabs.forEach(function(tab) {
    tab.addEventListener('click', function() {
      var persona = this.getAttribute('data-persona');
      // Toggle active tab
      personaTabs.forEach(function(t) { t.classList.remove('active'); });
      this.classList.add('active');
      // Toggle conversation
      var convos = document.querySelectorAll('.storm-conversation');
      convos.forEach(function(c) {
        if (c.getAttribute('data-persona') === persona) {
          c.classList.add('active');
        } else {
          c.classList.remove('active');
        }
      });
    });
  });
});
"""


# ---------------------------------------------------------------------------
# SVG Faithfulness Gauge
# ---------------------------------------------------------------------------

def _build_faith_gauge_svg(faith_pct: float) -> str:
    """Generate an SVG circular gauge for faithfulness percentage.

    Args:
        faith_pct: Faithfulness as 0-100 percentage.
    """
    # SVG parameters
    size = 80
    cx = cy = size / 2
    r = 32
    stroke_width = 6
    circumference = 2 * math.pi * r
    offset = circumference * (1 - faith_pct / 100)

    # Color based on value
    if faith_pct >= 80:
        color = "#22c55e"
    elif faith_pct >= 60:
        color = "#f59e0b"
    else:
        color = "#ef4444"

    return f"""<svg class="faith-gauge" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#262626" stroke-width="{stroke_width}"/>
      <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke_width}"
              stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
              stroke-linecap="round" transform="rotate(-90 {cx} {cy})"
              style="transition: stroke-dashoffset 0.8s ease;"/>
      <text x="{cx}" y="{cy + 1}" text-anchor="middle" dominant-baseline="middle"
            font-family="Inter, sans-serif" font-size="14" font-weight="700" fill="{color}">
        {faith_pct:.0f}%
      </text>
    </svg>"""


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _section_hero(grouped: dict, metrics: dict) -> str:
    """Executive hero section with KPI cards and SVG gauge."""
    vector_id = metrics["vector_id"]
    query = metrics["query"]
    faith = metrics["faithfulness"]
    faith_pct = faith * 100

    # Faithfulness color
    faith_color = (
        "var(--accent)" if faith >= 0.80
        else "var(--accent-amber)" if faith >= 0.60
        else "var(--accent-red)"
    )

    # SVG gauge
    gauge_svg = _build_faith_gauge_svg(faith_pct)

    # Gate status
    gate_tag = (
        '<span class="tag tag-success">PASS</span>'
        if metrics["gate_passed"]
        else '<span class="tag tag-error">FAIL</span>'
    )

    # Duration
    dur = _format_duration(metrics["total_duration"])
    cost = _format_cost(metrics["cost"])

    # Get timestamps from events
    all_events = []
    for evlist in grouped.values():
        all_events.extend(evlist)
    if all_events:
        timestamps = [e.get("ts", "") for e in all_events if e.get("ts")]
        first_ts = min(timestamps) if timestamps else "N/A"
        last_ts = max(timestamps) if timestamps else "N/A"
        # Trim to readable format
        if len(first_ts) > 19:
            first_ts = first_ts[:19].replace("T", " ")
        if len(last_ts) > 19:
            last_ts = last_ts[:19].replace("T", " ")
    else:
        first_ts = last_ts = "N/A"

    query_html = ""
    if query:
        query_html = f'<div class="query-text">{_esc(query)}</div>'

    return f"""
    <div class="hero-header" id="hero">
      <h1>Research Observatory</h1>
      <div class="vector-id">{_esc(vector_id)} &middot; {_esc(first_ts)} &rarr; {_esc(last_ts)} &middot; {dur} &middot; {gate_tag}</div>
      {query_html}
    </div>

    <div class="hero-metrics">
      <div class="metric-card">
        <div class="label">Faithfulness</div>
        <div class="metric-card-faith">
          {gauge_svg}
          <div class="faith-details">
            <div class="value" style="color: {faith_color};">{faith_pct:.1f}%</div>
            <div class="sub">of claims grounded in sources</div>
          </div>
        </div>
      </div>
      <div class="metric-card">
        <div class="label">Evidence</div>
        <div class="value">{metrics["final_evidence"]:,}</div>
        <div class="sub">pieces collected</div>
      </div>
      <div class="metric-card">
        <div class="label">Words</div>
        <div class="value">{metrics["total_words"]:,}</div>
        <div class="sub">in final report</div>
      </div>
    </div>

    <div class="hero-metrics-row2">
      <div class="metric-card">
        <div class="label">Citations</div>
        <div class="value">{metrics["total_citations"]}</div>
      </div>
      <div class="metric-card">
        <div class="label">Sources</div>
        <div class="value">{metrics["unique_sources"]}</div>
      </div>
      <div class="metric-card">
        <div class="label">Iterations</div>
        <div class="value">{metrics["iterations"]}</div>
      </div>
      <div class="metric-card">
        <div class="label">Cost</div>
        <div class="value">{cost}</div>
        <div class="sub">{metrics["llm_calls"]} LLM calls</div>
      </div>
    </div>"""


def _section_evidence_meter(metrics: dict) -> str:
    """Consensus-style evidence strength meter."""
    gold = metrics["gold"]
    silver = metrics["silver"]
    bronze = metrics["bronze"]
    total = gold + silver + bronze

    if total == 0:
        return ""

    gold_pct = (gold / total) * 100
    silver_pct = (silver / total) * 100
    bronze_pct = (bronze / total) * 100

    # Strength label
    if gold_pct >= 30:
        strength = "Strong"
        strength_class = "strength-strong"
    elif gold_pct >= 15 or (gold + silver) / total >= 0.5:
        strength = "Moderate"
        strength_class = "strength-moderate"
    elif total >= 10:
        strength = "Weak"
        strength_class = "strength-weak"
    else:
        strength = "Insufficient"
        strength_class = "strength-insufficient"

    return f"""
    <div class="strength-meter">
      <h3>Evidence Strength <span class="strength-label {strength_class}">{strength}</span></h3>
      <div class="meter-bar-container">
        <div class="meter-segment meter-gold" style="width: {gold_pct:.1f}%;">{gold if gold_pct > 8 else ''}</div>
        <div class="meter-segment meter-silver" style="width: {silver_pct:.1f}%;">{silver if silver_pct > 8 else ''}</div>
        <div class="meter-segment meter-bronze" style="width: {bronze_pct:.1f}%;">{bronze if bronze_pct > 8 else ''}</div>
      </div>
      <div class="meter-legend">
        <div class="meter-legend-item"><div class="meter-legend-dot" style="background:var(--gold);"></div>{gold} GOLD</div>
        <div class="meter-legend-item"><div class="meter-legend-dot" style="background:var(--silver);"></div>{silver} SILVER</div>
        <div class="meter-legend-item"><div class="meter-legend-dot" style="background:var(--bronze);"></div>{bronze} BRONZE</div>
        <div class="meter-legend-item" style="margin-left:auto; color:var(--text-tertiary);">{total} total</div>
      </div>
    </div>"""


def _section_pipeline_flow(grouped: dict) -> str:
    """Horizontal pipeline phase flow with status badges."""
    phase_status = _get_phase_status(grouped)

    # Node durations for tooltip
    node_ends = grouped.get("node_end", [])
    durations = {}
    for ev in node_ends:
        node = ev.get("node", "?")
        dur = ev.get("duration_ms", 0)
        durations[node] = durations.get(node, 0) + dur

    phases_html = ""
    for i, phase in enumerate(_PHASE_ORDER):
        status = phase_status.get(phase, "pending")
        label = _PHASE_LABELS.get(phase, phase)
        icon = _PHASE_ICONS.get(phase, "&#9679;")
        dur = durations.get(phase, 0)
        dur_str = _format_duration(dur) if dur > 0 else ""

        phase_class = f"flow-phase flow-phase-{status}"
        status_class = f"phase-status phase-status-{status}"

        if i > 0:
            phases_html += '<span class="flow-arrow">&#8594;</span>'

        phases_html += f"""
        <div class="{phase_class}" title="{label}: {dur_str}">
          <span class="phase-icon">{icon}</span>
          <span class="phase-name">{label}</span>
          <span class="{status_class}"></span>
        </div>"""

    return f"""
    <div class="pipeline-flow">
      <h3>Pipeline Phases</h3>
      <div class="flow-container">{phases_html}</div>
    </div>"""


def _section_evidence_funnel(grouped: dict) -> str:
    """Visual evidence funnel chart with gradient bars."""
    evidence_events = grouped.get("evidence", [])

    # Aggregate counts by action
    action_counts: dict[str, int] = defaultdict(int)
    for ev in evidence_events:
        action = ev.get("action", "unknown")
        count = ev.get("count", 0)
        if count > action_counts[action]:
            action_counts[action] = count

    # Funnel stages in order
    funnel_stages = [
        ("relevance_scored", "Searched", "#3b82f6"),
        ("offtopic_filtered", "On-topic", "#6366f1"),
        ("extracted", "Extracted", "#8b5cf6"),
        ("dedup_summary", "Deduplicated", "#a855f7"),
        ("verified", "Verified", "#22c55e"),
        ("clustering", "Clustered", "#14b8a6"),
        ("citation_audit", "Cited", "#06b6d4"),
        ("report_assembled", "Final", "#0ea5e9"),
    ]

    active_stages = []
    for action, label, color in funnel_stages:
        count = action_counts.get(action, 0)
        if count > 0:
            active_stages.append((action, label, color, count))

    if not active_stages:
        return ""

    # Use first stage as reference for funnel shape.
    # Skip any later stage whose count exceeds the first by >2x
    # (accumulated totals across iterations, not a real funnel step).
    first_count = active_stages[0][3]
    filtered_stages = []
    for stage in active_stages:
        if stage[3] > first_count * 2 and stage != active_stages[0]:
            continue  # skip inflated accumulated counts
        filtered_stages.append(stage)
    active_stages = filtered_stages if filtered_stages else active_stages
    max_count = active_stages[0][3] if active_stages else 1

    funnel_html = '<div class="funnel">'
    for action, label, color, count in active_stages:
        pct = (min(count, max_count) / max_count) * 100 if max_count > 0 else 0
        pct_of_first = (count / active_stages[0][3]) * 100 if active_stages[0][3] > 0 else 0
        funnel_html += f"""
        <div class="funnel-row">
          <span class="funnel-label">{label}</span>
          <div class="funnel-bar-track">
            <div class="funnel-bar-fill" style="width: {max(pct, 5):.0f}%; background: {color};">{count:,}</div>
          </div>
          <span class="funnel-pct">{pct_of_first:.0f}%</span>
        </div>"""
    funnel_html += '</div>'

    return f"""
    <div class="section" id="sec-funnel">
      <div class="section-header">
        <h2>Evidence Funnel</h2>
        <span class="section-badge">{len(evidence_events)} events</span>
      </div>
      {funnel_html}
    </div>"""


def _section_search_fetch(grouped: dict) -> str:
    """Search and fetch section with clean tables."""
    search_events = grouped.get("search_result", [])
    fetch_events = grouped.get("fetch", [])

    # Search summary by engine
    engine_counts: dict[str, int] = defaultdict(int)
    engine_results: dict[str, int] = defaultdict(int)
    for ev in search_events:
        eng = ev.get("engine", "unknown")
        engine_counts[eng] += 1
        engine_results[eng] += ev.get("result_count", 0)

    engine_summary = ""
    for eng in sorted(engine_counts.keys()):
        engine_summary += f"""
        <div class="metric-card" style="padding:10px 14px;">
          <div class="label">{_esc(eng)}</div>
          <div class="value" style="font-size:20px;">{engine_results[eng]:,}</div>
          <div class="sub">{engine_counts[eng]} queries</div>
        </div>"""

    # Search table (capped to 50)
    display_searches = search_events[:50]
    search_rows = ""
    for ev in display_searches:
        engine = _esc(ev.get("engine", "?"))
        query = _esc(_truncate(ev.get("query", ""), 80))
        count = ev.get("result_count", 0)
        search_rows += f"<tr><td><span class='tag tag-info'>{engine}</span></td><td>{query}</td><td>{count}</td></tr>"

    remainder_note = ""
    if len(search_events) > 50:
        remainder_note = f'<div style="padding:8px; font-size:12px; color:var(--text-tertiary);">Showing 50 of {len(search_events)} search queries.</div>'

    # Fetch table
    fetch_success = sum(1 for e in fetch_events if e.get("status") == "success")
    fetch_fail = len(fetch_events) - fetch_success

    display_fetches = fetch_events[:50]
    fetch_rows = ""
    for ev in display_fetches:
        url = _esc(ev.get("url", ""))
        domain = _extract_domain(ev.get("url", ""))
        status = ev.get("status", "?")
        content_len = ev.get("content_len", 0)
        dur = ev.get("duration_ms", 0)
        method = ev.get("method", "")

        status_class = "tag-success"
        if str(status).startswith("4") or str(status).startswith("5") or status == "error":
            status_class = "tag-error"
        elif status in ("paywall", "timeout", "stub"):
            status_class = "tag-warning"

        fetch_rows += f"""<tr>
          <td style="max-width:300px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="{url}">{_esc(domain)}</td>
          <td><span class="tag {status_class}">{_esc(str(status))}</span></td>
          <td>{content_len:,}</td>
          <td>{_format_duration(dur)}</td>
          <td style="color:var(--text-tertiary);">{_esc(method)}</td>
        </tr>"""

    fetch_remainder = ""
    if len(fetch_events) > 50:
        fetch_remainder = f'<div style="padding:8px; font-size:12px; color:var(--text-tertiary);">Showing 50 of {len(fetch_events)} fetches.</div>'

    return f"""
    <div class="section" id="sec-search">
      <div class="section-header">
        <h2>Search &amp; Fetch</h2>
        <span class="section-badge">{len(search_events)} searches, {len(fetch_events)} fetches</span>
      </div>

      <div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:8px; margin-bottom:16px;">
        {engine_summary}
        <div class="metric-card" style="padding:10px 14px;">
          <div class="label">Fetch Success</div>
          <div class="value" style="font-size:20px; color:var(--accent);">{fetch_success}</div>
          <div class="sub">{fetch_fail} failed</div>
        </div>
      </div>

      <details>
        <summary>Search Queries <span class="section-badge" style="margin-left:auto;">{len(search_events)}</span></summary>
        <div class="detail-body">
          <table>
            <thead><tr><th>Engine</th><th>Query</th><th>Results</th></tr></thead>
            <tbody>{search_rows if search_rows else '<tr><td colspan="3" style="color:var(--text-tertiary);">No searches</td></tr>'}</tbody>
          </table>
          {remainder_note}
        </div>
      </details>

      <details>
        <summary>URL Fetches <span class="section-badge" style="margin-left:auto;">{len(fetch_events)}</span></summary>
        <div class="detail-body">
          <table>
            <thead><tr><th>Domain</th><th>Status</th><th>Bytes</th><th>Duration</th><th>Method</th></tr></thead>
            <tbody>{fetch_rows if fetch_rows else '<tr><td colspan="5" style="color:var(--text-tertiary);">No fetches</td></tr>'}</tbody>
          </table>
          {fetch_remainder}
        </div>
      </details>
    </div>"""


def _section_storm(grouped: dict) -> str:
    """STORM interviews as chat-bubble conversation UI with persona tabs."""
    storm_events = grouped.get("storm_transcript", [])

    if not storm_events:
        # Check for STORM summary in llm_call events
        llm_events = grouped.get("llm_call", [])
        storm_llm = [e for e in llm_events if e.get("call_type") == "interview_simulation"]
        if storm_llm:
            ev = storm_llm[0]
            convos = ev.get("conversations", 0)
            rounds = ev.get("total_rounds", 0)
            completed = ev.get("completed_perspectives", [])
            skipped = ev.get("skipped_perspectives", [])

            perspectives_html = ""
            for p in completed:
                perspectives_html += f'<span class="tag tag-success" style="margin-right:4px;">{_esc(p)}</span>'
            for p in skipped:
                perspectives_html += f'<span class="tag tag-error" style="margin-right:4px;">{_esc(p)} (skipped)</span>'

            return f"""
            <div class="section" id="sec-storm">
              <div class="section-header">
                <h2>STORM Interviews</h2>
                <span class="section-badge">{convos} conversations, {rounds} rounds</span>
              </div>
              <div class="reasoning-card">
                <div class="reasoning-card-header">
                  <span class="reasoning-card-title">Interview Summary</span>
                </div>
                <div style="margin-bottom:8px;">{perspectives_html}</div>
                <div style="font-size:13px; color:var(--text-secondary);">
                  {convos} expert conversations across {rounds} rounds of questioning.
                  Detailed transcripts were not captured in this trace.
                </div>
              </div>
            </div>"""
        return ""

    # Group by persona
    personas: dict[str, list[dict]] = defaultdict(list)
    for ev in storm_events:
        personas[ev.get("persona", "Unknown")].append(ev)

    persona_names = sorted(personas.keys())

    # Persona tabs
    tabs_html = ""
    for i, name in enumerate(persona_names):
        active = " active" if i == 0 else ""
        rounds = len(personas[name])
        tabs_html += f'<div class="storm-persona-tab{active}" data-persona="{_esc(name)}">{_esc(name)} ({rounds})</div>'

    # Conversations
    conversations_html = ""
    for i, name in enumerate(persona_names):
        active = " active" if i == 0 else ""
        rounds = sorted(personas[name], key=lambda x: x.get("round", 0))

        rounds_html = ""
        for ev in rounds:
            question = _esc(ev.get("question", ""))
            answer = _esc(ev.get("answer", ""))
            sources = ev.get("sources", [])
            findings = ev.get("key_findings", [])
            quality = ev.get("interview_quality", "ok")
            round_num = ev.get("round", 0)

            fail_class = " storm-failed" if quality == "failed" else ""
            quality_tag = ""
            if quality == "failed":
                quality_tag = ' <span class="tag tag-error">FAILED</span>'
            elif quality == "degraded":
                quality_tag = ' <span class="tag tag-warning">DEGRADED</span>'

            sources_html = ""
            if sources:
                source_links = ", ".join(_esc(_extract_domain(s)) for s in sources[:5])
                sources_html = f'<div class="storm-meta">Sources: {source_links}</div>'

            findings_html = ""
            if findings:
                findings_list = "; ".join(_esc(_truncate(f, 120)) for f in findings[:4])
                findings_html = f'<div class="storm-meta">Findings: {findings_list}</div>'

            rounds_html += f"""
            <div class="storm-round">
              <div style="font-size:10px; color:var(--text-tertiary); margin-bottom:4px;">Round {round_num}{quality_tag}</div>
              <div class="storm-q">{question}</div>
              <div class="storm-a{fail_class}">{answer}{sources_html}{findings_html}</div>
            </div>"""

        conversations_html += f"""
        <div class="storm-conversation{active}" data-persona="{_esc(name)}">
          {rounds_html}
        </div>"""

    return f"""
    <div class="section" id="sec-storm">
      <div class="section-header">
        <h2>STORM Interviews</h2>
        <span class="section-badge">{len(storm_events)} rounds, {len(persona_names)} personas</span>
      </div>
      <div class="storm-personas">{tabs_html}</div>
      {conversations_html}
    </div>"""


def _section_verification(grouped: dict) -> str:
    """Verification section with faithfulness trend and verdict breakdown."""
    # Faithfulness history
    iter_decisions = grouped.get("iteration_decision", [])
    faith_scores = []
    for d in iter_decisions:
        rationale = d.get("rationale", {})
        fs = rationale.get("faithfulness_score", 0)
        if fs > 0:
            faith_scores.append((d.get("iteration", 0), fs))

    # Verification batches
    llm_events = grouped.get("llm_call", [])
    verify_batches = [
        e for e in llm_events
        if "verification" in e.get("call_type", "").lower()
        or e.get("call_type", "") == "verification_batch"
    ]

    # Verdict counts from verification_batch
    verdict_events = [
        e for e in llm_events
        if e.get("call_type") == "verification_batch"
    ]
    total_supported = sum(e.get("supported", 0) for e in verdict_events)
    total_partial = sum(e.get("partial", 0) for e in verdict_events)
    total_not_supported = sum(e.get("not_supported", 0) for e in verdict_events)
    total_verdicts = total_supported + total_partial + total_not_supported

    # Faithfulness trend bars
    trend_html = ""
    if faith_scores:
        trend_html += '<div style="margin-bottom:16px;"><div style="font-size:12px; color:var(--text-tertiary); margin-bottom:8px;">Faithfulness by Iteration</div>'
        trend_html += '<div class="faith-trend">'
        for iteration, score in faith_scores:
            pct = score * 100
            height = max(pct * 0.55, 5)
            color = (
                "var(--accent)" if pct >= 80
                else "var(--accent-amber)" if pct >= 60
                else "var(--accent-red)"
            )
            trend_html += f"""
            <div class="faith-bar" style="height:{height:.0f}px; background:{color};">{pct:.0f}%</div>"""
        trend_html += '</div>'
        trend_html += '<div style="display:flex; gap:6px; font-size:10px; color:var(--text-tertiary);">'
        for iteration, _ in faith_scores:
            trend_html += f'<div style="flex:1; text-align:center;">Iter {iteration}</div>'
        trend_html += '</div></div>'

    # Verdict breakdown bar
    verdict_html = ""
    if total_verdicts > 0:
        sup_pct = (total_supported / total_verdicts) * 100
        par_pct = (total_partial / total_verdicts) * 100
        ns_pct = (total_not_supported / total_verdicts) * 100

        verdict_html = f"""
        <div style="margin-bottom:16px;">
          <div style="font-size:12px; color:var(--text-tertiary); margin-bottom:8px;">Verdict Distribution ({total_verdicts} claims)</div>
          <div class="verdict-bar-container">
            <div class="verdict-seg verdict-supported" style="width:{sup_pct:.1f}%;"></div>
            <div class="verdict-seg verdict-partial" style="width:{par_pct:.1f}%;"></div>
            <div class="verdict-seg verdict-not-supported" style="width:{ns_pct:.1f}%;"></div>
          </div>
          <div class="verdict-legend">
            <div>Supported: {total_supported}</div>
            <div>Partial: {total_partial}</div>
            <div>Not Supported: {total_not_supported}</div>
          </div>
        </div>"""

    # Verification reasoning
    reasoning_events = grouped.get("reasoning_capture", [])
    verify_reasoning = [
        e for e in reasoning_events
        if "verification" in e.get("call_type", "").lower()
        or "verify" in e.get("call_type", "").lower()
    ]

    reasoning_html = ""
    for i, ev in enumerate(verify_reasoning[:10]):
        call_type = _esc(ev.get("call_type", ""))
        reasoning = _esc(_truncate(ev.get("reasoning_text", ""), 500))
        tokens = ev.get("input_tokens", 0) + ev.get("output_tokens", 0)

        reasoning_html += f"""
        <details>
          <summary>Batch {i + 1}: {call_type} <span class="section-badge" style="margin-left:auto;">{tokens:,} tok</span></summary>
          <div class="detail-body"><pre>{reasoning}</pre></div>
        </details>"""

    if len(verify_reasoning) > 10:
        reasoning_html += f'<div style="font-size:12px; color:var(--text-tertiary); padding:8px;">Showing 10 of {len(verify_reasoning)} verification batches.</div>'

    empty_note = ""
    if not trend_html and not verdict_html and not reasoning_html:
        empty_note = '<div style="color:var(--text-tertiary); font-size:13px;">No verification data captured in this trace.</div>'

    return f"""
    <div class="section" id="sec-verify">
      <div class="section-header">
        <h2>Verification</h2>
        <span class="section-badge">{len(verify_batches)} batches</span>
      </div>
      {trend_html}
      {verdict_html}
      {reasoning_html}
      {empty_note}
    </div>"""


def _section_quality_gates(grouped: dict) -> str:
    """Quality gate dashboard with visual gate cards."""
    gate_events = grouped.get("quality_gate", [])

    if not gate_events:
        return ""

    # Find the final gate for thresholds
    final_gate = None
    for g in reversed(gate_events):
        if g.get("gate") in ("post_synthesis_final", "post_synthesis"):
            final_gate = g
            break

    # Build gate cards
    cards_html = '<div class="gate-grid">'

    for ev in gate_events:
        gate_name = ev.get("gate", "unknown")
        passed = ev.get("passed", False)
        node = ev.get("node", "?")
        badge_class = "gate-pass" if passed else "gate-fail"
        badge_text = "PASS" if passed else "FAIL"

        tw = ev.get("total_words", 0)
        tc = ev.get("total_citations", 0)
        us = ev.get("unique_sources", 0)
        expansion = ev.get("expansion_pass", "")

        # Show key metrics as sub-items
        sub_items = []
        if tw > 0:
            sub_items.append(f"Words: {tw:,}")
        if tc > 0:
            sub_items.append(f"Citations: {tc}")
        if us > 0:
            sub_items.append(f"Sources: {us}")
        if expansion:
            sub_items.append(f"Expansion: {expansion}")

        sub_html = " | ".join(sub_items)

        # Word count gate visualization
        bar_html = ""
        if tw > 0:
            word_pct = min((tw / 2000) * 100, 100)
            bar_color = "var(--accent)" if tw >= 2000 else "var(--accent-amber)"
            bar_html = f"""
            <div class="gate-bar-track" style="margin-top:8px;">
              <div class="gate-bar-fill" style="width:{word_pct:.0f}%; background:{bar_color};"></div>
              <div class="gate-threshold" style="left:100%;"></div>
            </div>"""

        cards_html += f"""
        <div class="gate-card">
          <div class="gate-card-header">
            <span class="gate-card-name">{_esc(gate_name)}</span>
            <span class="gate-badge {badge_class}">{badge_text}</span>
          </div>
          <div class="gate-value">{_esc(node)}</div>
          <div class="gate-sub">{sub_html}</div>
          {bar_html}
        </div>"""

    cards_html += '</div>'

    return f"""
    <div class="section" id="sec-gates">
      <div class="section-header">
        <h2>Quality Gates</h2>
        <span class="section-badge">{len(gate_events)} gates</span>
      </div>
      {cards_html}
    </div>"""


def _section_iteration_decisions(grouped: dict) -> str:
    """Iteration decisions section."""
    iter_events = grouped.get("iteration_decision", [])

    if not iter_events:
        return ""

    cards = ""
    for ev in iter_events:
        iteration = ev.get("iteration", 0)
        decision = ev.get("decision", "?")
        rationale = ev.get("rationale", {})

        decision_color = "var(--accent)" if decision == "synthesize" else "var(--accent-amber)"
        decision_icon = "&#9989;" if decision == "synthesize" else "&#8635;"

        rationale_rows = ""
        for k, v in sorted(rationale.items()):
            val_str = _esc(str(v))
            if len(val_str) > 200:
                val_str = val_str[:200] + "..."
            rationale_rows += f"""<tr>
              <td style="font-weight:600; color:var(--text-tertiary); white-space:nowrap;">{_esc(k)}</td>
              <td style="color:var(--text-secondary);">{val_str}</td>
            </tr>"""

        cards += f"""
        <div class="reasoning-card">
          <div class="reasoning-card-header">
            <span style="font-size:16px;">{decision_icon}</span>
            <span class="reasoning-card-title" style="color:{decision_color};">Iteration {iteration}: {_esc(decision).upper()}</span>
          </div>
          <table style="font-size:12px;">{rationale_rows}</table>
        </div>"""

    return f"""
    <div class="section" id="sec-iterations">
      <div class="section-header">
        <h2>Iteration Decisions</h2>
        <span class="section-badge">{len(iter_events)} decisions</span>
      </div>
      {cards}
    </div>"""


def _section_synthesis(grouped: dict) -> str:
    """Synthesis section with section write and expand details."""
    llm_events = grouped.get("llm_call", [])

    # Section writes
    section_writes = [e for e in llm_events if e.get("call_type") == "section_write"]
    section_expands = [e for e in llm_events if e.get("call_type") == "section_expand"]

    # Reasoning captures for synthesis
    reasoning_events = grouped.get("reasoning_capture", [])
    synth_reasoning = [
        e for e in reasoning_events
        if any(kw in e.get("call_type", "").lower() for kw in [
            "clusterplan", "reportoutline", "outline",
            "synthesis", "cluster",
        ])
    ]

    if not section_writes and not section_expands and not synth_reasoning:
        return ""

    # Section writes summary
    writes_html = ""
    if section_writes:
        writes_html += '<div style="margin-bottom:16px;">'
        writes_html += '<div style="font-size:12px; color:var(--text-tertiary); margin-bottom:8px;">Section Drafts</div>'
        writes_html += '<div style="display:grid; grid-template-columns:repeat(auto-fill, minmax(180px, 1fr)); gap:8px;">'
        for ev in sorted(section_writes, key=lambda x: x.get("section_id", "")):
            sid = _esc(ev.get("section_id", "?"))
            title = _esc(_truncate(ev.get("title", sid), 30))
            wc = ev.get("word_count", 0)
            ec = ev.get("evidence_count", 0)
            writes_html += f"""
            <div class="metric-card" style="padding:10px 12px;">
              <div class="label" style="font-size:10px;">{title}</div>
              <div class="value" style="font-size:18px;">{wc:,}</div>
              <div class="sub">{ec} evidence</div>
            </div>"""
        writes_html += '</div></div>'

    # Section expansions
    expands_html = ""
    if section_expands:
        expands_html += '<details><summary>Section Expansions <span class="section-badge" style="margin-left:auto;">'
        expands_html += f'{len(section_expands)}</span></summary><div class="detail-body">'
        expands_html += '<table><thead><tr><th>Section</th><th>Original</th><th>Expanded</th><th>Added</th></tr></thead><tbody>'
        for ev in sorted(section_expands, key=lambda x: x.get("section_id", "")):
            sid = _esc(ev.get("section_id", "?"))
            title = _esc(_truncate(ev.get("title", sid), 25))
            orig = ev.get("original_words", 0)
            expanded = ev.get("expanded_words", 0)
            added = ev.get("added_words", 0)
            expands_html += f"<tr><td>{title}</td><td>{orig}</td><td>{expanded}</td><td style='color:var(--accent);'>+{added}</td></tr>"
        expands_html += '</tbody></table></div></details>'

    # Synthesis reasoning
    reasoning_html = ""
    for ev in synth_reasoning[:8]:
        call_type = _esc(ev.get("call_type", ""))
        reasoning = _esc(_truncate(ev.get("reasoning_text", ""), 500))
        tokens = ev.get("input_tokens", 0) + ev.get("output_tokens", 0)

        reasoning_html += f"""
        <details>
          <summary>{call_type} <span class="section-badge" style="margin-left:auto;">{tokens:,} tok</span></summary>
          <div class="detail-body"><pre>{reasoning}</pre></div>
        </details>"""

    return f"""
    <div class="section" id="sec-synthesis">
      <div class="section-header">
        <h2>Synthesis</h2>
        <span class="section-badge">{len(section_writes)} sections, {len(section_expands)} expansions</span>
      </div>
      {writes_html}
      {expands_html}
      {reasoning_html}
    </div>"""


def _section_llm_log(grouped: dict) -> str:
    """Compact LLM call log table."""
    llm_events = grouped.get("llm_call", [])

    if not llm_events:
        return ""

    # Reasoning index for matching
    reasoning_events = grouped.get("reasoning_capture", [])
    reasoning_by_type: dict[str, list[dict]] = defaultdict(list)
    for ev in reasoning_events:
        ct = ev.get("call_type", "")
        reasoning_by_type[ct].append(ev)

    # Group by call_type for summary
    call_type_counts: dict[str, int] = defaultdict(int)
    call_type_tokens: dict[str, int] = defaultdict(int)
    call_type_cost: dict[str, float] = defaultdict(float)
    for ev in llm_events:
        ct = ev.get("call_type", "unknown")
        call_type_counts[ct] += 1
        call_type_tokens[ct] += ev.get("input_tokens", 0) + ev.get("output_tokens", 0)
        call_type_cost[ct] += ev.get("cost_usd", 0)

    # Summary table
    summary_rows = ""
    for ct in sorted(call_type_counts.keys(), key=lambda x: -call_type_counts[x]):
        count = call_type_counts[ct]
        tokens = call_type_tokens[ct]
        cost = call_type_cost[ct]
        summary_rows += f"""<tr>
          <td>{_esc(ct)}</td>
          <td>{count}</td>
          <td>{tokens:,}</td>
          <td>{_format_cost(cost) if cost > 0 else '-'}</td>
        </tr>"""

    # Detail table (capped)
    display_events = llm_events[:80]
    detail_rows = ""
    for ev in display_events:
        call_type = _esc(ev.get("call_type", "?"))
        node = _esc(ev.get("node", "?"))
        tokens_in = ev.get("input_tokens", 0)
        tokens_out = ev.get("output_tokens", 0)
        dur = ev.get("duration_ms", 0)
        cost = ev.get("cost_usd", 0)
        model = _esc(_truncate(ev.get("model", ""), 30))

        detail_rows += f"""<tr>
          <td>{node}</td>
          <td>{call_type}</td>
          <td>{tokens_in:,}</td>
          <td>{tokens_out:,}</td>
          <td>{_format_duration(dur) if dur > 0 else '-'}</td>
          <td>{_format_cost(cost) if cost > 0 else '-'}</td>
        </tr>"""

    remainder = ""
    if len(llm_events) > 80:
        remainder = f'<div style="padding:8px; font-size:12px; color:var(--text-tertiary);">Showing 80 of {len(llm_events)} calls.</div>'

    # Total cost
    total_cost = sum(e.get("cost_usd", 0) for e in llm_events)
    total_tokens = sum(e.get("input_tokens", 0) + e.get("output_tokens", 0) for e in llm_events)

    return f"""
    <div class="section" id="sec-llm">
      <div class="section-header">
        <h2>LLM Call Log</h2>
        <span class="section-badge">{len(llm_events)} calls &middot; {total_tokens:,} tokens &middot; {_format_cost(total_cost)}</span>
      </div>

      <details open>
        <summary>Call Type Summary <span class="section-badge" style="margin-left:auto;">{len(call_type_counts)} types</span></summary>
        <div class="detail-body">
          <table>
            <thead><tr><th>Call Type</th><th>Count</th><th>Tokens</th><th>Cost</th></tr></thead>
            <tbody>{summary_rows}</tbody>
          </table>
        </div>
      </details>

      <details>
        <summary>Call Details <span class="section-badge" style="margin-left:auto;">{len(llm_events)} calls</span></summary>
        <div class="detail-body">
          <table class="llm-table">
            <thead><tr><th>Node</th><th>Call Type</th><th>In</th><th>Out</th><th>Duration</th><th>Cost</th></tr></thead>
            <tbody>{detail_rows}</tbody>
          </table>
          {remainder}
        </div>
      </details>
    </div>"""


def _section_planning(grouped: dict) -> str:
    """Planning section with reasoning captures."""
    reasoning_events = grouped.get("reasoning_capture", [])
    plan_events = [
        e for e in reasoning_events
        if any(kw in e.get("call_type", "").lower() for kw in [
            "queryplan", "seedqueryplan", "validate",
        ])
    ]

    # Also include evidence seed_query_plan for query details
    evidence_events = grouped.get("evidence", [])
    seed_plans = [e for e in evidence_events if e.get("action") == "seed_query_plan"]

    if not plan_events and not seed_plans:
        return ""

    # Seed plan queries
    queries_html = ""
    for ev in seed_plans:
        queries = ev.get("queries", [])
        perspectives = ev.get("perspective_distribution", {})
        strategy = ev.get("search_strategy", "")

        if queries:
            queries_html += '<div style="margin-bottom:12px;">'
            if strategy:
                queries_html += f'<div style="font-size:12px; color:var(--text-tertiary); margin-bottom:6px;">Strategy: {_esc(strategy)}</div>'
            queries_html += '<div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px;">'
            for q in queries[:25]:
                if isinstance(q, dict):
                    q_text = q.get("query", q.get("text", str(q)))
                else:
                    q_text = str(q)
                queries_html += f'<span class="tag tag-info" style="font-size:11px;">{_esc(_truncate(q_text, 60))}</span>'
            queries_html += '</div>'
            if perspectives:
                queries_html += '<div style="font-size:11px; color:var(--text-tertiary);">Perspectives: '
                queries_html += ", ".join(f"{k}: {v}" for k, v in perspectives.items())
                queries_html += '</div>'
            queries_html += '</div>'

    # Reasoning cards
    reasoning_html = ""
    for ev in plan_events[:5]:
        call_type = _esc(ev.get("call_type", ""))
        reasoning = _esc(_truncate(ev.get("reasoning_text", ""), 600))
        tokens = ev.get("input_tokens", 0) + ev.get("output_tokens", 0)

        reasoning_html += f"""
        <details>
          <summary>{call_type} <span class="section-badge" style="margin-left:auto;">{tokens:,} tok</span></summary>
          <div class="detail-body"><pre>{reasoning}</pre></div>
        </details>"""

    return f"""
    <div class="section" id="sec-planning">
      <div class="section-header">
        <h2>Planning</h2>
        <span class="section-badge">{len(plan_events)} reasoning captures</span>
      </div>
      {queries_html}
      {reasoning_html}
    </div>"""


def _section_evidence_detail(grouped: dict) -> str:
    """Evidence scoring detail section."""
    evidence_events = grouped.get("evidence", [])

    # Tier scoring detail
    scoring_items = []
    for ev in evidence_events:
        if ev.get("action") == "tier_scoring_detail":
            scores_list = ev.get("scores", [])
            scoring_items.extend(scores_list)
        elif ev.get("action") == "scoring_detail":
            scoring_items.append(ev)

    # Tier signal distribution
    tier_dist_events = [e for e in evidence_events if e.get("action") == "tier_signal_distribution"]

    # Dedup info
    dedup_events = [e for e in evidence_events if e.get("action") in ("dedup_detail", "dedup_summary")]

    if not scoring_items and not tier_dist_events and not dedup_events:
        return ""

    # Tier distribution summary
    tier_dist_html = ""
    if tier_dist_events:
        ev = tier_dist_events[-1]
        tier_counts = ev.get("tier_counts", {})
        total = ev.get("count", 0)
        tier_dist_html = '<div style="display:flex; gap:12px; margin-bottom:16px;">'
        for tier_name in ("GOLD", "SILVER", "BRONZE"):
            cnt = tier_counts.get(tier_name, 0)
            tier_class = tier_name.lower()
            tier_dist_html += f"""
            <div class="metric-card" style="padding:10px 14px;">
              <div class="label" style="color:var(--{tier_class});">{tier_name}</div>
              <div class="value" style="font-size:20px; color:var(--{tier_class});">{cnt}</div>
            </div>"""
        tier_dist_html += f"""
            <div class="metric-card" style="padding:10px 14px;">
              <div class="label">Total</div>
              <div class="value" style="font-size:20px;">{total}</div>
            </div>"""
        tier_dist_html += '</div>'

    # Dedup summary
    dedup_html = ""
    for ev in dedup_events:
        if ev.get("action") == "dedup_detail":
            exact = ev.get("exact_removed", 0)
            near = ev.get("near_removed", 0)
            before = ev.get("before_count", 0)
            after = ev.get("after_count", 0)
            dedup_html += f"""
            <div class="reasoning-card" style="margin-bottom:12px;">
              <div class="reasoning-card-title" style="margin-bottom:4px;">Deduplication</div>
              <div style="font-size:13px; color:var(--text-secondary);">
                {before} &rarr; {after} ({exact} exact, {near} near-duplicates removed)
              </div>
            </div>"""

    # Scoring table
    scoring_html = ""
    if scoring_items:
        display_items = scoring_items[:50]
        score_rows = ""
        for item in display_items:
            eid = _esc(str(item.get("id", item.get("evidence_id", "?"))))[:20]
            tier = item.get("tier", "?")
            tier_class = f"tier-{tier.lower()}" if tier in ("GOLD", "SILVER", "BRONZE") else ""
            sig_r = item.get("sig_relevance", 0)
            sig_a = item.get("sig_authority", 0)
            sig_d = item.get("sig_density", 0)
            sig_f = item.get("sig_freshness", 0)
            sig_g = item.get("sig_grounding", 0)
            composite = item.get("composite", 0)

            score_rows += f"""<tr>
              <td style="font-family:var(--font-mono); font-size:11px;">{eid}</td>
              <td><span class="tier-badge {tier_class}">{_esc(str(tier))}</span></td>
              <td>{composite:.2f}</td>
              <td>{sig_r:.2f}</td>
              <td>{sig_a:.2f}</td>
              <td>{sig_d:.2f}</td>
              <td>{sig_f:.2f}</td>
              <td>{sig_g:.2f}</td>
            </tr>"""

        remainder = ""
        if len(scoring_items) > 50:
            remainder = f'<div style="padding:8px; font-size:12px; color:var(--text-tertiary);">Showing 50 of {len(scoring_items)}.</div>'

        scoring_html = f"""
        <details>
          <summary>5-Signal Scoring Detail <span class="section-badge" style="margin-left:auto;">{len(scoring_items)} items</span></summary>
          <div class="detail-body">
            <table style="font-size:12px;">
              <thead><tr><th>ID</th><th>Tier</th><th>Composite</th><th>Rel</th><th>Auth</th><th>Dens</th><th>Fresh</th><th>Ground</th></tr></thead>
              <tbody>{score_rows}</tbody>
            </table>
            {remainder}
          </div>
        </details>"""

    return f"""
    <div class="section" id="sec-evidence">
      <div class="section-header">
        <h2>Evidence Analysis</h2>
        <span class="section-badge">{len(scoring_items)} scored</span>
      </div>
      {tier_dist_html}
      {dedup_html}
      {scoring_html}
    </div>"""


# ---------------------------------------------------------------------------
# Right panel: Evidence cards
# ---------------------------------------------------------------------------

def _build_evidence_panel(grouped: dict) -> str:
    """Build the right panel with filterable evidence cards."""
    evidence_events = grouped.get("evidence", [])

    # Collect evidence_detail items
    all_items = []
    for ev in evidence_events:
        if ev.get("action") == "evidence_detail":
            items = ev.get("items", [])
            all_items.extend(items)

    # If no evidence_detail, try tier_scoring_detail
    if not all_items:
        for ev in evidence_events:
            if ev.get("action") == "tier_scoring_detail":
                scores = ev.get("scores", [])
                all_items.extend(scores)

    # Count by tier
    tier_counts = defaultdict(int)
    for item in all_items:
        tier_counts[item.get("tier", "UNKNOWN")] += 1

    # Build cards (cap at 100 for performance)
    display_items = all_items[:100]
    cards_html = ""
    for item in display_items:
        eid = _esc(str(item.get("id", item.get("evidence_id", ""))))
        tier = item.get("tier", "UNKNOWN")
        tier_class = f"tier-{tier.lower()}" if tier in ("GOLD", "SILVER", "BRONZE") else ""
        source_url = item.get("source_url", "")
        domain = _extract_domain(source_url)
        title = _esc(_truncate(item.get("source_title", domain), 40))
        quote = _esc(_truncate(item.get("quote", item.get("statement", "")), 150))
        relevance = item.get("relevance", item.get("sig_relevance", 0))
        perspective = item.get("perspective", "")

        # Signal bars
        sig_r = item.get("sig_relevance", relevance)
        sig_a = item.get("sig_authority", 0)
        sig_d = item.get("sig_density", 0)
        sig_f = item.get("sig_freshness", 0)
        sig_g = item.get("sig_grounding", 0)

        signals_html = ""
        for label, val in [("Rel", sig_r), ("Auth", sig_a), ("Dens", sig_d), ("Fresh", sig_f), ("Gnd", sig_g)]:
            if val > 0:
                pct = min(val * 100, 100)
                color = "var(--accent)" if val >= 0.7 else "var(--accent-amber)" if val >= 0.4 else "var(--accent-red)"
                signals_html += f"""
                <div class="signal-bar">
                  <span>{label}</span>
                  <div class="signal-bar-track">
                    <div class="signal-bar-fill" style="width:{pct:.0f}%; background:{color};"></div>
                  </div>
                </div>"""

        perspective_html = ""
        if perspective:
            perspective_html = f'<span class="perspective-tag">{_esc(perspective)}</span>'

        cards_html += f"""
        <div class="evidence-card" data-tier="{tier}">
          <div class="evidence-card-header">
            <span class="tier-badge {tier_class}">{tier}</span>
            <span class="domain" title="{_esc(source_url)}">{_esc(title)}</span>
            {perspective_html}
          </div>
          <div class="quote">{quote}</div>
          <div class="signal-bars">{signals_html}</div>
        </div>"""

    remainder_note = ""
    if len(all_items) > 100:
        remainder_note = f'<div style="text-align:center; padding:12px; font-size:12px; color:var(--text-tertiary);">Showing 100 of {len(all_items)} evidence items.</div>'

    empty_note = ""
    if not all_items:
        empty_note = '<div style="text-align:center; padding:24px; color:var(--text-tertiary); font-size:13px;">No detailed evidence data in this trace.</div>'

    return f"""
    <aside class="evidence-panel">
      <div class="evidence-panel-header">
        <h2>Evidence <span class="evidence-count-badge" id="evidence-visible-count">{len(display_items)}</span></h2>
        <select class="evidence-filter" id="evidence-filter">
          <option value="all">All Tiers</option>
          <option value="GOLD">Gold ({tier_counts.get("GOLD", 0)})</option>
          <option value="SILVER">Silver ({tier_counts.get("SILVER", 0)})</option>
          <option value="BRONZE">Bronze ({tier_counts.get("BRONZE", 0)})</option>
        </select>
      </div>
      <div class="evidence-panel-body">
        {cards_html}
        {remainder_note}
        {empty_note}
      </div>
    </aside>"""


# ---------------------------------------------------------------------------
# Left sidebar
# ---------------------------------------------------------------------------

def _build_sidebar(grouped: dict, metrics: dict) -> str:
    """Build the left navigation sidebar."""
    phase_status = _get_phase_status(grouped)

    # Pipeline phases nav
    pipeline_nav = ""
    for phase in _PHASE_ORDER:
        status = phase_status.get(phase, "pending")
        label = _PHASE_LABELS.get(phase, phase)
        dot_class = f"nav-dot nav-dot-{status}"
        pipeline_nav += f"""
        <a href="#" data-section="sec-{phase.replace('_', '-')}" style="pointer-events:none; opacity:0.6;">
          <span class="{dot_class}"></span>{label}
        </a>"""

    # Section nav items
    section_nav_items = [
        ("hero", "Overview"),
        ("sec-funnel", "Evidence Funnel"),
        ("sec-planning", "Planning"),
        ("sec-search", "Search & Fetch"),
        ("sec-storm", "STORM Interviews"),
        ("sec-evidence", "Evidence Analysis"),
        ("sec-verify", "Verification"),
        ("sec-iterations", "Iterations"),
        ("sec-synthesis", "Synthesis"),
        ("sec-gates", "Quality Gates"),
        ("sec-llm", "LLM Call Log"),
    ]

    section_nav = ""
    for sid, label in section_nav_items:
        section_nav += f'<a href="#" data-section="{sid}">{label}</a>'

    # Query at bottom
    query = metrics.get("query", "")
    query_html = ""
    if query:
        query_html = f"""
        <div class="sidebar-query">
          <div class="sidebar-query-label">Research Query</div>
          <div class="sidebar-query-text">{_esc(query)}</div>
        </div>"""

    return f"""
    <nav class="sidebar">
      <div class="sidebar-logo">
        <h1>POLARIS</h1>
        <div class="subtitle">Research Observatory</div>
      </div>

      <div class="sidebar-section">
        <div class="sidebar-section-title">Pipeline</div>
        {pipeline_nav}
      </div>

      <div class="sidebar-section">
        <div class="sidebar-section-title">Sections</div>
        {section_nav}
      </div>

      {query_html}
    </nav>"""


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_dashboard(trace_path: str, output_path: str) -> str:
    """Generate an HTML dashboard from a JSONL trace file.

    Args:
        trace_path: Path to the JSONL trace file.
        output_path: Path for the output HTML file.

    Returns:
        Path to the generated HTML file.
    """
    print(f"Loading trace: {trace_path}")
    events = _load_events(trace_path)
    print(f"  Loaded {len(events)} events")

    if not events:
        print("  WARNING: No events found -- generating empty dashboard")

    grouped = _group_by_type(events)
    print(f"  Event types: {sorted(grouped.keys())}")

    # Extract metadata
    metrics = _extract_key_metrics(grouped)
    vector_id = metrics["vector_id"]

    # If no vector_id from pipeline_start, try first event
    if vector_id == "unknown" and events:
        vector_id = events[0].get("vid", "unknown")
        metrics["vector_id"] = vector_id

    # Build all sections for center panel
    center_sections = [
        _section_hero(grouped, metrics),
        _section_evidence_meter(metrics),
        _section_pipeline_flow(grouped),
        _section_evidence_funnel(grouped),
        _section_planning(grouped),
        _section_search_fetch(grouped),
        _section_storm(grouped),
        _section_evidence_detail(grouped),
        _section_verification(grouped),
        _section_iteration_decisions(grouped),
        _section_synthesis(grouped),
        _section_quality_gates(grouped),
        _section_llm_log(grouped),
    ]

    center_html = "\n".join(s for s in center_sections if s)

    # Build panels
    sidebar_html = _build_sidebar(grouped, metrics)
    evidence_panel_html = _build_evidence_panel(grouped)

    html_doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>POLARIS Observatory - {_esc(vector_id)}</title>
  <style>{_build_css()}</style>
</head>
<body>
  {sidebar_html}
  <main class="center">
    {center_html}
  </main>
  {evidence_panel_html}
  <script>{_build_js()}</script>
</body>
</html>"""

    # Write output
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_doc, encoding="utf-8")
    size_kb = output.stat().st_size / 1024
    print(f"  Dashboard written: {output_path} ({size_kb:.1f} KB)")
    return str(output)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate POLARIS Research Observatory dashboard from trace JSONL.",
    )
    parser.add_argument(
        "--trace",
        required=True,
        help="Path to the JSONL trace file (e.g., logs/pg_trace_V001.jsonl)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path for output HTML file (e.g., outputs/dashboard_V001.html)",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.trace):
        print(f"ERROR: Trace file not found: {args.trace}")
        sys.exit(1)

    generate_dashboard(args.trace, args.output)


if __name__ == "__main__":
    main()
