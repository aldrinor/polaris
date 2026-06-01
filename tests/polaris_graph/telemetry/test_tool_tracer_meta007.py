"""Spend-free offline smoke for the I-meta-007b per-tool utilization tracer.

Covers (per the verified spec ``.codex/I-meta-007/_wiring_specs.txt`` LANE
``wire:tool-tracker``):

* record mixed outcomes (serper ok + fail, fetch_content ok + stub),
* ``tool_trace.jsonl`` is written when ``run_dir`` is set (and NOT when unset),
* ``manifest()`` reports correct ``success_rate`` + ``latency_stats`` +
  ``error_reasons``,
* a tracer-internal error never propagates (fail-safe),
* ``reset_tool_tracer()`` isolates runs (no cross-run accumulation, run_dir
  rebinds).

NO network, NO LLM, NO unittest.mock. Pure in-memory + tmp-dir disk writes.
"""
from __future__ import annotations

import json
import threading

import pytest

from src.polaris_graph.telemetry.tool_tracer import (
    ToolCall,
    ToolTracer,
    attach_tool_utilization,
    get_tool_tracer,
    reset_tool_tracer,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Each test starts and ends with a fresh process-global tracer."""
    reset_tool_tracer()
    yield
    reset_tool_tracer()


def _read_jsonl(path):
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


# ── core: mixed outcomes + jsonl + manifest ──────────────────────────────────
def test_records_mixed_outcomes_and_writes_jsonl(tmp_path):
    tracer = ToolTracer(run_dir=tmp_path)

    # serper: 1 ok + 1 fail; fetch_content: 1 ok + 1 stub.
    tracer.record(
        "serper", target="q one", status="ok", latency_ms=120.0,
        bytes_sent=40, bytes_received=2500, backend_used="serper_api_v1",
        result_count=10,
    )
    tracer.record(
        "serper", target="q two", status="fail", latency_ms=5000.0,
        bytes_sent=40, backend_used="serper_api_v1", error="HTTP 502",
    )
    tracer.record(
        "fetch_content", target="https://example.org/a", status="ok",
        latency_ms=300.0, bytes_received=8000, backend_used="jina",
    )
    tracer.record(
        "fetch_content", target="https://example.org/b", status="stub",
        latency_ms=90.0, backend_used="crawl4ai", error="no_content",
    )

    # in-memory buffer
    calls = tracer.get_calls()
    assert len(calls) == 4
    assert all(isinstance(c, ToolCall) for c in calls)

    # jsonl written: exactly 4 valid JSON lines, fields preserved
    trace_path = tmp_path / "tool_trace.jsonl"
    assert trace_path.exists()
    rows = _read_jsonl(trace_path)
    assert len(rows) == 4
    assert {r["tool_name"] for r in rows} == {"serper", "fetch_content"}
    statuses = sorted(r["status"] for r in rows)
    assert statuses == ["fail", "ok", "ok", "stub"]
    # every row carries a UTC timestamp + the required telemetry fields
    for r in rows:
        assert r["timestamp"]
        assert "latency_ms" in r and "backend_used" in r


def test_manifest_success_rate_latency_and_error_reasons(tmp_path):
    tracer = ToolTracer(run_dir=tmp_path)

    # serper: 4 ok + 1 fail  → success_rate 0.8
    for i in range(4):
        tracer.record(
            "serper", target=f"q{i}", status="ok",
            latency_ms=float(100 + i * 100),  # 100, 200, 300, 400
            backend_used="serper_api_v1",
        )
    tracer.record(
        "serper", target="q-bad", status="fail", latency_ms=500.0,
        backend_used="serper_api_v1", error="HTTP 404: not found",
    )
    # a second fail with the SAME error prefix → histogram counts 2
    tracer.record(
        "serper", target="q-bad2", status="fail", latency_ms=600.0,
        backend_used="serper_api_v1", error="HTTP 404: gone",
    )

    man = tracer.manifest()
    assert man["total_calls"] == 6
    assert man["total_ok"] == 4
    assert man["total_fail"] == 2

    serper = man["summary_by_tool"]["serper"]
    assert serper["total_calls"] == 6
    assert serper["ok_count"] == 4
    assert serper["fail_count"] == 2
    assert serper["success_rate"] == pytest.approx(4 / 6)

    ls = serper["latency_stats"]
    assert ls["min_ms"] == 100.0
    assert ls["max_ms"] == 600.0
    # mean of [100,200,300,400,500,600] = 350
    assert ls["mean_ms"] == pytest.approx(350.0)
    # p95 nearest-rank over 6 sorted values → index int(0.95*6)=5 → 600
    assert ls["p95_ms"] == 600.0

    # error histogram aggregates by the leading token (before ':'), capped
    assert serper["error_reasons"] == {"HTTP 404": 2}

    assert serper["backends_used"] == ["serper_api_v1"]


def test_no_run_dir_means_no_jsonl_but_manifest_still_works(tmp_path):
    # run_dir=None → in-memory only; NO file side effect (OFF-mode byte-identity)
    tracer = ToolTracer(run_dir=None)
    tracer.record("serper", target="q", status="ok", latency_ms=10.0)
    assert not (tmp_path / "tool_trace.jsonl").exists()
    man = tracer.manifest()
    assert man["total_calls"] == 1
    assert man["total_ok"] == 1


def test_empty_manifest_is_well_formed():
    tracer = ToolTracer(run_dir=None)
    man = tracer.manifest()
    assert man["total_calls"] == 0
    assert man["total_ok"] == 0
    assert man["total_fail"] == 0
    assert man["summary_by_tool"] == {}
    assert man["timestamp_range"] == {"start": "", "end": ""}


# ── fail-safe: a tracer-internal error must never propagate ───────────────────
class _Unserializable:
    """A metadata value that json.dumps cannot encode → forces an internal
    failure inside ``_append_to_log`` (asdict + json.dumps)."""


def test_record_is_failsafe_on_bad_metadata(tmp_path):
    tracer = ToolTracer(run_dir=tmp_path)
    # This must NOT raise even though the metadata value is not JSON-serializable.
    tracer.record(
        "serper", target="q", status="ok", latency_ms=10.0,
        bad=_Unserializable(),
    )
    # The call is still buffered in memory (record() caught only the log write).
    # Either way, the key contract is: no exception propagated.
    man = tracer.manifest()
    assert man["total_calls"] >= 0  # reachable == no propagation


def test_record_is_failsafe_when_log_path_unwritable(tmp_path):
    # Point the tracer at a path whose parent is a FILE, so mkdir/open fails.
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file, not a dir", encoding="utf-8")
    tracer = ToolTracer(run_dir=blocker)  # tool_trace.jsonl under a file path
    # Must not raise; the disk error is swallowed + logged.
    tracer.record("serper", target="q", status="ok", latency_ms=10.0)
    man = tracer.manifest()
    assert man["total_calls"] == 1


# ── reset isolates runs (no cross-query accumulation; run_dir rebinds) ────────
def test_reset_isolates_runs(tmp_path):
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"

    t_a = get_tool_tracer(run_a)
    t_a.record("serper", target="qa", status="ok", latency_ms=10.0)
    assert get_tool_tracer().manifest()["total_calls"] == 1

    # Without reset, get_tool_tracer(run_b) would return run_a's tracer.
    reset_tool_tracer()
    t_b = get_tool_tracer(run_b)
    assert t_b is not t_a
    # Fresh tracer: zero accumulated calls from run A.
    assert t_b.manifest()["total_calls"] == 0
    t_b.record("s2", target="qb", status="ok", latency_ms=20.0)

    # Each run's jsonl contains only its own call.
    rows_a = _read_jsonl(run_a / "tool_trace.jsonl")
    rows_b = _read_jsonl(run_b / "tool_trace.jsonl")
    assert len(rows_a) == 1 and rows_a[0]["tool_name"] == "serper"
    assert len(rows_b) == 1 and rows_b[0]["tool_name"] == "s2"


def test_singleton_ignores_run_dir_until_reset(tmp_path):
    # get_tool_tracer honors run_dir only on first creation (documented contract).
    first = get_tool_tracer(tmp_path / "first")
    second = get_tool_tracer(tmp_path / "second")
    assert first is second
    assert first.run_dir == (tmp_path / "first")


# ── thread safety: concurrent record() loses no rows ──────────────────────────
def test_thread_safe_record(tmp_path):
    tracer = ToolTracer(run_dir=tmp_path)

    def _worker():
        for _ in range(10):
            tracer.record("fetch_content", target="u", status="ok", latency_ms=1.0)

    threads = [threading.Thread(target=_worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(tracer.get_calls()) == 30
    rows = _read_jsonl(tmp_path / "tool_trace.jsonl")
    assert len(rows) == 30


# ── I-meta-007b P1: attach_tool_utilization (every-manifest-write hook) ────────
def test_attach_tool_utilization_on_writes_summary_and_sets_key(tmp_path, monkeypatch):
    """ON-mode: writes run_dir/tool_summary.json AND sets the rich
    manifest['tool_utilization'] key (the exact shape the success path emits)."""
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")
    tracer = get_tool_tracer(tmp_path)
    tracer.record("serper", target="q", status="ok", latency_ms=120.0,
                  backend_used="serper_api_v1")
    tracer.record("fetch_content", target="u", status="fail", latency_ms=50.0,
                  backend_used="httpx_naive", error="boom")

    manifest = {"status": "abort_no_verified_sections", "existing": "untouched"}
    out = attach_tool_utilization(manifest, tmp_path)

    # mutates + returns the same dict; existing keys untouched
    assert out is manifest
    assert manifest["existing"] == "untouched"

    # file written
    summary_path = tmp_path / "tool_summary.json"
    assert summary_path.exists()
    on_disk = json.loads(summary_path.read_text(encoding="utf-8"))
    assert on_disk["total_calls"] == 2

    # rich key shape (matches the pre-existing success-path block exactly)
    tu = manifest["tool_utilization"]
    assert set(tu.keys()) == {
        "trace_file", "summary_file", "total_tool_calls", "total_ok",
        "total_fail", "tool_success_rate", "summary_by_tool",
    }
    assert tu["trace_file"] == "tool_trace.jsonl"
    assert tu["summary_file"] == "tool_summary.json"
    assert tu["total_tool_calls"] == 2
    assert tu["total_ok"] == 1
    assert tu["total_fail"] == 1
    assert tu["tool_success_rate"] == pytest.approx(0.5)
    assert set(tu["summary_by_tool"].keys()) == {"serper", "fetch_content"}


def test_attach_tool_utilization_off_is_pure_noop(tmp_path, monkeypatch):
    """OFF-mode: NO file written, NO key added, manifest byte-identical."""
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    tracer = get_tool_tracer(tmp_path)
    tracer.record("serper", target="q", status="ok", latency_ms=10.0)

    manifest = {"status": "success", "a": 1}
    before = json.dumps(manifest, sort_keys=True)
    out = attach_tool_utilization(manifest, tmp_path)

    assert out is manifest
    assert "tool_utilization" not in manifest
    assert json.dumps(manifest, sort_keys=True) == before  # unchanged
    assert not (tmp_path / "tool_summary.json").exists()  # no file side effect


# ── I-meta-007b P2a: fallback-success records the fallback outcome (ok) ────────
def test_fallback_naive_fetch_records_success_outcome(tmp_path, monkeypatch):
    """A SUCCESSFUL naive-httpx fallback must be recorded 'ok' (not the
    pre-fallback 'fail'/'timeout'), with backend httpx_naive + real bytes."""
    import time as _time

    from src.polaris_graph.retrieval import live_retriever

    # Bind the process-global tracer to a run_dir so we can inspect records.
    reset_tool_tracer()
    get_tool_tracer(tmp_path)
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")

    # Offline synthetic success tuple from the naive fetcher (no network).
    fake = ("hello world content", True, "Title", "article", "")
    monkeypatch.setattr(
        live_retriever, "_fetch_content_httpx_naive",
        lambda url, max_chars: fake,
    )

    t0 = _time.time()
    result = live_retriever._fallback_naive_fetch(
        "https://example.org/x", 5000, t0, "access_bypass_timeout_90s",
    )
    # return value is the naive fetcher's tuple, unchanged
    assert result == fake

    calls = get_tool_tracer().get_calls()
    fetch_calls = [c for c in calls if c.tool_name == "fetch_content"]
    assert len(fetch_calls) == 1
    rec = fetch_calls[0]
    assert rec.status == "ok"  # the FINAL outcome, not the pre-fallback fail
    assert rec.backend_used == "httpx_naive"
    assert rec.bytes_received == len("hello world content")
    # primary reason carried in metadata for diagnostics; error empty on success
    assert rec.error == ""
    assert rec.metadata.get("primary_reason") == "access_bypass_timeout_90s"


def test_fallback_naive_fetch_records_failure_outcome(tmp_path, monkeypatch):
    """A FAILED naive-httpx fallback is recorded 'fail' with the primary reason."""
    import time as _time

    from src.polaris_graph.retrieval import live_retriever

    reset_tool_tracer()
    get_tool_tracer(tmp_path)
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")

    fail_tuple = ("", False, "", "", "")
    monkeypatch.setattr(
        live_retriever, "_fetch_content_httpx_naive",
        lambda url, max_chars: fail_tuple,
    )

    result = live_retriever._fallback_naive_fetch(
        "https://example.org/y", 5000, _time.time(), "access_bypass_no_result",
    )
    assert result == fail_tuple

    fetch_calls = [
        c for c in get_tool_tracer().get_calls() if c.tool_name == "fetch_content"
    ]
    assert len(fetch_calls) == 1
    assert fetch_calls[0].status == "fail"
    assert fetch_calls[0].backend_used == "httpx_naive"
    assert fetch_calls[0].error == "access_bypass_no_result"


# ── I-meta-007b P2b: _trace_tool is gated on PG_ENABLE_TOOL_TRACKER ───────────
def test_trace_tool_gated_off_records_nothing(tmp_path, monkeypatch):
    """When PG_ENABLE_TOOL_TRACKER is OFF, _trace_tool is a pure no-op even if
    a stale ON singleton (with a run_dir) exists."""
    from src.polaris_graph.retrieval import live_retriever

    reset_tool_tracer()
    get_tool_tracer(tmp_path)  # stale ON singleton bound to a run_dir
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")

    live_retriever._trace_tool(
        "fetch_content", target="u", status="ok", latency_ms=1.0,
        backend_used="httpx_naive",
    )
    # nothing recorded
    assert get_tool_tracer().get_calls() == []


def test_trace_tool_gated_on_records(tmp_path, monkeypatch):
    """Default/ON: _trace_tool records into the singleton (control for the
    gated-off test above)."""
    from src.polaris_graph.retrieval import live_retriever

    reset_tool_tracer()
    get_tool_tracer(tmp_path)
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "1")

    live_retriever._trace_tool(
        "fetch_content", target="u", status="ok", latency_ms=1.0,
        backend_used="httpx_naive",
    )
    calls = get_tool_tracer().get_calls()
    assert len(calls) == 1
    assert calls[0].tool_name == "fetch_content"
