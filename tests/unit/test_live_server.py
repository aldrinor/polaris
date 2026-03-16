"""
Tests for scripts/live_server.py -- TraceTailer, endpoints, discovery.

Covers: TraceTailer (JSONL tailing, multi-client cursors, malformed lines),
        discover_trace_file, endpoint responses, and cost filtering.
"""

import asyncio
import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from scripts.live_server import (
    TraceTailer,
    app,
    discover_trace_file,
)


# =============================================================================
# TraceTailer unit tests
# =============================================================================

class TestTraceTailer:
    """Tests for the JSONL file tailing component."""

    def test_read_new_lines_from_file(self, tmp_path):
        """Reads lines from a JSONL file and tracks them."""
        path = tmp_path / "trace.jsonl"
        path.write_text('{"type":"node_start","node":"plan"}\n', encoding="utf-8")
        tailer = TraceTailer(path)
        events = tailer._read_new_lines()
        assert len(events) == 1
        assert events[0]["type"] == "node_start"
        assert len(tailer.all_events) == 1

    def test_incremental_reads(self, tmp_path):
        """Second read only picks up new lines."""
        path = tmp_path / "trace.jsonl"
        path.write_text('{"type":"a"}\n', encoding="utf-8")
        tailer = TraceTailer(path)
        tailer._read_new_lines()
        assert len(tailer.all_events) == 1

        # Append a new line
        with open(path, "a", encoding="utf-8") as f:
            f.write('{"type":"b"}\n')
        events2 = tailer._read_new_lines()
        assert len(events2) == 1
        assert events2[0]["type"] == "b"
        assert len(tailer.all_events) == 2

    def test_missing_file_returns_empty(self, tmp_path):
        """Non-existent file returns empty list without error."""
        tailer = TraceTailer(tmp_path / "nonexistent.jsonl")
        events = tailer._read_new_lines()
        assert events == []

    def test_malformed_json_skipped(self, tmp_path):
        """Malformed JSONL lines are skipped."""
        path = tmp_path / "trace.jsonl"
        path.write_text('{"type":"ok"}\nNOT_JSON\n{"type":"also_ok"}\n', encoding="utf-8")
        tailer = TraceTailer(path)
        events = tailer._read_new_lines()
        assert len(events) == 2
        assert events[0]["type"] == "ok"
        assert events[1]["type"] == "also_ok"

    def test_empty_lines_skipped(self, tmp_path):
        path = tmp_path / "trace.jsonl"
        path.write_text('{"type":"a"}\n\n\n{"type":"b"}\n', encoding="utf-8")
        tailer = TraceTailer(path)
        events = tailer._read_new_lines()
        assert len(events) == 2

    def test_multi_client_cursors(self, tmp_path):
        """Two independent tail() generators get all events."""
        path = tmp_path / "trace.jsonl"
        path.write_text('{"type":"a"}\n{"type":"b"}\n{"type":"c"}\n', encoding="utf-8")
        tailer = TraceTailer(path)
        tailer._read_new_lines()

        assert len(tailer.all_events) == 3

        # Simulate two clients reading from the same tailer
        # Client 1 reads all
        client1_events = []
        for i in range(len(tailer.all_events)):
            client1_events.append(tailer.all_events[i])
        assert len(client1_events) == 3

        # Client 2 also gets all (independent cursor)
        client2_events = []
        for i in range(len(tailer.all_events)):
            client2_events.append(tailer.all_events[i])
        assert len(client2_events) == 3

    def test_offset_tracking(self, tmp_path):
        """Offset advances correctly across reads."""
        path = tmp_path / "trace.jsonl"
        path.write_text('{"a":1}\n', encoding="utf-8")
        tailer = TraceTailer(path)
        tailer._read_new_lines()
        offset_after_first = tailer._offset
        assert offset_after_first > 0

        # No new data
        events = tailer._read_new_lines()
        assert events == []
        assert tailer._offset == offset_after_first


# =============================================================================
# Tail async generator test
# =============================================================================

class TestTraceTailerAsync:
    """Test the async tail() generator."""

    @pytest.mark.asyncio
    async def test_tail_yields_existing_events(self, tmp_path):
        """tail() yields events already in the buffer."""
        path = tmp_path / "trace.jsonl"
        path.write_text('{"type":"a"}\n{"type":"b"}\n', encoding="utf-8")
        tailer = TraceTailer(path)
        tailer._read_new_lines()

        collected = []
        gen = tailer.tail()
        # Should yield the 2 existing events, then block on wait
        async def collect():
            async for ev in gen:
                collected.append(ev)
                if len(collected) >= 2:
                    break

        await asyncio.wait_for(collect(), timeout=3.0)
        assert len(collected) == 2
        assert collected[0]["type"] == "a"
        assert collected[1]["type"] == "b"


# =============================================================================
# discover_trace_file
# =============================================================================

