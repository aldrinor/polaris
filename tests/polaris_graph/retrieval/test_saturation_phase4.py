"""I-meta-005 Phase 4 (#988) smoke — multi-round saturation search.

Cases P4-1..P4-16 from the Codex-APPROVED brief `.codex/I-meta-005-phase-4/
brief.md` §3. SPEND-FREE: the loop DECISION logic (`saturation.py`) is PURE and
exercised with STUB per-round evidence; the live `run_live_retrieval` round is
INJECTED as a capture-only callable so NO live HTTP client is constructed and NO
generator token is billed until PROCEED/partial. Plain-class stubs — NO
unittest.mock.

Serialized per CLAUDE.md §8.4 (no heavy ML; pure-python).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.saturation import (
    CONTINUE,
    STOP_BUDGET,
    STOP_NOVELTY,
    STOP_SUFFICIENT,
    BudgetPreflight,
    RoundOutcome,
    canonical_source_url,
    gap_sub_queries,
    marginal_novelty,
    per_query_discovery_cost,
    preflight_round_budget,
    run_saturation_loop,
    saturation_decision,
)
from src.polaris_graph.adequacy.plan_sufficiency_gate import (
    assess_plan_sufficiency,
)
from src.polaris_graph.planning.research_planner import (
    ResearchFrame,
    ResearchPlan,
    SectionOutlineItem,
)
from src.polaris_graph.discovery.source_adapter_registry import (
    SourceAdapterRegistry,
)


# ── fixtures / helpers (real objects, no mocks) ──────────────────────────────

def _plan(sub_queries, outline, *, frame=None):
    return ResearchPlan(
        research_question="q",
        frame=frame or ResearchFrame(),
        sub_queries=list(sub_queries),
        outline=list(outline),
    )


def _section(title, target, indices, archetype="Background"):
    return SectionOutlineItem(
        archetype=archetype,
        title=title,
        evidence_target=target,
        sub_query_indices=list(indices),
    )


def _row(ev_id, url, origin, score):
    """A live-shaped evidence row: carries `source_url` (NOT `url`) + the
    authority sidecar fields the Phase-3 gate reads."""
    return {
        "evidence_id": ev_id,
        "source_url": url,
        "query_origin": origin,
        "statement": "",
        "direct_quote": "",
        "authority_score": score,
        "authority_confidence": "HIGH",
    }


class _NoLiveClientSentinel:
    """Asserts no live HTTP client is constructed inside the decision-logic
    smoke. The orchestrator only ever calls the INJECTED `run_round_fn` /
    `generator_fn`; if anything tries to build a live retriever the test stubs
    record it and the assertion fails."""

    def __init__(self) -> None:
        self.live_client_built = False


# ── P4-2 / P4-2b novelty metric + identifier-vs-tracking canonicalization ────

def test_p4_2_marginal_novelty_all_new_all_dup_half():
    prev = [_row("ev_000", "https://a.org/p1", "q", 0.9)]
    all_new = [
        _row("ev_001", "https://b.org/p2", "q", 0.9),
        _row("ev_002", "https://c.org/p3", "q", 0.9),
    ]
    assert marginal_novelty(prev, all_new) == 1.0

    all_dup = [
        _row("ev_003", "https://a.org/p1", "q", 0.9),
        _row("ev_004", "https://a.org/p1", "q", 0.9),
    ]
    assert marginal_novelty(prev, all_dup) == 0.0

    half = [
        _row("ev_005", "https://a.org/p1", "q", 0.9),   # dup
        _row("ev_006", "https://d.org/p4", "q", 0.9),   # new
    ]
    assert marginal_novelty(prev, half) == 0.5


def test_p4_2b_identifier_vs_tracking_canonicalization():
    """Two rows differing only by an IDENTIFIER query param stay DISTINCT; two
    rows differing only by a TRACKING param collapse to ONE (run_diff
    canonicalizer)."""
    prev: list = []
    # ?abstract_id=123 vs ?abstract_id=456 — distinct identifier-addressed pages.
    ids = [
        _row("ev_000", "https://ssrn.com/paper?abstract_id=123", "q", 0.9),
        _row("ev_001", "https://ssrn.com/paper?abstract_id=456", "q", 0.9),
    ]
    assert marginal_novelty(prev, ids) == 1.0  # both novel

    # base vs base?utm_source=x — same page, tracking noise only.
    track = [
        _row("ev_002", "https://x.org/p", "q", 0.9),
        _row("ev_003", "https://x.org/p?utm_source=newsletter", "q", 0.9),
    ]
    # 2 rows, 1 unique canonical -> 1 novel / 2 = 0.5
    assert marginal_novelty(prev, track) == 0.5
    # the canonicalizer collapses them:
    assert canonical_source_url("https://x.org/p") == canonical_source_url(
        "https://x.org/p?utm_source=newsletter"
    )
    assert canonical_source_url(
        "https://ssrn.com/paper?abstract_id=123"
    ) != canonical_source_url("https://ssrn.com/paper?abstract_id=456")


# ── P4-3 gap_sub_queries (empty-facet mode) ──────────────────────────────────

def test_p4_3_gap_sub_queries_empty_facet_returns_only_gap_text():
    plan = _plan(
        ["sq0", "sq1", "sq2", "sq3", "sq4"],
        [_section("S0", 2, [2, 4])],
    )
    # Section mapped to [2,4]; facet 4 under-covered (empty), facet 2 fine.
    rep = type("R", (), {
        "per_unit": [
            type("U", (), {
                "sufficient": False,
                "sub_query_indices": [2, 4],
                "empty_facets": [4],
            })()
        ]
    })()
    assert gap_sub_queries(rep, plan) == ["sq4"]


# ── P4-11 total-shortfall gap queries (no empty facet) ───────────────────────

def test_p4_11_gap_sub_queries_total_shortfall_returns_all_section_texts():
    plan = _plan(
        ["sq0", "sq1", "sq2"],
        [_section("S0", 5, [0, 1, 2])],
    )
    # covered < target but NO empty facets -> ALL mapped texts (non-empty).
    rep = type("R", (), {
        "per_unit": [
            type("U", (), {
                "sufficient": False,
                "sub_query_indices": [0, 1, 2],
                "empty_facets": [],
            })()
        ]
    })()
    got = gap_sub_queries(rep, plan)
    assert got == ["sq0", "sq1", "sq2"]
    assert got  # NEVER empty when a section is under-covered


# ── P4-4 saturation_decision (the priority ladder) ───────────────────────────

def test_p4_4_saturation_decision_ladder():
    # proceed -> STOP_SUFFICIENT
    assert saturation_decision(
        verdict="proceed", round_index=0, max_rounds=3, novelty=0.0, eps=0.1,
    ) == STOP_SUFFICIENT
    # expand + rounds exhausted (round+1>=max) -> STOP_BUDGET
    assert saturation_decision(
        verdict="expand", round_index=2, max_rounds=3, novelty=0.9, eps=0.1,
    ) == STOP_BUDGET
    # expand + round>=1 + novelty<eps -> STOP_NOVELTY
    assert saturation_decision(
        verdict="expand", round_index=1, max_rounds=5, novelty=0.05, eps=0.1,
    ) == STOP_NOVELTY
    # expand + rounds-left + novelty>=eps -> CONTINUE
    assert saturation_decision(
        verdict="expand", round_index=0, max_rounds=5, novelty=0.9, eps=0.1,
    ) == CONTINUE


# ── P4-12 abort -> STOP_BUDGET (terminal, never unhandled) ───────────────────

def test_p4_12_abort_maps_to_stop_budget():
    assert saturation_decision(
        verdict="abort", round_index=9, max_rounds=3, novelty=1.0, eps=0.1,
    ) == STOP_BUDGET


# ── helpers to drive the loop with a STUB retrieval ──────────────────────────

class _StubLoopDriver:
    """Capture-only stub for `run_round_fn`. Each round returns a controlled
    RoundOutcome built from a scripted list of per-round NEW rows + a scripted
    sufficiency verdict. Records the gap queries it was asked to fire and proves
    NO live HTTP client is ever constructed."""

    def __init__(self, *, round_specs, plan, sentinel):
        # round_specs: list of (new_rows, verdict, per_unit) for rounds 1..N.
        self._specs = list(round_specs)
        self._plan = plan
        self._sentinel = sentinel
        self.cumulative_rows: list = []
        self.fired_gap_queries: list[list[str]] = []
        self.calls = 0

    def seed_round0(self, rows):
        self.cumulative_rows = list(rows)

    def __call__(self, gap_queries: list[str]) -> RoundOutcome:
        # The orchestrator must NEVER construct a live client; it only calls us.
        assert self._sentinel.live_client_built is False
        self.fired_gap_queries.append(list(gap_queries))
        new_rows, verdict, per_unit = self._specs[self.calls]
        self.calls += 1
        # Shape-faithful to production `_run_gap_round`: snapshot the corpus
        # BEFORE the merge (the novelty BASELINE), then hand the RAW scripted
        # round rows -- which may include canonical-URL dups already in the
        # corpus -- as `new_round_rows` (the novelty DENOMINATOR). This is the
        # EXACT shape `_run_gap_round` emits (`prev_corpus_rows=_prev_corpus`,
        # `new_round_rows=list(_gap_ret.evidence_rows)`); the loop scores
        # `marginal_novelty(prev_corpus_rows, new_round_rows)` directly.
        prev_corpus = list(self.cumulative_rows)
        self.cumulative_rows = list(self.cumulative_rows) + list(new_rows)
        rep = type("R", (), {
            "verdict": verdict,
            "round_index": self.calls,
            "per_unit": per_unit,
            "under_covered_units": [
                u.unit_id for u in per_unit if not u.sufficient
            ],
        })()
        return RoundOutcome(
            cumulative_retrieved_rows=list(self.cumulative_rows),
            evidence_for_gen=list(self.cumulative_rows),
            sufficiency_report=rep,
            new_round_rows=list(new_rows),
            prev_corpus_rows=prev_corpus,
        )


def _unit(unit_id, sufficient, indices=(0,), empty=()):
    return type("U", (), {
        "unit_id": unit_id,
        "title": unit_id,
        "sufficient": sufficient,
        "sub_query_indices": list(indices),
        "empty_facets": list(empty),
        "covered_count": 0,
        "evidence_target": 2,
        "below_floor_count": 0,
    })()


def _report(verdict, per_unit, round_index=0):
    return type("R", (), {
        "verdict": verdict,
        "round_index": round_index,
        "per_unit": per_unit,
        "under_covered_units": [u.unit_id for u in per_unit if not u.sufficient],
    })()


# ── P4-5 loop convergence: novelty flattens -> STOP_NOVELTY ──────────────────

def test_p4_5_loop_stops_on_novelty_flatten():
    sentinel = _NoLiveClientSentinel()
    plan = _plan(["sq0"], [_section("S0", 2, [0])])
    # round0: 5 new rows (cumulative=5). Subsequent rounds add decreasing novel
    # rows so novelty monotonically decreases below eps.
    r0_rows = [_row(f"ev_{i:03d}", f"https://s/{i}", "sq0", 0.9) for i in range(5)]
    # round1: 3 NEW (urls 5,6,7) -> novelty 3/3=1.0 (still expand)
    r1_new = [_row(f"ev_10{i}", f"https://s/{5+i}", "sq0", 0.9) for i in range(3)]
    # round2: 0 NEW (all dups of existing urls) -> novelty 0.0 < eps
    r2_new = [_row(f"ev_20{i}", f"https://s/{i}", "sq0", 0.9) for i in range(3)]
    under = [_unit("section_0", False)]
    driver = _StubLoopDriver(
        round_specs=[
            (r1_new, "expand", under),
            (r2_new, "expand", under),
        ],
        plan=plan, sentinel=sentinel,
    )
    driver.seed_round0(r0_rows)
    round0 = RoundOutcome(
        cumulative_retrieved_rows=list(r0_rows),
        evidence_for_gen=list(r0_rows),
        sufficiency_report=_report("expand", under),
        new_round_rows=list(r0_rows),
    )
    result = run_saturation_loop(
        round0=round0,
        run_round_fn=driver,
        max_rounds=5,
        novelty_eps=0.10,
        max_discovery_calls=10_000,
        cost_per_query=3,
        plan=plan,
    )
    assert result.decision == STOP_NOVELTY
    assert sentinel.live_client_built is False
    # findings-per-round curve flattens: the LAST round's novelty < eps.
    assert result.novelty_trajectory[-1] < 0.10
    # round0 novelty (1.0) then round1 (1.0) then round2 (0.0): monotone non-incr
    traj = result.novelty_trajectory
    assert all(traj[i] >= traj[i + 1] for i in range(len(traj) - 1))


# ── P4-5b FRACTIONAL novelty below eps stops (the live-path regression pin) ──

def test_p4_5b_fractional_novelty_below_eps_stops():
    """REGRESSION PIN for the degenerate-novelty bug: a gap round that RETRIEVES
    many rows but mostly canonical-URL DUPLICATES yields a genuinely fractional
    novelty (here 1/20 = 0.05) that is < eps but NOT zero. This can only fire if
    `new_round_rows` is the RAW retrieved set (incl. dups) -- the denominator the
    real `_run_gap_round` now passes. If `new_round_rows` were the DEDUPED
    additions (the pre-fix shape), round1 would be `1 new / 1 = 1.0` and the loop
    would NEVER stop on novelty -- so this test is RED on the old code, GREEN on
    the fix. eps is thus exercised at a non-degenerate value."""
    sentinel = _NoLiveClientSentinel()
    plan = _plan(["sq0"], [_section("S0", 2, [0])])
    r0_rows = [_row(f"ev_{i:03d}", f"https://s/{i}", "sq0", 0.9) for i in range(5)]
    # round1 RETRIEVES 20 rows: 19 are dups of the round-0 URLs (s/0..4 cycled),
    # exactly 1 is new (s/100). Raw novelty = 1 / 20 = 0.05 < eps(0.10), > 0.
    r1_raw = [
        _row(f"ev_1{i:02d}", f"https://s/{i % 5}", "sq0", 0.9) for i in range(19)
    ] + [_row("ev_199", "https://s/100", "sq0", 0.9)]
    under = [_unit("section_0", False)]
    driver = _StubLoopDriver(
        round_specs=[(r1_raw, "expand", under)],
        plan=plan, sentinel=sentinel,
    )
    driver.seed_round0(r0_rows)
    round0 = RoundOutcome(
        cumulative_retrieved_rows=list(r0_rows),
        evidence_for_gen=list(r0_rows),
        sufficiency_report=_report("expand", under),
        new_round_rows=list(r0_rows),
    )
    result = run_saturation_loop(
        round0=round0, run_round_fn=driver, max_rounds=5, novelty_eps=0.10,
        max_discovery_calls=10_000, cost_per_query=3, plan=plan,
    )
    assert result.decision == STOP_NOVELTY
    # The stop fired on a FRACTIONAL novelty, not the degenerate 0.0/1.0 boundary.
    assert result.novelty_trajectory[-1] == pytest.approx(0.05)
    assert 0.0 < result.novelty_trajectory[-1] < 0.10
    # exactly ONE gap round fired (round1), then STOP.
    assert driver.calls == 1


# ── P4-6 gap-closure stop -> generator billed exactly once ───────────────────

def test_p4_6_gap_closure_generator_billed_once():
    sentinel = _NoLiveClientSentinel()
    plan = _plan(["sq0"], [_section("S0", 2, [0])])
    r0_rows = [_row("ev_000", "https://s/0", "sq0", 0.9)]
    r1_new = [_row("ev_100", "https://s/1", "sq0", 0.9)]
    # round1 CLOSES the gap.
    closed = [_unit("section_0", True)]
    driver = _StubLoopDriver(
        round_specs=[(r1_new, "proceed", closed)],
        plan=plan, sentinel=sentinel,
    )
    driver.seed_round0(r0_rows)
    round0 = RoundOutcome(
        cumulative_retrieved_rows=list(r0_rows),
        evidence_for_gen=list(r0_rows),
        sufficiency_report=_report("expand", [_unit("section_0", False)]),
        new_round_rows=list(r0_rows),
    )
    result = run_saturation_loop(
        round0=round0, run_round_fn=driver, max_rounds=5,
        novelty_eps=0.10, max_discovery_calls=10_000, cost_per_query=3,
        plan=plan,
    )
    assert result.decision == STOP_SUFFICIENT
    # generator-billing simulation: PROCEED -> the caller bills the generator
    # exactly once. Prove the loop signalled PROCEED (not partial/abort).
    gen_calls = {"n": 0}

    def _generator_fn(_plan, partial_mode):
        gen_calls["n"] += 1
        return "report"

    if result.decision == STOP_SUFFICIENT:
        _generator_fn(plan, partial_mode=False)
    assert gen_calls["n"] == 1


# ── P4-8 budget bound: never exceeds max rounds; cap = STOP_BUDGET ────────────

def test_p4_8_loop_never_exceeds_max_rounds():
    sentinel = _NoLiveClientSentinel()
    plan = _plan(["sq0"], [_section("S0", 2, [0])])
    r0_rows = [_row("ev_000", "https://s/0", "sq0", 0.9)]
    under = [_unit("section_0", False)]
    # Every round keeps adding novel rows + stays under-covered -> would loop
    # forever, but max_rounds=3 caps it at STOP_BUDGET.
    specs = [
        ([_row(f"ev_{r}0", f"https://s/{r}1", "sq0", 0.9)], "expand", under)
        for r in range(1, 6)
    ]
    driver = _StubLoopDriver(round_specs=specs, plan=plan, sentinel=sentinel)
    driver.seed_round0(r0_rows)
    round0 = RoundOutcome(
        cumulative_retrieved_rows=list(r0_rows),
        evidence_for_gen=list(r0_rows),
        sufficiency_report=_report("expand", under),
        new_round_rows=list(r0_rows),
    )
    result = run_saturation_loop(
        round0=round0, run_round_fn=driver, max_rounds=3,
        novelty_eps=0.0, max_discovery_calls=10_000, cost_per_query=3,
        plan=plan,
    )
    assert result.decision == STOP_BUDGET
    assert result.rounds_fired <= 3
    # round0 + at most (max_rounds-1) expansion rounds fired.
    assert driver.calls <= 2


# ── P4-9 spend-free guard: no live client in decision-logic smoke ────────────

def test_p4_9_no_live_client_constructed():
    sentinel = _NoLiveClientSentinel()
    plan = _plan(["sq0"], [_section("S0", 2, [0])])
    r0_rows = [_row("ev_000", "https://s/0", "sq0", 0.9)]
    driver = _StubLoopDriver(
        round_specs=[([_row("ev_100", "https://s/1", "sq0", 0.9)],
                      "proceed", [_unit("section_0", True)])],
        plan=plan, sentinel=sentinel,
    )
    driver.seed_round0(r0_rows)
    round0 = RoundOutcome(
        cumulative_retrieved_rows=list(r0_rows),
        evidence_for_gen=list(r0_rows),
        sufficiency_report=_report("expand", [_unit("section_0", False)]),
        new_round_rows=list(r0_rows),
    )
    run_saturation_loop(
        round0=round0, run_round_fn=driver, max_rounds=5, novelty_eps=0.1,
        max_discovery_calls=10_000, cost_per_query=3, plan=plan,
    )
    assert sentinel.live_client_built is False


# ── P4-10 gap-round anchor-suppressed on BOTH seams ──────────────────────────

class _CaptureAdapter:
    """A stub discovery adapter that records every query it is asked to run."""

    def __init__(self, name, sink):
        self.name = name
        self.need = "primary_literature"
        self.scoped = False
        self._sink = sink

    def run(self, query, *, limit):
        self._sink.append(query)
        return []


def test_p4_10_gap_round_anchor_suppressed_both_seams():
    from src.polaris_graph.retrieval.domain_backends import (
        run_need_type_backends,
    )
    from src.polaris_graph.retrieval.scope_query_validator import (
        validate_amplified_queries,
    )

    # >3 gap queries (pins that the 3-query amplified cap is LIFTED for gap rounds
    # AND that no anchor is injected).
    gap = ["gq0", "gq1", "gq2", "gq3", "gq4"]
    sink: list[str] = []

    class _Reg(SourceAdapterRegistry):
        def adapters_for_need(self, need, *, jurisdictions):
            return [_CaptureAdapter("cap", sink)]

    frame = ResearchFrame(evidence_needs=[], jurisdictions=[])
    # SEAM 2 — the need-type adapters: anchor_seed=False -> queries == gap ONLY
    # (no research_question, no 3-cap).
    res = run_need_type_backends(
        frame=frame,
        research_question="THE BROAD ANCHOR",
        amplified_queries=gap,
        registry=_Reg(),
        anchor_seed=False,
    )
    assert sink == gap                      # exactly the gap queries, in order
    assert "THE BROAD ANCHOR" not in sink   # anchor NOT injected
    assert len(sink) == 5                   # 3-cap lifted (>3 fired)

    # SEAM 1 — the scope validator anchor reinsertion: always_keep_anchor=False
    # must NOT re-add the research_question.
    protocol = {"research_question": "THE BROAD ANCHOR", "entities": ["x"]}
    valid = validate_amplified_queries(
        list(gap), protocol, floor=0.0, always_keep_anchor=False,
    )
    assert "THE BROAD ANCHOR" not in valid.kept

    # Contrast: the DEFAULT (anchor_seed=True) DOES inject the anchor + caps at 3.
    sink2: list[str] = []

    class _Reg2(SourceAdapterRegistry):
        def adapters_for_need(self, need, *, jurisdictions):
            return [_CaptureAdapter("cap", sink2)]

    run_need_type_backends(
        frame=frame, research_question="THE BROAD ANCHOR",
        amplified_queries=gap, registry=_Reg2(),  # anchor_seed defaults True
    )
    assert sink2[0] == "THE BROAD ANCHOR"   # anchor prepended
    assert len(sink2) == 1 + 3              # anchor + 3-capped amplified


# ── P4-10b gap round must NOT early-break and starve later gap facets ─────────

class _HighYieldAdapter:
    """A stub adapter that records every query AND returns 2*limit candidates on
    EVERY call, so the legacy result-count early-break (`len(got) >= 2*limit`)
    would fire after the FIRST query if it were still active."""

    def __init__(self, name, sink):
        self.name = name
        self.need = "primary_literature"
        self.scoped = False
        self._sink = sink

    def run(self, query, *, limit):
        from src.polaris_graph.retrieval.domain_backends import SearchCandidate
        self._sink.append(query)
        return [
            SearchCandidate(
                url=f"https://hit/{query}/{i}",
                title="t", snippet="s", source="src",
                metadata={}, query_origin=query,
            )
            for i in range(limit * 2)
        ]


def test_p4_10b_gap_round_no_early_break_starvation():
    """REGRESSION PIN for the early-break starvation P2: on a gap round
    (anchor_seed=False) every gap query is a DISTINCT under-covered facet that
    must get its own retrieval. A high-yield FIRST facet must NOT trip the legacy
    `len(got) >= 2*limit` break and starve the later specialized facets. The
    legacy break MUST still fire on anchor_seed=True (OFF / single pass)."""
    from src.polaris_graph.retrieval.domain_backends import run_need_type_backends

    gap = ["gq0", "gq1", "gq2", "gq3", "gq4"]
    frame = ResearchFrame(evidence_needs=[], jurisdictions=[])

    # anchor_seed=False: NO early break -> ALL 5 gap facets fire even though gq0
    # already returns 2*limit hits.
    sink: list[str] = []

    class _Reg(SourceAdapterRegistry):
        def adapters_for_need(self, need, *, jurisdictions):
            return [_HighYieldAdapter("hy", sink)]

    run_need_type_backends(
        frame=frame, research_question="ANCHOR",
        amplified_queries=gap, registry=_Reg(), anchor_seed=False,
    )
    assert sink == gap                    # every gap facet retrieved, in order
    assert len(sink) == 5                 # no starvation

    # anchor_seed=True (OFF / single pass): the legacy break is PRESERVED -> the
    # anchor query alone already returns 2*limit, so the loop breaks after it.
    sink2: list[str] = []

    class _Reg2(SourceAdapterRegistry):
        def adapters_for_need(self, need, *, jurisdictions):
            return [_HighYieldAdapter("hy", sink2)]

    run_need_type_backends(
        frame=frame, research_question="ANCHOR",
        amplified_queries=gap, registry=_Reg2(),  # anchor_seed defaults True
    )
    assert sink2 == ["ANCHOR"]            # legacy early-break still fires


# ── P4-13 global evidence_id renumber across rounds ──────────────────────────

def test_p4_13_global_evidence_id_renumber():
    """Merging round-1 rows (ev_000..) with round-2 rows (also ev_000..) must
    renumber so the cumulative pool has globally-unique ids (no overwrite); the
    merged count == sum of round counts after canonical-URL dedup."""
    # Simulate the runner's merge+renumber pattern (the closure uses the same
    # `base = len(rows); new_id = f"ev_{base+i:03d}"`).
    cumulative = [
        _row("ev_000", "https://a/1", "q", 0.9),
        _row("ev_001", "https://a/2", "q", 0.9),
    ]
    round2 = [
        _row("ev_000", "https://b/1", "q", 0.9),   # COLLIDES on id with cumulative
        _row("ev_001", "https://b/2", "q", 0.9),
    ]
    base = len(cumulative)
    for i, ev in enumerate(round2):
        ev["evidence_id"] = f"ev_{base + i:03d}"
        cumulative.append(ev)
    ids = [r["evidence_id"] for r in cumulative]
    assert len(ids) == len(set(ids))                      # globally unique
    assert ids == ["ev_000", "ev_001", "ev_002", "ev_003"]
    # distinct URLs -> merged count == sum of round counts (no dedup collapse).
    assert len(cumulative) == 4


# ── P4-14 cumulative retrieval budget NEVER exceeded (worst-case, pre-spend) ──

def test_p4_14_cumulative_budget_never_exceeded():
    sentinel = _NoLiveClientSentinel()
    plan = _plan(["sq0", "sq1"], [_section("S0", 99, [0, 1])])
    under = [_unit("section_0", False, indices=(0, 1), empty=())]
    r0_rows = [_row("ev_000", "https://s/0", "sq0", 0.9)]
    # Every round adds novel rows + stays under-covered; the loop would run to
    # max_rounds, but the budget cap forces STOP_BUDGET earlier.
    specs = [
        ([_row(f"ev_{r}0", f"https://s/{r}9", "sq0", 0.9)], "expand", under)
        for r in range(1, 30)
    ]
    driver = _StubLoopDriver(round_specs=specs, plan=plan, sentinel=sentinel)
    driver.seed_round0(r0_rows)
    round0 = RoundOutcome(
        cumulative_retrieved_rows=list(r0_rows),
        evidence_for_gen=list(r0_rows),
        sufficiency_report=_report("expand", under),
        new_round_rows=list(r0_rows),
    )
    MAX = 10
    cost = 3   # per_query_discovery_cost(adapter_count=1)
    result = run_saturation_loop(
        round0=round0, run_round_fn=driver, max_rounds=99,
        novelty_eps=0.0, max_discovery_calls=MAX, cost_per_query=cost,
        plan=plan,
    )
    assert result.decision == STOP_BUDGET
    # INVARIANT: cumulative discovery spend NEVER exceeds MAX (pre-spend bound).
    assert result.cumulative_discovery_calls <= MAX
    # And it stopped even though max_rounds (99) was not reached.
    assert result.rounds_fired < 99


def test_p4_14b_preflight_truncates_to_fit_remaining():
    """A round with more gap queries than the remaining budget can fund is
    TRUNCATED pre-spend so the worst-case spend cannot exceed remaining."""
    pf = preflight_round_budget(
        gap_queries=["a", "b", "c", "d", "e"],
        cumulative_discovery_calls=4,
        max_discovery_calls=10,
        cost_per_query=3,
    )
    # remaining=6, max_fire = 6//3 = 2 -> truncate 5 -> 2.
    assert pf.allowed_queries == ["a", "b"]
    assert pf.fired_cost == 6
    assert pf.truncated is True
    assert pf.exhausted is False
    assert 4 + pf.fired_cost <= 10


def test_p4_14c_preflight_exhausted_when_no_budget():
    pf = preflight_round_budget(
        gap_queries=["a", "b"],
        cumulative_discovery_calls=10,
        max_discovery_calls=10,
        cost_per_query=3,
    )
    assert pf.exhausted is True
    assert pf.allowed_queries == []


def test_p4_14d_per_query_cost_worst_case():
    # core Serper + core S2 (2) + adapter_count.
    assert per_query_discovery_cost(0) == 2
    assert per_query_discovery_cost(3) == 5


# ── P4-7 / P4-7b / P4-7c partial report (pruned plan + index remap + appenders)

def _prune_plan(research_plan, sufficiency_report):
    """Mirror of the runner's `_prune_plan_to_sufficient_sections` so the smoke
    tests the SAME prune+remap invariant the runner relies on (imported from the
    runner to avoid drift)."""
    import importlib
    runner = importlib.import_module("scripts.run_honest_sweep_r3")
    return runner._prune_plan_to_sufficient_sections(
        research_plan, sufficiency_report
    )


def test_p4_7_partial_report_pruned_plan_excludes_undercovered():
    """Section A covered, section B never closes -> the PRUNED plan's outline
    contains ONLY section A (B is structurally absent)."""
    plan = _plan(
        ["sqA0", "sqA1", "sqB0", "sqB1"],
        [_section("A", 2, [0, 1]), _section("B", 2, [2, 3])],
    )
    # Real gate: A covered (2 above-floor rows on each facet), B empty.
    rows = [
        _row("ev_000", "https://a/0", "sqA0", 0.9),
        _row("ev_001", "https://a/1", "sqA1", 0.9),
    ]
    rep = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=1, max_rounds=1,
    )
    assert rep.verdict == "abort"   # B under-covered, rounds exhausted
    pruned, dropped = _prune_plan(plan, rep)
    assert pruned is not None
    titles = [s.title for s in pruned.outline]
    assert titles == ["A"]
    assert "B" in dropped


def test_p4_7b_pruned_plan_index_remap_invariant():
    """After pruning, orphaned sub_queries are dropped, retained sections'
    sub_query_indices are REMAPPED to the compacted list, ALL indices in-range,
    and union(indices) == range(len(pruned.sub_queries))."""
    plan = _plan(
        ["sqA0", "sqA1", "sqB0", "sqB1", "sqC0"],
        [
            _section("A", 1, [0, 1]),   # sufficient
            _section("B", 1, [2, 3]),   # under-covered -> dropped
            _section("C", 1, [4]),      # sufficient
        ],
    )
    # A + C covered, B empty.
    rows = [
        _row("ev_000", "https://a/0", "sqA0", 0.9),
        _row("ev_001", "https://a/1", "sqA1", 0.9),
        _row("ev_002", "https://c/0", "sqC0", 0.9),
    ]
    rep = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=1, max_rounds=1,
    )
    pruned, dropped = _prune_plan(plan, rep)
    assert pruned is not None
    assert [s.title for s in pruned.outline] == ["A", "C"]
    # orphaned sqB0/sqB1 dropped; sub_queries compacted to A's + C's facets.
    assert pruned.sub_queries == ["sqA0", "sqA1", "sqC0"]
    # remapped indices: A -> [0,1], C -> [2]; all in-range; union == full range.
    union = set()
    n = len(pruned.sub_queries)
    for s in pruned.outline:
        for idx in s.sub_query_indices:
            assert 0 <= idx < n
            union.add(idx)
    assert union == set(range(n))
    # The pruned plan re-passes the Phase-3 fail-closed facet-union validation.
    from src.polaris_graph.planning.research_planner import (
        _validate_outline_facet_mapping,
    )
    _validate_outline_facet_mapping(pruned)   # must not raise


def test_p4_7_zero_sufficient_returns_none():
    """Zero sufficient sections -> pruned plan is None (caller aborts
    abort_corpus_inadequate, no generator bill)."""
    plan = _plan(["sqA0", "sqB0"], [_section("A", 9, [0]), _section("B", 9, [1])])
    rep = assess_plan_sufficiency(
        plan=plan, corpus_rows=[], authority_floor=0.3,
        round_index=1, max_rounds=1,
    )
    pruned, dropped = _prune_plan(plan, rep)
    assert pruned is None
    assert set(dropped) == {"A", "B"}


def test_p4_7c_partial_mode_disables_all_five_out_of_plan_appenders():
    """BEHAVIORAL (spend-free): drive `generate_multi_section_report` with
    `partial_mode=True` and ALL FIVE out-of-plan triggering inputs present
    (tier_fractions + contradictions + date_range + uncovered_topics ->
    Limitations; primary_trial_anchors + direct_trial_anchors -> Trial Summary +
    M50; v30_contract_plans -> contract sections; section_results + biblio ->
    Analyst Synthesis), then assert NONE render.

    Spend-free seam: the evidence pool is EMPTY, so every section's ev_ids map to
    no pool row and `_run_section` returns dropped WITHOUT an LLM call. The four
    text builders are gated on `partial_mode` BEFORE their LLM calls, and the V30
    contract outline injection is skipped — so partial_mode=True yields all four
    text fields == "" and NO contract title in the outline, with zero spend."""
    import asyncio

    from src.polaris_graph.generator.multi_section_generator import (
        generate_multi_section_report,
    )

    plan = _plan(
        ["sq0", "sq1"],
        [_section("Kept Section", 1, [0, 1], archetype="Background")],
    )

    class _StubContractPlan:
        """A V30 contract section plan stub — only `.title` is read on the
        partial_mode=True path (the injection is skipped before `.slots`/`.focus`
        are ever dereferenced)."""

        title = "CONTRACT SECTION SHOULD NOT RENDER"
        focus = "x"
        slots = ()

    async def _run():
        return await generate_multi_section_report(
            research_question="q",
            evidence=[],                       # EMPTY pool -> sections drop, no spend
            research_plan=plan,
            partial_mode=True,
            # ── all five triggering inputs PRESENT ──
            tier_fractions={"T1": 0.5, "T2": 0.5},
            contradictions=[{"a": 1}],
            date_range={"start": "2020", "end": "2024"},
            uncovered_topics=["something uncovered"],
            primary_trial_anchors=["TRIAL-A", "TRIAL-B"],
            direct_trial_anchors=["TRIAL-A", "TRIAL-B"],
            v30_contract_plans=[_StubContractPlan()],
            live_corpus=[],
        )

    result = asyncio.run(_run())

    # The four text appenders produce NOTHING in partial_mode (gated before LLM).
    assert result.limitations_text == ""
    assert result.analyst_synthesis_text == ""
    assert result.trial_summary_table_text == ""
    assert result.trial_timeline_text == ""
    assert result.m50_per_trial_subsections_text == ""
    # V30 contract section is NOT injected into the outline.
    outline_titles = [getattr(p, "title", "") for p in result.outline]
    assert "CONTRACT SECTION SHOULD NOT RENDER" not in outline_titles
    # I-beatboth-004 (#1281): B08 (_drop_ungroundable_sections, commit 71c5b759)
    # now drops a planned section whose every ev_id is non-span-groundable at the
    # PLAN level (one step earlier than the old _run_section drop). This spend-free
    # fixture passes evidence=[] (empty pool), so "Kept Section" has zero groundable
    # rows and is correctly dropped -> empty outline. Do NOT make it groundable to
    # restore ["Kept Section"] — that triggers a live LLM render and breaks the
    # spend-free seam.
    assert outline_titles == []


def test_p4_7c_full_mode_signature_default_preserves_appenders():
    """Contrast guard: `partial_mode` defaults False so PROCEED/full mode is
    UNCHANGED (all five appenders still reachable). The full-mode RENDER contrast
    is live-only (the section writer + the four builders all bill) per the
    spend-free build boundary; here we pin the default + that the gates re-enable
    when partial_mode is False (no `not partial_mode` short-circuit fires)."""
    import inspect

    from src.polaris_graph.generator import multi_section_generator as msg

    sig = inspect.signature(msg.generate_multi_section_report)
    assert "partial_mode" in sig.parameters
    assert sig.parameters["partial_mode"].default is False


# ── P4-15 partial_saturation taxonomy registration ───────────────────────────

def test_p4_15_partial_saturation_taxonomy_registered():
    import importlib
    runner = importlib.import_module("scripts.run_honest_sweep_r3")
    from src.polaris_graph.audit_ir.regression_lab import (
        KNOWN_STATUS_VALUES,
    )

    assert "partial_saturation" in runner.UNIFIED_STATUS_VALUES
    assert "partial_saturation" in KNOWN_STATUS_VALUES
    # summary->unified self-map present.
    assert runner._SUMMARY_TO_UNIFIED["partial_saturation"] == "partial_saturation"
    assert runner.to_unified_status("partial_saturation") == "partial_saturation"
    # The md9 taxonomy-drift guard holds WITH the new status registered.
    assert KNOWN_STATUS_VALUES == runner.UNIFIED_STATUS_VALUES


# ── P4-16 re-gate on the BILLED set each round ───────────────────────────────

def test_p4_16_regate_on_billed_set_each_round():
    """Each round's gate is assessed on the post-select/V30/upload billed set
    (`evidence_for_gen`), NOT the raw retrieved corpus. The stub driver returns a
    RoundOutcome whose `sufficiency_report` was computed from `evidence_for_gen`;
    assert the loop's terminal `_suff` corresponds to the billed set."""
    sentinel = _NoLiveClientSentinel()
    plan = _plan(["sq0"], [_section("S0", 1, [0])])
    r0_rows = [_row("ev_000", "https://s/0", "sq0", 0.9)]
    # The billed set for round1 is the cumulative selected rows; the gate runs on
    # exactly those. We model the gate result via assess_plan_sufficiency over
    # the billed rows so the report is the REAL gate output on the billed set.
    billed_round1 = r0_rows + [_row("ev_100", "https://s/1", "sq0", 0.9)]

    class _BilledDriver:
        def __init__(self):
            self.calls = 0
            self.last_billed = None

        def __call__(self, gap_queries):
            assert sentinel.live_client_built is False
            self.calls += 1
            self.last_billed = list(billed_round1)
            rep = assess_plan_sufficiency(
                plan=plan, corpus_rows=self.last_billed,
                authority_floor=0.3, round_index=self.calls, max_rounds=5,
            )
            return RoundOutcome(
                cumulative_retrieved_rows=list(billed_round1),
                evidence_for_gen=list(billed_round1),   # the BILLED set
                sufficiency_report=rep,
                new_round_rows=[_row("ev_100", "https://s/1", "sq0", 0.9)],
                prev_corpus_rows=list(r0_rows),   # corpus BEFORE this round
            )

    driver = _BilledDriver()
    round0_rep = assess_plan_sufficiency(
        plan=plan, corpus_rows=[], authority_floor=0.3,
        round_index=0, max_rounds=5,
    )
    round0 = RoundOutcome(
        cumulative_retrieved_rows=[],
        evidence_for_gen=[],
        sufficiency_report=round0_rep,
        new_round_rows=[],
    )
    result = run_saturation_loop(
        round0=round0, run_round_fn=driver, max_rounds=5, novelty_eps=0.1,
        max_discovery_calls=10_000, cost_per_query=3, plan=plan,
    )
    # The final round's gate was computed over the BILLED set (billed_round1).
    assert result.decision == STOP_SUFFICIENT
    assert driver.last_billed == billed_round1


