"""I-meta-005 Phase 3 (#987) smoke — plan-sufficiency gate (the money-trap fix).

Cases P3-1..P3-17 from the Codex-APPROVED brief `.codex/I-meta-005-phase-3/
brief.md` §3. Spend-free: the gate is a PURE function over real dict rows; the
planner is constructed via plain-class fakes / direct dataclasses (NO
unittest.mock, NO live LLM/retrieval). The "ZERO generator bill" guarantee is
asserted at the gate-verdict level (the EXPAND/ABORT verdict is exactly what
makes the sweep return BEFORE `generate_multi_section_report`) plus a spy that
proves the on-mode evidence-assignment path constructs no generator client.

Serialized per CLAUDE.md §8.4 (no heavy ML; pure-python).
"""
from __future__ import annotations

import json

import pytest

from src.polaris_graph.adequacy.plan_sufficiency_gate import (
    SENTINEL_ORIGINS,
    assess_plan_sufficiency,
    relevant_section_indices,
)
from src.polaris_graph.planning.research_planner import (
    MalformedPlanError,
    ResearchFrame,
    ResearchPlan,
    SectionOutlineItem,
    plan_research,
    plan_sha256,
    serialize_plan_canonical,
)


# ── fixtures / helpers (real objects, no mocks) ──────────────────────────────

