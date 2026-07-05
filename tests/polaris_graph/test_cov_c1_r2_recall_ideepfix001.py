"""I-deepfix-001 cov C1 (RECALL) — R2 facet-completeness genuinely widens the effective query frontier.

Proves the EFFECT the DRB-II recall lever must deliver and that the parent audit flagged as UNPROVEN:

  * GREEN — on a multi-facet task the facet planner + R2 completeness loop drive the EFFECTIVE query
    count WELL ABOVE the measured ~15-query baseline (the drb_72 starvation: manifest
    effective_query_count=15 for a ~53-facet task), AND the R2 expansion loop runs >0 rounds AND
    issues real expansion queries for the UNCOVERED facets from each facet's RESERVE angles.

  * RED — the exact pre-fix vacuous no-op: when every facet angle is already registered as a seed
    (the bug the seed/reserve split fixed) OR the facet state is a vacuous "0 of 0" (no measurable
    facet subject), the R2 loop issues ZERO expansion queries. The loop fires on a genuine gap only,
    never as a tautology.

§-1.3 WIDEN-ONLY: every assertion is on ADDED on-topic queries; the loop drops ZERO sources and
touches no faithfulness gate. OFFLINE — pure control flow over injected llm + retrieve stubs; no
network, no key, no GPU.
"""
from __future__ import annotations

from src.polaris_graph.retrieval import fs_researcher_query_gen as fsr
from src.polaris_graph.retrieval import facet_completeness as fc
from src.polaris_graph.retrieval.expert_facet_planner import Facet

# The measured drb_72 baseline the widened frontier must beat (manifest effective_query_count=15).
_STARVED_BASELINE = 15

# A realistic multi-facet task: 12 distinct expert facets (the compute-safety cap default), each with
# content-word subject tokens so coverage is genuinely measurable.
_FACET_TREE = "\n".join([
    "manufacturing automation displacement",
    "worker reskilling programs",
    "wage polarization dynamics",
    "gig platform labor",
    "occupational task restructuring",
    "regional employment divergence",
    "productivity growth diffusion",
    "collective bargaining response",
    "algorithmic management surveillance",
    "small business adoption barriers",
    "public retraining policy",
    "generative model capability frontier",
])


def _llm(prompt: str) -> str:
    if "expert research planner" in prompt:
        return _FACET_TREE + "\n"
    return "NONE\n"


def _uncovering_retrieve_factory():
    """A retrieve stub that returns a NEW distinct source every call whose text mentions NONE of the
    facet subjects — so every facet stays UNCOVERED and the R2 loop keeps firing reserve angles until
    the facet frontier is exhausted (maximally exercises expansion). Records the issued queries."""
    fetched: list = []

    def retrieve(research_question, **kw):
        fetched.append(research_question)

        class _R:
            evidence_rows = [{
                "source_url": f"https://src/{len(fetched)}",
                "statement": "generic macro commentary with no facet subject terms",
            }]
        return _R()

    return retrieve, fetched


# ── GREEN: effective query count rises well above the ~15 baseline + R2 rounds > 0 ────────────────

def test_c1_green_effective_query_count_rises_and_r2_expansion_fires(monkeypatch):
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "1")
    monkeypatch.setenv("PG_FACET_COMPLETENESS", "1")
    monkeypatch.setenv("PG_EXPERT_FACET_MAX_FACETS", "12")
    monkeypatch.setenv("PG_EXPERT_FACET_ANGLES", "5")       # 5 angles/facet
    monkeypatch.setenv("PG_EXPERT_FACET_SEED_ANGLES", "2")  # seed 2 -> 3 reserve angles/facet
    monkeypatch.setenv("PG_QGEN_FS_RESEARCHER_MAX_QUERIES", "200")  # do not budget-cap the proof
    monkeypatch.setenv("PG_SUBENTITY_QUERY_EXPANSION", "0")  # isolate C1/R2 from the sub-entity lever
    monkeypatch.setenv("PG_MULTILINGUAL_RETRIEVAL", "0")     # isolate from R5

    # Spy on the R2 loop to read rounds_run + expansion_queries on the WIRED path.
    captured: dict = {}
    real_expand = fc.run_facet_expansion

    def _spy(*a, **k):
        r = real_expand(*a, **k)
        captured["result"] = r
        return r

    monkeypatch.setattr(fc, "run_facet_expansion", _spy)

    retrieve, fetched = _uncovering_retrieve_factory()
    queries, results = fsr.plan_fs_researcher_queries(
        "AI and the labor market across sectors", _llm, retrieve,
    )

    # 1) EFFECTIVE query count rises WELL ABOVE the starved ~15 baseline (12 facets x 2 seed angles =
    #    24 breadth-first seeds alone already clears it; reserve-angle expansion adds more).
    assert len(queries) > _STARVED_BASELINE, (
        f"effective query count {len(queries)} must exceed the ~15 starved baseline"
    )
    assert len(queries) >= 30, (
        f"a 12-facet task must issue a wide frontier (seeds + reserve expansion); got {len(queries)}"
    )

    # 2) The R2 completeness loop was REACHED and ran > 0 rounds (not the vacuous skip).
    assert "result" in captured, "R2 expansion loop was never reached on the wired path"
    exp = captured["result"]
    assert exp.rounds_run > 0, "R2 expansion rounds must be > 0"

    # 3) The loop issued REAL expansion queries for the uncovered facets (from the reserve angles),
    #    and each reached the issued frontier.
    assert exp.expansion_queries, "R2 must issue expansion queries for the uncovered facets"
    for q in exp.expansion_queries:
        assert q in queries, "an expansion query must reach the issued frontier"

    # 4) Faithfulness-neutral: one retrieval per issued query, nothing dropped.
    assert len(results) == len(queries) == len(fetched)


