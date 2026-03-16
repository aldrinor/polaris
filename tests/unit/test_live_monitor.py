"""
Tests for scripts/live_monitor.py -- AnomalyDetector + AnomalyWriter.

Covers all 9 anomaly categories with specific inputs and expected outputs.
"""

import json
import os
from pathlib import Path

import pytest

from scripts.live_monitor import (
    AnomalyDetector,
    AnomalyWriter,
    _make_anomaly,
    _ALL_COT_PATTERNS,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def detector():
    """Fresh AnomalyDetector instance."""
    return AnomalyDetector()


@pytest.fixture
def writer(tmp_path):
    """AnomalyWriter writing to tmp_path."""
    jsonl = str(tmp_path / "anomaly.jsonl")
    md = str(tmp_path / "anomaly.md")
    return AnomalyWriter(jsonl, md)


def _ev(ev_type, node="test", **data):
    """Helper to construct a trace event dict."""
    return {"type": ev_type, "node": node, "ts": "2026-02-26T00:00:00Z", **data}


# =============================================================================
# Category 1: CoT Leakage
# =============================================================================

class TestCotLeakage:
    """Category 1: CoT pattern detection in reasoning_capture events."""

    def test_no_cot_no_anomaly(self, detector):
        ev = _ev("reasoning_capture", "plan",
                 call_type="generate",
                 reasoning_text="Water filtration removes contaminants through activated carbon.")
        anomalies = detector.process_event(ev)
        assert len(anomalies) == 0

    def test_single_cot_pattern_is_warn(self, detector):
        ev = _ev("reasoning_capture", "plan",
                 call_type="generate",
                 reasoning_text="Let me analyze the available evidence on PFAS treatment.")
        anomalies = detector.process_event(ev)
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "WARN"
        assert anomalies[0]["category"] == "cot_leakage"

    def test_three_cot_patterns_is_critical(self, detector):
        ev = _ev("reasoning_capture", "plan",
                 call_type="generate",
                 reasoning_text="Let me think. I need to analyze this. Step 1: review the data.")
        anomalies = detector.process_event(ev)
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "CRITICAL"
        assert anomalies[0]["data"]["match_count"] >= 3

    def test_heuristic_patterns_detected(self, detector):
        ev = _ev("reasoning_capture", "synthesize",
                 call_type="section_write",
                 reasoning_text="I must write this section carefully. I am instructed to stay grounded.")
        anomalies = detector.process_event(ev)
        assert len(anomalies) == 1
        assert anomalies[0]["data"]["match_count"] >= 2

    def test_empty_reasoning_triggers_stub_not_cot(self, detector):
        ev = _ev("reasoning_capture", "plan",
                 call_type="generate",
                 reasoning_text="")
        anomalies = detector.process_event(ev)
        # Should trigger empty_stub (short_reasoning), not cot_leakage
        categories = [a["category"] for a in anomalies]
        assert "empty_stub" in categories
        assert "cot_leakage" not in categories


# =============================================================================
# Category 2: Empty/Stub Content
# =============================================================================

class TestEmptyStub:
    """Category 2: Short reasoning, failed fetches, stub content."""

    def test_short_reasoning_is_critical(self, detector):
        ev = _ev("reasoning_capture", "plan",
                 call_type="generate",
                 reasoning_text="OK")
        anomalies = detector.process_event(ev)
        stub_anomalies = [a for a in anomalies if a["rule"] == "short_reasoning"]
        assert len(stub_anomalies) == 1
        assert stub_anomalies[0]["severity"] == "CRITICAL"

    def test_paywall_fetch_is_warn(self, detector):
        ev = _ev("fetch", "search",
                 url="https://example.com/article", status="paywall", content_len=50)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "fetch_failed" for a in anomalies)

    def test_http_4xx_fetch(self, detector):
        ev = _ev("fetch", "search",
                 url="https://example.com/404", status="404", content_len=0)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "fetch_http_error" for a in anomalies)

    def test_stub_content_detected(self, detector):
        ev = _ev("fetch", "search",
                 url="https://example.com/stub", status="ok", content_len=200)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "stub_content" for a in anomalies)

    def test_ok_fetch_no_anomaly(self, detector):
        ev = _ev("fetch", "search",
                 url="https://example.com/good", status="ok", content_len=5000)
        anomalies = detector.process_event(ev)
        assert len(anomalies) == 0


