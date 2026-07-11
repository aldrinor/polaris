"""T1 toolkit (outline/outline_toolkit.py) — per-tool unit tests.

Every tool is READ-ONLY over the workspace or DETERMINISTIC-COMPUTE; no network. These lock the
behavior the redesign (PART 4) requires and the driver wiring (registered on the real agent).
"""
from __future__ import annotations

import asyncio

from src.polaris_graph.outline.outline_agent import OutlineAgent, OutlineWorkspace
from src.polaris_graph.outline.outline_toolkit import (
    _tool_calculator,
    _tool_coverage_audit,
    _tool_find_contradictions,
    _tool_get_evidence,
    _tool_list_baskets,
    _tool_preview_section_evidence,
    _tool_search_corpus,
    _tool_verified_compute,
    register_outline_toolkit,
)
from src.polaris_graph.tools.tool_registry import ToolRegistry


def _run(coro):
    return asyncio.run(coro)


def _ev():
    return {
        "ev_000": {"evidence_id": "ev_000", "title": "Adobe FY2016 10-K",
                   "direct_quote": "Adobe reported operating income of 1,493,602 for fiscal 2016.",
                   "source_url": "http://sec/adobe2016"},
        "ev_001": {"evidence_id": "ev_001", "title": "Adobe FY2015 10-K",
                   "direct_quote": "Adobe reported operating income of 903,095 for fiscal 2015.",
                   "source_url": "http://sec/adobe2015"},
        "ev_002": {"evidence_id": "ev_002", "title": "Weather report",
                   "direct_quote": "It was sunny in California all week.",
                   "source_url": "http://weather"},
    }


class _Plan:
    def __init__(self, title, ev_ids, basket_ids=None):
        self.title = title
        self.ev_ids = ev_ids
        self.basket_ids = basket_ids or []


class _Menu:
    def __init__(self, member_map, corr=None):
        self.basket_member_ev_ids = member_map
        self.basket_work_corroboration = corr or {}


def _ws(**kw):
    ws = OutlineWorkspace(research_question="Adobe operating income change", ev_store=_ev())
    for k, v in kw.items():
        setattr(ws, k, v)
    return ws


# --------------------------------------------------------------------------- calculator


def test_calculator_evaluates_pure_arithmetic():
    r = _run(_tool_calculator(_ws(), expression="(1493602-903095)*1000"))
    assert r.success and r.statistics["value"] == 590507000.0


def test_calculator_rejects_non_arithmetic():
    r = _run(_tool_calculator(_ws(), expression="__import__('os').system('x')"))
    assert not r.success and "formula_invalid" in (r.error or "")


def test_calculator_rejects_unbound_names():
    # constant-only: any bare name is unknown to the AST validator -> rejected, never evaluated.
    r = _run(_tool_calculator(_ws(), expression="revenue*2"))
    assert not r.success and "unknown_name:revenue" in (r.error or "")


def test_calculator_rejects_division_by_zero():
    r = _run(_tool_calculator(_ws(), expression="1/0"))
    assert not r.success and "eval_error" in (r.error or "")


# --------------------------------------------------------------------------- get_evidence


def test_get_evidence_returns_full_text():
    r = _run(_tool_get_evidence(_ws(), ev_id="ev_000"))
    assert r.success and "1,493,602" in r.markdown and r.source_evidence_ids == ["ev_000"]


def test_get_evidence_missing_row():
    r = _run(_tool_get_evidence(_ws(), ev_id="ev_999"))
    assert not r.success and r.error == "ev_not_found"


def test_get_evidence_truncates_at_max_chars():
    ws = _ws()
    ws.ev_store["ev_000"]["direct_quote"] = "A" * 5000
    r = _run(_tool_get_evidence(ws, ev_id="ev_000", max_chars=100))
    assert r.success and "truncated" in r.markdown


# --------------------------------------------------------------------------- search_corpus


def test_search_corpus_ranks_relevant_over_irrelevant():
    r = _run(_tool_search_corpus(_ws(), query="operating income fiscal", top_k=3))
    assert r.success
    # the two Adobe rows must rank above the weather row (which shares no query token)
    assert r.source_evidence_ids[:2] == ["ev_000", "ev_001"] or set(r.source_evidence_ids[:2]) == {"ev_000", "ev_001"}
    assert "ev_002" not in r.source_evidence_ids


