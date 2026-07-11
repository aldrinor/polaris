"""H-corr: single-work-masquerade cases — corroboration_profile (redesign Category D #27).

Design PART 2 + redesign.md:217: a basket whose rows are all the SAME underlying work (a paper
mirrored across hosts, or one DOI cited three times) LOOKS like x3 multi-source corroboration but
is ONE work cited three times. Silently counting that single work as multi-work corroboration is a
FAIL. ``corroboration_profile`` (Category D #27) must surface DISTINCT-WORK counts (not member
rows) and FLAG the masquerade. A genuinely multi-work basket must NOT be false-flagged.

These are behavior-verifiable structural assertions on the tool's returned profile (never on prose).
"""
from __future__ import annotations

from tests.battery.harness import Assertion, BatteryCase


def _corroboration_profile_available() -> bool:
    try:
        from src.polaris_graph.outline import outline_toolkit  # noqa: PLC0415
    except Exception:
        return False
    return hasattr(outline_toolkit, "_tool_corroboration_profile")


class _Menu:
    def __init__(self, member_map, corr=None):
        self.basket_member_ev_ids = member_map
        self.basket_work_corroboration = corr or {}


# ── H-corr-1: three rows of ONE work (shared DOI) masquerading as x3 corroboration ──
async def _case_single_work_masquerade() -> list[Assertion]:
    if not _corroboration_profile_available():
        return [Assertion("corroboration_profile_registered", False,
                          "tool available", "tool absent", severity="S1",
                          detail="Category D #27 not yet built")]
    from src.polaris_graph.outline.outline_agent import OutlineWorkspace  # noqa: PLC0415
    from src.polaris_graph.outline.outline_toolkit import _tool_corroboration_profile  # noqa: PLC0415

    # Same DOI across three DIFFERENT hosts: the cp3 url-first digest key over-counts this as 3
    # works (basket_work_corroboration=3), the exact silent overcount redesign.md:217 warns about.
    ev = {
        "ev_0": {"evidence_id": "ev_0", "title": "Landmark Trial", "tier": "T1",
                 "doi": "10.1056/nejm.2020.1", "source_url": "https://nejm.org/full"},
        "ev_1": {"evidence_id": "ev_1", "title": "Landmark Trial (mirror)", "tier": "T2",
                 "doi": "10.1056/nejm.2020.1", "source_url": "https://medrxiv.org/preprint"},
        "ev_2": {"evidence_id": "ev_2", "title": "Landmark Trial press release", "tier": "T3",
                 "doi": "10.1056/nejm.2020.1", "source_url": "https://news.org/story"},
    }
    ws = OutlineWorkspace(research_question="Does the drug work?", ev_store=dict(ev))
    ws.basket_menu = _Menu({"b0": ["ev_0", "ev_1", "ev_2"]}, corr={"b0": 3})
    res = await _tool_corroboration_profile(ws, basket_id="b0")
    stats = getattr(res, "statistics", {}) or {}
    prof = (stats.get("profiles") or [{}])[0]
    return [
        # S0: the masquerade MUST be flagged — silently treating one work as multi-source is the
        # lethal over-corroboration faithfulness failure this tool exists to catch.
        Assertion("masquerade_flagged", prof.get("single_work_masquerade") is True,
                  True, prof.get("single_work_masquerade"), severity="S0"),
        # distinct WORKS is 1 (the honest count), not the 3 member rows.
        Assertion("distinct_works_is_one", prof.get("distinct_works") == 1,
                  1, prof.get("distinct_works"), severity="S0"),
        Assertion("member_rows_is_three", prof.get("members") == 3,
                  3, prof.get("members"), severity="S1"),
        # the silent-overcount tripwire fires (digest said 3, recompute says 1).
        Assertion("digest_disagreement_surfaced", prof.get("digest_disagreement") is True,
                  True, prof.get("digest_disagreement"), severity="S1"),
    ]


# ── H-corr-2: two genuinely distinct works must NOT be false-flagged ──────────
async def _case_genuine_multiwork_not_flagged() -> list[Assertion]:
    if not _corroboration_profile_available():
        return [Assertion("corroboration_profile_registered", False,
                          "tool available", "tool absent", severity="S1")]
    from src.polaris_graph.outline.outline_agent import OutlineWorkspace  # noqa: PLC0415
    from src.polaris_graph.outline.outline_toolkit import _tool_corroboration_profile  # noqa: PLC0415

    ev = {
        "ev_a": {"evidence_id": "ev_a", "title": "A randomized trial of therapy alpha",
                 "tier": "T1", "doi": "10.1/aaa", "source_url": "https://a.org/paper"},
        "ev_b": {"evidence_id": "ev_b", "title": "An independent cohort study of therapy beta",
                 "tier": "T1", "doi": "10.2/bbb", "source_url": "https://b.org/paper"},
    }
    ws = OutlineWorkspace(research_question="Do the therapies work?", ev_store=dict(ev))
    ws.basket_menu = _Menu({"b0": ["ev_a", "ev_b"]}, corr={"b0": 2})
    res = await _tool_corroboration_profile(ws, basket_id="b0")
    prof = ((getattr(res, "statistics", {}) or {}).get("profiles") or [{}])[0]
    return [
        Assertion("genuine_multiwork_not_flagged",
                  prof.get("single_work_masquerade") is False,
                  False, prof.get("single_work_masquerade"), severity="S1"),
        Assertion("distinct_works_is_two", prof.get("distinct_works") == 2,
                  2, prof.get("distinct_works"), severity="S1"),
        Assertion("two_independent_hosts", prof.get("independent_hosts") == 2,
                  2, prof.get("independent_hosts"), severity="S1"),
    ]


BATTERY_CASES = [
    BatteryCase("h_corr1_single_work_masquerade", "cross-domain", "corroboration_profile",
                _case_single_work_masquerade, xfail=False,
                note="corroboration_profile landed 2026-07-11 -> active"),
    BatteryCase("h_corr2_genuine_multiwork", "cross-domain", "corroboration_profile",
                _case_genuine_multiwork_not_flagged, xfail=False),
]
