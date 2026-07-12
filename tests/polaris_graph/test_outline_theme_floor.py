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


# ---------------------------------------------------------------------------
# Corpus-derived THEME-COVERAGE clustering (adds a dedicated section for a large
# corpus theme the seed under-covers). Query-agnostic + DETERMINISTIC.
# ---------------------------------------------------------------------------
import random as _random

from src.polaris_graph.outline.outline_agent import (
    _derive_theme_coverage_sections,
    _titlecase_terms,
)


class _P:
    def __init__(self, title, focus, ev_ids):
        self.title = title
        self.focus = focus
        self.ev_ids = list(ev_ids)


def _synth_corpus(themes, per=30, seed=1):
    rng = _random.Random(seed)
    ev = []
    i = 0
    for name, base in themes.items():
        words = base.split()
        for _ in range(per):
            rng.shuffle(words)
            ev.append({
                "evidence_id": f"ev_{i}", "title": f"{name} study {i}",
                "statement": base, "direct_quote": " ".join(words[:14]),
            })
            i += 1
    return ev


_MARINE = {
    "bleaching": "Coral bleaching driven by ocean warming and thermal stress causes zooxanthellae "
                 "expulsion and widespread reef mortality across tropical waters",
    "acidification": "Ocean acidification lowers seawater pH reducing calcium carbonate saturation "
                     "and impairing coral skeleton calcification and shell formation",
    "restoration": "Reef restoration through coral gardening larval seeding and transplantation of "
                   "nursery grown fragments rebuilds degraded reef habitat and biodiversity",
}


def test_theme_floor_adds_uncovered_theme_and_is_query_agnostic():
    # Different DOMAIN than task-72: proves the clustering derives themes from corpus text only,
    # never from any hardcoded labor/AI wording.
    ev = _synth_corpus(_MARINE)
    seed = [_P("Coral Bleaching and Thermal Stress", "bleaching", [f"ev_{j}" for j in range(30)])]
    new, diag = _derive_theme_coverage_sections(
        ev, seed, min_frac=0.05, max_new=3, cover_thresh=0.5,
    )
    titles = " ".join(p.title.lower() for p in new)
    # the seed-covered bleaching theme must NOT be re-added; the two uncovered themes must surface.
    assert "acidification" in titles
    assert "restoration" in titles
    assert "bleaching" not in titles
    # every added section carries only REAL corpus ev_ids (faithfulness: no invented evidence).
    all_ids = {r["evidence_id"] for r in ev}
    for p in new:
        assert p.ev_ids and all(e in all_ids for e in p.ev_ids)


def test_theme_floor_is_deterministic():
    ev = _synth_corpus(_MARINE)
    seed = [_P("Coral Bleaching and Thermal Stress", "bleaching", [f"ev_{j}" for j in range(30)])]
    a, _ = _derive_theme_coverage_sections(ev, seed, min_frac=0.05, max_new=3, cover_thresh=0.5)
    b, _ = _derive_theme_coverage_sections(ev, seed, min_frac=0.05, max_new=3, cover_thresh=0.5)
    assert [p.title for p in a] == [p.title for p in b]
    assert [p.ev_ids for p in a] == [p.ev_ids for p in b]


def test_theme_floor_rejects_scraping_boilerplate_cluster():
    # A big cluster of Cloudflare/PDF boilerplate rows must NOT become a section (low salience).
    boiler = ("Just a moment please enable javascript and cookies to continue Ray ID unusual "
              "activity from your network cloudflare checking your browser")
    themes = {"realtheme": "renewable solar photovoltaic energy generation capacity grid storage "
                           "battery deployment cost decline efficiency"}
    ev = _synth_corpus(themes, per=60)
    # inject 60 pure-boilerplate rows
    for j in range(60):
        ev.append({"evidence_id": f"junk_{j}", "title": "Attention Required", "statement": "",
                   "direct_quote": boiler})
    seed = [_P("Unrelated Seed", "unrelated", [])]
    new, diag = _derive_theme_coverage_sections(ev, seed, min_frac=0.05, max_new=3, cover_thresh=0.5)
    joined = " ".join(p.title.lower() for p in new)
    assert "cloudflare" not in joined and "moment" not in joined and "javascript" not in joined
    # a low-salience artifact cluster should be recorded as skipped somewhere in diag
    assert any(d.get("skipped") == "low_salience_artifact" for d in diag) or all(
        "cloudflare" not in " ".join(d.get("top_terms", [])) for d in diag if not d.get("skipped")
    )


def test_titlecase_dedupes_near_duplicate_prefixes():
    assert _titlecase_terms(["public", "regulation", "regulatory", "governance"]) == (
        "Public, Regulation and Governance"
    )
    assert _titlecase_terms(["skill"]) == "Skill"
