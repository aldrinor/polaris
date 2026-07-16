"""S2 telemetry proof — the retrieval projection reaches the FS frontier BEFORE
any fetch, and the gate path NEVER reduces the candidate lane count (997-guard).

Offline + deterministic. NO network, NO LLM: the FS ``per_query_retrieve`` is a
recording stub that captures every issued query WITHOUT fetching, the facet
planner is monkeypatched to a fixed facet tree, and the projection is compiled
from a canned task-72 contract + plan (the same shape the S1 compiler emits).

The acceptance criteria (GATE_DESIGN_CONSOLIDATED §8 S2 / sol_gate_design §7
"FS no-starvation spike"):

  (a) on the task-72 contract, the emitted query strings / frontier carry the
      journal/scholarly ROUTING (primary_literature evidence-need = S2/OpenAlex),
      the ENGLISH source-language lane, and EACH mandatory topic — BEFORE results
      exist (the recorded frontier is captured at query-issue time);
  (b) the mechanized 997-guard: the gate path's candidate query/evidence-need
      count is >= the no-gate path's — the gate can only ADD lanes, never reduce
      them, at PLANNING level before any fetch.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.planning.planning_gate_schema import (
    contract_from_dict,
    plan_from_dict,
)
from src.polaris_graph.planning import retrieval_projection as rp

# ---------------------------------------------------------------------------
# The task-72 contract + plan (canned; the shape the S1 compiler emits).
# ---------------------------------------------------------------------------

TASK_72_PROMPT = (
    "Please write a literature review on the restructuring impact of "
    "Artificial Intelligence (AI) on the labor market. Ensure the review only "
    "cites high-quality, English-language journal articles."
)


def _span(phrase: str) -> dict:
    i = TASK_72_PROMPT.find(phrase)
    assert i != -1
    return {"start": i, "end": i + len(phrase), "quote": phrase}


def _task72_contract():
    return contract_from_dict({
        "objective": [{
            "term_id": "objective.question", "dimension": "objective.question",
            "value": "restructuring impact of AI on the labor market",
            "origin": "explicit", "force": "open",
            "spans": [_span("literature review")],
        }],
        "scope": [
            {"term_id": "scope.language", "dimension": "scope.source_languages",
             "value": "English", "origin": "explicit", "force": "hard",
             "spans": [_span("English-language")]},
            {"term_id": "scope.source_types", "dimension": "scope.source_types",
             "value": "journal article", "origin": "explicit", "force": "hard",
             "spans": [_span("journal articles")]},
        ],
        "deliverable": [{
            "term_id": "deliverable.kind", "dimension": "deliverable.kind",
            "value": "literature_review", "origin": "explicit", "force": "hard",
            "spans": [_span("literature review")]}],
        "coverage": [
            {"requirement_id": "cov1", "kind": "topic", "statement": {
                "term_id": "cov1", "dimension": "content.coverage",
                "value": "AI restructuring of labor market",
                "origin": "inferred", "force": "open"}},
            {"requirement_id": "cov2", "kind": "topic", "statement": {
                "term_id": "cov2", "dimension": "content.coverage",
                "value": "employment effects of AI",
                "origin": "inferred", "force": "open"}},
            {"requirement_id": "cov3", "kind": "topic", "statement": {
                "term_id": "cov3", "dimension": "content.coverage",
                "value": "skill demand shifts from AI",
                "origin": "inferred", "force": "open"}},
        ],
    })


def _task72_plan():
    return plan_from_dict({
        "threads": [
            {"thread_id": f"t{i}", "question": f"q{i}", "mandatory": True,
             "coverage_requirement_ids": [f"cov{i}"]}
            for i in range(1, 4)
        ],
        "query_intents": [
            {"intent_id": "qi1", "thread_id": "t1", "purpose": "discovery",
             "concepts": ["AI restructuring of labor market"],
             "source_type": "journal_article", "language": "en", "mandatory": True},
            {"intent_id": "qi2", "thread_id": "t2", "purpose": "discovery",
             "concepts": ["employment effects of AI"],
             "source_type": "journal_article", "language": "en", "mandatory": True},
            {"intent_id": "qi3", "thread_id": "t3", "purpose": "discovery",
             "concepts": ["skill demand shifts from AI"],
             "source_type": "journal_article", "language": "en", "mandatory": True},
        ],
        "coverage_matrix": [
            {"contract_term_id": "scope.language", "owning_stages": ["retrieval"]},
            {"contract_term_id": "scope.source_types", "owning_stages": ["retrieval"]},
        ],
        "budget": {"mandatory_lane_count": 3, "overflow_policy": "expand"},
    })


def _projection():
    return rp.from_contract_and_plan(
        _task72_contract(), _task72_plan(), original_prompt=TASK_72_PROMPT
    )


# ---------------------------------------------------------------------------
# (a1) Projection COMPILE: journal routing + English + each mandatory topic.
# ---------------------------------------------------------------------------

def test_projection_routes_journals_and_carries_english_and_topics():
    proj = _projection()

    # journal/scholarly ROUTING: source_types -> primary_literature evidence-need
    # (the need-type registry routes S2/OpenAlex scholarly adapters off this).
    scope = proj.to_scope_terms()
    assert "primary_literature" in scope["evidence_needs"], (
        "journal-only must route the primary_literature (scholarly) evidence-need "
        "= GO FIND journals, not filter a general corpus"
    )

    frame = proj.to_research_frame()
    assert frame is not None
    assert "primary_literature" in frame.evidence_needs

    # the hard journal scope term is folded into the query text (scope-anchored),
    # never a post-fetch drop.
    assert any("journal" in t.lower() for t in scope["hard"]), scope["hard"]

    # EACH mandatory topic reaches the emitted frontier BEFORE any fetch.
    queries = proj.to_amplified_queries(base_question=TASK_72_PROMPT)
    joined = " || ".join(queries).lower()
    for topic in ("restructuring", "employment", "skill demand"):
        assert topic in joined, f"mandatory topic {topic!r} missing from frontier: {queries}"

    # the journal scope rule shapes the FIRST-class query text (scope suffix folded in).
    assert all(
        "journal" in q.lower()
        for q in queries
        if any(tp in q.lower() for tp in ("restructuring", "employment", "skill"))
    ), f"a mandatory-topic query lost its journal scope anchor: {queries}"


# ---------------------------------------------------------------------------
# (a2) Telemetry: the projection lanes reach the FS frontier BEFORE any fetch.
# ---------------------------------------------------------------------------

def test_projection_reaches_fs_frontier_before_fetch(monkeypatch):
    """Drive the FS expert-facet path with a recording ``per_query_retrieve``
    that NEVER fetches — it just captures every issued query. Assert the gate
    projection's journal/English/topic lanes are in the captured frontier, and
    that they appear BEFORE the baseline facet queries (gate lanes lead)."""
    from src.polaris_graph.retrieval import fs_researcher_query_gen as fsq
    from src.polaris_graph.retrieval import expert_facet_planner as efp

    # ON the expert-facet path (the ON-mode frontier the design names).
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER", "1")
    # keep the multilingual / sub-entity / landmark widen lanes OFF so the frontier
    # is exactly {gate lanes} + {facet seeds} (a clean superset assertion).
    for off in (
        "PG_MULTILINGUAL_RETRIEVAL", "PG_SUBENTITY_QUERY_EXPANSION",
        "PG_LANDMARK_EXPANDER", "PG_STANCE_DIVERSIFY_SEEDS",
        "PG_FACET_COMPLETENESS",
    ):
        monkeypatch.setenv(off, "0")

    # fixed facet tree (no LLM): two facets, one baseline angle query each.
    def _fake_facets(question, llm):
        return [
            efp.Facet(name="labor economics", queries=["AI labor market economics baseline"]),
            efp.Facet(name="policy", queries=["AI workforce policy baseline"]),
        ]
    monkeypatch.setattr(efp, "plan_expert_facets", _fake_facets)

    issued: list[str] = []

    def _recording_retrieve(*, research_question=None, query=None, **kw):
        # capture whatever query text the FS loop issues, WITHOUT fetching.
        issued.append(research_question or query or "")
        return []  # empty corpus row list -> no results, no network

    def _stub_llm(prompt: str) -> str:
        return ""  # never used on the facet path for query text (angles are full queries)

    class _LRR:
        def __init__(self, *a, **k): ...

    def _factory(*a, **k):
        return _LRR()

    proj = _projection()
    gate_lanes = proj.to_amplified_queries(base_question=TASK_72_PROMPT)
    assert gate_lanes, "sanity: the projection produced no lanes"

    # NO-GATE frontier (champion): retrieval_plan=None.
    issued.clear()
    fsq.run_fs_researcher_retrieval(
        TASK_72_PROMPT, _stub_llm, _recording_retrieve, _factory,
        max_queries=50, retrieval_plan=None,
    )
    no_gate_frontier = list(issued)

    # GATE frontier: retrieval_plan=projection.
    issued.clear()
    fsq.run_fs_researcher_retrieval(
        TASK_72_PROMPT, _stub_llm, _recording_retrieve, _factory,
        max_queries=50, retrieval_plan=proj,
    )
    gate_frontier = list(issued)

    frontier_l = [q.lower() for q in gate_frontier]
    joined = " || ".join(frontier_l)

    # journal scope + English + each mandatory topic reached the ISSUED frontier
    # BEFORE any fetch (the recording stub returned [] every time).
    assert "journal" in joined, f"journal scope never reached the FS frontier: {gate_frontier}"
    for topic in ("restructuring", "employment", "skill demand"):
        assert topic in joined, f"mandatory topic {topic!r} not in FS frontier: {gate_frontier}"

    # gate lanes LEAD the frontier (they were prepended, budget raised).
    lead = frontier_l[: len(gate_lanes)]
    for gl in gate_lanes:
        assert gl.lower() in frontier_l, f"gate lane {gl!r} not issued"
    assert any(g.lower() in lead for g in gate_lanes), (
        "gate lanes should lead the issued frontier"
    )

    # the gate frontier is a strict SUPERSET of the no-gate frontier (nothing dropped).
    assert set(q.lower() for q in no_gate_frontier) <= set(frontier_l), (
        "the gate path must never DROP a champion facet query (superset invariant)"
    )
    assert len(gate_frontier) > len(no_gate_frontier), (
        "the gate path must ADD lanes, never merely re-order"
    )


# ---------------------------------------------------------------------------
# (b) The mechanized 997-guard: gate never reduces the candidate lane count.
# ---------------------------------------------------------------------------

def test_997_guard_gate_never_reduces_candidate_count():
    proj = _projection()
    gate_count = proj.candidate_query_count(base_question=TASK_72_PROMPT)

    # the no-gate candidate count at planning level: the projection is empty
    # (no contract terms, no plan intents) -> zero added lanes.
    empty = rp.from_contract_and_plan(
        contract_from_dict({}), plan_from_dict({}), original_prompt=TASK_72_PROMPT
    )
    no_gate_count = empty.candidate_query_count(base_question=TASK_72_PROMPT)

    assert gate_count >= no_gate_count, (
        f"THE 997-GUARD: gate lane count {gate_count} < no-gate {no_gate_count} — "
        f"the gate reduced candidate lanes (the banned post-fetch-filter anti-pattern)"
    )
    assert gate_count > 0
    # explicitly: the gate ADDS the routed evidence-need + every mandatory topic.
    assert gate_count >= 3 + 1, (
        "expected >= 3 mandatory-topic lanes + >= 1 routed evidence-need"
    )


# ---------------------------------------------------------------------------
# (c) OFF path: an empty / no projection yields the champion (None) routing.
# ---------------------------------------------------------------------------

def test_empty_projection_keeps_champion_none_path():
    empty = rp.from_contract_and_plan(contract_from_dict({}), plan_from_dict({}))
    assert empty.to_research_frame() is None, (
        "an empty projection must return None frame so the caller keeps the "
        "byte-identical champion research_frame=None path"
    )
    assert empty.to_amplified_queries() == []
    assert empty.to_protocol() is None


# ---------------------------------------------------------------------------
# (d) OFF path byte-identity: retrieval_plan=None issues the champion frontier.
# ---------------------------------------------------------------------------

def test_retrieval_plan_none_is_champion_frontier(monkeypatch):
    """With ``retrieval_plan=None`` (PG_GATE OFF default) the FS frontier is
    EXACTLY the champion frontier — the projection threading is fully inert."""
    from src.polaris_graph.retrieval import fs_researcher_query_gen as fsq
    from src.polaris_graph.retrieval import expert_facet_planner as efp

    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER", "1")
    for off in (
        "PG_MULTILINGUAL_RETRIEVAL", "PG_SUBENTITY_QUERY_EXPANSION",
        "PG_LANDMARK_EXPANDER", "PG_STANCE_DIVERSIFY_SEEDS", "PG_FACET_COMPLETENESS",
    ):
        monkeypatch.setenv(off, "0")
    monkeypatch.setattr(efp, "plan_expert_facets", lambda q, llm: [
        efp.Facet(name="f", queries=["baseline facet query one", "baseline facet query two"]),
    ])

    def _rec(sink):
        def _r(*, research_question=None, query=None, **kw):
            sink.append(research_question or query or "")
            return []
        return _r

    a, b = [], []

    class _LRR:
        def __init__(self, *x, **k): ...

    fsq.run_fs_researcher_retrieval(
        TASK_72_PROMPT, lambda p: "", _rec(a), lambda *x, **k: _LRR(),
        max_queries=50, retrieval_plan=None,
    )
    # a second None run must be identical (determinism).
    fsq.run_fs_researcher_retrieval(
        TASK_72_PROMPT, lambda p: "", _rec(b), lambda *x, **k: _LRR(),
        max_queries=50,  # retrieval_plan omitted -> defaults None
    )
    assert a == b and a, "retrieval_plan=None must be deterministic + non-empty"
