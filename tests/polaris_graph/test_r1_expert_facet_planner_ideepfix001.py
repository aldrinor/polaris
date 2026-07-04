"""R1 (I-deepfix-001, #1344) — LLM expert-facet planner widens the query frontier.

Proves the EFFECT in the real planner output (the queries actually issued into production
retrieval), not a flag-check:

* RED (legacy, flag OFF): a concise question yields ONE TOC-derived query — the measured drb_72
  starvation (7 of 35).
* GREEN (flag ON): the facet planner seeds MANY distinct facet-angle queries covering all five
  vantage points (mechanism / stakeholder / counter-evidence / temporal / geographic), and EVERY
  emitted query carries the question's own subject keywords as a scope anchor (so a facet can never
  generalise off-subject — the drb_72-v2 contamination guard, asserted hard).
* Deterministic FLOOR: a degenerate (empty) facet-tree LLM reply still emits a scope-anchored
  frontier from the question itself — the frontier never shrinks below legacy.
* Drops ZERO sources: per_query_retrieve is called once per issued query and every result is kept.
"""
from src.polaris_graph.retrieval import expert_facet_planner as efp
from src.polaris_graph.retrieval import fs_researcher_query_gen as fsr

QUESTION = (
    "Please write a literature review on the restructuring impact of Artificial Intelligence (AI) "
    "on the labor market."
)

_FACET_TREE = "\n".join([
    "Manufacturing and supply chain automation",
    "Wage and employment displacement effects",
    "Worker reskilling and education programs",
])


class _StubResult:
    def __init__(self, url: str):
        self.evidence_rows = [{"source_url": url, "statement": f"finding from {url}"}]


def _facet_llm(recorder):
    """LLM that returns the facet tree for the expert-planner prompt, NONE otherwise."""
    def _llm(prompt):
        recorder.append(prompt)
        if "expert research planner" in prompt:
            return _FACET_TREE + "\n"
        return "NONE\n"
    return _llm


def _legacy_llm(recorder):
    """Legacy FS-Researcher stub: TOC -> one bare sub-topic, then a query, then NONE."""
    def _llm(prompt):
        recorder.append(prompt)
        if "Deconstruct" in prompt:
            return "One narrow sub-topic\n"
        if "search query" in prompt:
            return "one narrow sub-topic query\n"
        return "NONE\n"
    return _llm


def _retriever(calls):
    def _r(research_question, **kw):
        calls.append(research_question)
        return _StubResult(url=f"https://src/{len(calls)}")
    return _r


def test_r1_off_is_legacy_narrow_frontier(monkeypatch):
    """RED: flag OFF -> the legacy one-query-per-sub-topic frontier (the measured starvation)."""
    monkeypatch.delenv("PG_EXPERT_FACET_PLANNER", raising=False)
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_ROUNDS", "1")
    calls: list = []
    queries, results = fsr.plan_fs_researcher_queries(
        QUESTION, _legacy_llm([]), _retriever(calls),
    )
    assert len(queries) == 1, "legacy path must issue exactly one TOC-derived query (RED baseline)"
    assert len(results) == 1


def test_r1_on_widens_frontier_with_all_angles(monkeypatch):
    """GREEN: flag ON -> many distinct facet-angle queries across all five vantage points."""
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.delenv("PG_FACET_COMPLETENESS", raising=False)  # R1 only for this test
    llm_calls: list = []
    fetch_calls: list = []
    queries, results = fsr.plan_fs_researcher_queries(
        QUESTION, _facet_llm(llm_calls), _retriever(fetch_calls),
    )

    # The frontier is WIDE: 3 facets x 5 angles = 15 distinct queries (>> the legacy 1).
    assert len(queries) >= 12, f"facet planner must widen the frontier; got {len(queries)}"
    assert len(set(q.lower() for q in queries)) == len(queries), "queries must be distinct"

    # Exactly ONE LLM call built the facet tree (bounded cost — no per-angle LLM call).
    assert sum(1 for p in llm_calls if "expert research planner" in p) == 1
    assert len(llm_calls) == 1, "angles are deterministic; only the facet tree costs an LLM call"

    # All five angle vantage points are represented in the emitted frontier.
    blob = " ".join(queries).lower()
    for lens_word in ("mechanism", "stakeholders", "criticism", "recent", "regional"):
        assert lens_word in blob, f"missing the {lens_word!r} facet-angle vantage point"

    # HARD scope-anchor assertion: EVERY emitted query carries the question's subject keywords, so a
    # facet can never generalise into its broad field (the drb_72-v2 off-topic contamination guard).
    anchor = efp._question_anchor(QUESTION)
    assert anchor and len(anchor.split()) >= 2, "expected a real multi-token scope anchor"
    for q in queries:
        assert anchor in q, f"scope anchor {anchor!r} missing from query {q!r} (off-topic drift risk)"

    # Drops ZERO sources: one retrieve call per issued query, every result kept.
    assert len(fetch_calls) == len(queries)
    assert len(results) == len(queries)


def test_r1_deterministic_floor_on_empty_llm(monkeypatch):
    """A degenerate (empty) facet-tree reply still emits a scope-anchored frontier (never shrinks)."""
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    facets = efp.plan_expert_facets(QUESTION, lambda _p: "")  # LLM returns nothing usable
    assert facets, "the deterministic floor must still yield at least one facet"
    anchor = efp._question_anchor(QUESTION)
    for facet in facets:
        assert facet.queries, "each floor facet still emits angle queries"
        for q in facet.queries:
            assert anchor in q, "floor queries must still be scope-anchored"


def test_r1_max_facets_bound_is_compute_cap(monkeypatch):
    """PG_EXPERT_FACET_MAX_FACETS bounds cost UP-side (a compute cap, never forcing a number up)."""
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_EXPERT_FACET_MAX_FACETS", "2")
    facets = efp.plan_expert_facets(QUESTION, lambda _p: _FACET_TREE + "\n")
    assert len(facets) == 2, "max-facets bound must cap the facet count"