# =============================================================================
# Category 3: Evidence Quality
# =============================================================================

class TestEvidenceQuality:
    """Category 3: Low extraction, high off-topic, dedup removal."""

    def test_low_extraction_warn(self, detector):
        ev = _ev("evidence", "analyze", action="extracted", count=3)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "low_extraction" for a in anomalies)

    def test_normal_extraction_no_anomaly(self, detector):
        ev = _ev("evidence", "analyze", action="extracted", count=50)
        anomalies = detector.process_event(ev)
        assert len(anomalies) == 0

    def test_high_offtopic_ratio(self, detector):
        detector.process_event(_ev("evidence", "analyze", action="extracted", count=100))
        ev = _ev("evidence", "analyze", action="off_topic_filtered", count=60)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "high_offtopic" for a in anomalies)

    def test_normal_offtopic_ratio(self, detector):
        detector.process_event(_ev("evidence", "analyze", action="extracted", count=100))
        ev = _ev("evidence", "analyze", action="off_topic_filtered", count=10)
        anomalies = detector.process_event(ev)
        assert len(anomalies) == 0

    def test_high_dedup_ratio(self, detector):
        detector.process_event(_ev("evidence", "analyze", action="extracted", count=100))
        ev = _ev("evidence", "analyze", action="dedup_removed", count=50)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "high_dedup" for a in anomalies)

    def test_duplicate_fetch_url(self, detector):
        url = "https://example.com/same"
        detector.process_event(_ev("fetch", "search", url=url, status="ok", content_len=5000))
        ev2 = _ev("fetch", "search", url=url, status="ok", content_len=5000)
        anomalies = detector.process_event(ev2)
        assert any(a["rule"] == "duplicate_fetch_url" for a in anomalies)


# =============================================================================
# Category 4: Verification
# =============================================================================

class TestVerification:
    """Category 4: Batch timeouts, rubber-stamping, failures."""

    def test_rubber_stamp_suspect(self, detector):
        # Set up: quality gate shows 100% faithfulness
        detector.process_event(_ev("quality_gate", "evaluate",
                                    gate="faithfulness", passed=True, actual=1.0, threshold=0.70))
        # Feed 10 verification LLM calls
        for _ in range(10):
            detector.process_event(_ev("llm_call", "verify",
                                        call_type="verification_batch",
                                        input_tokens=1000, output_tokens=500, duration_ms=5000))
        # Trigger verify node end
        anomalies = detector.process_event(_ev("node_end", "verify", duration_ms=60000))
        rules = [a["rule"] for a in anomalies]
        assert "rubber_stamp_suspect" in rules

    def test_high_batch_failure_rate(self, detector):
        # Feed 10 batches, 5 with near-zero output (failures)
        for i in range(10):
            out_tok = 5 if i < 5 else 500  # 50% failure
            detector.process_event(_ev("llm_call", "verify",
                                        call_type="verification_batch",
                                        input_tokens=1000, output_tokens=out_tok, duration_ms=5000))
        anomalies = detector.process_event(_ev("node_end", "verify", duration_ms=60000))
        rules = [a["rule"] for a in anomalies]
        assert "high_batch_failure" in rules

    def test_slow_verification_batches(self, detector):
        for _ in range(3):
            detector.process_event(_ev("llm_call", "verify",
                                        call_type="verification_batch",
                                        input_tokens=1000, output_tokens=500,
                                        duration_ms=150000))  # 150s > 120s threshold
        anomalies = detector.process_event(_ev("node_end", "verify", duration_ms=500000))
        rules = [a["rule"] for a in anomalies]
        assert "batch_timeouts" in rules


# =============================================================================
# Category 5+7: Synthesis + Quality Gates
# =============================================================================