# ── RED: pre-fix vacuous no-op — all angles pre-seeded => frontier exhausted => zero expansion ─────

def test_c1_red_all_angles_preseeded_yields_zero_expansion():
    """The EXACT pre-fix bug: when every facet angle is already registered as a seed (no reserve),
    ``run_facet_expansion`` — which draws from the SAME ``facet.queries`` — reads the frontier as
    exhausted and issues ZERO expansion queries. The seed/reserve split is what creates the gap."""
    facets = [
        Facet(name="worker reskilling programs", queries=[
            "worker reskilling programs mechanism ai labor",
            "worker reskilling programs stakeholders ai labor",
        ]),
        Facet(name="manufacturing automation displacement", queries=[
            "manufacturing automation displacement mechanism ai labor",
            "manufacturing automation displacement counter-evidence ai labor",
        ]),
    ]
    seed = [{"source_url": "https://s/0", "statement": "generic filler with no facet subject"}]
    all_angles = {q.lower() for f in facets for q in f.queries}

    def retrieve(research_question, **kw):
        raise AssertionError("no expansion query must be issued when the frontier is pre-exhausted")

    result = fc.run_facet_expansion(facets, seed, retrieve, already_issued=all_angles, max_rounds=5)
    assert result.expansion_queries == [], "pre-seeded frontier => ZERO expansion (the vacuous no-op)"
    assert result.stop_reason == "frontier_exhausted"


def test_c1_red_zero_of_zero_facets_is_a_noop():
    """The vacuous clinical-only "0 of 0 covered" state: facets carrying no measurable subject token
    are treated as covered, so there is nothing to expand and the loop fires ZERO queries."""
    facets = [
        Facet(name="the a of to in on", queries=["q1", "q2"]),   # pure stopwords -> no subject token
        Facet(name="over under about across", queries=["q3", "q4"]),
    ]
    seed = [{"source_url": "https://s/0", "statement": "anything"}]

    def retrieve(research_question, **kw):
        raise AssertionError("a 0-of-0 vacuous facet state must issue no expansion query")

    result = fc.run_facet_expansion(facets, seed, retrieve, max_rounds=5)
    assert result.expansion_queries == []
    assert result.stop_reason == "all_covered"


# ── GREEN contrast: the seed/reserve split turns the vacuous no-op into real expansion ─────────────

def test_c1_green_reserve_split_creates_the_expansion_gap():
    """Same facet, but only the seed angle is pre-issued (the seed/reserve split): the UNCOVERED facet
    now has RESERVE angles left, so R2 fires real expansion queries (contrast with the RED no-op)."""
    facet = Facet(name="worker reskilling programs", queries=[
        "worker reskilling programs mechanism ai labor",       # seed angle (pre-issued)
        "worker reskilling programs stakeholders ai labor",    # reserve angle
        "worker reskilling programs counter-evidence ai labor",  # reserve angle
    ])
    seed = [{"source_url": "https://s/0", "statement": "generic filler with no facet subject"}]
    seeded = {facet.queries[0].lower()}  # only the seed angle registered

    issued: list = []

    def retrieve(research_question, **kw):
        issued.append(research_question)

        class _R:
            evidence_rows = [{
                "source_url": f"https://exp/{len(issued)}",
                "statement": "still generic, does not cover the reskilling facet subject",
            }]
        return _R()

    result = fc.run_facet_expansion([facet], seed, retrieve,
                                    already_issued=seeded, max_rounds=5)
    assert result.expansion_queries, "reserve angles must fire expansion for the uncovered facet"
    assert all("reskilling" in q for q in result.expansion_queries)
    assert result.rounds_run > 0
    # every reserve angle issued exactly once (dedup against the seed) — zero dropped.
    assert len(result.results) == len(result.expansion_queries) == len(issued)
