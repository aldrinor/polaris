"""R3 (I-deepfix-001 #1344) — multi-hop / widened corrective (CRAG) retrieval.

FAIL-LOUD behavioral tests proving the EFFECT of R3, not a flag tautology:

1. The corrective CRAG loop is WIDENED by SOURCE-YIELD SATURATION — it fires MORE
   than the legacy fixed 1 pass while each round keeps surfacing NEW sources, and
   STOPS when the yield flattens. Driven through a real mini corrective loop over
   real evidence-row dicts (source_url), the decision trajectory is the "output".
2. The still-missing-entity gap-detect emits targeted retrieval queries ONLY for
   required entities the corpus does not yet mention (the chained 2nd-order recall
   lever), anchored to the research question.

Offline / $0 / no network / no LLM.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes import crag_adequacy_loop as crag
from src.polaris_graph.retrieval import required_entity_retrieval as ren


def _rows(urls):
    """Build live-shape evidence rows keyed by source_url (the novelty identity)."""
    return [{"source_url": u, "direct_quote": f"finding at {u}"} for u in urls]


# ---------------------------------------------------------------------------
# 1. CRAG corrective loop widened by source-yield saturation
# ---------------------------------------------------------------------------

def test_loop_widens_past_legacy_single_pass_while_sources_keep_arriving(monkeypatch):
    """The R3 loop fires a 2nd corrective round (loops_done==1) when the last
    round still surfaced NEW sources — the legacy fixed cap of 1 would STOP here.

    This is the core EFFECT: chained/2nd-order recall needs more than one pass,
    and the legacy `should_loop_back` (max_loops default 1) stopped too early.
    """
    monkeypatch.delenv("PG_ADEQUACY_CRAG_MAX_LOOPS", raising=False)
    monkeypatch.delenv("PG_ADEQUACY_CRAG_YIELD_EPS", raising=False)
    monkeypatch.delenv("PG_ADEQUACY_CRAG_MAX_SATURATION_LOOPS", raising=False)

    prev = _rows(["a", "b"])
    # A high-yield 2nd round: 3 of 3 rows are brand-new URLs (novelty 1.0).
    last = _rows(["c", "d", "e"])

    # Legacy fixed-count bound STOPS at loops_done==1 (default max_loops==1).
    assert crag.should_loop_back(sufficient=False, loops_done=1) is False

    # R3 saturation bound KEEPS GOING — the corpus is still growing.
    assert (
        crag.should_loop_back_saturating(
            sufficient=False,
            loops_done=1,
            prev_corpus_rows=prev,
            last_round_rows=last,
        )
        is True
    ), "R3 must widen the loop past the legacy single pass while sources keep arriving"


def test_loop_stops_when_source_yield_saturates(monkeypatch):
    """When a corrective round re-fetches mostly-seen sources (yield < eps), the
    loop STOPS — a saturation stop, not a fixed count and not a breadth target."""
    monkeypatch.setenv("PG_ADEQUACY_CRAG_YIELD_EPS", "0.10")
    prev = _rows(["a", "b", "c", "d", "e"])
    # 5 rows, all already in the corpus -> novelty 0.0 < eps -> saturated.
    last = _rows(["a", "b", "c", "d", "e"])

    assert crag.corrective_yield_saturated(
        prev_corpus_rows=prev, last_round_rows=last
    ) is True

    assert (
        crag.should_loop_back_saturating(
            sufficient=False,
            loops_done=2,
            prev_corpus_rows=prev,
            last_round_rows=last,
        )
        is False
    ), "a saturated yield must stop the corrective loop"


def test_first_corrective_round_is_guaranteed_on_insufficient(monkeypatch):
    """Corrective-RAG guarantees the first corrective round on an insufficient
    corpus even with no yield history yet (loops_done==0)."""
    assert (
        crag.should_loop_back_saturating(
            sufficient=False,
            loops_done=0,
            prev_corpus_rows=[],
            last_round_rows=[],
        )
        is True
    )


def test_sufficient_verdict_never_loops(monkeypatch):
    assert (
        crag.should_loop_back_saturating(
            sufficient=True,
            loops_done=0,
            prev_corpus_rows=_rows(["a"]),
            last_round_rows=_rows(["b", "c"]),
        )
        is False
    )


def test_outer_compute_bound_terminates_even_when_still_yielding(monkeypatch):
    """The outer compute-safety bound guarantees termination even if the grader
    keeps saying insufficient while a trickle of new sources keeps arriving."""
    monkeypatch.setenv("PG_ADEQUACY_CRAG_MAX_SATURATION_LOOPS", "3")
    prev = _rows(["a"])
    last = _rows(["x", "y", "z"])  # high yield, but the cap is reached
    assert (
        crag.should_loop_back_saturating(
            sufficient=False,
            loops_done=3,
            prev_corpus_rows=prev,
            last_round_rows=last,
        )
        is False
    )


def test_full_corrective_trajectory_widens_then_saturates(monkeypatch):
    """Drive a real mini corrective loop end-to-end: rounds keep yielding new
    sources (loop widens well past 1), then a round saturates and the loop stops.
    The number of rounds fired is the observable OUTPUT."""
    monkeypatch.delenv("PG_ADEQUACY_CRAG_MAX_LOOPS", raising=False)
    monkeypatch.setenv("PG_ADEQUACY_CRAG_YIELD_EPS", "0.10")
    monkeypatch.setenv("PG_ADEQUACY_CRAG_MAX_SATURATION_LOOPS", "10")

    # Scripted per-round retrieved rows: 3 growing rounds, then a saturated round.
    scripted = [
        _rows(["c1", "c2", "c3"]),        # round 1: all new
        _rows(["c4", "c5"]),              # round 2: all new
        _rows(["c6", "c7", "c8"]),        # round 3: all new
        _rows(["c1", "c2", "c6", "c7"]),  # round 4: all already seen -> saturated
    ]
    corpus = _rows(["a", "b"])
    loops_done = 0
    sufficient = False  # grader never satisfied — only saturation/compute can stop
    fired = 0
    prev_rows: list = []
    last_rows: list = []

    while crag.should_loop_back_saturating(
        sufficient=sufficient,
        loops_done=loops_done,
        prev_corpus_rows=prev_rows,
        last_round_rows=last_rows,
    ):
        if fired >= len(scripted):
            pytest.fail("loop fired more rounds than scripted — unbounded widening")
        prev_rows = list(corpus)
        last_rows = scripted[fired]
        corpus.extend(last_rows)
        fired += 1
        loops_done += 1

    # It must widen past the legacy single pass (>1) and stop on the saturated round.
    assert fired == 4, f"expected 4 corrective rounds (3 growth + 1 saturating), got {fired}"
    assert fired > 1, "R3 must widen the corrective loop past the legacy fixed 1 pass"


# ---------------------------------------------------------------------------
# 2. Still-missing-entity gap-detect (field-agnostic)
# ---------------------------------------------------------------------------

def test_missing_entity_gap_queries_target_only_uncovered_entities():
    """Emit ONE research-question-anchored query per required entity the corpus
    does not mention; covered entities produce no query."""
    required = ["Acemoglu", "Eloundou", "Brynjolfsson", "Autor"]
    corpus_texts = [
        "Daron Acemoglu and Pascual Restrepo model task automation.",
        "David Autor studies labor market polarization.",
    ]
    question = "How does AI automation affect the labor market?"

    queries = ren.missing_entity_gap_queries(
        required_entities=required,
        corpus_texts=corpus_texts,
        research_question=question,
    )

    # Acemoglu + Autor are present -> no query; Eloundou + Brynjolfsson missing.
    joined = " || ".join(queries).lower()
    assert "eloundou" in joined
    assert "brynjolfsson" in joined
    assert "acemoglu" not in joined, "covered entity must not get a corrective query"
    assert "autor" not in joined, "covered entity must not get a corrective query"
    assert len(queries) == 2

    # Each query is anchored to the research question (keeps it on-subject).
    for q in queries:
        assert question.lower() in q.lower(), f"gap query not scope-anchored: {q!r}"


def test_missing_entity_gap_queries_empty_when_all_covered():
    required = ["Acemoglu", "Autor"]
    corpus_texts = ["Acemoglu and Autor both appear in the corpus."]
    assert (
        ren.missing_entity_gap_queries(
            required_entities=required,
            corpus_texts=corpus_texts,
            research_question="labor market AI",
        )
        == []
    )


def test_missing_entity_gap_queries_bounded(monkeypatch):
    monkeypatch.setenv("PG_MISSING_ENTITY_GAP_MAX_QUERIES", "2")
    required = [f"entity_{i}" for i in range(10)]
    queries = ren.missing_entity_gap_queries(
        required_entities=required,
        corpus_texts=[],  # nothing covered -> all missing
        research_question="topic",
    )
    assert len(queries) == 2, "compute-safety cap must bound the emitted gap queries"