def test_search_corpus_no_match():
    r = _run(_tool_search_corpus(_ws(), query="quantum chromodynamics"))
    assert r.success and r.statistics["matches"] == 0


def test_search_corpus_requires_query():
    r = _run(_tool_search_corpus(_ws(), query=""))
    assert not r.success and r.error == "missing_query"


# --------------------------------------------------------------------------- list_baskets


def test_list_baskets_reports_assignment_status():
    menu = _Menu({"b1": ["ev_000", "ev_001"], "b2": ["ev_002"]},
                 corr={"b1": 2, "b2": 1})
    ws = _ws(basket_menu=menu, outline_draft=[_Plan("S1", ["ev_000", "ev_001"])])
    r = _run(_tool_list_baskets(ws))
    assert r.success and r.statistics["baskets"] == 2
    assert "b1: 2 member(s), corroboration=2, assigned" in r.markdown
    assert "b2: 1 member(s), corroboration=1, unassigned" in r.markdown


def test_list_baskets_no_menu():
    r = _run(_tool_list_baskets(_ws()))
    assert r.success and r.statistics["baskets"] == 0


# --------------------------------------------------------------------------- coverage_audit


def test_coverage_audit_counts_residual_and_unassigned():
    menu = _Menu({"b1": ["ev_000"], "b2": ["ev_001"], "b3": ["ev_002"]})
    ws = _ws(basket_menu=menu, outline_draft=[_Plan("S1", ["ev_000"], basket_ids=["b1"])])
    r = _run(_tool_coverage_audit(ws))
    assert r.success
    # 1 of 3 ev rows assigned -> residual 2/3
    assert abs(r.statistics["residual"] - 0.6667) < 0.001
    assert r.statistics["unassigned_baskets"] == 2   # b2, b3
    assert r.statistics["sections_below_floor"] == 0  # S1 has a basket


def test_coverage_audit_flags_section_below_floor():
    ws = _ws(outline_draft=[_Plan("Empty", [], basket_ids=[])])
    r = _run(_tool_coverage_audit(ws))
    assert r.statistics["sections_below_floor"] == 1
    assert "BELOW FLOOR" in r.markdown


# --------------------------------------------------------------------------- preview_section_evidence


def test_preview_section_evidence_lists_assigned_rows():
    ws = _ws(outline_draft=[_Plan("Financials", ["ev_000", "ev_001"])])
    r = _run(_tool_preview_section_evidence(ws, section="Financials"))
    assert r.success and r.source_evidence_ids == ["ev_000", "ev_001"]
    assert "Adobe FY2016 10-K" in r.markdown


def test_preview_section_evidence_unknown_section():
    r = _run(_tool_preview_section_evidence(_ws(outline_draft=[]), section="Nope"))
    assert not r.success and r.error == "section_not_found"


# --------------------------------------------------------------------------- verified_compute (moat)


def test_verified_compute_renders_calc_token_and_registers_model():
    ws = _ws()
    dps = [
        {"evidence_id": "ev_000", "label": "o16", "context": "fiscal 2016", "value": "1493602", "unit": "k"},
        {"evidence_id": "ev_001", "label": "o15", "context": "fiscal 2015", "value": "903095", "unit": "k"},
    ]
    spec = {"model_id": "opinc_delta", "title": "t",
            "inputs": [
                {"name": "o16", "datapoint_ref": {"ev_id": "ev_000", "label": "o16", "context": "fiscal 2016", "value": "1493602", "unit": "k"}},
                {"name": "o15", "datapoint_ref": {"ev_id": "ev_001", "label": "o15", "context": "fiscal 2015", "value": "903095", "unit": "k"}}],
            "outputs": [{"name": "delta", "formula": "(o16-o15)*1000", "unit": "USD", "display_kind": "currency"}]}
    r = _run(_tool_verified_compute(ws, question="Adobe opinc delta", datapoints=dps, spec=spec,
                                    lead="Adobe operating income rose by"))
    assert r.success
    assert r.statistics["display_value"] == "$590,507,000.00"
    assert r.statistics["calc_token"].startswith("[#calc:opinc_delta:")
    # the model is registered so the token will verify downstream
    assert (r.statistics["model_id"], r.statistics["spec_hash"]) in ws.quantified_models


