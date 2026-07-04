"""I-deepfix-001 (#1344) L5 query-length fix — offline unit tests.

The DRB-II coverage lane (``run_l5_required_entity_coverage``) and its sibling
``missing_entity_gap_queries`` prepend the WHOLE research question to each
still-missing entity to build the targeted search query. On drb_72 the raw
question was 2116 chars, so the built query blew past Serper's 2048-char ``q``
hard limit -> HTTP 400 "query too long" -> the lane merged 0 rows and every
derived entity stayed a gap.

These tests prove the bound: a 2116-char question plus an entity now yields a
query under 2048 that does NOT 400, so the coverage-l5 lane can merge more than
0 rows. ALL deterministic, NO network — ``search_fn`` / ``retrieval_fn`` are
stubs; the search stub reproduces the real backend contract (an over-limit query
400s in Serper and the wrapper returns []).

FAITHFULNESS (§-1.3): bounding a QUERY STRING length is NOT dropping a source.
The research_question that flows to the fetch/verify chokepoint is UNCHANGED —
only the discovery SEARCH query is length-bounded.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.required_entity_retrieval import (
    missing_entity_gap_queries,
    run_l5_required_entity_coverage,
)

# Serper's documented hard limit on the `q` field. A literal (not the module
# constant) so this test collects + genuinely FAILS on the pre-fix base source
# (RED) instead of erroring on a missing import.
_LIMIT = 2048
_ENTITY = "Mounjaro"  # single capitalized proper noun -> exactly one derived entity


def _long_question(entity: str = _ENTITY, target_len: int = 2116) -> str:
    """A realistic research question >= ``target_len`` chars carrying exactly one
    capitalized proper-noun entity. Filler is lowercase so no extra proper nouns
    are derived and the derived set is deterministically ``{entity}``.
    """
    head = f"how does {entity} influence long term glycemic control "
    filler = (
        "and what are the downstream metabolic and cardiovascular outcomes "
        "reported across the large observational cohorts studied to date "
    )
    q = head
    while len(q) < target_len:
        q += filler
    q = q[:target_len]
    assert len(q) == target_len
    return q


class _SerperLikeSearch:
    """Reproduces the production ``_serper_search_sync`` contract: an over-limit
    query 400s in Serper and the wrapper returns [] (zero results); an in-limit
    query returns one candidate URL.
    """

    def __init__(self, hit_url: str, limit: int = _LIMIT):
        self.calls: list[str] = []
        self._hit_url = hit_url
        self._limit = limit

    def __call__(self, query, *, domains=None, max_results=5):
        self.calls.append(query)
        if len(query) > self._limit:
            return []  # Serper HTTP 400 "query too long" -> wrapper returns []
        return [{"url": self._hit_url, "title": "", "snippet": ""}]


class _RetrievalStub:
    """Records retrieval_fn kwargs and returns evidence rows for the seed urls."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        seeds = list(kwargs.get("seed_urls") or [])
        rows = [
            {
                "source_url": u,
                "url": u,
                "direct_quote": f"{_ENTITY} safety and dosing content." + "x" * 60,
                "title": "authoritative page",
                "tier": "T1",
            }
            for u in seeds
        ]

        class _Result:
            evidence_rows = rows

        return _Result()


# ─────────────────────────────────────────────────────────────────────
# (1) missing_entity_gap_queries: long question -> query under the limit
# ─────────────────────────────────────────────────────────────────────
def test_gap_queries_bounded_under_serper_limit():
    q = _long_question()
    assert len(q) > _LIMIT  # precondition: the raw question ALONE would 400
    queries = missing_entity_gap_queries(
        required_entities=[_ENTITY],
        corpus_texts=[],  # entity not covered -> a query is emitted
        research_question=q,
    )
    assert queries, "a still-missing entity must yield one gap query"
    # BEFORE the fix each query was `<2116-char question> Mounjaro` (> 2048).
    for built in queries:
        assert len(built) <= _LIMIT, f"query too long: {len(built)} > {_LIMIT}"
    # the entity is still present in the (bounded) query — coverage intent kept
    assert _ENTITY.lower() in queries[0].lower()


# ─────────────────────────────────────────────────────────────────────
# (2) L5 lane: long question -> query fits -> lane merges > 0 rows
# ─────────────────────────────────────────────────────────────────────
def test_l5_lane_merges_rows_with_long_question(monkeypatch):
    monkeypatch.setenv("PG_COVERAGE_L5_REQUIRED_ENTITY", "1")
    q = _long_question()
    search = _SerperLikeSearch(hit_url="https://www.drugs.com/mounjaro.html")
    retr = _RetrievalStub()

    result = run_l5_required_entity_coverage(
        research_question=q,
        facets=None,  # question-only derivation -> exactly {Mounjaro}
        corpus_texts=[],  # nothing covered -> Mounjaro is missing
        search_fn=search,
        retrieval_fn=retr,
    )

    # the entity was derived and flagged missing
    assert _ENTITY in result.derived_entities
    assert _ENTITY in result.missing_entities
    # every built query fits under the Serper limit (was > 2048 pre-fix -> 400)
    assert search.calls, "the lane must fire at least one targeted query"
    for built in search.calls:
        assert len(built) <= _LIMIT, f"query too long: {len(built)} > {_LIMIT}"
    # the lane surfaced candidate seed urls and merged > 0 rows (was 0 pre-fix)
    assert len(result.seed_urls) > 0
    assert len(result.evidence_rows) > 0
    # the entity did NOT stay a gap (it would have, pre-fix, on the 400)
    assert _ENTITY not in result.gap_entities


# ─────────────────────────────────────────────────────────────────────
# (3) faithfulness: the FETCH chokepoint still receives the FULL question
# ─────────────────────────────────────────────────────────────────────
def test_l5_fetch_receives_unbounded_research_question(monkeypatch):
    monkeypatch.setenv("PG_COVERAGE_L5_REQUIRED_ENTITY", "1")
    q = _long_question()
    search = _SerperLikeSearch(hit_url="https://www.drugs.com/mounjaro.html")
    retr = _RetrievalStub()

    run_l5_required_entity_coverage(
        research_question=q,
        facets=None,
        corpus_texts=[],
        search_fn=search,
        retrieval_fn=retr,
    )

    # only the SEARCH query is length-bounded; the research_question handed to the
    # fetch/verify chokepoint is the UNCHANGED full-length question (§-1.3).
    assert retr.calls, "seed urls were surfaced -> the fetch chokepoint must fire"
    assert retr.calls[0]["research_question"] == q


# ─────────────────────────────────────────────────────────────────────
# (4) search_agent defensive clip: over-limit `q` clipped before the POST
# ─────────────────────────────────────────────────────────────────────
def test_serper_search_sync_clips_overlong_query(monkeypatch):
    from src.agents import search_agent

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = "{}"

        def raise_for_status(self):
            return None

        def json(self):
            return {"organic": []}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["q"] = (json or {}).get("q", "")
        return _Resp()

    monkeypatch.setenv("SERPER_API_KEY", "test-key")
    monkeypatch.delenv("SERPER_QUERY_MAX_CHARS", raising=False)
    monkeypatch.setattr(search_agent.requests, "post", _fake_post)

    long_q = "term " * 800  # ~4000 chars, well over the 2048 limit
    assert len(long_q) > _LIMIT
    search_agent._serper_search_sync(long_q, search_type="search")

    # BEFORE the fix the full ~4000-char query was POSTed -> Serper HTTP 400.
    assert "q" in captured
    assert len(captured["q"]) <= _LIMIT
