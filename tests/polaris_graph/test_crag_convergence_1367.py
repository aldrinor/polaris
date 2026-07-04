"""I-deepfix-001 #1367 — retrieval-convergence fix for the CRAG corrective loop.

THE DEFECT (found live on drb_72, diagnosed by Codex+Fable from the loop code):
the corrective query generator ran dry and echoed near-verbatim question fragments
(e.g. "researching impact generative future labor market please help").
`openalex_search` (/works?search=<q>) returns ~nothing on those malformed long
queries, so the corrective rounds fetched almost nothing, the CRAG adequacy grader
could never reach CORRECT, and the loop burned its full budget every adequacy cycle
(non-convergence, blowing past the retrieval wall and padding the corpus with
degraded-query junk).

THE FIX (2-part, §-1.3 weight-and-consolidate — never a drop / cap / thinner):

  (a) QUERY GENERATOR (`derive_gap_queries` + `sanitize_query` / `normalize_query_key`):
      strip search-noise boilerplate ("please help", "researching" …), CAP query
      length so openalex accepts it, and add a novelty/dedup guard (`already_tried`)
      so a corrective round never re-emits a near-duplicate / already-tried query.
      A round emits genuinely NEW useful sub-queries or NOTHING (which trips
      yield-saturation) — it never regurgitates the raw question.

  (b) CRAG ARBITRATION (`crag_loop_arbitration`): when a corrective round stopped
      surfacing NEW sources (yield saturated) OR the outer compute bound is hit and
      the count-floor already says PROCEED, ACCEPT-with-disclosed-gap (proceed to
      composition, disclosing the residual gap) instead of grading the corpus
      INCORRECT and spinning another empty corrective round.

These are OFFLINE unit tests over the PURE decision / query-derivation helpers — no
network, no LLM, no GPU, no run-script import. FAITHFULNESS is untouched: these are
retrieval query-hygiene + STOP-decision helpers; they feed the UNCHANGED tier
classifier + strict_verify / NLI / 4-role / provenance engine, never a source drop.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.nodes import crag_adequacy_loop as crag


def _rows(urls):
    """Live-shape evidence rows keyed by source_url (the novelty identity)."""
    return [{"source_url": u, "direct_quote": f"finding at {u}"} for u in urls]


# ─────────────────────────────────────────────────────────────────────────────
# (a) QUERY GENERATOR — sanitize / normalize / dedup / length-cap
# ─────────────────────────────────────────────────────────────────────────────

def test_sanitize_query_strips_boilerplate() -> None:
    """Conversational / imperative filler is search NOISE for a keyword backend —
    strip it. Subject terms are byte-preserved."""
    out = crag.sanitize_query(
        "researching the impact of generative AI on the labor market please help"
    )
    low = out.lower()
    assert "please help" not in low
    assert not low.startswith("researching")
    # Subject terms survive.
    for term in ("impact", "generative", "labor", "market"):
        assert term in low


def test_sanitize_query_does_not_strip_inside_words() -> None:
    """Boilerplate is stripped only as whole tokens — a subject word that CONTAINS a
    filler substring is preserved (no over-stripping)."""
    out = crag.sanitize_query("self-help seeking behavior in adolescents")
    assert "self-help" in out.lower(), "must not strip 'help' inside 'self-help'"


def test_sanitize_query_caps_word_count(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_ADEQUACY_CRAG_QUERY_MAX_WORDS", "10")
    long_q = " ".join(f"w{i}" for i in range(40))
    out = crag.sanitize_query(long_q)
    assert len(out.split()) == 10, "an over-long query must be capped to the word cap"


def test_query_max_words_env_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_ADEQUACY_CRAG_QUERY_MAX_WORDS", raising=False)
    assert crag._query_max_words() == crag._DEFAULT_QUERY_MAX_WORDS
    monkeypatch.setenv("PG_ADEQUACY_CRAG_QUERY_MAX_WORDS", "not-a-number")
    assert crag._query_max_words() == crag._DEFAULT_QUERY_MAX_WORDS
    monkeypatch.setenv("PG_ADEQUACY_CRAG_QUERY_MAX_WORDS", "7")
    assert crag._query_max_words() == 7


def test_normalize_query_key_is_case_and_punct_insensitive() -> None:
    assert crag.normalize_query_key("  How does AI?  ") == "how does ai"
    assert crag.normalize_query_key('"generative AI, labor."') == "generative ai, labor"
    a = crag.normalize_query_key("Wage Effects Of Automation")
    b = crag.normalize_query_key("wage effects of automation")
    assert a == b


def test_corrective_round_does_not_reemit_already_tried_queries() -> None:
    """(a) THE core assertion: a corrective round given the SAME exhausted context
    (its own prior queries marked tried) emits a DEDUPED / empty set — it does NOT
    re-emit an already-tried query."""
    q = "How does generative AI affect the future labor market?"
    gaps = ["automation exposure by occupation", "wage inequality effects"]

    r1 = crag.derive_gap_queries(
        research_question=q, findings=[], gap_dimensions=gaps
    )
    assert r1, "round 1 must derive some gap queries"

    # Round 2: same gap context, but round-1's queries (+ the raw question) are tried.
    tried = {crag.normalize_query_key(x) for x in r1}
    tried.add(crag.normalize_query_key(q))
    r2 = crag.derive_gap_queries(
        research_question=q, findings=[], gap_dimensions=gaps, already_tried=tried
    )
    assert r2 == [], (
        "a corrective round given the same exhausted context must not re-emit "
        "already-tried queries — it emits an empty set (trips yield-saturation)"
    )


def test_gap_query_strips_boilerplate_and_caps_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """(a) A regurgitated, boilerplate-laden, over-long question is turned into a
    clean, capped query openalex_search can accept — never sent verbatim."""
    monkeypatch.setenv("PG_ADEQUACY_CRAG_QUERY_MAX_WORDS", "12")
    q = (
        "researching the impact of generative AI on the future labor market please help "
        + " ".join(f"tok{i}" for i in range(40))
    )
    out = crag.derive_gap_queries(
        research_question=q, findings=[], gap_dimensions=["automation exposure"]
    )
    assert out, "a gap dimension must still yield a (cleaned) query"
    for query in out:
        low = query.lower()
        assert "please help" not in low, "boilerplate must be stripped"
        assert not low.startswith("researching"), "leading filler must be stripped"
        assert len(query.split()) <= 12, "the query must be length-capped for openalex"


def test_seeding_raw_question_does_not_block_gap_queries() -> None:
    """Seeding the raw question into `already_tried` (so it can't be regurgitated)
    must NOT block a legitimate stem+phrase gap query — it is novel vs the bare
    question."""
    q = "How does generative AI affect the labor market?"
    tried = {crag.normalize_query_key(q)}
    out = crag.derive_gap_queries(
        research_question=q, findings=[], gap_dimensions=["wage effects"],
        already_tried=tried,
    )
    assert out, "a stem+phrase gap query is novel vs the bare question and must emit"
    qk = crag.normalize_query_key(q)
    assert all(crag.normalize_query_key(x) != qk for x in out), (
        "no emitted query may equal the raw question (no regurgitation)"
    )


# ─────────────────────────────────────────────────────────────────────────────
# (b) CRAG ARBITRATION — accept-with-disclosed-gap vs loop-back
# ─────────────────────────────────────────────────────────────────────────────

def test_arbitration_accept_disclosed_gap_when_proceed_and_saturated() -> None:
    """(b) THE core assertion: count-floor=PROCEED + yield-saturated (a corrective
    round surfaced no new sources) => ACCEPT-with-disclosed-gap, NOT another loop."""
    prev = _rows(["a", "b", "c"])
    last = _rows(["a"])  # all already in the corpus -> saturated
    assert (
        crag.crag_loop_arbitration(
            sufficient=False,
            count_floor_proceed=True,
            loops_done=1,
            prev_corpus_rows=prev,
            last_round_rows=last,
        )
        == crag.ARBITRATION_ACCEPT_DISCLOSED_GAP
    )


def test_arbitration_empty_round_is_accept_disclosed_gap() -> None:
    """A corrective round that fetched NOTHING (empty) is saturated by definition =>
    accept-with-disclosed-gap when the count-floor says proceed."""
    assert (
        crag.crag_loop_arbitration(
            sufficient=False,
            count_floor_proceed=True,
            loops_done=1,
            prev_corpus_rows=_rows(["a", "b"]),
            last_round_rows=[],
        )
        == crag.ARBITRATION_ACCEPT_DISCLOSED_GAP
    )


def test_arbitration_below_floor_label_when_not_proceed() -> None:
    """Saturated but the count-floor did NOT clear => still ACCEPT (adequacy is never
    a hard abort — the faithfulness engine is the only hard gate), but the stronger
    below-floor disclosure label."""
    assert (
        crag.crag_loop_arbitration(
            sufficient=False,
            count_floor_proceed=False,
            loops_done=1,
            prev_corpus_rows=_rows(["a"]),
            last_round_rows=[],
        )
        == crag.ARBITRATION_ACCEPT_SATURATED_BELOW_FLOOR
    )
    # Both disclosed-gap variants are grouped for the run-script's disclosure path.
    assert (
        crag.ARBITRATION_ACCEPT_SATURATED_BELOW_FLOOR
        in crag.ARBITRATION_ACCEPT_DISCLOSED_GAP_REASONS
    )
    assert (
        crag.ARBITRATION_ACCEPT_DISCLOSED_GAP
        in crag.ARBITRATION_ACCEPT_DISCLOSED_GAP_REASONS
    )


def test_arbitration_loops_back_while_yielding_new_sources() -> None:
    """A corrective round that surfaced NEW sources and is under the compute bound =>
    keep going (the widening the R3 saturation loop models)."""
    assert (
        crag.crag_loop_arbitration(
            sufficient=False,
            count_floor_proceed=True,
            loops_done=1,
            prev_corpus_rows=_rows(["a"]),
            last_round_rows=_rows(["x", "y"]),  # novel -> not saturated
        )
        == crag.ARBITRATION_LOOP_BACK
    )


def test_arbitration_guarantees_first_corrective_round() -> None:
    """Corrective-RAG guarantees the FIRST corrective round on an insufficient corpus
    (no yield history yet)."""
    assert (
        crag.crag_loop_arbitration(
            sufficient=False,
            count_floor_proceed=True,
            loops_done=0,
            prev_corpus_rows=[],
            last_round_rows=[],
        )
        == crag.ARBITRATION_LOOP_BACK
    )


def test_arbitration_sufficient_accepts_immediately() -> None:
    assert (
        crag.crag_loop_arbitration(
            sufficient=True,
            count_floor_proceed=False,
            loops_done=0,
            prev_corpus_rows=[],
            last_round_rows=[],
        )
        == crag.ARBITRATION_ACCEPT_SUFFICIENT
    )


def test_arbitration_outer_compute_bound_terminates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even if every round keeps yielding a trickle of new sources, the outer
    compute-safety bound terminates the loop (accept-with-disclosed-gap)."""
    monkeypatch.setenv("PG_ADEQUACY_CRAG_MAX_SATURATION_LOOPS", "3")
    assert (
        crag.crag_loop_arbitration(
            sufficient=False,
            count_floor_proceed=True,
            loops_done=3,
            prev_corpus_rows=_rows(["a"]),
            last_round_rows=_rows(["x", "y", "z"]),  # high yield, but cap reached
        )
        == crag.ARBITRATION_ACCEPT_DISCLOSED_GAP
    )


# ─────────────────────────────────────────────────────────────────────────────
# Behavioral: the non-convergence is bounded (the drb_72 defect, reproduced + fixed)
# ─────────────────────────────────────────────────────────────────────────────

def _drive_loop(*, scripted_rows, count_floor_proceed, max_loops=3):
    """Drive the run-script corrective-loop shape over PURE helpers.

    Mirrors the run-script:
        while should_loop_back(sufficient, loops_done):   # outer max_loops ceiling
            arb = crag_loop_arbitration(...)              # #1367 early saturation stop
            if arb != loop_back: stop; break
            <fire one corrective round: scripted_rows[fired]>
    Returns (rounds_fired, stop_reason).
    """
    corpus = _rows(["init0", "init1", "init2"])
    loops_done = 0
    sufficient = False  # the grader is never satisfied (worst case)
    prev_rows: list = []
    last_rows: list = []
    fired = 0
    stop_reason = None
    while (not sufficient) and loops_done < max_loops:  # should_loop_back ceiling
        arb = crag.crag_loop_arbitration(
            sufficient=sufficient,
            count_floor_proceed=count_floor_proceed,
            loops_done=loops_done,
            prev_corpus_rows=prev_rows,
            last_round_rows=last_rows,
        )
        if arb != crag.ARBITRATION_LOOP_BACK:
            stop_reason = arb
            break
        if fired >= len(scripted_rows):
            pytest.fail("loop fired more rounds than scripted — unbounded")
        prev_rows = list(corpus)          # snapshot BEFORE merge (correct novelty base)
        last_rows = scripted_rows[fired]  # rows THIS round fetched
        corpus.extend(last_rows)
        fired += 1
        loops_done += 1
    return fired, stop_reason


def test_non_convergence_is_bounded_to_one_futile_round() -> None:
    """THE drb_72 shape: corrective rounds fetch NOTHING new (malformed queries) and
    the grader never reaches CORRECT. The fix fires the ONE guaranteed round then
    ACCEPTs-with-disclosed-gap — it does NOT burn the whole budget."""
    fired, stop = _drive_loop(
        scripted_rows=[[], [], []],  # every round fetches nothing new
        count_floor_proceed=True,
    )
    assert fired == 1, (
        "malformed corrective rounds must converge after ONE guaranteed round, "
        f"got {fired}"
    )
    assert stop == crag.ARBITRATION_ACCEPT_DISCLOSED_GAP


def test_productive_rounds_still_widen_within_the_outer_bound() -> None:
    """When rounds ARE productive (each surfaces new sources), the loop widens past
    the legacy single pass — up to the outer max_loops ceiling — proving the fix did
    NOT collapse the corrective loop to one round."""
    scripted = [
        _rows(["c1", "c2", "c3"]),  # round 1: all new
        _rows(["c4", "c5"]),        # round 2: all new
        _rows(["c6", "c7"]),        # round 3: all new
    ]
    fired, _ = _drive_loop(scripted_rows=scripted, count_floor_proceed=True, max_loops=3)
    assert fired == 3, f"productive rounds must widen to the outer bound, got {fired}"
    assert fired > 1, "the fix must not collapse widening to a single pass"
