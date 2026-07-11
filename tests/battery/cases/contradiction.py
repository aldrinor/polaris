"""H07 / H22 contradiction cases — marked xfail until find_contradictions lands.

Design PART 2: a corpus with two sources reporting OPPOSITE effect direction on the same endpoint
(H07), or one absurd 1000x outlier contradicted by corroborating sources (H22), must surface the
CONFLICT as named outline material — never silently average, never silently delete (§-1.3 weight,
don't filter). The capability tool is ``find_contradictions`` (redesign Category D #26), not yet
registered. These cases are ``xfail=True``: they FAIL today (the tool is absent) and will flip to
measured PASS when the tool lands. An xfail that PASSES is reported as ``xpass`` — the signal to
land the case into the active set.
"""
from __future__ import annotations

from tests.battery.harness import Assertion, BatteryCase


def _find_contradictions_available() -> bool:
    try:
        from src.polaris_graph.outline import outline_toolkit  # noqa: PLC0415
    except Exception:
        return False
    return hasattr(outline_toolkit, "_tool_find_contradictions")


# ── H07: two RCTs, opposite effect direction on the same endpoint ─────────────
async def _case_h07_opposite_direction() -> list[Assertion]:
    if not _find_contradictions_available():
        return [Assertion("find_contradictions_registered", False,
                          "tool available", "tool absent", severity="S1",
                          detail="Category D #26 not yet built")]
    from src.polaris_graph.outline.outline_agent import OutlineWorkspace  # noqa: PLC0415
    from src.polaris_graph.outline.outline_toolkit import _tool_find_contradictions  # noqa: PLC0415

    ev = {
        "ev_a": {"evidence_id": "ev_a",
                 "direct_quote": "Drug X reduced mortality by 20% versus placebo (p<0.01)."},
        "ev_b": {"evidence_id": "ev_b",
                 "direct_quote": "Drug X increased mortality by 15% versus placebo (p=0.03)."},
    }
    ws = OutlineWorkspace(research_question="Does Drug X affect mortality?", ev_store=dict(ev))
    res = await _tool_find_contradictions(ws, ev_ids=["ev_a", "ev_b"])
    stats = getattr(res, "statistics", {}) or {}
    conflicts = stats.get("conflicts", 0)
    return [
        Assertion("conflict_surfaced", conflicts >= 1, ">=1 conflict pair", conflicts,
                  severity="S0"),
        Assertion("both_sides_cited",
                  set(getattr(res, "source_evidence_ids", []) or []) >= {"ev_a", "ev_b"},
                  {"ev_a", "ev_b"}, getattr(res, "source_evidence_ids", []), severity="S0"),
    ]


# ── H22: one 1000x-off outlier contradicted by 3 corroborating sources ────────
async def _case_h22_absurd_outlier() -> list[Assertion]:
    if not _find_contradictions_available():
        return [Assertion("find_contradictions_registered", False,
                          "tool available", "tool absent", severity="S1",
                          detail="Category D #26 not yet built")]
    from src.polaris_graph.outline.outline_agent import OutlineWorkspace  # noqa: PLC0415
    from src.polaris_graph.outline.outline_toolkit import _tool_find_contradictions  # noqa: PLC0415

    ev = {
        "ev_1": {"evidence_id": "ev_1", "direct_quote": "The incidence rate was 12.4 per 100,000."},
        "ev_2": {"evidence_id": "ev_2", "direct_quote": "The incidence rate was 12.1 per 100,000."},
        "ev_3": {"evidence_id": "ev_3", "direct_quote": "The incidence rate was 12.8 per 100,000."},
        "ev_bad": {"evidence_id": "ev_bad",
                   "direct_quote": "The incidence rate was 12400 per 100,000."},
    }
    ws = OutlineWorkspace(research_question="What is the incidence rate?", ev_store=dict(ev))
    res = await _tool_find_contradictions(ws, ev_ids=["ev_1", "ev_2", "ev_3", "ev_bad"])
    stats = getattr(res, "statistics", {}) or {}
    return [
        Assertion("outlier_flagged", stats.get("conflicts", 0) >= 1, ">=1 conflict", stats,
                  severity="S0"),
        Assertion("outlier_not_deleted", "ev_bad" in (ws.ev_store or {}),
                  "ev_bad kept (weight, don't filter)", "ev_bad" in ws.ev_store, severity="S0"),
    ]


BATTERY_CASES = [
    BatteryCase("h07_opposite_direction", "medical", "find_contradictions",
                _case_h07_opposite_direction, xfail=False,
                note="find_contradictions landed 2026-07-11 -> active"),
    BatteryCase("h22_absurd_outlier", "medical", "find_contradictions+weight_dont_filter",
                _case_h22_absurd_outlier, xfail=False),
]