def test_verified_compute_fail_closed_on_bad_spec():
    ws = _ws()
    r = _run(_tool_verified_compute(ws, question="q", datapoints=[], spec={"bad": 1}))
    assert not r.success and ws.quantified_models == {}


def test_verified_compute_rejects_bad_arg_types():
    r = _run(_tool_verified_compute(_ws(), datapoints=None, spec=None))
    assert not r.success and r.error == "bad_args"


# --------------------------------------------------------------------------- find_contradictions


def _contradiction_ws(ev):
    return OutlineWorkspace(research_question="q", ev_store=dict(ev))


def test_find_contradictions_direction_conflict_surfaced_both_cited():
    ev = {
        "ev_a": {"evidence_id": "ev_a",
                 "direct_quote": "Drug X reduced mortality by 20% versus placebo (p<0.01)."},
        "ev_b": {"evidence_id": "ev_b",
                 "direct_quote": "Drug X increased mortality by 15% versus placebo (p=0.03)."},
    }
    r = _run(_tool_find_contradictions(_contradiction_ws(ev), ev_ids=["ev_a", "ev_b"]))
    assert r.success and r.statistics["conflicts"] == 1
    assert r.statistics["pairs"][0]["type"] == "direction_conflict"
    assert set(r.source_evidence_ids) == {"ev_a", "ev_b"}


def test_find_contradictions_magnitude_outlier_flagged_not_deleted():
    ev = {
        "ev_1": {"evidence_id": "ev_1", "direct_quote": "The incidence rate was 12.4 per 100,000."},
        "ev_2": {"evidence_id": "ev_2", "direct_quote": "The incidence rate was 12.1 per 100,000."},
        "ev_bad": {"evidence_id": "ev_bad",
                   "direct_quote": "The incidence rate was 12400 per 100,000."},
    }
    ws = _contradiction_ws(ev)
    r = _run(_tool_find_contradictions(ws, ev_ids=["ev_1", "ev_2", "ev_bad"]))
    assert r.success and r.statistics["conflicts"] >= 1
    assert any(p["type"] == "magnitude_outlier" for p in r.statistics["pairs"])
    # weight, don't filter (§-1.3): the outlier row is NEVER deleted from the pool.
    assert "ev_bad" in ws.ev_store


def test_find_contradictions_agreement_yields_zero_conflicts():
    ev = {
        "ev_1": {"evidence_id": "ev_1", "direct_quote": "The rate was 12.4 per 100,000."},
        "ev_2": {"evidence_id": "ev_2", "direct_quote": "The rate was 12.1 per 100,000."},
    }
    r = _run(_tool_find_contradictions(_contradiction_ws(ev), ev_ids=["ev_1", "ev_2"]))
    assert r.success and r.statistics["conflicts"] == 0


def test_find_contradictions_ignores_years_as_magnitudes():
    # bare 4-digit years must not be treated as magnitudes (would false-flag an outlier).
    ev = {
        "ev_1": {"evidence_id": "ev_1", "direct_quote": "In 2019 the value was 5.0 units."},
        "ev_2": {"evidence_id": "ev_2", "direct_quote": "In 2000 the value was 5.2 units."},
    }
    r = _run(_tool_find_contradictions(_contradiction_ws(ev), ev_ids=["ev_1", "ev_2"]))
    assert r.success and r.statistics["conflicts"] == 0


# --------------------------------------------------------------------------- registration wiring


def test_register_outline_toolkit_wires_all_tools_on_a_registry():
    reg = ToolRegistry()
    names = register_outline_toolkit(reg, _ws(), "stub/agent")
    for n in ("calculator", "get_evidence", "search_corpus", "list_baskets",
              "coverage_audit", "preview_section_evidence", "verified_compute",
              "find_contradictions"):
        assert n in names and reg.get_tool(n) is not None


def test_toolkit_is_registered_on_the_real_agent():
    ws = OutlineWorkspace(research_question="q", ev_store={})
    agent = OutlineAgent(workspace=ws, agent_model="stub/agent", max_turns=1, wall_seconds=5)
    for n in ("calculator", "verified_compute", "coverage_audit"):
        assert agent.registry.get_tool(n) is not None