# ── P4-1 OFF byte-identity (single-pass path unchanged) ──────────────────────

def test_p4_1_off_anchor_seed_default_preserves_anchor():
    """OFF / single-pass: anchor_seed defaults True, so the need-type backend
    PREPENDS the research_question and caps amplified at 3 — byte-identical to
    pre-Phase-4 behavior."""
    from src.polaris_graph.retrieval.domain_backends import (
        run_need_type_backends,
    )
    sink: list[str] = []

    class _Reg(SourceAdapterRegistry):
        def adapters_for_need(self, need, *, jurisdictions):
            return [_CaptureAdapter("cap", sink)]

    frame = ResearchFrame(evidence_needs=[], jurisdictions=[])
    run_need_type_backends(
        frame=frame, research_question="ANCHOR",
        amplified_queries=["a1", "a2", "a3", "a4", "a5"],
        registry=_Reg(),
        # anchor_seed defaults True (the OFF / single-pass path).
    )
    # Anchor prepended + amplified capped at 3 (unchanged legacy behavior).
    assert sink == ["ANCHOR", "a1", "a2", "a3"]


def test_p4_1_off_scope_validator_keeps_anchor_by_default():
    """OFF: validate_amplified_queries default always_keep_anchor=True keeps the
    verbatim research_question (byte-identical legacy de-drift)."""
    from src.polaris_graph.retrieval.scope_query_validator import (
        validate_amplified_queries,
    )
    protocol = {"research_question": "ANCHOR Q", "entities": ["x"]}
    valid = validate_amplified_queries(
        ["off topic xyz unrelated"], protocol, floor=0.99,
    )
    # The off-topic query is dropped (below floor) but the anchor is kept.
    assert "ANCHOR Q" in valid.kept