class TestSynthesisAndGates:
    """Categories 5 & 7: Word count, citations, gate failures."""

    def test_quality_gate_fail_is_anomaly(self, detector):
        ev = _ev("quality_gate", "evaluate",
                 gate="word_count", passed=False, actual=1500, threshold=2000)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "gate_fail" for a in anomalies)

    def test_faithfulness_gate_fail_is_critical(self, detector):
        ev = _ev("quality_gate", "evaluate",
                 gate="faithfulness", passed=False, actual=0.50, threshold=0.70)
        anomalies = detector.process_event(ev)
        critical = [a for a in anomalies if a["severity"] == "CRITICAL"]
        assert len(critical) >= 1

    def test_low_citations_warn(self, detector):
        ev = _ev("quality_gate", "synthesize",
                 gate="citation_count", passed=True, actual=15, threshold=10)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "low_citations" for a in anomalies)

    def test_low_word_count_warn(self, detector):
        ev = _ev("quality_gate", "synthesize",
                 gate="word_count", passed=True, actual=5000, threshold=2000)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "low_word_count" for a in anomalies)

    def test_quality_gate_pass_no_anomaly(self, detector):
        ev = _ev("quality_gate", "evaluate",
                 gate="word_count", passed=True, actual=12000, threshold=10000)
        anomalies = detector.process_event(ev)
        # Should NOT trigger low_word_count (12000 >= 8000)
        assert not any(a["rule"] == "low_word_count" for a in anomalies)


# =============================================================================
# Category 6: Cost
# =============================================================================

class TestCost:
    """Category 6: Budget overruns, token explosions."""

    def test_cost_warn_threshold(self, detector, monkeypatch):
        import scripts.live_monitor as lm
        monkeypatch.setattr(lm, "PG_MONITOR_COST_WARN", 1.0)
        monkeypatch.setattr(lm, "PG_MONITOR_COST_CRIT", 5.0)
        # Each call: (50K * 0.45/1e6) + (20K * 2.25/1e6) = 0.0675
        # 20 calls = $1.35 > $1.0 warn threshold
        for _ in range(20):
            detector.process_event(_ev("llm_call", "analyze",
                                        call_type="generate",
                                        input_tokens=50000, output_tokens=20000,
                                        duration_ms=5000))
        cost_anomalies = [a for a in detector.anomalies if a["category"] == "cost"]
        assert len(cost_anomalies) > 0
        assert any(a["rule"] == "cost_warn" for a in cost_anomalies)

    def test_token_explosion(self, detector):
        ev = _ev("llm_call", "synthesize",
                 call_type="section_write",
                 input_tokens=10000, output_tokens=60000, duration_ms=30000)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "token_explosion" for a in anomalies)

    def test_normal_call_no_cost_anomaly(self, detector):
        ev = _ev("llm_call", "plan",
                 call_type="generate",
                 input_tokens=1000, output_tokens=500, duration_ms=3000)
        anomalies = detector.process_event(ev)
        assert not any(a["category"] == "cost" for a in anomalies)


# =============================================================================
# Category 8: Timing
# =============================================================================

class TestTiming:
    """Category 8: Node duration anomalies."""

    def test_slow_node_warn(self, detector):
        # Plan expected ~90s, send 200s (>2x)
        detector.process_event(_ev("node_start", "plan"))
        ev = _ev("node_end", "plan", duration_ms=200000)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "node_slow" for a in anomalies)

    def test_very_slow_node_critical(self, detector):
        # Plan expected ~90s, send 300s (>3x)
        detector.process_event(_ev("node_start", "plan"))
        ev = _ev("node_end", "plan", duration_ms=300000)
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "node_very_slow" for a in anomalies)

    def test_normal_duration_no_anomaly(self, detector):
        detector.process_event(_ev("node_start", "plan"))
        ev = _ev("node_end", "plan", duration_ms=60000)  # 60s < 90s expected
        anomalies = detector.process_event(ev)
        assert not any(a["category"] == "timing" for a in anomalies)


# =============================================================================
# Category 9: Log Errors
# =============================================================================