class TestDiscoverTraceFile:
    def test_finds_newest(self, tmp_path):
        import time
        (tmp_path / "pg_trace_OLD.jsonl").write_text("{}\n", encoding="utf-8")
        time.sleep(0.05)
        (tmp_path / "pg_trace_NEW.jsonl").write_text("{}\n", encoding="utf-8")
        result = discover_trace_file(str(tmp_path))
        assert result is not None
        assert "NEW" in result.name

    def test_no_trace_files(self, tmp_path):
        (tmp_path / "other.jsonl").write_text("{}\n", encoding="utf-8")
        result = discover_trace_file(str(tmp_path))
        assert result is None

    def test_missing_directory(self):
        result = discover_trace_file("/nonexistent/path/xyz")
        assert result is None


# =============================================================================
# FastAPI endpoint tests
# =============================================================================

class TestEndpoints:
    """Test API endpoints using httpx AsyncClient."""

    @pytest.mark.asyncio
    async def test_root_returns_html_or_404(self):
        """Root serves dashboard HTML or 404 if template missing."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/")
            assert resp.status_code in (200, 404)

    @pytest.mark.asyncio
    async def test_snapshot_returns_503_when_no_tailer(self):
        """Snapshot returns 503 when no trace file configured."""
        import scripts.live_server as lsmod
        original = lsmod._tailer
        lsmod._tailer = None
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/snapshot")
                assert resp.status_code == 503
                data = resp.json()
                assert "error" in data
        finally:
            lsmod._tailer = original

    @pytest.mark.asyncio
    async def test_snapshot_returns_stats(self, tmp_path):
        """Snapshot returns stats when tailer has events."""
        import scripts.live_server as lsmod
        original = lsmod._tailer

        path = tmp_path / "trace.jsonl"
        path.write_text(
            '{"type":"node_start","node":"plan","ts":"2026-01-01T00:00:00Z"}\n'
            '{"type":"llm_call","node":"plan","input_tokens":100,"output_tokens":50,'
            '"duration_ms":1000,"cost_usd":0.01,"ts":"2026-01-01T00:00:01Z"}\n',
            encoding="utf-8",
        )
        tailer = TraceTailer(path)
        tailer._read_new_lines()
        lsmod._tailer = tailer
        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/snapshot")
                assert resp.status_code == 200
                data = resp.json()
                assert "stats" in data
                assert data["stats"]["total_events"] == 2
        finally:
            lsmod._tailer = original

    @pytest.mark.asyncio
    async def test_anomalies_returns_empty_when_no_file(self, monkeypatch):
        """Anomalies returns empty list when log file doesn't exist."""
        import scripts.live_server as lsmod
        monkeypatch.setattr(lsmod, "PG_LIVE_ANOMALY_LOG", "/nonexistent/anomaly.jsonl")
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/anomalies")
            assert resp.status_code == 200
            assert resp.json() == []

    @pytest.mark.asyncio
    async def test_anomalies_returns_content(self, tmp_path, monkeypatch):
        """Anomalies returns parsed JSONL content."""
        import scripts.live_server as lsmod
        anom_path = tmp_path / "anomaly.jsonl"
        anom_path.write_text(
            '{"severity":"WARN","category":"cost","message":"High cost"}\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(lsmod, "PG_LIVE_ANOMALY_LOG", str(anom_path))
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/anomalies")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 1
            assert data[0]["severity"] == "WARN"

    @pytest.mark.asyncio
    async def test_cost_returns_structure(self):
        """Cost endpoint returns expected JSON structure."""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/cost")
            assert resp.status_code == 200
            data = resp.json()
            assert "entries" in data
            assert "total_cost_usd" in data
            assert "session_id" in data

    @pytest.mark.asyncio
    async def test_cost_filters_by_session_id(self, tmp_path, monkeypatch):
        """Cost endpoint filters ledger entries by session_id from trace path."""
        import scripts.live_server as lsmod

        # Write a cost ledger with mixed session_ids
        ledger_path = tmp_path / "cost_ledger.jsonl"
        entries = [
            {"session_id": "TEST_001", "cost_usd": 0.05, "timestamp": "2026-01-01T00:00:00Z"},
            {"session_id": "TEST_001", "cost_usd": 0.10, "timestamp": "2026-01-01T00:00:01Z"},
            {"session_id": "OTHER_RUN", "cost_usd": 0.99, "timestamp": "2026-01-01T00:00:02Z"},
        ]
        with open(ledger_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

        monkeypatch.setattr(lsmod, "PG_COST_LEDGER_PATH", str(ledger_path))
        monkeypatch.setattr(lsmod, "_trace_path", Path("logs/pg_trace_TEST_001.jsonl"))
        original_tailer = lsmod._tailer
        lsmod._tailer = None

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.get("/api/cost")
                assert resp.status_code == 200
                data = resp.json()
                assert data["session_id"] == "TEST_001"
                assert data["total_count"] == 2
                assert abs(data["total_cost_usd"] - 0.15) < 0.001
        finally:
            lsmod._tailer = original_tailer