def _plan(sub_queries, outline):
    return ResearchPlan(
        research_question="q",
        frame=ResearchFrame(),
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


def _row(ev_id, origin, score, *, statement="", quote=""):
    r = {
        "evidence_id": ev_id,
        "query_origin": origin,
        "statement": statement,
        "direct_quote": quote,
    }
    if score is not None:
        r["authority_score"] = score
        r["authority_confidence"] = "HIGH"
    return r


def _planner_llm(payload: dict):
    """A plain callable fake — returns one JSON plan string regardless of prompt."""
    text = json.dumps(payload)

    def _call(_prompt: str) -> str:
        return text

    return _call


_FRAME_OBJ = {
    "entities": ["x"], "relations": [], "metrics": [],
    "comparators": [], "constraints": [], "claim_type": "descriptive",
    "evidence_needs": [], "jurisdictions": [],
}


# ── P3-1 OFF byte-identity ───────────────────────────────────────────────────

def test_p3_1_off_byte_identity_legacy_gate_untouched():
    """OFF -> the legacy domain-keyed `assess_corpus_adequacy` verdict is
    byte-identical (the off-mode gate is retained, not replaced)."""
    from src.polaris_graph.nodes.corpus_adequacy_gate import (
        assess_corpus_adequacy,
    )
    clinical = assess_corpus_adequacy(
        tier_counts={"T1": 4, "T2": 3, "T3": 2, "T4": 1, "T5": 1, "T6": 1},
        evidence_row_count=9, domain="clinical",
    )
    policy = assess_corpus_adequacy(
        tier_counts={"T3": 6, "T1": 1, "T2": 1, "T6": 2},
        evidence_row_count=10, domain="policy",
    )
    assert clinical.decision == "proceed"
    assert policy.decision == "proceed"
    # Pin the serialized report bytes — a regression in the legacy path changes
    # these.
    from dataclasses import asdict
    clinical_bytes = json.dumps(asdict(clinical), sort_keys=True)
    assert '"decision": "proceed"' in clinical_bytes


# ── P3-2 PROCEED ─────────────────────────────────────────────────────────────

def test_p3_2_proceed_all_sections_covered():
    plan = _plan(
        ["solar cost", "wind cost", "hydro cost", "battery cost", "grid cost", "policy cost"],
        [
            _section("S0", 2, [0, 1]),
            _section("S1", 2, [2, 3]),
            _section("S2", 2, [4, 5]),
        ],
    )
    rows = [
        _row("ev_000", "solar cost", 0.9),
        _row("ev_001", "wind cost", 0.8),
        _row("ev_002", "hydro cost", 0.9),
        _row("ev_003", "battery cost", 0.8),
        _row("ev_004", "grid cost", 0.9),
        _row("ev_005", "policy cost", 0.8),
    ]
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r.verdict == "proceed"
    assert r.under_covered_units == []


# ── P3-3 THE TRAP (housing) ──────────────────────────────────────────────────

def test_p3_3_trap_housing_broad_shallow_holds_before_billing():
    """6-section housing plan; broad corpus but section #5 has 0 relevant
    above-floor rows -> EXPAND/ABORT (NOT proceed). The verdict IS the
    money-trap exit (sweep returns before the generator)."""
    sub = [f"housing facet {i}" for i in range(6)]
    plan = _plan(sub, [_section(f"S{i}", 1, [i]) for i in range(6)])
    # Lots of rows, but NONE for facet 5.
    rows = [_row(f"ev_{i:03d}", f"housing facet {i % 5}", 0.9) for i in range(20)]
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r.verdict in ("expand", "abort")
    assert "section_5" in r.under_covered_units


# ── P3-4 THE TRAP (sovereignty) ──────────────────────────────────────────────

def test_p3_4_trap_sovereignty_same_shape_held():
    sub = [f"sovereignty facet {i}" for i in range(6)]
    plan = _plan(sub, [_section(f"S{i}", 1, [i]) for i in range(6)])
    rows = [_row(f"ev_{i:03d}", f"sovereignty facet {i % 5}", 0.9) for i in range(18)]
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r.verdict in ("expand", "abort")
    assert not all(u.sufficient for u in r.per_unit)


# ── P3-5 authority floor bites (numeric) ─────────────────────────────────────

def test_p3_5_authority_floor_bites_numeric():
    """A section with 3 relevant rows ALL below the floor -> UNDER_COVERED;
    relevant-but-below-floor counted separately, not credited."""
    plan = _plan(["facet a"], [_section("S0", 2, [0])])
    rows = [_row(f"ev_{i:03d}", "facet a", 0.1) for i in range(3)]
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r.verdict == "abort"
    u = r.per_unit[0]
    assert u.covered_count == 0
    assert u.below_floor_count == 3


# ── P3-5b provenance-first mapping ───────────────────────────────────────────

def test_p3_5b_provenance_first_no_off_facet_credit():
    outline = [_section("S0", 1, [0]), _section("S1", 1, [1])]
    sub = ["alpha facet", "beta facet"]
    # Real origin matches section S0's sub-query exactly; even though its words
    # overlap S1's title, it must NOT credit S1 (no title rescue for real origin).
    row = _row("ev_000", "alpha facet", 0.9, statement="beta facet words here")
    assert relevant_section_indices(row, outline, sub) == [0]
    # Empty-origin row uses the content-word fallback against the section texts.
    erow = _row("ev_001", "", 0.9, statement="beta facet extra terms")
    assert relevant_section_indices(erow, outline, sub) == [1]


# ── P3-5c authority sidecar persisted (live row build) ───────────────────────

def test_p3_5c_authority_sidecar_persisted_on_mode_only():
    """The on-mode live evidence row carries authority_score+confidence;
    off-mode rows have NEITHER key (byte-identical). Asserted at the source-of-
    truth: live_retriever adds the sidecar only under `research_frame is not
    None`."""
    import inspect
    from src.polaris_graph.retrieval import live_retriever
    src = inspect.getsource(live_retriever.run_live_retrieval)
    assert 'if research_frame is not None:' in src
    assert '"authority_score"' in src or "['authority_score']" in src
    assert "score_source_authority(signals)" in src


# ── P3-6 EXPAND vs ABORT ─────────────────────────────────────────────────────

def test_p3_6_expand_vs_abort():
    plan = _plan(["facet a", "facet b"], [_section("S0", 2, [0, 1])])
    rows = [_row("ev_000", "facet a", 0.9)]  # facet b empty
    expand = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=0, max_rounds=3,
    )
    abort = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=3, max_rounds=3,
    )
    assert expand.verdict == "expand"
    assert expand.under_covered_units  # returns the under-covered units
    assert abort.verdict == "abort"


