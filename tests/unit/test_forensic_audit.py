"""
Tests for scripts/forensic_audit.py -- section builders, helpers, and full audit.

Covers: _load_jsonl, _filter_cost_ledger, _jaccard_words, _fmt_ts, _fmt_dur,
        _extract_domain, _group_events, section builders, and run_forensic_audit.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts.forensic_audit import (
    _extract_domain,
    _filter_cost_ledger,
    _fmt_dur,
    _fmt_ts,
    _group_events,
    _jaccard_words,
    _load_json,
    _load_jsonl,
    _load_text,
    _section_1_timeline,
    _section_2_planning,
    _section_3_search_fetch,
    _section_4_storm,
    _section_5_evidence,
    _section_6_verification,
    _section_7_report_text,
    _section_8_quality_gates,
    _section_9_llm_calls,
    _section_10_anomaly_digest,
    _section_11_benchmark,
    run_forensic_audit,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def trace_events():
    """Minimal trace events representing a short pipeline run."""
    base_ts = "2026-02-26T10:00:00+00:00"
    return [
        {"type": "node_start", "node": "plan", "ts": "2026-02-26T10:00:00+00:00"},
        {"type": "llm_call", "node": "plan", "call_type": "generate",
         "input_tokens": 5000, "output_tokens": 2000, "duration_ms": 3000,
         "ts": "2026-02-26T10:00:03+00:00"},
        {"type": "reasoning_capture", "node": "plan", "call_type": "generate",
         "reasoning_text": "This is a planning query analysis.",
         "ts": "2026-02-26T10:00:03+00:00"},
        {"type": "node_end", "node": "plan", "duration_ms": 5000,
         "ts": "2026-02-26T10:00:05+00:00"},
        {"type": "node_start", "node": "search", "ts": "2026-02-26T10:00:06+00:00"},
        {"type": "search_result", "node": "search", "engine": "serper",
         "query": "water filtration", "result_count": 10,
         "ts": "2026-02-26T10:00:08+00:00"},
        {"type": "fetch", "node": "search", "url": "https://example.com/water",
         "status": "ok", "content_len": 5000, "duration_ms": 1000,
         "ts": "2026-02-26T10:00:09+00:00"},
        {"type": "node_end", "node": "search", "duration_ms": 15000,
         "ts": "2026-02-26T10:00:21+00:00"},
        {"type": "node_start", "node": "verify", "ts": "2026-02-26T10:00:22+00:00"},
        {"type": "llm_call", "node": "verify", "call_type": "verification_batch",
         "input_tokens": 8000, "output_tokens": 3000, "duration_ms": 5000,
         "ts": "2026-02-26T10:00:27+00:00"},
        {"type": "node_end", "node": "verify", "duration_ms": 6000,
         "ts": "2026-02-26T10:00:28+00:00"},
        {"type": "quality_gate", "node": "evaluate", "gate": "faithfulness",
         "passed": True, "actual": 0.85, "threshold": 0.70,
         "ts": "2026-02-26T10:00:29+00:00"},
        {"type": "quality_gate", "node": "evaluate", "gate": "word_count",
         "passed": True, "actual": 10000, "threshold": 2000,
         "ts": "2026-02-26T10:00:30+00:00"},
    ]


@pytest.fixture
def trace_jsonl_file(tmp_path, trace_events):
    """Write trace events to a temp JSONL file."""
    path = tmp_path / "pg_trace_TEST_001.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for ev in trace_events:
            f.write(json.dumps(ev) + "\n")
    return path


@pytest.fixture
def result_json(tmp_path):
    """Minimal result JSON with evidence, claims, quality_metrics."""
    data = {
        "vector_id": "TEST_001",
        "evidence": [
            {"evidence_id": "ev_001", "quality_tier": "GOLD", "relevance_score": 0.95,
             "source_url": "https://example.com/water", "direct_quote": "Water is treated."},
            {"evidence_id": "ev_002", "quality_tier": "SILVER", "relevance_score": 0.70,
             "source_url": "https://academic.org/study", "direct_quote": "PFAS removal rates."},
        ],
        "claims": [
            {"claim_id": "c_001", "statement": "Water filtration removes contaminants.",
             "is_faithful": True, "verdict": "SUPPORTED", "nli_score": 0.92,
             "verification_method": "nli", "evidence_ids": ["ev_001"]},
            {"claim_id": "c_002", "statement": "PFAS can be filtered.",
             "is_faithful": False, "verdict": "NOT_SUPPORTED", "nli_score": 0.40,
             "verification_method": "llm", "evidence_ids": ["ev_002"]},
        ],
        "quality_metrics": {
            "total_words": 10000,
            "total_citations": 150,
            "unique_sources": 25,
            "total_evidence": 200,
            "faithfulness_score": 0.85,
        },
        "bibliography": [
            {"reference_number": 1, "url": "https://example.com/water", "title": "Water Study"},
            {"reference_number": 2, "url": "https://academic.org/study", "title": "PFAS Paper"},
        ],
    }
    path = tmp_path / "TEST_001.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path, data


@pytest.fixture
def report_text_file(tmp_path):
    """Minimal report markdown."""
    text = (
        "# Water Filtration Report\n\n"
        "Water filtration [1] is essential for removing contaminants [2]. "
        "PFAS levels [1] have been a concern [3] in municipal water systems. "
        "Multiple studies [2][3] confirm the effectiveness of activated carbon [1].\n"
    )
    path = tmp_path / "TEST_001_report.md"
    path.write_text(text, encoding="utf-8")
    return path, text


# =============================================================================
# Utility functions
# =============================================================================

class TestFmtTs:
    def test_valid_iso(self):
        assert _fmt_ts("2026-02-26T10:05:30+00:00") == "10:05:30"

    def test_empty(self):
        assert _fmt_ts("") == "--"

    def test_invalid(self):
        result = _fmt_ts("not-a-date-12345678901")
        assert isinstance(result, str)


class TestFmtDur:
    def test_milliseconds(self):
        assert _fmt_dur(500) == "500ms"

    def test_seconds(self):
        assert _fmt_dur(5000) == "5.0s"

    def test_minutes(self):
        assert _fmt_dur(120000) == "2.0min"

    def test_zero(self):
        assert _fmt_dur(0) == "--"

    def test_none(self):
        assert _fmt_dur(None) == "--"


class TestExtractDomain:
    def test_normal_url(self):
        assert _extract_domain("https://www.example.com/path") == "www.example.com"

    def test_empty(self):
        assert _extract_domain("") == ""


class TestJaccardWords:
    def test_identical(self):
        assert _jaccard_words("hello world", "hello world") == 1.0

    def test_disjoint(self):
        assert _jaccard_words("hello world", "foo bar") == 0.0

    def test_partial(self):
        result = _jaccard_words("hello world foo", "hello bar baz")
        assert 0.0 < result < 1.0

    def test_empty(self):
        assert _jaccard_words("", "hello") == 0.0

    def test_both_empty(self):
        assert _jaccard_words("", "") == 0.0


# =============================================================================
# File loading
# =============================================================================

class TestLoadJsonl:
    def test_valid_file(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
        items = _load_jsonl(path)
        assert len(items) == 2
        assert items[0] == {"a": 1}

    def test_missing_file(self, tmp_path):
        path = tmp_path / "missing.jsonl"
        items = _load_jsonl(path)
        assert items == []

    def test_malformed_lines(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a":1}\nNOT JSON\n{"b":2}\n', encoding="utf-8")
        items = _load_jsonl(path)
        assert len(items) == 2

    def test_empty_lines_skipped(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a":1}\n\n\n{"b":2}\n', encoding="utf-8")
        items = _load_jsonl(path)
        assert len(items) == 2


class TestLoadJson:
    def test_valid(self, tmp_path):
        path = tmp_path / "test.json"
        path.write_text('{"key":"value"}', encoding="utf-8")
        data = _load_json(path)
        assert data == {"key": "value"}

    def test_missing(self, tmp_path):
        data = _load_json(tmp_path / "missing.json")
        assert data is None


class TestLoadText:
    def test_valid(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("hello world", encoding="utf-8")
        assert _load_text(path) == "hello world"

    def test_missing(self, tmp_path):
        assert _load_text(tmp_path / "missing.txt") is None


# =============================================================================
# _group_events
# =============================================================================

class TestGroupEvents:
    def test_groups_by_type(self, trace_events):
        grouped = _group_events(trace_events)
        assert "node_start" in grouped
        assert "llm_call" in grouped
        assert "quality_gate" in grouped
        assert len(grouped["node_start"]) == 3  # plan, search, verify
        assert len(grouped["quality_gate"]) == 2

    def test_empty(self):
        assert _group_events([]) == {}

    def test_missing_type(self):
        grouped = _group_events([{"data": 1}])
        assert "unknown" in grouped


# =============================================================================
# _filter_cost_ledger
# =============================================================================

class TestFilterCostLedger:
    def test_filters_by_time_window(self, trace_events):
        """Cost entries within trace window should be kept."""
        entries = [
            {"timestamp": "2026-02-26T10:00:02+00:00", "cost_usd": 0.01},
            {"timestamp": "2026-02-26T10:00:15+00:00", "cost_usd": 0.05},
            {"timestamp": "2026-02-26T09:00:00+00:00", "cost_usd": 0.99},  # before
            {"timestamp": "2026-02-26T12:00:00+00:00", "cost_usd": 0.88},  # after
        ]
        filtered = _filter_cost_ledger(entries, trace_events)
        assert len(filtered) == 2
        costs = [e["cost_usd"] for e in filtered]
        assert 0.01 in costs
        assert 0.05 in costs

    def test_empty_trace(self):
        entries = [{"timestamp": "2026-02-26T10:00:00+00:00", "cost_usd": 0.01}]
        result = _filter_cost_ledger(entries, [])
        assert result == entries  # falls back to returning all

    def test_empty_entries(self, trace_events):
        result = _filter_cost_ledger([], trace_events)
        assert result == []

    def test_no_timestamps_in_trace(self):
        entries = [{"timestamp": "2026-02-26T10:00:00+00:00", "cost_usd": 0.01}]
        trace = [{"type": "node_start", "node": "plan"}]  # no ts field
        result = _filter_cost_ledger(entries, trace)
        assert result == entries  # falls back to all


# =============================================================================
# Section builders (smoke tests: non-empty output + key content)
# =============================================================================

class TestSection1Timeline:
    def test_produces_table(self, trace_events):
        grouped = _group_events(trace_events)
        out = _section_1_timeline(trace_events, grouped)
        assert "## 1. Pipeline Timeline" in out
        assert "plan" in out
        assert "search" in out
        assert "Critical path" in out

    def test_empty_events(self):
        out = _section_1_timeline([], {})
        assert "## 1. Pipeline Timeline" in out


class TestSection2Planning:
    def test_with_reasoning(self, trace_events):
        grouped = _group_events(trace_events)
        out = _section_2_planning(grouped)
        assert "## 2. Planning Deep-Dive" in out
        assert "planning query analysis" in out

    def test_no_planning(self):
        out = _section_2_planning({})
        assert "## 2." in out


class TestSection3SearchFetch:
    def test_with_search_and_fetch(self, trace_events):
        grouped = _group_events(trace_events)
        out = _section_3_search_fetch(grouped)
        assert "## 3." in out
        assert "serper" in out
        assert "example.com" in out

    def test_no_searches(self):
        out = _section_3_search_fetch({})
        assert "## 3." in out


class TestSection4Storm:
    def test_with_transcripts(self):
        grouped = {
            "storm_transcript": [
                {"persona": "Chemistry Expert", "round": 1,
                 "question": "What about PFAS?", "answer": "PFAS requires special...",
                 "sources": ["s1"], "key_findings": ["f1"]},
            ]
        }
        out = _section_4_storm(grouped)
        assert "Chemistry Expert" in out
        assert "PFAS" in out

    def test_no_storm(self):
        out = _section_4_storm({})
        assert "## 4." in out


class TestSection5Evidence:
    def test_with_result(self, result_json):
        _, data = result_json
        out = _section_5_evidence(data, {})
        assert "## 5." in out
        assert "ev_001" in out
        assert "Source Concentration" in out
        assert "Relevance" in out

    def test_no_result(self):
        out = _section_5_evidence(None, {})
        assert "## 5." in out


class TestSection6Verification:
    def test_with_claims(self, result_json, trace_events):
        _, data = result_json
        grouped = _group_events(trace_events)
        out = _section_6_verification(data, grouped)
        assert "## 6." in out
        assert "c_001" in out
        assert "FAITH" in out

    def test_no_result(self):
        out = _section_6_verification(None, {})
        assert "## 6." in out


class TestSection7ReportText:
    def test_with_report(self, report_text_file, result_json, trace_events):
        _, text = report_text_file
        _, data = result_json
        grouped = _group_events(trace_events)
        out = _section_7_report_text(text, data, grouped)
        assert "## 7." in out
        assert "Total words" in out
        assert "Citation Frequency" in out

    def test_no_report(self):
        out = _section_7_report_text(None, None, {})
        assert "No report text" in out or "not available" in out.lower()


class TestSection8QualityGates:
    def test_with_gates(self, trace_events):
        grouped = _group_events(trace_events)
        out = _section_8_quality_gates(grouped)
        assert "## 8." in out
        assert "faithfulness" in out
        assert "PASS" in out

    def test_no_gates(self):
        out = _section_8_quality_gates({})
        assert "## 8." in out


class TestSection9LlmCalls:
    def test_with_calls(self, trace_events):
        grouped = _group_events(trace_events)
        out = _section_9_llm_calls(grouped, [])
        assert "## 9." in out
        assert "generate" in out or "verification_batch" in out

    def test_with_ledger(self, trace_events):
        grouped = _group_events(trace_events)
        ledger = [{"cost_usd": 0.01}, {"cost_usd": 0.05}]
        out = _section_9_llm_calls(grouped, ledger)
        assert "## 9." in out


class TestSection10AnomalyDigest:
    def test_with_anomalies(self):
        anomalies = [
            {"severity": "WARN", "category": "cost", "rule": "cost_warn",
             "message": "Cost exceeded"},
            {"severity": "CRITICAL", "category": "cot_leakage", "rule": "cot",
             "message": "CoT detected"},
        ]
        out = _section_10_anomaly_digest(anomalies)
        assert "## 10." in out
        assert "WARN" in out
        assert "CRITICAL" in out

    def test_no_anomalies(self):
        out = _section_10_anomaly_digest([])
        assert "## 10." in out
        assert "No anomalies" in out or "0" in out


class TestSection11Benchmark:
    def test_produces_table(self, result_json):
        _, data = result_json
        out = _section_11_benchmark(data, total_cost=1.50, total_time_min=45.0)
        assert "## 11." in out
        assert "POLARIS" in out

    def test_no_result(self):
        out = _section_11_benchmark(None, 0.0, 0.0)
        assert "## 11." in out


# =============================================================================
# Full run_forensic_audit
# =============================================================================

class TestRunForensicAudit:
    def test_full_run_with_fixtures(
        self, tmp_path, trace_jsonl_file, result_json, report_text_file,
    ):
        result_path, _ = result_json
        report_path, _ = report_text_file
        md, summary = run_forensic_audit(
            vector_id="TEST_001",
            trace_path=trace_jsonl_file,
            result_path=result_path,
            report_path=report_path,
        )
        # Markdown has all 11 sections
        for i in range(1, 12):
            assert f"## {i}." in md, f"Section {i} missing from report"

        # JSON summary has expected keys
        assert summary["vector_id"] == "TEST_001"
        assert summary["total_trace_events"] > 0
        assert "quality_metrics" in summary
        assert summary["quality_metrics"]["total_words"] == 10000

    def test_missing_all_files(self, tmp_path):
        """Should still produce a report (with 'not available' sections)."""
        md, summary = run_forensic_audit(
            vector_id="MISSING_001",
            trace_path=tmp_path / "missing_trace.jsonl",
            result_path=tmp_path / "missing_result.json",
            report_path=tmp_path / "missing_report.md",
        )
        assert "MISSING_001" in md
        assert summary["total_trace_events"] == 0

    def test_trace_only(self, trace_jsonl_file, tmp_path):
        """Only trace file exists, others missing."""
        md, summary = run_forensic_audit(
            vector_id="TRACE_ONLY",
            trace_path=trace_jsonl_file,
            result_path=tmp_path / "missing.json",
            report_path=tmp_path / "missing.md",
        )
        assert summary["total_trace_events"] > 0
        assert "## 1." in md
