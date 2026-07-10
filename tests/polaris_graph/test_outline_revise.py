"""Unit tests for S4 ORCH-3 revise loop core (Design 5 ORCH-3): outcomes, parse, apply.

Proves the deterministic apply contract — the section RE-OPEN (recompose) set + kept
byte-identity — on the fixture. Pure; no LLM.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.polaris_graph.generator.outline_revise import (
    apply_revision_ops,
    build_section_outcomes,
    find_orphan_baskets,
    parse_revision_ops,
    plan_signature,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "outline_digest" / "mini_bank.json"


def _bank() -> dict:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def _allowed(bank: dict) -> set[str]:
    allowed = {str(e) for e in bank["pool_ev_ids"]}
    return allowed


# ── outcomes / checklist ────────────────────────────────────────────────────
def test_section_outcomes_unused_and_dropped() -> None:
    bank = _bank()
    outcomes = build_section_outcomes(
        bank["plans"], bank["section_results"],
        basket_members=bank["basket_members"], basket_corroboration=bank["basket_corroboration"],
    )
    by_title = {o.title: o for o in outcomes}
    assert by_title["Glycemic Efficacy"].unused_ev_ids == ["ev04"]  # assigned, never cited
    assert by_title["Cost"].dropped is True
    assert by_title["Cost"].unused_ev_ids == ["ev06"]
    # B01 members ev05/ev09 were cited => not uncovered
    assert by_title["Weight and Safety"].uncovered_baskets == []


def test_uncovered_basket_detected() -> None:
    plans = [{"title": "S", "ev_ids": ["e1"], "basket_ids": ["B00"]}]
    results = {"S": {"verified_sentence_count": 1, "cited_ev_ids": ["e1"]}}
    outcomes = build_section_outcomes(
        plans, results, basket_members={"B00": ["e2", "e3"]}, basket_corroboration={"B00": 3},
    )
    assert outcomes[0].uncovered_baskets == ["B00"]  # no member cited


def test_find_orphan_baskets() -> None:
    plans = [{"title": "S", "basket_ids": ["B00"]}]
    orphans = find_orphan_baskets(plans, {"B00": 3, "B02": 2, "B03": 1})
    assert orphans == ["B02"]  # B02 corr>=2 unassigned; B03 corr<2 ignored; B00 assigned


# ── parse validation ────────────────────────────────────────────────────────
def test_parse_rejects_unknown_title_and_ev_id() -> None:
    bank = _bank()
    titles = [p["title"] for p in bank["plans"]]
    parsed = parse_revision_ops(bank["reviser_output"], allowed_ev_ids=_allowed(bank), plan_titles=titles)
    assert parsed.parse_failed is False
    reasons = {r["reason_code"] for r in parsed.rejected}
    assert any(r.startswith("unknown_title:Nonexistent Section") for r in reasons)
    assert any(r.startswith("unknown_ev_ids") for r in reasons)
    # keep / retitle / reassign(Cost) / add all accepted => 4
    kinds = sorted(op["op"] for op in parsed.ops)
    assert kinds == ["add", "keep", "reassign", "retitle"]


def test_parse_failed_on_garbage_is_fail_open() -> None:
    parsed = parse_revision_ops("not json {{{", allowed_ev_ids=set(), plan_titles=[])
    assert parsed.parse_failed is True
    assert parsed.ops == []


def test_parse_accepts_dict_input() -> None:
    parsed = parse_revision_ops({"ops": [{"op": "keep", "title": "S"}]},
                                allowed_ev_ids=set(), plan_titles=["S"])
    assert len(parsed.ops) == 1 and parsed.parse_failed is False


# ── apply engine ────────────────────────────────────────────────────────────
def test_apply_keep_is_byte_identical() -> None:
    bank = _bank()
    titles = [p["title"] for p in bank["plans"]]
    before = {p["title"]: plan_signature(p) for p in bank["plans"]}
    parsed = parse_revision_ops(bank["reviser_output"], allowed_ev_ids=_allowed(bank), plan_titles=titles)
    applied = apply_revision_ops(bank["plans"], parsed)
    assert "Glycemic Efficacy" in applied.kept_titles
    kept = next(p for p in applied.new_plans if p["title"] == "Glycemic Efficacy")
    assert plan_signature(kept) == before["Glycemic Efficacy"]


def test_apply_recompose_set_is_the_reopen_signal() -> None:
    bank = _bank()
    titles = [p["title"] for p in bank["plans"]]
    parsed = parse_revision_ops(bank["reviser_output"], allowed_ev_ids=_allowed(bank), plan_titles=titles)
    applied = apply_revision_ops(bank["plans"], parsed)
    assert applied.changed is True
    assert set(applied.recompose_titles) == {
        "Weight Reduction and Adverse Events",  # retitle
        "Cost",                                  # reassign
        "Cardiovascular Outcomes",               # add
    }
    final_titles = [p["title"] for p in applied.new_plans]
    assert "Weight and Safety" not in final_titles  # retitled away
    assert "Cardiovascular Outcomes" in final_titles
    # the reassign must actually MUTATE the plan, not merely recompose the title: ev07 is a
    # genuinely-new member for Cost and must appear in the recomposed plan's ev_ids.
    cost = next(p for p in applied.new_plans if p["title"] == "Cost")
    assert "ev07" in cost["ev_ids"]  # add_ev_ids member landed
    assert "ev06" in cost["ev_ids"]  # original member preserved


def test_reassign_ev_ids_alias_lands_members() -> None:
    # (a) a reassign carrying a bare `ev_ids` (no add_ev_ids/drop_ev_ids) must alias ev_ids ->
    # add_ev_ids so the members actually LAND in the target plan after apply. This is the fix for
    # the reproduced silent no-op: apply reads only add_ev_ids/drop_ev_ids, so an ev_ids-shaped
    # reassign used to recompose the section while dropping the payload.
    plans = [{"title": "Target", "ev_ids": ["e1"], "basket_ids": []}]
    parsed = parse_revision_ops(
        {"ops": [{"op": "reassign", "title": "Target", "ev_ids": ["e2"]}]},
        allowed_ev_ids={"e1", "e2"}, plan_titles=["Target"],
    )
    assert [op["op"] for op in parsed.ops] == ["reassign"]  # accepted, not rejected
    applied = apply_revision_ops(plans, parsed)
    target = next(p for p in applied.new_plans if p["title"] == "Target")
    assert "e2" in target["ev_ids"]  # aliased member landed in the plan
    assert "e1" in target["ev_ids"]  # original member preserved
    assert "Target" in applied.recompose_titles
    assert applied.changed is True


def test_reassign_payloadless_is_rejected_no_op() -> None:
    # (b) a reassign with neither add_ev_ids nor drop_ev_ids (nor a bare ev_ids) moves nothing:
    # reject it as no_op_reassign so it cannot fake changed=True or burn a recompose slot.
    plans = [{"title": "Target", "ev_ids": ["e1"], "basket_ids": []}]
    parsed = parse_revision_ops(
        {"ops": [{"op": "reassign", "title": "Target", "reason": "moves nothing"}]},
        allowed_ev_ids={"e1"}, plan_titles=["Target"],
    )
    assert parsed.ops == []
    assert any(r["reason_code"] == "no_op_reassign" for r in parsed.rejected)
    applied = apply_revision_ops(plans, parsed)
    assert applied.changed is False
    assert applied.recompose_titles == []
    assert "Target" not in applied.recompose_titles


def test_reassign_empty_lists_is_rejected_no_op() -> None:
    # a reassign that explicitly carries empty add_ev_ids AND empty drop_ev_ids is also a no-op.
    parsed = parse_revision_ops(
        {"ops": [{"op": "reassign", "title": "S", "add_ev_ids": [], "drop_ev_ids": []}]},
        allowed_ev_ids={"e1"}, plan_titles=["S"],
    )
    assert parsed.ops == []
    assert any(r["reason_code"] == "no_op_reassign" for r in parsed.rejected)


def test_reassign_pure_drop_is_kept() -> None:
    # a reassign that only DROPs members (empty/absent add) is a real op, not a no-op.
    plans = [{"title": "S", "ev_ids": ["e1", "e2"], "basket_ids": []}]
    parsed = parse_revision_ops(
        {"ops": [{"op": "reassign", "title": "S", "drop_ev_ids": ["e2"]}]},
        allowed_ev_ids={"e1", "e2"}, plan_titles=["S"],
    )
    assert [op["op"] for op in parsed.ops] == ["reassign"]
    applied = apply_revision_ops(plans, parsed)
    s = next(p for p in applied.new_plans if p["title"] == "S")
    assert s["ev_ids"] == ["e1"]  # e2 dropped
    assert "S" in applied.recompose_titles


def test_apply_merge_unions_ev_ids() -> None:
    plans = [
        {"title": "A", "ev_ids": ["e1", "e2"], "basket_ids": ["B0"]},
        {"title": "B", "ev_ids": ["e2", "e3"], "basket_ids": ["B1"]},
    ]
    parsed = parse_revision_ops(
        {"ops": [{"op": "merge", "titles": ["A", "B"], "new_title": "AB", "reason": "same theme"}]},
        allowed_ev_ids={"e1", "e2", "e3"}, plan_titles=["A", "B"],
    )
    applied = apply_revision_ops(plans, parsed)
    ab = next(p for p in applied.new_plans if p["title"] == "AB")
    assert ab["ev_ids"] == ["e1", "e2", "e3"]  # union, deduped, sorted
    assert [p["title"] for p in applied.new_plans] == ["AB"]  # A and B removed
    assert applied.recompose_titles == ["AB"]


def test_apply_split_recomposes_children() -> None:
    plans = [{"title": "Big", "ev_ids": ["e1", "e2"], "basket_ids": []}]
    parsed = parse_revision_ops(
        {"ops": [{"op": "split", "title": "Big", "into": [
            {"title": "Left", "ev_ids": ["e1"]}, {"title": "Right", "ev_ids": ["e2"]}]}]},
        allowed_ev_ids={"e1", "e2"}, plan_titles=["Big"],
    )
    applied = apply_revision_ops(plans, parsed)
    titles = [p["title"] for p in applied.new_plans]
    assert "Big" not in titles and "Left" in titles and "Right" in titles
    assert set(applied.recompose_titles) == {"Left", "Right"}


def test_apply_wholesale_invalid_keeps_wave1() -> None:
    bank = _bank()
    parsed = parse_revision_ops("garbage", allowed_ev_ids=set(), plan_titles=[])
    applied = apply_revision_ops(bank["plans"], parsed)
    assert applied.changed is False
    assert applied.recompose_titles == []
    assert [p["title"] for p in applied.new_plans] == [p["title"] for p in bank["plans"]]
    assert applied.kept_titles == [p["title"] for p in bank["plans"]]


def test_apply_respects_max_recompose_ceiling() -> None:
    plans = [{"title": f"S{i}", "ev_ids": ["e1"]} for i in range(5)]
    ops = [{"op": "retitle", "title": f"S{i}", "new_title": f"R{i}"} for i in range(5)]
    parsed = parse_revision_ops({"ops": ops}, allowed_ev_ids={"e1"},
                                plan_titles=[f"S{i}" for i in range(5)])
    applied = apply_revision_ops(plans, parsed, max_recompose_cap=2)
    assert len(applied.recompose_titles) == 2
    assert len(applied.deferred_ops) == 3
    assert all(d["reason_code"] == "max_recompose_ceiling" for d in applied.deferred_ops)


def test_ceiling_prioritizes_dropped_sections() -> None:
    plans = [{"title": "Good", "ev_ids": ["e1"]}, {"title": "Bad", "ev_ids": ["e1"]}]
    outcomes = build_section_outcomes(
        plans,
        {"Good": {"verified_sentence_count": 3, "cited_ev_ids": ["e1"]},
         "Bad": {"verified_sentence_count": 0, "cited_ev_ids": [], "dropped": True}},
    )
    parsed = parse_revision_ops(
        {"ops": [{"op": "retitle", "title": "Good", "new_title": "G2"},
                 {"op": "retitle", "title": "Bad", "new_title": "B2"}]},
        allowed_ev_ids={"e1"}, plan_titles=["Good", "Bad"],
    )
    applied = apply_revision_ops(plans, parsed, max_recompose_cap=1, outcomes=outcomes)
    assert applied.recompose_titles == ["B2"]  # dropped section wins the single slot
