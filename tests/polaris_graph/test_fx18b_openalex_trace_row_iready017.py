"""FX-18b item-1 (I-ready-017 #1123): emit an OpenAlex `retrieval_trace` QUERY row.

Context: the OpenAlex sweep backend (live_retriever, ~line 2461, gated on PG_OPENALEX_SEARCH)
already calls `_trace_tool("openalex_search", ...)` (FX-20) but was MISSING the
`_trace_query("openalex_search", q, urls)` row that serper/s2 emit — so `retrieval_trace.jsonl`
had no openalex row and the RERUN §-1.1 line-by-line audit could not confirm the OpenAlex
academic backend fired. FX-18b adds that one telemetry-only, additive line on the OK path,
mirroring serper (which only traces on ok).

These tests are OFFLINE (no network). They verify the trace row is recorded and retrievable via
`pathB_capture.retrieval_trace_records()` with backend == 'openalex_search'. PURELY OBSERVATIONAL:
nothing here touches grounding / strict_verify / 4-role.
"""
from __future__ import annotations

import src.polaris_graph.benchmark.benchmark_run_capture as pathb
import src.polaris_graph.retrieval.domain_backends as _db
import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate

_NL = (
    "To what extent will artificial intelligence and automation technologies displace or transform "
    "jobs across the labor market over the next decade, and what does the empirical economics "
    "literature conclude about net employment effects?"
)


def _has_openalex_query_row(records: list[dict]) -> dict | None:
    for rec in records:
        if rec.get("kind") == "query" and rec.get("backend") == "openalex_search":
            return rec
    return None


def test_trace_query_records_openalex_search_row():
    """Unit-level: _trace_query('openalex_search', q, urls) appends a retrievable trace row.

    Mirrors exactly the call FX-18b added in the OpenAlex OK branch. No run_live_retrieval needed —
    this proves the helper + pathB_capture wiring records the backend the RERUN audit looks for.
    """
    pathb.start_retrieval_trace()
    urls = ["https://oa.org/a", "https://oa.org/b"]
    lr._trace_query("openalex_search", _NL, urls)

    records = pathb.retrieval_trace_records()
    row = _has_openalex_query_row(records)
    assert row is not None, "expected an 'openalex_search' query row in the retrieval trace"
    assert row["query"] == _NL
    assert row["return_count"] == 2
    assert row["urls"] == urls


def test_run_live_retrieval_emits_openalex_query_row(monkeypatch):
    """End-to-end OK path: run the minimal retrieval that hits the OpenAlex branch and assert the
    trace carries the openalex_search query row with the 2 returned URLs. Offline (all backends
    stubbed); the trace is started before the run, exactly as run_one_query does in production.
    """
    monkeypatch.setenv("PG_OPENALEX_SEARCH", "1")

    monkeypatch.setattr(lr, "_serper_search", lambda q, num=10, api_calls=None: [])
    monkeypatch.setattr(lr, "_s2_bulk_search", lambda query, limit=20: [])

    _oa_urls = ["https://oa.org/first", "https://oa.org/second"]

    def _fake_openalex(query, limit=20):
        return [
            SearchCandidate(url=_oa_urls[0], title="OA 1", snippet="", source="openalex_search"),
            SearchCandidate(url=_oa_urls[1], title="OA 2", snippet="", source="openalex_search"),
        ]
    monkeypatch.setattr(_db, "openalex_search", _fake_openalex)

    # Stub the fetch so no network is touched; content is irrelevant to the trace assertion.
    monkeypatch.setattr(
        lr, "_fetch_content",
        lambda url, max_chars, **kwargs: (
            "Automation displaced manufacturing jobs in the labor market. " * 8, True, "T", "html", ""
        ),
    )

    pathb.start_retrieval_trace()
    lr.run_live_retrieval(
        research_question=_NL,
        protocol=None,            # no scope validation -> effective_queries = [the NL question]
        anchor_seed=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        fetch_cap=10,
    )

    records = pathb.retrieval_trace_records()
    row = _has_openalex_query_row(records)
    assert row is not None, "OpenAlex branch ran but emitted no 'openalex_search' query trace row"
    assert row["return_count"] == 2
    assert set(row["urls"]) == set(_oa_urls)


def test_openalex_query_row_absent_when_flag_off(monkeypatch):
    """Guard: PG_OPENALEX_SEARCH=0 disables the branch, so NO openalex_search query row is emitted.

    Confirms FX-18b's row lives strictly inside the existing flag gate — it does not fire when the
    operator turns the OpenAlex backend off.
    """
    monkeypatch.setenv("PG_OPENALEX_SEARCH", "0")
    monkeypatch.setattr(lr, "_serper_search", lambda q, num=10, api_calls=None: [])
    monkeypatch.setattr(lr, "_s2_bulk_search", lambda query, limit=20: [])

    def _boom(query, limit=20):  # should never be called when the flag is off
        raise AssertionError("openalex_search must not run when PG_OPENALEX_SEARCH=0")
    monkeypatch.setattr(_db, "openalex_search", _boom)
    monkeypatch.setattr(
        lr, "_fetch_content",
        lambda url, max_chars, **kwargs: ("text " * 8, True, "T", "html", ""),
    )

    pathb.start_retrieval_trace()
    lr.run_live_retrieval(
        research_question=_NL,
        protocol=None,
        anchor_seed=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        fetch_cap=10,
    )

    records = pathb.retrieval_trace_records()
    assert _has_openalex_query_row(records) is None, (
        "no 'openalex_search' query row should be emitted when PG_OPENALEX_SEARCH=0"
    )
