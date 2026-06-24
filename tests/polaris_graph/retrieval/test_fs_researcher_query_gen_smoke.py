"""Offline $0 smoke test for the FS-Researcher production query-gen wiring (I-recency-001 #1296).

Proves the FS-Researcher loop SELECTS + issues queries and that merge_retrieval_results preserves
the downstream LiveRetrievalResult contract — WITHOUT any LLM, network, GPU, or paid call. Every
dependency is a pure-Python stub. Cost: $0.
"""
from __future__ import annotations

import os

from src.polaris_graph.retrieval import fs_researcher_query_gen as fsq


class _MockLRR:
    """Stand-in for LiveRetrievalResult: accepts the full result_factory contract."""

    def __init__(self, **kw):
        self.classified_sources = kw.get("classified_sources", [])
        self.evidence_rows = kw.get("evidence_rows", [])
        self.api_calls = kw.get("api_calls", {})
        self.notes = kw.get("notes", [])
        self.corpus_truncated = kw.get("corpus_truncated", False)
        self.journal_metadata_sidecar = kw.get("journal_metadata_sidecar")
        for k, v in kw.items():
            setattr(self, k, v)


def _make_llm(call_log):
    """Deterministic stub policy: TOC -> 3 sub-topics; per-todo -> a distinct query; checklist -> NONE."""

    def llm(prompt: str) -> str:
        call_log["llm"] += 1
        p = prompt.lower()
        if "index.md table of contents" in p or "deconstruct this research topic" in p:
            return "Sub-topic alpha\nSub-topic beta\nSub-topic gamma"
        if "write one search query" in p:
            # echo the sub-topic into a distinct query string
            tail = prompt.strip().splitlines()[-1].strip()
            return f"query for {tail}"
        if "self-review" in p:
            return "NONE"  # stop after the first round
        return "NONE"

    return llm


def _make_retrieve(call_log):
    def retrieve(*, research_question: str, **_kw):
        call_log["retrieve"] += 1
        call_log["queries"].append(research_question)
        # ev_000 each call (the production retriever restarts at ev_000 -> merge must renumber)
        return _MockLRR(
            evidence_rows=[
                {"evidence_id": "ev_000", "source_url": f"https://ex/{call_log['retrieve']}/a",
                 "statement": f"row for {research_question}"},
                {"evidence_id": "ev_001", "source_url": f"https://ex/{call_log['retrieve']}/b",
                 "statement": "second row"},
            ],
            api_calls={"serper": 1},
            candidates_fetched=2,
            notes=[f"retrieved {research_question}"],
        )

    return retrieve


def test_fs_researcher_flag_default_off():
    """Default (unset) => FS-Researcher path is OFF (legacy behaviour preserved, byte-identical)."""
    os.environ.pop("PG_QGEN_FS_RESEARCHER", None)
    assert fsq.fs_researcher_enabled() is False
    os.environ["PG_QGEN_FS_RESEARCHER"] = "1"
    try:
        assert fsq.fs_researcher_enabled() is True
    finally:
        os.environ.pop("PG_QGEN_FS_RESEARCHER", None)


def test_fs_researcher_loop_issues_queries_and_merges():
    """Stub llm + retrieve: the TOC/todo loop issues distinct queries; merge renumbers ev ids."""
    call_log = {"llm": 0, "retrieve": 0, "queries": []}
    llm = _make_llm(call_log)
    retrieve = _make_retrieve(call_log)

    queries, results = fsq.plan_fs_researcher_queries(
        "What governs X?", llm, retrieve, max_queries=10, max_rounds=3, retrieve_kwargs={}
    )

    # the index.md TOC produced 3 sub-topics -> 3 distinct queries, each retrieved once
    assert len(queries) == 3, f"expected 3 queries, got {queries}"
    assert call_log["retrieve"] == 3
    assert len(set(q.lower() for q in queries)) == 3, "queries must be distinct (dedup)"
    assert all(isinstance(q, str) and q for q in queries)

    merged = fsq.merge_retrieval_results(results, _MockLRR)
    assert merged is not None
    # 3 queries x 2 rows = 6 rows, renumbered ev_000..ev_005, all distinct
    ev_ids = [r["evidence_id"] for r in merged.evidence_rows]
    assert ev_ids == [f"ev_{i:03d}" for i in range(6)], f"renumbering broken: {ev_ids}"
    assert merged.api_calls.get("serper") == 3, "api_calls must aggregate across queries"
    assert any("fs_researcher: merged" in n for n in merged.notes), "merge note missing"


def test_fs_researcher_empty_results_merge():
    """Zero queries (e.g. budget 0) merges to an empty-but-valid result, not a crash."""
    merged = fsq.merge_retrieval_results([], _MockLRR)
    assert merged is not None
    assert merged.evidence_rows == []
    assert any("no rounds" in n for n in merged.notes)


if __name__ == "__main__":
    test_fs_researcher_flag_default_off()
    test_fs_researcher_loop_issues_queries_and_merges()
    test_fs_researcher_empty_results_merge()
    print("PASS — FS-Researcher wiring smoke ($0, no llm/network/gpu)")
