"""Unit tests for the AC3 raw LLM I/O sink (I-obs-001 #1141)."""
from __future__ import annotations

import json

from src.polaris_graph.telemetry.llm_io_sink import LlmIoSink


def test_record_writes_file_with_schema(tmp_path):
    sink = LlmIoSink(tmp_path / "llm_io")
    req = {"model": "x", "messages": [{"role": "user", "content": "[sanitized]"}], "provider": {"order": ["A"]}}
    resp = {"choices": [{"message": {"content": "hi"}}], "usage": {"total_tokens": 5}}
    sink.record(call_id="abc123", call_type="section", role="generator",
                request=req, raw_response=resp, duration_ms=42.0, status="ok")

    f = tmp_path / "llm_io" / "abc123.json"
    assert f.exists()
    doc = json.loads(f.read_text(encoding="utf-8"))
    assert doc["call_id"] == "abc123"
    assert doc["call_type"] == "section"
    assert doc["role"] == "generator"
    assert doc["status"] == "ok"
    assert doc["duration_ms"] == 42.0
    assert doc["timestamp_utc"].endswith("Z")
    assert doc["request"]["provider"] == {"order": ["A"]}  # final-body provider chain preserved
    assert doc["raw_response"]["usage"]["total_tokens"] == 5


def test_lazy_mkdir(tmp_path):
    out = tmp_path / "deep" / "llm_io"
    assert not out.exists()
    sink = LlmIoSink(out)
    # constructing does not create the dir; first record does
    assert not out.exists()
    sink.record(call_id="c1", call_type="judge", role=None, request={}, raw_response={})
    assert (out / "c1.json").exists()


def test_default_status_ok(tmp_path):
    sink = LlmIoSink(tmp_path / "llm_io")
    sink.record(call_id="c2", call_type="mirror", role="mirror", request={}, raw_response={})
    assert json.loads((tmp_path / "llm_io" / "c2.json").read_text())["status"] == "ok"


def test_never_raises_and_does_not_mutate_args(tmp_path, monkeypatch):
    sink = LlmIoSink(tmp_path / "llm_io")
    req = {"model": "x"}
    resp = {"choices": []}

    # Force the write to fail; record must swallow it.
    import src.polaris_graph.telemetry.llm_io_sink as mod
    monkeypatch.setattr(mod.json, "dumps", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    sink.record(call_id="c3", call_type="section", role=None, request=req, raw_response=resp,
                status="empty_choices")  # must not raise

    assert req == {"model": "x"}  # unmutated
    assert resp == {"choices": []}


def test_status_variants_persist(tmp_path):
    sink = LlmIoSink(tmp_path / "llm_io")
    for i, st in enumerate(["empty_choices", "empty", "provider_error", "http_error", "no_endpoint"]):
        sink.record(call_id=f"s{i}", call_type="section", role=None, request={}, raw_response={}, status=st)
        assert json.loads((tmp_path / "llm_io" / f"s{i}.json").read_text())["status"] == st
