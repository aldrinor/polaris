"""
Live anomaly detector for POLARIS pipeline.

Tails trace JSONL + polaris_graph.log concurrently and applies 50+ anomaly
detection rules across 10 categories. Writes alerts to both machine-readable
JSONL and human-readable markdown logs.

10 Anomaly Categories:
    1. CoT Leakage          Scan reasoning_capture text for CoT patterns
    2. Empty/Stub Content   Short reasoning, failed fetches, stub content
    3. Evidence Quality      Low extraction, high off-topic, duplicates
    4. Verification          Batch timeouts, rubber-stamping, failures
    5. Synthesis             Low word count, citation poverty
    6. Cost                  Budget overruns, token explosions
    7. Quality Gates         Gate failures, high iteration count
    8. Timing                Node duration anomalies
    9. Log Errors            ERROR/CRITICAL in polaris_graph.log
   10. Emission Completeness  Missing new visibility emissions after node completes

CLI: python scripts/live_monitor.py --trace logs/pg_trace_XXX.jsonl
     [--log logs/polaris_graph.log]

Zero new dependencies. Uses: watchfiles (already installed).
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration (LAW VI)
# ---------------------------------------------------------------------------
PG_MONITOR_COST_WARN = float(os.getenv("PG_MONITOR_COST_WARN", "3.0"))
PG_MONITOR_COST_CRIT = float(os.getenv("PG_MONITOR_COST_CRIT", "5.0"))
PG_MONITOR_BATCH_TIMEOUT_MS = int(os.getenv("PG_MONITOR_BATCH_TIMEOUT_MS", "120000"))
PG_MONITOR_NODE_TIMEOUT_MULT = float(os.getenv("PG_MONITOR_NODE_TIMEOUT_MULT", "2.0"))
PG_LIVE_ANOMALY_JSONL = os.getenv(
    "PG_LIVE_ANOMALY_LOG", "logs/live_anomaly_log.jsonl"
)
PG_LIVE_ANOMALY_MD = os.getenv(
    "PG_LIVE_ANOMALY_LOG_MD", "logs/live_anomaly_log.md"
)

# Pricing (from openrouter_client.py:53-54)
INPUT_COST_PER_M = float(os.getenv("OPENROUTER_INPUT_COST_PER_M", "0.45"))
OUTPUT_COST_PER_M = float(os.getenv("OPENROUTER_OUTPUT_COST_PER_M", "2.25"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("live_monitor")

# ---------------------------------------------------------------------------
# CoT patterns (imported conceptually from automated_deep_audit.py:50-90)
# ---------------------------------------------------------------------------
_COT_PATTERNS = [
    r"\bLet me\b",
    r"\bI need to\b",
    r"\bFirst,",
    r"\bStep\s+\d+:",
    r"\bNow I will\b",
    r"\bthinking about\b",
    r"\bIn summary, I\b",
    r"\bAs an AI\b",
    r"\bmy analysis\b",
    r"\bI should note\b",
]

_COT_HEURISTIC_PATTERNS = [
    r"\bI will now\b",
    r"\bLet's\b",
    r"\bI have identified\b",
    r"\bI'll\b",
    r"\bmy assessment\b",
    r"\bI believe\b",
    r"\bI think\b",
    r"\bI would\b",
    r"\bmy review\b",
    r"\bI must write\b",
    r"\bI only have \d+\b",
    r"\bGiven the strict instruction\b",
    r"\bThe content stays grounded\b",
    r"\bI should indicate\b",
    r"\bI should write\b",
    r"\bI cannot invent\b",
    r"\bI am instructed\b",
    r"\bI was told to\b",
    r"\bthe provided evidence\b",
    r"^\s*\d+[a-z]\.\s",
]

_ALL_COT_PATTERNS = [re.compile(p, re.IGNORECASE | re.MULTILINE)
                     for p in _COT_PATTERNS + _COT_HEURISTIC_PATTERNS]

# Expected node durations (ms) from test history (PG_TEST_039, 037, 047)
_EXPECTED_NODE_DURATION_MS = {
    "plan": 90_000,        # ~90s
    "search": 300_000,     # ~5min
    "storm_interviews": 300_000,  # ~5min
    "analyze": 600_000,    # ~10min
    "verify": 300_000,     # ~5min
    "evaluate": 60_000,    # ~1min
    "synthesize": 600_000, # ~10min
    "search_gaps": 180_000, # ~3min
}

# Log patterns to detect
_LOG_ERROR_PATTERN = re.compile(r"\b(ERROR|CRITICAL)\b")
_LOG_API_ERROR_PATTERN = re.compile(r"api_error|APIError|HTTPStatusError", re.IGNORECASE)
_LOG_HARD_STOP_PATTERN = re.compile(r"Hard stop|astream failed|HALT", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Anomaly data model
# ---------------------------------------------------------------------------
def _make_anomaly(
    severity: str,
    category: str,
    rule: str,
    message: str,
    event_ref: Optional[str] = None,
    data: Optional[dict] = None,
) -> dict:
    """Create a structured anomaly record."""
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "severity": severity,  # INFO, WARN, CRITICAL
        "category": category,
        "rule": rule,
        "message": message,
        "event_ref": event_ref,
        "data": data or {},
    }


# ---------------------------------------------------------------------------
# AnomalyDetector: stateful anomaly analysis engine
# ---------------------------------------------------------------------------
class AnomalyDetector:
    """Stateful anomaly detector maintaining running pipeline state.

    Processes trace events one at a time, maintaining cumulative state
    and emitting anomalies when rules are triggered.
    """

    def __init__(self):
        # Cumulative state
        self.cumulative_cost: float = 0.0
        self.event_counts: dict[str, int] = defaultdict(int)
        self.node_start_times: dict[str, str] = {}  # node -> ISO timestamp
        self.node_durations: dict[str, float] = {}
        self.fetch_urls: set[str] = set()
        self.fetch_statuses: dict[str, int] = defaultdict(int)  # status -> count
        self.evidence_extracted: int = 0
        self.evidence_offtopic: int = 0
        self.evidence_dedup_removed: int = 0
        self.evidence_total: int = 0
        self.verification_batches: list[dict] = []
        self.verification_verdicts: list[str] = []
        self.word_count: int = 0
        self.citation_count: int = 0
        self.faithfulness: float = -1.0
        self.iteration: int = 0
        self.quality_gates: list[dict] = []
        self.api_error_count: int = 0
        self.log_error_count: int = 0
        self.total_output_tokens: int = 0

        # Emission completeness tracking (new visibility emissions)
        self.seen_emissions: set[str] = set()  # track which new emission types we've seen
        self.node_completed: set[str] = set()  # track which nodes have completed

        # New emission state
        self.nli_faithfulness_pct: float = -1.0
        self.hallucination_ratios: list[float] = []
        self.evidence_conflicts_count: int = 0
        self.dedup_removal_ratio: float = 0.0
        self.signal_medians: dict[str, float] = {}
        self.gap_needs_iteration: Optional[bool] = None
        self.full_report_received: bool = False
        self.expansion_pass_count: int = 0

        # Anomaly accumulator
        self.anomalies: list[dict] = []

    def process_event(self, ev: dict) -> list[dict]:
        """Process a single trace event, return any new anomalies."""
        new_anomalies: list[dict] = []
        ev_type = ev.get("type", "")
        node = ev.get("node", "")
        self.event_counts[ev_type] += 1

        ref = f"{ev.get('ts', '')}:{node}:{ev_type}"

        # Dispatch to category handlers
        if ev_type == "reasoning_capture":
            new_anomalies.extend(self._check_cot_leakage(ev, ref))
            new_anomalies.extend(self._check_empty_stub(ev, ref))

        elif ev_type == "fetch":
            new_anomalies.extend(self._check_fetch(ev, ref))

        elif ev_type == "evidence":
            new_anomalies.extend(self._check_evidence(ev, ref))

        elif ev_type == "llm_call":
            new_anomalies.extend(self._check_cost(ev, ref))
            # Track verification batch results for rubber-stamp detection
            if node == "verify":
                self._track_verification_call(ev)

        elif ev_type == "quality_gate":
            new_anomalies.extend(self._check_quality_gate(ev, ref))

        elif ev_type == "node_start":
            self.node_start_times[node] = ev.get("ts", "")
            if ev.get("iteration") is not None:
                self.iteration = ev["iteration"]

        elif ev_type == "node_end":
            self.node_completed.add(node)
            new_anomalies.extend(self._check_timing(ev, node, ref))
            # BUG-1 fix: Check verification batches when verify node ends
            if node == "verify":
                new_anomalies.extend(self._check_verification_summary(ref))
            # Check emission completeness after final nodes
            if node in ("synthesize", "evaluate"):
                new_anomalies.extend(self.check_emission_completeness())

        elif ev_type == "iteration_decision":
            self.iteration = ev.get("iteration", self.iteration)
            new_anomalies.extend(self._check_iteration(ev, ref))

        elif ev_type == "search_result":
            pass  # Tracked passively

        # Accumulate
        self.anomalies.extend(new_anomalies)
        return new_anomalies

    def process_log_line(self, line: str) -> list[dict]:
        """Process a polaris_graph.log line for error detection."""
        new_anomalies: list[dict] = []
        ref = f"log:{datetime.now(timezone.utc).isoformat()}"

        if _LOG_ERROR_PATTERN.search(line):
            self.log_error_count += 1
            severity = "CRITICAL" if "CRITICAL" in line else "WARN"
            new_anomalies.append(_make_anomaly(
                severity, "log_errors", "error_line",
                f"Log {severity}: {line.strip()[:200]}",
                ref,
            ))

        if _LOG_API_ERROR_PATTERN.search(line):
            self.api_error_count += 1
            if self.api_error_count > 10:
                new_anomalies.append(_make_anomaly(
                    "CRITICAL", "log_errors", "api_error_flood",
                    f"API error count: {self.api_error_count} (threshold: 10)",
                    ref,
                    {"count": self.api_error_count},
                ))

        if _LOG_HARD_STOP_PATTERN.search(line):
            new_anomalies.append(_make_anomaly(
                "CRITICAL", "log_errors", "hard_stop",
                f"Hard stop detected: {line.strip()[:200]}",
                ref,
            ))

        self.anomalies.extend(new_anomalies)
        return new_anomalies

    # -- Category 1: CoT Leakage ------------------------------------------
    def _check_cot_leakage(self, ev: dict, ref: str) -> list[dict]:
        text = ev.get("reasoning_text", "")
        if not text:
            return []

        matches = []
        for pattern in _ALL_COT_PATTERNS:
            found = pattern.findall(text)
            matches.extend(found)

        if not matches:
            return []

        count = len(matches)
        # FIX-P7: CoT patterns in reasoning_content are EXPECTED — downgrade to INFO.
        # Only flag as CRITICAL/WARN when CoT appears in actual output text.
        _is_reasoning_field = ev.get("evidence_action") == "reasoning_capture"
        if _is_reasoning_field:
            severity = "INFO"
        else:
            severity = "CRITICAL" if count >= 3 else "WARN"
        return [_make_anomaly(
            severity, "cot_leakage", "cot_pattern_match",
            f"CoT leakage: {count} pattern matches in {ev.get('call_type', 'unknown')} "
            f"reasoning ({len(text)} chars). Samples: {matches[:5]}",
            ref,
            {"match_count": count, "samples": matches[:10], "text_len": len(text)},
        )]

    # -- Category 2: Empty/Stub Content -----------------------------------
    def _check_empty_stub(self, ev: dict, ref: str) -> list[dict]:
        anomalies = []
        text = ev.get("reasoning_text", "")

        if len(text) < 20:
            anomalies.append(_make_anomaly(
                "CRITICAL", "empty_stub", "short_reasoning",
                f"Reasoning text only {len(text)} chars (threshold: 20) "
                f"for {ev.get('call_type', 'unknown')}",
                ref,
                {"text_len": len(text), "text": text[:100]},
            ))

        return anomalies

    def _check_fetch(self, ev: dict, ref: str) -> list[dict]:
        anomalies = []
        url = ev.get("url", "")
        status = ev.get("status", "")
        content_len = ev.get("content_len", 0)

        # Track fetch URLs for duplicate detection
        if url:
            if url in self.fetch_urls:
                anomalies.append(_make_anomaly(
                    "INFO", "evidence", "duplicate_fetch_url",
                    f"Duplicate fetch URL: {url[:120]}",
                    ref,
                ))
            self.fetch_urls.add(url)

        self.fetch_statuses[status] += 1

        # Failed fetches
        if status in ("error", "timeout", "paywall", "blocked"):
            anomalies.append(_make_anomaly(
                "WARN", "empty_stub", "fetch_failed",
                f"Fetch {status}: {url[:120]} (content_len={content_len})",
                ref,
                {"status": status, "url": url[:200], "content_len": content_len},
            ))
        elif status.startswith("4") or status.startswith("5"):
            anomalies.append(_make_anomaly(
                "WARN", "empty_stub", "fetch_http_error",
                f"Fetch HTTP {status}: {url[:120]}",
                ref,
                {"status": status, "url": url[:200]},
            ))

        # Stub content
        if status == "ok" and 0 < content_len < 500:
            anomalies.append(_make_anomaly(
                "WARN", "empty_stub", "stub_content",
                f"Stub content ({content_len} chars): {url[:120]}",
                ref,
                {"content_len": content_len, "url": url[:200]},
            ))

        return anomalies

    # -- Category 3: Evidence Quality --------------------------------------
    def _check_evidence(self, ev: dict, ref: str) -> list[dict]:
        anomalies = []
        action = ev.get("action", "")
        count = ev.get("count", 0)

        if action == "extracted":
            self.evidence_extracted = count
            if count < 5:
                anomalies.append(_make_anomaly(
                    "WARN", "evidence", "low_extraction",
                    f"Only {count} evidence extracted (threshold: 5)",
                    ref,
                    {"count": count},
                ))

        elif action == "off_topic_filtered":
            self.evidence_offtopic = count
            if self.evidence_extracted > 0:
                ratio = count / max(self.evidence_extracted, 1)
                if ratio > 0.50:
                    anomalies.append(_make_anomaly(
                        "WARN", "evidence", "high_offtopic",
                        f"Off-topic ratio: {ratio:.0%} ({count}/{self.evidence_extracted})",
                        ref,
                        {"offtopic": count, "total": self.evidence_extracted},
                    ))

        elif action == "dedup_removed":
            self.evidence_dedup_removed = count
            if self.evidence_extracted > 0:
                ratio = count / max(self.evidence_extracted, 1)
                if ratio > 0.40:
                    anomalies.append(_make_anomaly(
                        "WARN", "evidence", "high_dedup",
                        f"Dedup removed {ratio:.0%} ({count}/{self.evidence_extracted})",
                        ref,
                        {"removed": count, "total": self.evidence_extracted},
                    ))

        elif action == "accumulated":
            self.evidence_total = count

        # -- New visibility emission handlers ------------------------------
        elif action == "query_plan" or action == "seed_query_plan":
            self.seen_emissions.add("query_plan")
            missing = ev.get("missing_perspectives", [])
            if len(missing) >= 4:
                anomalies.append(_make_anomaly(
                    "WARN", "evidence", "many_missing_perspectives",
                    f"Query plan missing {len(missing)} perspectives: {', '.join(missing[:5])}",
                    ref, {"missing": missing},
                ))

        elif action == "tier_signal_distribution":
            self.seen_emissions.add("tier_signal_distribution")
            stats = ev.get("signal_stats", {})
            for sig_name, vals in stats.items():
                median = vals.get("median", 0.5)
                self.signal_medians[sig_name] = median
                if median < 0.15:
                    anomalies.append(_make_anomaly(
                        "WARN", "evidence", "low_signal_median",
                        f"Signal '{sig_name}' median={median:.3f} (threshold: 0.15)",
                        ref, {"signal": sig_name, "median": median},
                    ))

        elif action == "dedup_summary":
            self.seen_emissions.add("dedup_summary")
            pre = ev.get("pre_dedup", 0)
            post = ev.get("post_dedup", ev.get("count", 0))
            if pre > 0:
                self.dedup_removal_ratio = 1.0 - (post / pre)
                if self.dedup_removal_ratio > 0.60:
                    anomalies.append(_make_anomaly(
                        "WARN", "evidence", "excessive_dedup",
                        f"Dedup removed {self.dedup_removal_ratio:.0%} ({pre}->{post})",
                        ref, {"pre": pre, "post": post, "ratio": self.dedup_removal_ratio},
                    ))

        elif action == "fetch_summary":
            self.seen_emissions.add("fetch_summary")
            total = ev.get("total_attempted", 0)
            failed = ev.get("failed", 0)
            if total > 0 and failed / total > 0.40:
                anomalies.append(_make_anomaly(
                    "WARN", "evidence", "high_fetch_failure",
                    f"Fetch failure rate: {failed}/{total} ({failed/total:.0%})",
                    ref, {"total": total, "failed": failed},
                ))

        elif action == "nli_verification_detail":
            self.seen_emissions.add("nli_verification_detail")
            pct = ev.get("faithfulness_pct", 0)
            self.nli_faithfulness_pct = pct
            disputed = ev.get("disputed_count", 0)
            if pct < 60.0:
                anomalies.append(_make_anomaly(
                    "CRITICAL", "verification", "low_nli_faithfulness",
                    f"NLI faithfulness {pct:.1f}% < 60% threshold",
                    ref, {"faithfulness_pct": pct, "disputed": disputed},
                ))
            elif pct < 75.0:
                anomalies.append(_make_anomaly(
                    "WARN", "verification", "moderate_nli_faithfulness",
                    f"NLI faithfulness {pct:.1f}% < 75%",
                    ref, {"faithfulness_pct": pct, "disputed": disputed},
                ))

        elif action == "cross_reference_groups":
            self.seen_emissions.add("cross_reference_groups")

        elif action == "report_outline":
            self.seen_emissions.add("report_outline")
            sections = ev.get("sections", [])
            if len(sections) < 3:
                anomalies.append(_make_anomaly(
                    "WARN", "synthesis", "thin_outline",
                    f"Report outline has only {len(sections)} sections (expected >= 3)",
                    ref, {"section_count": len(sections)},
                ))

        elif action == "section_evidence_map":
            self.seen_emissions.add("section_evidence_map")
            mapping = ev.get("mapping", [])
            starved = [m for m in mapping if (m.get("evidence_count", 0)) < 3]
            if starved:
                anomalies.append(_make_anomaly(
                    "WARN", "synthesis", "evidence_starved_sections",
                    f"{len(starved)} sections have <3 evidence pieces",
                    ref, {"starved": [m.get("section_id") for m in starved]},
                ))

        elif action == "hallucination_audit":
            self.seen_emissions.add("hallucination_audit")
            sections = ev.get("sections", [])
            for s in sections:
                ratio = s.get("hallucination_ratio", 0)
                self.hallucination_ratios.append(ratio)
                if ratio > 0.40:
                    anomalies.append(_make_anomaly(
                        "WARN" if ratio < 0.60 else "CRITICAL",
                        "synthesis", "high_hallucination",
                        f"Section '{s.get('title', s.get('section_id', '?'))[:50]}' "
                        f"hallucination ratio {ratio:.0%}",
                        ref, {"section": s.get("section_id"), "ratio": ratio,
                               "needs_rewrite": s.get("needs_rewrite")},
                    ))

        elif action == "evidence_conflicts":
            self.seen_emissions.add("evidence_conflicts")
            conflicts = ev.get("conflicts", [])
            self.evidence_conflicts_count = len(conflicts)
            high_score = [c for c in conflicts if (c.get("score", 0)) > 0.85]
            if high_score:
                anomalies.append(_make_anomaly(
                    "WARN", "evidence", "high_score_conflicts",
                    f"{len(high_score)} evidence conflicts with score > 0.85",
                    ref, {"total": len(conflicts), "high_score": len(high_score)},
                ))

        elif action == "expansion_pass":
            self.seen_emissions.add("expansion_pass")
            self.expansion_pass_count += 1
            if self.expansion_pass_count > 3:
                anomalies.append(_make_anomaly(
                    "WARN", "synthesis", "excessive_expansion",
                    f"Expansion pass #{self.expansion_pass_count} (threshold: 3)",
                    ref, {"pass_count": self.expansion_pass_count},
                ))

        elif action == "gap_analysis_detail":
            self.seen_emissions.add("gap_analysis_detail")
            self.gap_needs_iteration = ev.get("needs_iteration")
            gaps = ev.get("gaps", [])
            if len(gaps) > 10:
                anomalies.append(_make_anomaly(
                    "WARN", "evidence", "many_gaps",
                    f"Gap analysis found {len(gaps)} gaps (threshold: 10)",
                    ref, {"gap_count": len(gaps)},
                ))

        elif action == "agentic_round_summary":
            self.seen_emissions.add("agentic_round_summary")

        elif action == "agentic_search_complete":
            self.seen_emissions.add("agentic_search_complete")

        elif action == "section_evidence_filtered":
            self.seen_emissions.add("section_evidence_filtered")

        elif action == "report_assembled":
            if ev.get("full_report"):
                self.full_report_received = True

        return anomalies

    # -- Category 4: Verification ------------------------------------------
    def _track_verification_call(self, ev: dict) -> None:
        """Track verification LLM call for rubber-stamp & batch analysis."""
        duration_ms = ev.get("duration_ms", 0)
        call_type = ev.get("call_type", "")
        self.verification_batches.append({
            "duration_ms": duration_ms,
            "call_type": call_type,
            "output_tokens": ev.get("output_tokens", 0),
        })

    def _check_verification_summary(self, ref: str) -> list[dict]:
        """Check verification summary when verify node ends."""
        anomalies = []

        if not self.verification_batches:
            return anomalies

        # Batch timeout check
        slow_batches = [b for b in self.verification_batches
                        if b["duration_ms"] > PG_MONITOR_BATCH_TIMEOUT_MS]
        if slow_batches:
            anomalies.append(_make_anomaly(
                "WARN", "verification", "batch_timeouts",
                f"{len(slow_batches)}/{len(self.verification_batches)} verification "
                f"batches exceeded {PG_MONITOR_BATCH_TIMEOUT_MS}ms timeout",
                ref,
                {"slow_count": len(slow_batches),
                 "total": len(self.verification_batches)},
            ))

        # Batch failure rate (output_tokens < 10 = likely failed)
        failed = [b for b in self.verification_batches if b["output_tokens"] < 10]
        if len(self.verification_batches) > 5:
            fail_rate = len(failed) / len(self.verification_batches)
            if fail_rate > 0.30:
                anomalies.append(_make_anomaly(
                    "CRITICAL", "verification", "high_batch_failure",
                    f"Verification batch failure rate: {fail_rate:.0%} "
                    f"({len(failed)}/{len(self.verification_batches)})",
                    ref,
                    {"failed": len(failed),
                     "total": len(self.verification_batches)},
                ))

        # Rubber-stamp detection: check if faithfulness gate passed but
        # all verification verdicts are identical (tracked via quality_gate)
        faithful_gates = [g for g in self.quality_gates
                          if g.get("gate") == "faithfulness"]
        if faithful_gates:
            last_gate = faithful_gates[-1]
            actual = last_gate.get("actual")
            if actual is not None and actual >= 0.99 and len(self.verification_batches) > 5:
                anomalies.append(_make_anomaly(
                    "WARN", "verification", "rubber_stamp_suspect",
                    f"100% faithfulness with {len(self.verification_batches)} "
                    f"batches — possible rubber-stamping",
                    ref,
                    {"faithfulness": actual,
                     "batch_count": len(self.verification_batches)},
                ))

        return anomalies

    # -- Category 5: Synthesis (checked via quality gates) -----------------

    # -- Category 6: Cost --------------------------------------------------
    def _check_cost(self, ev: dict, ref: str) -> list[dict]:
        anomalies = []
        in_tok = ev.get("input_tokens", 0)
        out_tok = ev.get("output_tokens", 0)
        call_cost = (in_tok * INPUT_COST_PER_M / 1e6) + (out_tok * OUTPUT_COST_PER_M / 1e6)
        self.cumulative_cost += call_cost
        self.total_output_tokens += out_tok

        # Single call token explosion
        if out_tok > 50_000:
            anomalies.append(_make_anomaly(
                "WARN", "cost", "token_explosion",
                f"Single LLM call: {out_tok:,} output tokens "
                f"({ev.get('call_type', 'unknown')})",
                ref,
                {"output_tokens": out_tok, "call_type": ev.get("call_type", "")},
            ))

        # Cumulative cost thresholds
        if self.cumulative_cost > PG_MONITOR_COST_CRIT:
            anomalies.append(_make_anomaly(
                "CRITICAL", "cost", "cost_critical",
                f"Cumulative cost ${self.cumulative_cost:.2f} > "
                f"${PG_MONITOR_COST_CRIT:.2f} threshold",
                ref,
                {"cumulative_cost": self.cumulative_cost},
            ))
        elif self.cumulative_cost > PG_MONITOR_COST_WARN:
            anomalies.append(_make_anomaly(
                "WARN", "cost", "cost_warn",
                f"Cumulative cost ${self.cumulative_cost:.2f} > "
                f"${PG_MONITOR_COST_WARN:.2f} threshold",
                ref,
                {"cumulative_cost": self.cumulative_cost},
            ))

        return anomalies

    # -- Category 7: Quality Gates -----------------------------------------
    def _check_quality_gate(self, ev: dict, ref: str) -> list[dict]:
        anomalies = []
        gate = ev.get("gate", "")
        passed = ev.get("passed", True)
        actual = ev.get("actual")
        threshold = ev.get("threshold")

        self.quality_gates.append(ev)

        if not passed:
            severity = "CRITICAL" if gate in ("faithfulness",) else "WARN"
            anomalies.append(_make_anomaly(
                severity, "quality_gates", "gate_fail",
                f"Quality gate FAIL: {gate} "
                f"(actual={actual}, threshold={threshold})",
                ref,
                {"gate": gate, "actual": actual, "threshold": threshold},
            ))

        # Track specific metrics
        if gate == "faithfulness" and actual is not None:
            self.faithfulness = actual
        if gate == "word_count" and actual is not None:
            self.word_count = actual
        if gate == "citation_count" and actual is not None:
            self.citation_count = actual

        # Synthesis checks
        if gate == "word_count" and actual is not None and actual < 8000:
            anomalies.append(_make_anomaly(
                "WARN", "synthesis", "low_word_count",
                f"Word count {actual} < 8000 at synthesis end",
                ref,
                {"word_count": actual},
            ))

        if gate == "citation_count" and actual is not None and actual < 30:
            anomalies.append(_make_anomaly(
                "WARN", "synthesis", "low_citations",
                f"Citation count {actual} < 30",
                ref,
                {"citation_count": actual},
            ))

        return anomalies

    # -- Category 8: Timing ------------------------------------------------
    def _check_timing(self, ev: dict, node: str, ref: str) -> list[dict]:
        anomalies = []
        duration_ms = ev.get("duration_ms", 0)
        self.node_durations[node] = duration_ms

        expected = _EXPECTED_NODE_DURATION_MS.get(node)
        if expected:
            mult = PG_MONITOR_NODE_TIMEOUT_MULT
            if duration_ms > expected * (mult + 1):  # 3x expected = CRIT
                anomalies.append(_make_anomaly(
                    "CRITICAL", "timing", "node_very_slow",
                    f"Node {node}: {duration_ms/1000:.1f}s "
                    f"(>{(mult+1):.0f}x expected {expected/1000:.0f}s)",
                    ref,
                    {"node": node, "duration_ms": duration_ms, "expected_ms": expected},
                ))
            elif duration_ms > expected * mult:  # 2x expected = WARN
                anomalies.append(_make_anomaly(
                    "WARN", "timing", "node_slow",
                    f"Node {node}: {duration_ms/1000:.1f}s "
                    f"(>{mult:.0f}x expected {expected/1000:.0f}s)",
                    ref,
                    {"node": node, "duration_ms": duration_ms, "expected_ms": expected},
                ))

        # Total pipeline time check (sum all node durations)
        total_ms = sum(self.node_durations.values())
        if total_ms > 60 * 60 * 1000:  # > 60 min
            anomalies.append(_make_anomaly(
                "WARN", "timing", "total_time_exceeded",
                f"Total pipeline time: {total_ms/60000:.1f}min > 60min",
                ref,
                {"total_ms": total_ms},
            ))

        return anomalies

    # -- Iteration check ---------------------------------------------------
    def _check_iteration(self, ev: dict, ref: str) -> list[dict]:
        anomalies = []
        iteration = ev.get("iteration", 0)
        decision = ev.get("decision", "")

        if iteration >= 3:
            anomalies.append(_make_anomaly(
                "WARN", "quality_gates", "high_iteration",
                f"Iteration {iteration} (>= 3): decision={decision}",
                ref,
                {"iteration": iteration, "decision": decision},
            ))

        if decision in ("CASE_3", "CASE_4"):
            severity = "CRITICAL" if decision == "CASE_4" else "WARN"
            anomalies.append(_make_anomaly(
                severity, "quality_gates", "gating_case",
                f"Gating case {decision} at iteration {iteration}",
                ref,
                {"case": decision, "iteration": iteration},
            ))

        return anomalies

    # -- Category 10: Emission Completeness ---------------------------------
    def check_emission_completeness(self) -> list[dict]:
        """Check that all expected new emissions were seen after pipeline completes.

        Called externally after all events are processed (e.g., on pipeline end).
        """
        anomalies = []
        ref = f"completeness:{datetime.now(timezone.utc).isoformat()}"

        # Map: node -> expected emissions
        # FIX-P8: Conditionally include emissions that depend on feature flags.
        import os as _emission_os
        _nli_enabled = _emission_os.getenv("PG_NLI_ENABLED", "0") == "1"
        _halluc_enabled = _emission_os.getenv("PG_HALLUCINATION_AUDIT_ENABLED", "0") == "1"

        _verify_emissions = ["nli_verification_detail"] if _nli_enabled else []
        _synth_emissions = ["report_outline", "section_evidence_map"]
        if _halluc_enabled:
            _synth_emissions.append("hallucination_audit")

        expected = {
            "plan": ["query_plan"],
            "analyze": ["tier_signal_distribution", "dedup_summary", "fetch_summary"],
            "verify": _verify_emissions,
            "synthesize": _synth_emissions,
            "evaluate": ["gap_analysis_detail"],
        }

        for node, emissions in expected.items():
            if node not in self.node_completed:
                continue  # Node didn't run, skip
            for em in emissions:
                if em not in self.seen_emissions:
                    anomalies.append(_make_anomaly(
                        "WARN", "emission_completeness", "missing_emission",
                        f"Node '{node}' completed but no '{em}' emission received",
                        ref, {"node": node, "emission": em},
                    ))

        # Full report check
        if "synthesize" in self.node_completed and not self.full_report_received:
            anomalies.append(_make_anomaly(
                "WARN", "emission_completeness", "missing_full_report",
                "Synthesis completed but no full_report in report_assembled event",
                ref,
            ))

        self.anomalies.extend(anomalies)
        return anomalies


# ---------------------------------------------------------------------------
# Log writer: writes anomalies to JSONL + Markdown
# ---------------------------------------------------------------------------
class AnomalyWriter:
    """Writes anomalies to both JSONL and Markdown log files."""

    def __init__(self, jsonl_path: str, md_path: str):
        self._jsonl_path = Path(jsonl_path)
        self._md_path = Path(md_path)
        self._jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        self._md_path.parent.mkdir(parents=True, exist_ok=True)
        self._count = 0

        # Initialize markdown with header
        with open(self._md_path, "w", encoding="utf-8") as f:
            f.write("# POLARIS Live Anomaly Log\n\n")
            f.write(f"Started: {datetime.now(timezone.utc).isoformat()}\n\n")
            f.write("---\n\n")

        # Clear JSONL
        with open(self._jsonl_path, "w", encoding="utf-8") as f:
            pass

    def write(self, anomaly: dict) -> None:
        """Append an anomaly to both log files."""
        self._count += 1

        # JSONL
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(anomaly, default=str) + "\n")

        # Markdown
        severity = anomaly.get("severity", "UNKNOWN")
        category = anomaly.get("category", "")
        rule = anomaly.get("rule", "")
        message = anomaly.get("message", "")
        ts = anomaly.get("ts", "")

        icon = {"CRITICAL": "!!!", "WARN": "!", "INFO": ""}.get(severity, "")

        with open(self._md_path, "a", encoding="utf-8") as f:
            f.write(f"### [{severity}] {category}/{rule}\n")
            f.write(f"**Time:** {ts}  \n")
            f.write(f"**Message:** {message}  \n\n")

    @property
    def count(self) -> int:
        return self._count


# ---------------------------------------------------------------------------
# File tailer (shared logic)
# ---------------------------------------------------------------------------
async def tail_file(path: Path, offset: int = 0, poll: float = 0.5):
    """Async generator yielding new lines from a file."""
    current_offset = offset

    while True:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(current_offset)
                    new_data = f.read()
                    current_offset = f.tell()

                for line in new_data.splitlines():
                    line = line.strip()
                    if line:
                        yield line
            except (OSError, PermissionError):
                pass

        await asyncio.sleep(poll)


# ---------------------------------------------------------------------------
# Main monitor loop
# ---------------------------------------------------------------------------
async def run_monitor(
    trace_path: Path,
    log_path: Optional[Path],
    writer: AnomalyWriter,
):
    """Main monitoring loop tailing trace + log concurrently."""
    detector = AnomalyDetector()

    async def monitor_trace():
        """Tail trace JSONL and process events."""
        logger.info("Monitoring trace: %s", trace_path)
        async for line in tail_file(trace_path):
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue

            new_anomalies = detector.process_event(ev)
            for a in new_anomalies:
                writer.write(a)
                sev = a["severity"]
                prefix = f"[{sev}]"
                if sev == "CRITICAL":
                    logger.critical("%s %s", prefix, a["message"])
                elif sev == "WARN":
                    logger.warning("%s %s", prefix, a["message"])
                else:
                    logger.info("%s %s", prefix, a["message"])

    async def monitor_log():
        """Tail polaris_graph.log and check for errors."""
        if not log_path:
            return
        logger.info("Monitoring log: %s", log_path)

        # Start from end of file
        offset = 0
        if log_path.exists():
            offset = log_path.stat().st_size

        async for line in tail_file(log_path, offset=offset):
            new_anomalies = detector.process_log_line(line)
            for a in new_anomalies:
                writer.write(a)
                sev = a["severity"]
                if sev == "CRITICAL":
                    logger.critical("[%s] %s", sev, a["message"])
                else:
                    logger.warning("[%s] %s", sev, a["message"])

    async def status_reporter():
        """Periodically log a status summary."""
        while True:
            await asyncio.sleep(30)
            logger.info(
                "STATUS: events=%d anomalies=%d cost=$%.2f evidence=%d "
                "faith=%.1f%% iter=%d",
                sum(detector.event_counts.values()),
                writer.count,
                detector.cumulative_cost,
                detector.evidence_total,
                detector.faithfulness * 100 if detector.faithfulness >= 0 else -1,
                detector.iteration,
            )

    # Run all tasks concurrently
    tasks = [
        asyncio.create_task(monitor_trace()),
        asyncio.create_task(status_reporter()),
    ]
    if log_path:
        tasks.append(asyncio.create_task(monitor_log()))

    logger.info("=" * 60)
    logger.info("POLARIS Live Monitor ACTIVE")
    logger.info("Trace: %s", trace_path)
    if log_path:
        logger.info("Log: %s", log_path)
    logger.info("Anomaly JSONL: %s", PG_LIVE_ANOMALY_JSONL)
    logger.info("Anomaly MD: %s", PG_LIVE_ANOMALY_MD)
    logger.info("=" * 60)

    await asyncio.gather(*tasks)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Live Anomaly Monitor"
    )
    parser.add_argument(
        "--trace",
        type=str,
        required=True,
        help="Path to trace JSONL file (e.g., logs/pg_trace_PG_TEST_059.jsonl)",
    )
    parser.add_argument(
        "--log",
        type=str,
        default="logs/polaris_graph.log",
        help="Path to polaris_graph.log (default: logs/polaris_graph.log)",
    )
    args = parser.parse_args()

    trace_path = Path(args.trace)
    log_path = Path(args.log) if args.log else None

    if log_path and not log_path.exists():
        logger.warning("Log file not found: %s (will watch for creation)", log_path)

    writer = AnomalyWriter(PG_LIVE_ANOMALY_JSONL, PG_LIVE_ANOMALY_MD)

    try:
        asyncio.run(run_monitor(trace_path, log_path, writer))
    except KeyboardInterrupt:
        logger.info("Monitor stopped. Total anomalies: %d", writer.count)


if __name__ == "__main__":
    main()