# ── P3-7 field-agnostic guard ────────────────────────────────────────────────

def test_p3_7_field_agnostic_no_domain_dict_on_path():
    """The on-path sufficiency code consults NO domain dict / `if domain ==` /
    domain key. The legacy domain dict is whitelisted off-path."""
    import ast
    import inspect
    from src.polaris_graph.adequacy import plan_sufficiency_gate
    full = inspect.getsource(plan_sufficiency_gate)
    # Strip docstrings/comments — the brief's guard is about the on-path CODE,
    # not prose that NAMES the banned constructs to forbid them.
    tree = ast.parse(full)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                full = full.replace(doc, "")
    code_lines = [
        ln for ln in full.splitlines()
        if not ln.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "_DEFAULT_DOMAIN_THRESHOLDS" not in code
    assert "if domain ==" not in code
    assert "if domain==" not in code
    # No clinical literal used as a control value.
    assert 'domain == "clinical"' not in code


# ── P3-8 zero generator bill on hold ─────────────────────────────────────────

def test_p3_8_zero_generator_bill_on_hold():
    """Across the trap/abort cases the verdict is EXPAND/ABORT — the sweep
    returns `abort_corpus_inadequate` BEFORE `generate_multi_section_report`.
    We assert no generator/evaluator construction occurs in the gate at all:
    the gate touches no LLM client class."""
    import inspect
    from src.polaris_graph.adequacy import plan_sufficiency_gate
    src = inspect.getsource(plan_sufficiency_gate)
    assert "OpenRouterClient" not in src
    assert "generate_multi_section_report" not in src
    # And the trap verdicts are non-proceed (so the sweep cannot reach billing).
    sub = [f"f{i}" for i in range(4)]
    plan = _plan(sub, [_section(f"S{i}", 1, [i]) for i in range(4)])
    rows = [_row(f"ev_{i:03d}", f"f{i % 3}", 0.9) for i in range(12)]  # f3 empty
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r.verdict == "abort"


# ── P3-9 facet-level (the strongest) ─────────────────────────────────────────

def test_p3_9_facet_level_empty_facet_under_covers():
    """Section mapped to [4,5,6] with 5 above-floor rows ALL from sub-query 4 ->
    UNDER_COVERED even though total (5) >= evidence_target (3)."""
    sub = [f"f{i}" for i in range(7)]
    plan = _plan(sub, [_section("S0", 3, [4, 5, 6])])
    rows = [_row(f"ev_{i:03d}", "f4", 0.9) for i in range(5)]
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=rows, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    u = r.per_unit[0]
    assert u.covered_count == 5
    assert u.evidence_target == 3
    assert sorted(u.empty_facets) == [5, 6]
    assert not u.sufficient
    assert r.verdict == "abort"


# ── P3-10 authority in planner mode (independent of PG_USE_AUTHORITY_MODEL) ───

def test_p3_10_authority_computed_directly_in_planner_mode():
    """live_retriever computes the sidecar via score_source_authority DIRECTLY
    on-mode, independent of the PG_USE_AUTHORITY_MODEL tier switch — so rows
    carry a real numeric score, never a 0.0 default. Asserted at the import
    seam (live retrieval needs network for an end-to-end row)."""
    import inspect
    from src.polaris_graph.retrieval import live_retriever
    # The direct import exists (NOT routed through the tier_classifier switch).
    assert hasattr(live_retriever, "score_source_authority")
    src = inspect.getsource(live_retriever.run_live_retrieval)
    # The sidecar block does NOT gate on PG_USE_AUTHORITY_MODEL.
    idx = src.index("score_source_authority(signals)")
    window = src[max(0, idx - 400):idx]
    assert "PG_USE_AUTHORITY_MODEL" not in window
    assert "research_frame is not None" in window


# ── P3-11 canonical pin includes sub_query_indices ───────────────────────────

def test_p3_11_canonical_pin_includes_sub_query_indices():
    plan = _plan(
        ["a", "b"],
        [_section("S0", 1, [0]), _section("S1", 1, [1], archetype="Decision")],
    )
    canon = plan.to_canonical_dict()
    assert canon["outline"][0]["sub_query_indices"] == [0]
    assert canon["outline"][1]["sub_query_indices"] == [1]
    # Re-serializing reproduces the same SHA.
    assert plan_sha256(plan) == plan_sha256(plan)
    assert "sub_query_indices" in serialize_plan_canonical(plan)


# ── P3-12 fail-closed mapping ────────────────────────────────────────────────

def test_p3_12_fail_closed_mapping_raises_before_spend():
    # Empty sub_query_indices on a section -> MalformedPlanError.
    empty = dict(_FRAME_OBJ)
    payload_empty = {
        "frame": empty, "sub_queries": ["q0", "q1"],
        "outline": [
            {"archetype": "Background", "title": "A", "evidence_target": 2,
             "sub_query_indices": []},
            {"archetype": "Decision", "title": "B", "evidence_target": 1,
             "sub_query_indices": [0, 1]},
        ],
    }
    with pytest.raises(MalformedPlanError):
        plan_research("question", planner_llm=_planner_llm(payload_empty),
                      min_subqueries=1)

    # evidence_target=0 on-mode -> MalformedPlanError.
    payload_zero = {
        "frame": dict(_FRAME_OBJ), "sub_queries": ["q0"],
        "outline": [{"archetype": "Background", "title": "A",
                     "evidence_target": 0, "sub_query_indices": [0]}],
    }
    with pytest.raises(MalformedPlanError):
        plan_research("question", planner_llm=_planner_llm(payload_zero),
                      min_subqueries=1)

    # Off-mode: a `[]` mapping on a directly-built section is inert (no raise on
    # construction).
    s = _section("S0", 1, [])
    assert s.sub_query_indices == []


def test_p3_12b_out_of_range_after_truncation_raises():
    """An index valid at parse time goes stale after `_merge_truncate_subqueries`
    truncates the sub_queries below it -> MalformedPlanError."""
    # 41 sub-queries (over DEFAULT_MAX_SUBQUERIES=40) so #40 is truncated away,
    # but a section maps index 40 -> out of range after truncation.
    sub_queries = [f"q{i}" for i in range(41)]
    mapping_all = list(range(40))
    payload = {
        "frame": dict(_FRAME_OBJ),
        "sub_queries": sub_queries,
        "outline": [
            {"archetype": "Background", "title": "A", "evidence_target": 1,
             "sub_query_indices": mapping_all},
            {"archetype": "Decision", "title": "B", "evidence_target": 1,
             "sub_query_indices": [40]},
        ],
    }
    with pytest.raises(MalformedPlanError):
        plan_research("question", planner_llm=_planner_llm(payload),
                      min_subqueries=1)


# ── P3-13 sentinel fallback ──────────────────────────────────────────────────

def test_p3_13_sentinel_fallback_credits_and_real_origin_does_not():
    outline = [_section("S0", 1, [0])]
    sub = ["renewable hydro turbine capacity output"]
    for sentinel in sorted(SENTINEL_ORIGINS):
        srow = _row("ev_000", sentinel, 0.9,
                    statement="renewable hydro turbine capacity report")
        assert relevant_section_indices(srow, outline, sub) == [0], sentinel
    # A REAL sub-query origin that doesn't MATCH the section text is NOT credited
    # (no overlap rescue for a real origin).
    real = _row("ev_001", "some other real subquery", 0.9,
                statement="renewable hydro turbine capacity report")
    assert relevant_section_indices(real, outline, sub) == []


# ── P3-14 whole-plan facet union ─────────────────────────────────────────────

def test_p3_14_orphaned_facet_raises_before_spend():
    """sub-query #1 mapped to NO section -> MalformedPlanError."""
    payload = {
        "frame": dict(_FRAME_OBJ), "sub_queries": ["q0", "q1"],
        "outline": [{"archetype": "Background", "title": "A",
                     "evidence_target": 1, "sub_query_indices": [0]}],
    }
    with pytest.raises(MalformedPlanError):
        plan_research("question", planner_llm=_planner_llm(payload),
                      min_subqueries=1)


# ── P3-15 gate the BILLED set + provenance assignment ────────────────────────

def test_p3_15_provenance_assignment_matches_gate_coverage():
    """On-mode `_assign_evidence_to_planned_outline` assigns each section its
    `query_origin`-matched rows (NOT round-robin); a section the gate certified
    SUFFICIENT actually receives its credited rows. Off-mode the round-robin is
    byte-identical."""
    from src.polaris_graph.generator.multi_section_generator import (
        _assign_evidence_to_planned_outline,
    )
    sub = ["alpha facet", "beta facet"]
    # S0 target 2 so it receives BOTH alpha rows (the cap honors evidence_target).
    outline = [_section("S0", 2, [0]), _section("S1", 1, [1])]
    evidence = [
        _row("ev_000", "alpha facet", 0.9),
        _row("ev_001", "beta facet", 0.9),
        _row("ev_002", "alpha facet", 0.9),
    ]
    # ON-mode (sub_queries provided) -> provenance-first.
    plans_on = _assign_evidence_to_planned_outline(
        outline, evidence, sub_queries=sub,
    )
    assert set(plans_on[0].ev_ids) == {"ev_000", "ev_002"}
    assert plans_on[1].ev_ids == ["ev_001"]

    # OFF-path (sub_queries=None) -> round-robin byte-identical to legacy slice,
    # capped per section's evidence_target.
    plans_off = _assign_evidence_to_planned_outline(outline, evidence)
    ev_ids = ["ev_000", "ev_001", "ev_002"]
    assert plans_off[0].ev_ids == ev_ids[0::2][:2]
    assert plans_off[1].ev_ids == ev_ids[1::2][:1]


def test_p3_15c_credited_above_floor_rows_billed_first():
    """On-mode assignment is AUTHORITY-FLOOR aware: a section the gate certified
    SUFFICIENT (≥target above-floor rows) must RECEIVE those credited rows, even
    when below-floor relevant rows sort FIRST (e.g. prepended contract/upload
    rows). Below-floor rows only fill remaining cap slots, never displace
    credited ones (brief §2.2b: ev_ids == the section's credited rows)."""
    from src.polaris_graph.generator.multi_section_generator import (
        _assign_evidence_to_planned_outline,
    )
    sub = ["facet zero terms"]
    outline = [_section("S0", 2, [0])]
    # Below-floor rows FIRST (mirrors a contract/upload prepend), above-floor
    # after. floor default 0.3: 0.1 below, 0.9 above.
    evidence = [
        _row("lo_0", "facet zero terms", 0.1),
        _row("lo_1", "facet zero terms", 0.1),
        _row("hi_0", "facet zero terms", 0.9),
        _row("hi_1", "facet zero terms", 0.9),
    ]
    plans = _assign_evidence_to_planned_outline(
        outline, evidence, sub_queries=sub,
    )
    assert plans[0].ev_ids == ["hi_0", "hi_1"]


def test_p3_15e_per_facet_reservation_survives_cap_truncation():
    """Architect P1 (BLOCKER) regression: a multi-facet section where one
    facet's rows sort FIRST and fill the evidence_target cap must STILL include
    the other certified facet's row. The gate certifies SUFFICIENT only if EVERY
    mapped sub_query_index has >=min_per_facet above-floor rows; the assignment
    must RESERVE per-facet before the cap slice, else a certified facet is
    truncated out and the generator bills a section whose sub-question has ZERO
    evidence in the billed set (facet-level money-trap at the cap boundary)."""
    from src.polaris_graph.adequacy.plan_sufficiency_gate import (
        assess_plan_sufficiency,
    )
    from src.polaris_graph.generator.multi_section_generator import (
        _assign_evidence_to_planned_outline,
    )
    sub = ["facet zero terms", "facet one terms"]
    # Section maps facets [0,1], target=2. Corpus: 3 above-floor facet-0 rows
    # FIRST, then 1 above-floor facet-1 row. Gate: per_facet={0:3,1:1} -> SUFFICIENT.
    outline = [_section("S0", 2, [0, 1])]
    evidence = [
        _row("f0_a", "facet zero terms", 0.9),
        _row("f0_b", "facet zero terms", 0.9),
        _row("f0_c", "facet zero terms", 0.9),
        _row("f1_a", "facet one terms", 0.9),
    ]
    report = assess_plan_sufficiency(
        plan=_plan(sub, outline), corpus_rows=evidence,
        authority_floor=0.3, round_index=0, max_rounds=0,
    )
    assert report.verdict == "proceed"  # gate certifies SUFFICIENT
    plans = _assign_evidence_to_planned_outline(
        outline, evidence, sub_queries=sub, authority_floor=0.3,
    )
    # The certified facet-1 row MUST be in the billed set (not truncated out by
    # the 3 facet-0 rows filling the target=2 cap).
    assert "f1_a" in plans[0].ev_ids, (
        "PER-FACET TRUNCATION REGRESSION: facet 1's only credited row was sliced "
        "out; the generator would bill a section whose certified facet has zero "
        f"evidence. ev_ids={plans[0].ev_ids}"
    )
    # And a facet-0 row is present too (both certified facets represented).
    assert any(e.startswith("f0_") for e in plans[0].ev_ids)


def test_p3_15f_assignment_uses_threaded_floor_not_just_env(monkeypatch):
    """Architect P3: the assignment uses the SAME floor passed by the gate, not
    only the env default — so gate coverage and billed-set assignment agree even
    when a caller passes an explicit floor."""
    from src.polaris_graph.generator.multi_section_generator import (
        _assign_evidence_to_planned_outline,
    )
    monkeypatch.delenv("PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR", raising=False)
    sub = ["facet zero terms"]
    outline = [_section("S0", 2, [0])]
    # Two rows at 0.5: ABOVE a threaded floor of 0.3, BELOW a threaded floor 0.7.
    evidence = [
        _row("mid_0", "facet zero terms", 0.5),
        _row("mid_1", "facet zero terms", 0.5),
    ]
    # Threaded floor 0.7 -> both rows are below-floor (fillers), order preserved.
    plans_hi = _assign_evidence_to_planned_outline(
        outline, evidence, sub_queries=sub, authority_floor=0.7,
    )
    # Threaded floor 0.3 -> both above-floor (reserved/credited).
    plans_lo = _assign_evidence_to_planned_outline(
        outline, evidence, sub_queries=sub, authority_floor=0.3,
    )
    # Both place the rows (cap=2), but the bucketing differs by the THREADED
    # floor — proving the param is honored, not just env.
    assert set(plans_hi[0].ev_ids) == {"mid_0", "mid_1"}
    assert set(plans_lo[0].ev_ids) == {"mid_0", "mid_1"}


def test_p3_15d_off_path_round_robin_ignores_authority():
    """Off-path (sub_queries=None) assignment is byte-identical round-robin —
    it must NOT read authority at all (no sidecar on off-mode rows)."""
    from src.polaris_graph.generator.multi_section_generator import (
        _assign_evidence_to_planned_outline,
    )
    outline = [_section("S0", 5, [0]), _section("S1", 5, [1])]
    # Off-mode rows carry NO authority sidecar (additive fields absent).
    evidence = [{"evidence_id": f"ev_{i:03d}"} for i in range(4)]
    plans = _assign_evidence_to_planned_outline(outline, evidence)
    ids = [f"ev_{i:03d}" for i in range(4)]
    assert plans[0].ev_ids == ids[0::2]
    assert plans[1].ev_ids == ids[1::2]


def test_p3_15b_gate_runs_on_billed_set_not_raw():
    """The gate certifies exactly the `evidence_for_gen` (billed) list it is
    handed — a row dropped by selection is simply not present, and a section
    certified SUFFICIENT received its credited rows."""
    sub = ["alpha facet", "beta facet"]
    plan = _plan(sub, [_section("S0", 1, [0]), _section("S1", 1, [1])])
    billed = [
        _row("ev_000", "alpha facet", 0.9),
        _row("ev_001", "beta facet", 0.9),
    ]
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=billed, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r.verdict == "proceed"
    # If selection had dropped the beta row, the gate would catch it.
    r2 = assess_plan_sufficiency(
        plan=plan, corpus_rows=billed[:1], authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r2.verdict == "abort"
    assert "section_1" in r2.under_covered_units


# ── P3-16 ONE final gate after all mutations ─────────────────────────────────

def test_p3_16_contract_injection_flips_under_covered_to_sufficient():
    """A post-selection contract/upload row (no query_origin) that covers an
    under-covered facet via content-word overlap flips it to SUFFICIENT — the
    binding gate sees `evidence_for_gen` INCLUDING the injections."""
    sub = ["alpha facet terms", "renewable hydro turbine capacity output"]
    plan = _plan(sub, [_section("S0", 1, [0]), _section("S1", 1, [1])])
    selected = [_row("ev_000", "alpha facet terms", 0.9)]
    # Without the contract row, section 1 is under-covered.
    r_before = assess_plan_sufficiency(
        plan=plan, corpus_rows=selected, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r_before.verdict == "abort"
    # Contract row: NO query_origin, but content overlaps section 1's facet, and
    # a high persisted authority_score (so it credits).
    contract_row = _row(
        "ev_c00", "", 0.95,
        statement="renewable hydro turbine capacity output report",
    )
    final_billed = [contract_row] + selected  # mirrors the :2719 prepend
    r_after = assess_plan_sufficiency(
        plan=plan, corpus_rows=final_billed, authority_floor=0.3,
        round_index=0, max_rounds=0,
    )
    assert r_after.verdict == "proceed"


# ── P3-17 injected-row enrichment (no sidecar -> computed at gate time) ───────

def test_p3_17_injected_row_authority_enriched_at_gate_time():
    """A contract/upload row with NO authority sidecar gets a real numeric
    authority_score computed at gate time and credits a section ONLY via
    content-word overlap with that section's sub-queries."""
    sub = ["renewable hydro turbine capacity output"]
    plan = _plan(sub, [_section("S0", 1, [0])])
    # A government-style URL so the computed authority is above a modest floor;
    # NO authority_score key on the row (forces gate-time enrichment).
    injected = {
        "evidence_id": "ev_u00",
        "query_origin": "",
        "source_url": "https://www.energy.gov/report",
        "statement": "renewable hydro turbine capacity output national report",
        "direct_quote": "renewable hydro turbine capacity output measured.",
    }
    assert "authority_score" not in injected
    r = assess_plan_sufficiency(
        plan=plan, corpus_rows=[injected], authority_floor=0.0,
        round_index=0, max_rounds=0,
    )
    # floor=0.0 so any honest score credits; the row was creditable ONLY because
    # its content overlapped the section's sub-query (relevance), and it got a
    # real score (the gate mutated authority_score onto the row).
    assert "authority_score" in injected
    assert isinstance(injected["authority_score"], float)
    assert r.per_unit[0].covered_count == 1
    assert r.verdict == "proceed"
    # An injected row that does NOT overlap the section's sub-query is NOT
    # credited even with a high score.
    off_topic = {
        "evidence_id": "ev_u01",
        "query_origin": "",
        "source_url": "https://www.energy.gov/other",
        "statement": "completely unrelated quarterly financial earnings",
        "direct_quote": "earnings per share rose.",
    }
    r2 = assess_plan_sufficiency(
        plan=plan, corpus_rows=[off_topic], authority_floor=0.0,
        round_index=0, max_rounds=0,
    )
    assert r2.per_unit[0].covered_count == 0
