"""RACE-FLOOR fix (2026-07-12): the corpus-derived thematic-coverage floor.

Two byte-identical full renders of DRB task 72 diverged on RACE (0.4447 vs 0.3518). The
low-scoring run's agentic outline loop, over more turns, issued ``merge`` ops that collapsed
distinct corpus themes (Wage-Inequality, Policy) into fewer, thinner sections. The floor caps NET
thematic reduction: the SEED outline's own section count (a query-agnostic corpus decomposition
built by ``_call_outline``) becomes a minimum the loop may not merge below. split/add still raise
the count; reassign/retitle/keep are count-neutral; only floor-violating merges are deferred.

Faithfulness-neutral: pure structural placement — strict_verify / NLI / [#calc] lane untouched.
"""
import asyncio

from src.polaris_graph.generator.outline_revise import (
    apply_revision_ops,
    parse_revision_ops,
)

SEED = [
    "Introduction and Scope",
    "Task-Based Frameworks",
    "Occupational Exposure",
    "Empirical Employment Evidence",
    "Productivity Effects",
    "Wage Inequality and Polarization",
    "Policy Implications",
    "Cross-Study Synthesis",
    "Conclusions and Research Gaps",
]


def _mk(titles):
    return [
        {"title": t, "focus": t, "ev_ids": [f"ev_{i}"], "basket_ids": []}
        for i, t in enumerate(titles)
    ]


def _run(ops, plans, floor):
    pr = parse_revision_ops(
        {"ops": ops},
        allowed_ev_ids={f"ev_{i}" for i in range(50)},
        plan_titles=[p["title"] for p in plans],
    )
    return apply_revision_ops(plans, pr, min_sections=floor)


def test_theme_collapsing_merge_deferred_under_floor():
    plans = _mk(SEED)
    ops = [{"op": "merge", "titles": ["Wage Inequality and Polarization", "Policy Implications"],
            "new_title": "Wage and Policy", "reason": "consolidate"}]
    r = _run(ops, plans, len(SEED))
    assert len(r.new_plans) == 9
    assert any("min_sections_floor" in str(d.get("reason_code")) for d in r.deferred_ops)
    titles = {p["title"] for p in r.new_plans}
    assert "Wage Inequality and Polarization" in titles
    assert "Policy Implications" in titles


def test_without_floor_merge_collapses_reproducing_regression():
    plans = _mk(SEED)
    ops = [{"op": "merge", "titles": ["Wage Inequality and Polarization", "Policy Implications"],
            "new_title": "Wage and Policy", "reason": "consolidate"}]
    r = _run(ops, plans, 0)  # legacy: no floor
    assert len(r.new_plans) == 8
    assert "Wage and Policy" in {p["title"] for p in r.new_plans}


def test_split_allowed_and_no_theme_lost():
    plans = _mk(SEED)
    ops = [
        {"op": "split", "title": "Task-Based Frameworks", "into": [
            {"title": "Displacement Effects", "ev_ids": ["ev_1"], "focus": "d"},
            {"title": "Reinstatement Effects", "ev_ids": ["ev_20"], "focus": "r"}]},
        {"op": "merge", "titles": ["Wage Inequality and Polarization", "Policy Implications"],
         "new_title": "Wage and Policy", "reason": "consolidate"},
    ]
    r = _run(ops, plans, len(SEED))
    # merge is ordered before split, so it is evaluated at count=9 and deferred; split then raises
    # the count to 10. No original theme is lost — the guard errs toward MORE coverage.
    assert len(r.new_plans) == 10
    t = {p["title"] for p in r.new_plans}
    assert {"Wage Inequality and Polarization", "Policy Implications",
            "Displacement Effects", "Reinstatement Effects"} <= t


def test_reassign_is_never_blocked_by_floor():
    plans = _mk(SEED)
    ops = [{"op": "reassign", "title": "Policy Implications", "add_ev_ids": ["ev_30", "ev_31"]}]
    r = _run(ops, plans, len(SEED))
    assert len(r.new_plans) == 9
    assert not any("min_sections_floor" in str(d.get("reason_code")) for d in r.deferred_ops)
    pol = next(p for p in r.new_plans if p["title"] == "Policy Implications")
    assert "ev_30" in pol["ev_ids"] and "ev_31" in pol["ev_ids"]


def test_cumulative_protection_across_op_batch():
    plans = _mk(SEED)
    ops = [
        {"op": "merge", "titles": ["Occupational Exposure", "Empirical Employment Evidence"],
         "new_title": "Exposure and Employment", "reason": "x"},
        {"op": "merge", "titles": ["Productivity Effects", "Cross-Study Synthesis"],
         "new_title": "Productivity and Synthesis", "reason": "y"},
    ]
    r = _run(ops, plans, len(SEED))
    assert len(r.new_plans) == 9
    blocked = [c for c in (str(d.get("reason_code")) for d in r.deferred_ops)
               if "min_sections_floor" in c]
    assert len(blocked) == 2


def test_workspace_seam_threads_floor():
    from src.polaris_graph.outline.outline_agent import OutlineWorkspace, _tool_update_outline
    from src.polaris_graph.generator.multi_section_generator import SectionPlan

    plans = [SectionPlan(title=t, focus=t, ev_ids=[f"ev_{i}"]) for i, t in enumerate(SEED)]
    ev_store = {f"ev_{i}": {"evidence_id": f"ev_{i}", "statement": "x"} for i in range(50)}
    ws = OutlineWorkspace(research_question="q", ev_store=ev_store,
                          outline_draft=list(plans), min_sections=len(plans))
    op = [{"op": "merge", "titles": ["Wage Inequality and Polarization", "Policy Implications"],
           "new_title": "Wage and Policy", "reason": "consolidate"}]
    asyncio.run(_tool_update_outline(ws, ops=op))
    assert len(ws.outline_draft) == 9
    tset = {p.title for p in ws.outline_draft}
    assert "Wage Inequality and Polarization" in tset and "Policy Implications" in tset
