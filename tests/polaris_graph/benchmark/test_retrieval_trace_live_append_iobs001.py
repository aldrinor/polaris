"""AC2 (I-obs-001 #1141): retrieval_trace live-append tests.

Verifies each retrieval record appends to the .jsonl AS IT HAPPENS when a path is supplied,
that no-path callers do zero file I/O (byte-unchanged), and — the hardest risk — that the
end-of-retrieval truncating "w" reconcile flush does NOT double records.
"""
from __future__ import annotations

import json

import pytest

from polaris_graph.benchmark import pathB_capture as pb


@pytest.fixture(autouse=True)
def _isolate():
    pb.start_retrieval_trace()  # reset to a clean no-path state
    yield
    pb.clear_pathB_capture()


def _read_lines(p):
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_live_append_writes_each_record_as_it_happens(tmp_path):
    path = tmp_path / "retrieval_trace.jsonl"
    pb.start_retrieval_trace(path)

    pb.record_retrieval_query("serper", "metal ions cvd", ["http://a", "http://b"])
    assert len(_read_lines(path)) == 1  # visible immediately (tail -f safe)
    pb.record_retrieval_kept("http://a", "serper")
    assert len(_read_lines(path)) == 2
    pb.record_retrieval_drop("http://b", "offtopic")
    live = _read_lines(path)
    assert len(live) == 3
    assert [r["kind"] for r in live] == ["query", "kept", "drop"]
    # live lines == in-memory records (same dict objects appended)
    assert pb.retrieval_trace_records() == live


def test_no_path_writes_nothing(tmp_path):
    # default no-path start (autouse) — recording must do zero file I/O
    pb.record_retrieval_query("serper", "q", ["http://a"])
    pb.record_retrieval_kept("http://a", "serper")
    assert list(tmp_path.iterdir()) == []
    assert len(pb.retrieval_trace_records()) == 2  # in-memory still works


def test_end_flush_w_does_not_double(tmp_path):
    """The end-of-retrieval 'w' flush rewrites from the in-memory list; it must REPLACE the
    live-appended lines, not append to them (no doubling)."""
    path = tmp_path / "retrieval_trace.jsonl"
    pb.start_retrieval_trace(path)
    pb.record_retrieval_query("serper", "q", ["http://a"])
    pb.record_retrieval_kept("http://a", "serper")
    assert len(_read_lines(path)) == 2

    # Simulate run_honest_sweep_r3's end-flush: truncating "w" rewrite from the in-memory list.
    records = pb.retrieval_trace_records()
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    final = _read_lines(path)
    assert len(final) == 2  # NOT 4 — no doubling
    assert final == records


def test_clear_resets_path(tmp_path):
    path = tmp_path / "retrieval_trace.jsonl"
    pb.start_retrieval_trace(path)
    pb.record_retrieval_query("serper", "q", ["http://a"])
    assert path.exists()
    pb.clear_pathB_capture()
    # after clear, a no-path restart records only in-memory; the old file is untouched
    pb.start_retrieval_trace()
    pb.record_retrieval_kept("http://a", "serper")
    assert len(_read_lines(path)) == 1  # the post-clear record did NOT append to the old file


def test_live_append_never_raises_on_io_error(tmp_path, monkeypatch):
    path = tmp_path / "retrieval_trace.jsonl"
    pb.start_retrieval_trace(path)

    def _boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", _boom)
    # must NOT raise (module contract: capture never raises)
    pb.record_retrieval_query("serper", "q", ["http://a"])
    assert len(pb.retrieval_trace_records()) == 1  # in-memory unaffected
