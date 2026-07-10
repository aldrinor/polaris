"""S4 outline — Fable coverage + parse-robustness fix wave (items 2, 3c, 4a, 5a, 5b).

Each test reproduces the concrete defect the fix closes, on the SMALLEST branch-coverage input:

  item 2  — same-work TITLE fallback folds two TITLE-identical rows the cp3 URL/DOI groups missed;
            the >=25-alnum-char guard keeps two SHORT-title distinct works un-merged.
  item 4a — a T1 singleton is sorted to the TOP of the singleton block + carries a seminal marker
            when armed; default is byte-identical (pool order, no marker).
  item 5a — an unknown ev_id is STRIPPED (valid remainder kept), never hollowing a required section.
  item 5b — a duplicate title MERGES its ev_ids into the first occurrence instead of losing them.
  item 3c — the router's SINGLETON leg routes an on-topic high-tier singleton, DELETES a
            judge-confirmed off-topic one (fail-open), and is a no-op when the flag is OFF.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.outline_digest import build_outline_digest
from src.polaris_graph.generator.multi_section_generator import SectionPlan, _parse_outline
from src.polaris_graph.generator.verified_compose import (
    route_orphan_baskets_to_section_plans,
)


# ── item 2: normalized-title fallback fold ──────────────────────────────────────────────
def test_title_fallback_folds_identical_titles() -> None:
    ev = [
        {"evidence_id": "e1", "tier": "T1",
         "title": "GPTs are GPTs An Early Look at the Labor Market Impact Potential",
         "statement": "", "url": "http://arxiv.org/x"},
        {"evidence_id": "e2", "tier": "T1",
         "title": "GPTs are GPTs An Early Look at the Labor Market Impact Potential",
         "statement": "", "url": "http://govai.org/y"},
    ]
    # same_work_groups=[] => work-aware, but NO cp3 URL/DOI group unifies e1/e2.
    menu = build_outline_digest(ev, [], same_work_groups=[])
    assert menu.covered_ev_ids() >= {"e1", "e2"}          # nothing dropped (§-1.3)
    assert len(menu.singleton_lines) == 1                 # folded to ONE work line
    assert menu.singleton_alias_ev_ids.get("e1") == ["e2"]  # e2 disclosed as the fold


def test_title_fallback_does_not_merge_short_titles() -> None:
    ev = [
        {"evidence_id": "e1", "tier": "T3", "title": "OECD Policy", "statement": "a"},
        {"evidence_id": "e2", "tier": "T3", "title": "OECD Policy", "statement": "b"},
    ]
    menu = build_outline_digest(ev, [], same_work_groups=[])
    # "oecdpolicy" == 10 alnum chars < 25 => NOT folded (two distinct works stay distinct).
    assert len(menu.singleton_lines) == 2
    assert menu.singleton_alias_ev_ids == {}


# ── item 4a: T1 singletons lead + seminal marker (armed); byte-identical by default ──────
def test_tier1_singletons_sorted_to_top_and_marked() -> None:
    ev = [
        {"evidence_id": "e_t5", "tier": "T5", "title": "Recent Blog Post About A Thing",
         "statement": ""},
        {"evidence_id": "e_t1", "tier": "T1", "title": "Acemoglu Restrepo Automation And New Tasks",
         "statement": ""},
    ]
    armed = build_outline_digest(ev, [], same_work_groups=[], prioritize_tier1=True)
    assert armed.singleton_lines[0].startswith("e_t1 ")       # T1 leads despite pool order
    assert "[seminal T1" in armed.singleton_lines[0]          # marker present

    default = build_outline_digest(ev, [], same_work_groups=[])
    assert default.singleton_lines[0].startswith("e_t5 ")     # pool order preserved
    assert "[seminal T1" not in "\n".join(default.singleton_lines)


# ── item 5a: unknown ev_id stripped, required section kept (not hollowed) ────────────────
def test_unknown_ev_ids_stripped_keeps_required_section() -> None:
    raw = json.dumps({"sections": [
        {"title": "Required A", "focus": "f", "ev_ids": ["ev_1", "ev_bogus"]},
    ]})
    res = _parse_outline(
        raw, allowed_ev_ids={"ev_1", "ev_2"}, facet_titles=True,
        required_sections=["Required A"],
    )
    plan = next(p for p in res.plans if p.title == "Required A")
    assert plan.ev_ids == ["ev_1"]                            # bogus stripped, valid remainder kept
    assert plan.undersupplied is True                         # disclosed, not resurrected-empty
    assert any(rc.startswith("unknown_ev_ids") for rc in res.reason_codes)


def test_unknown_ev_ids_stripped_keeps_full_section() -> None:
    raw = json.dumps({"sections": [
        {"title": "Displacement", "focus": "f", "ev_ids": ["ev_1", "ev_bogus", "ev_2"]},
    ]})
    res = _parse_outline(raw, allowed_ev_ids={"ev_1", "ev_2"}, facet_titles=True)
    plan = next(p for p in res.plans if p.title == "Displacement")
    assert plan.ev_ids == ["ev_1", "ev_2"]                    # one bad id no longer drops the section
    assert plan.undersupplied is False


# ── item 5b: duplicate title merges ev_ids into first occurrence ─────────────────────────
def test_duplicate_title_merges_ev_ids_into_first() -> None:
    raw = json.dumps({"sections": [
        {"title": "Displacement", "focus": "f", "ev_ids": ["ev_1", "ev_2"]},
        {"title": "Displacement", "focus": "f2", "ev_ids": ["ev_2", "ev_3", "ev_4"]},
    ]})
    res = _parse_outline(
        raw, allowed_ev_ids={"ev_1", "ev_2", "ev_3", "ev_4"}, facet_titles=True,
    )
    dup = [p for p in res.plans if p.title == "Displacement"]
    assert len(dup) == 1                                      # merged, not two sections
    assert dup[0].ev_ids == ["ev_1", "ev_2", "ev_3", "ev_4"]  # 2nd block merged, dedup preserved
    assert any(rc.startswith("duplicate_title") for rc in res.reason_codes)


# ── item 3c: router singleton leg (route on-topic, delete confirmed off-topic, fail-open) ─
def test_router_singleton_leg_routes_and_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", "1")
    plans = [SectionPlan(
        title="Labor Market Productivity", focus="labor market productivity effects",
        ev_ids=["seed"], archetype="",
    )]
    cred = SimpleNamespace(baskets=[])  # no baskets => only the singleton leg exercises
    cands = [
        {"evidence_id": "e_on", "text": "generative ai labor productivity gains"},
        {"evidence_id": "e_off", "text": "unrelated tourism travel content"},
    ]
    out = route_orphan_baskets_to_section_plans(
        plans, cred, section_plan_cls=SectionPlan,
        off_topic_ev_ids={"e_off"}, singleton_candidates=cands,
    )
    sec = next(p for p in out if p.title == "Labor Market Productivity")
    assert "e_on" in sec.ev_ids                               # on-topic singleton routed by overlap
    assert all("e_off" not in p.ev_ids for p in out)         # confirmed off-topic DELETED everywhere


def test_router_singleton_failopen_keeps_uncertain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PG_ROUTE_ALL_BASKETS", "1")
    plans = [SectionPlan(title="Labor Market", focus="labor market", ev_ids=["seed"], archetype="")]
    cred = SimpleNamespace(baskets=[])
    cands = [{"evidence_id": "e_unc", "text": "tourism travel content unrelated"}]
    out = route_orphan_baskets_to_section_plans(
        plans, cred, section_plan_cls=SectionPlan,
        off_topic_ev_ids=None, singleton_candidates=cands,
    )
    all_ids = {e for p in out for e in p.ev_ids}
    assert "e_unc" in all_ids                                 # uncertain => KEPT (residual), never deleted


def test_router_flag_off_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PG_ROUTE_ALL_BASKETS", raising=False)
    plans = [SectionPlan(title="A", focus="a", ev_ids=["x"], archetype="")]
    cred = SimpleNamespace(baskets=[])
    out = route_orphan_baskets_to_section_plans(
        plans, cred, section_plan_cls=SectionPlan,
        singleton_candidates=[{"evidence_id": "e1", "text": "a"}],
    )
    assert out is plans                                       # early return, byte-identical