class TestLogErrors:
    """Category 9: ERROR/CRITICAL lines from polaris_graph.log."""

    def test_error_line_detected(self, detector):
        anomalies = detector.process_log_line(
            "2026-02-26 00:00:00 ERROR verifier: batch 5 failed with timeout"
        )
        assert len(anomalies) >= 1
        assert any(a["category"] == "log_errors" for a in anomalies)

    def test_critical_line_detected(self, detector):
        anomalies = detector.process_log_line(
            "2026-02-26 00:00:00 CRITICAL graph: Hard stop triggered"
        )
        assert any(a["severity"] == "CRITICAL" for a in anomalies)

    def test_api_error_flood(self, detector):
        for i in range(12):
            detector.process_log_line(f"ERROR api_error {i}")
        assert detector.api_error_count >= 12
        flood = [a for a in detector.anomalies if a["rule"] == "api_error_flood"]
        assert len(flood) > 0

    def test_normal_log_line_no_anomaly(self, detector):
        anomalies = detector.process_log_line(
            "2026-02-26 00:00:00 INFO plan: Generated 25 queries"
        )
        assert len(anomalies) == 0


# =============================================================================
# Iteration checks
# =============================================================================

class TestIteration:
    """Iteration-related anomalies."""

    def test_high_iteration_warn(self, detector):
        ev = _ev("iteration_decision", "evaluate",
                 iteration=3, decision="continue")
        anomalies = detector.process_event(ev)
        assert any(a["rule"] == "high_iteration" for a in anomalies)

    def test_case_4_critical(self, detector):
        ev = _ev("iteration_decision", "evaluate",
                 iteration=2, decision="CASE_4")
        anomalies = detector.process_event(ev)
        assert any(a["severity"] == "CRITICAL" and a["rule"] == "gating_case"
                    for a in anomalies)


# =============================================================================
# AnomalyWriter
# =============================================================================

class TestAnomalyWriter:
    """Test JSONL + Markdown output."""

    def test_writes_jsonl(self, writer, tmp_path):
        anomaly = _make_anomaly("WARN", "test", "test_rule", "test message")
        writer.write(anomaly)
        jsonl_path = tmp_path / "anomaly.jsonl"
        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["severity"] == "WARN"
        assert parsed["message"] == "test message"

    def test_writes_markdown(self, writer, tmp_path):
        anomaly = _make_anomaly("CRITICAL", "cost", "cost_warn", "Cost exceeded $3")
        writer.write(anomaly)
        md_path = tmp_path / "anomaly.md"
        content = md_path.read_text()
        assert "[CRITICAL]" in content
        assert "Cost exceeded $3" in content

    def test_count_increments(self, writer):
        assert writer.count == 0
        writer.write(_make_anomaly("INFO", "test", "test", "msg"))
        assert writer.count == 1
        writer.write(_make_anomaly("WARN", "test", "test", "msg"))
        assert writer.count == 2


# =============================================================================
# State accumulation
# =============================================================================

class TestStateAccumulation:
    """Test that detector maintains correct cumulative state."""

    def test_cumulative_cost(self, detector):
        for _ in range(5):
            detector.process_event(_ev("llm_call", "plan",
                                        call_type="generate",
                                        input_tokens=1000, output_tokens=1000,
                                        duration_ms=1000))
        # 5 calls * (1000 * 0.45/1e6 + 1000 * 2.25/1e6) = 5 * 0.0027 = 0.0135
        assert detector.cumulative_cost > 0.01

    def test_event_counts(self, detector):
        detector.process_event(_ev("node_start", "plan"))
        detector.process_event(_ev("llm_call", "plan"))
        detector.process_event(_ev("llm_call", "plan"))
        detector.process_event(_ev("node_end", "plan", duration_ms=1000))
        assert detector.event_counts["node_start"] == 1
        assert detector.event_counts["llm_call"] == 2
        assert detector.event_counts["node_end"] == 1

    def test_node_durations_tracked(self, detector):
        detector.process_event(_ev("node_end", "plan", duration_ms=45000))
        assert detector.node_durations["plan"] == 45000
