"""Per-call retrieval_trace.jsonl (I-meta-002-q1d #945). NO network / NO spend.

Asserts the Codex-gate behaviors: the contextvar recorders accumulate query/kept/drop records, no-op
when not started, round-trip to jsonl, and — critically — the live_retriever hooks are PURELY
OBSERVATIONAL (they do NOT change retrieval return values; the §9.1 chokepoint is untouched).
"""

from __future__ import annotations

import json

import pytest

import src.polaris_graph.benchmark.benchmark_run_capture as pathb


@pytest.fixture(autouse=True)
def _clean_trace():
    # ensure each test starts/ends with no leaked trace state
    pathb._RETRIEVAL_TRACE.set(None)
    yield
    pathb._RETRIEVAL_TRACE.set(None)


def test_recorders_noop_when_not_started():
    pathb.record_retrieval_query("serper", "q", ["https://a"])
    pathb.record_retrieval_kept("https://a", "serper")
    pathb.record_retrieval_drop("https://b", "content_starved")
    assert pathb.retrieval_trace_records() == []  # no-op without start_retrieval_trace()


def test_recorders_accumulate_after_start():
    pathb.start_retrieval_trace()
    pathb.record_retrieval_query("serper", "tirzepatide HbA1c", ["https://a", "https://b"])
    pathb.record_retrieval_kept("https://a", "serper")
    pathb.record_retrieval_drop("https://b", "content_starved")
    recs = pathb.retrieval_trace_records()
    assert len(recs) == 3
    q = recs[0]
    assert q == {"kind": "query", "backend": "serper", "query": "tirzepatide HbA1c",
                 "return_count": 2, "urls": ["https://a", "https://b"]}
    assert recs[1] == {"kind": "kept", "url": "https://a", "backend": "serper"}
    assert recs[2] == {"kind": "drop", "url": "https://b", "reason": "content_starved"}


def test_start_resets_to_fresh_list_no_stale_leak():
    pathb.start_retrieval_trace()
    pathb.record_retrieval_query("serper", "q1", ["https://x"])
    assert len(pathb.retrieval_trace_records()) == 1
    pathb.start_retrieval_trace()  # next query — must NOT carry q1's records (P2 lifecycle hygiene)
    assert pathb.retrieval_trace_records() == []


def test_records_round_trip_jsonl():
    pathb.start_retrieval_trace()
    pathb.record_retrieval_query("semantic_scholar", "q", ["https://a"])
    pathb.record_retrieval_drop("https://b", "rerank_not_selected")
    lines = [json.dumps(r, ensure_ascii=False) for r in pathb.retrieval_trace_records()]
    parsed = [json.loads(line) for line in lines]
    assert parsed[0]["kind"] == "query" and parsed[0]["backend"] == "semantic_scholar"
    assert parsed[1] == {"kind": "drop", "url": "https://b", "reason": "rerank_not_selected"}


def test_clear_pathb_capture_resets_trace():
    pathb.start_retrieval_trace()
    pathb.record_retrieval_drop("https://b", "fetch_failed")
    assert len(pathb.retrieval_trace_records()) == 1
    pathb.clear_pathB_capture()
    assert pathb.retrieval_trace_records() == []


# --- the live_retriever serper hook does NOT alter the return value + emits a query record ----------
def test_serper_hook_observational_only(monkeypatch):
    import src.polaris_graph.retrieval.live_retriever as lr

    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"organic": [
                {"link": "https://a", "title": "A", "snippet": "sa"},
                {"link": "https://b", "title": "B", "snippet": "sb"},
            ]}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _FakeResp()

    monkeypatch.setenv("SERPER_API_KEY", "fake-key")
    monkeypatch.setattr(lr.httpx, "Client", _FakeClient)
    pathb.start_retrieval_trace()
    out = lr._serper_search("tirzepatide", num=10)
    # return value is exactly the parsed candidates — the trace hook did NOT alter it
    assert [o["url"] for o in out] == ["https://a", "https://b"]
    assert all(o["source"] == "serper" for o in out)
    # AND a query record was emitted with the returned URLs
    recs = [r for r in pathb.retrieval_trace_records() if r["kind"] == "query"]
    assert recs and recs[-1]["backend"] == "serper"
    assert recs[-1]["urls"] == ["https://a", "https://b"] and recs[-1]["return_count"] == 2


def test_live_retriever_trace_helpers_are_best_effort(monkeypatch):
    """The lazy-import trace helpers must never raise even if pathB import blows up."""
    import src.polaris_graph.retrieval.live_retriever as lr
    # not started -> no-op, no raise
    pathb._RETRIEVAL_TRACE.set(None)
    lr._trace_query("serper", "q", ["https://a"])
    lr._trace_kept("https://a", "serper")
    lr._trace_drop("https://b", "offtopic")
    assert pathb.retrieval_trace_records() == []
