"""BUG-9 (#1262): STORM must RESERVE a disclosed minimum wall-time slice for Phase 3
outline generation so the interview phase cannot consume the WHOLE budget and force the
degraded one-section-per-perspective fallback outline (the observed
``Time budget too low for outline generation (-32s) — using fallback outline`` log).

What these tests prove:

  1. ``_resolve_outline_time_reserve`` — env-driven (LAW VI): floor default when unset,
     explicit operator override wins outright, negative clamps to 0, garbage falls back to
     the floor with a warning.

  2. ``_STORM_OUTLINE_MIN_VIABLE_S`` — the historical magic ``15.0`` literal is now a named,
     env-overridable constant (LAW VI).

  3. REGRESSION (the OLD bug is gone): the per-persona interview budget is now sized off
     ``PG_STORM_MAX_TIME_SECONDS - elapsed - reserve``, i.e. it CARVES OUT the reserve
     before dividing across personas. Pre-fix it divided the whole remaining budget, leaving
     nothing for Phase 3. We capture the budget actually handed to each interview and assert
     it equals the reserve-aware value (strictly less than the old whole-budget value).

  4. DISCLOSURE (not a silent degrade): when the reserve still cannot be met, the fallback
     outline sections are LABELED ``storm_outline_degraded=True`` and a degrade reason is
     attached, so an observer sees the degrade rather than a green-looking outline.

Faithfulness (BUG-9 / #1262): the STORM outline is an organizational scaffold for routing
evidence to sections, NOT a verified-claim gate. Reserving time so the real outline runs can
only improve organization of the same evidence; it never drops or alters a verified claim.
The hard gates (strict_verify / NLI / 4-role / span-grounding) are untouched. All tests are
fully offline — no live LLM / paid calls.
"""

import asyncio

import pytest

import src.polaris_graph.agents.storm_interviews as storm
from src.polaris_graph.agents.storm_interviews import (
    StormConversation,
    _STORM_OUTLINE_TIME_RESERVE_FLOOR_S,
    _resolve_outline_time_reserve,
    run_storm_interviews,
)


# ───────────────────────── _resolve_outline_time_reserve ─────────────────────────


def test_reserve_unset_uses_floor_default(monkeypatch):
    monkeypatch.delenv("PG_STORM_OUTLINE_TIME_RESERVE_S", raising=False)
    assert _resolve_outline_time_reserve() == _STORM_OUTLINE_TIME_RESERVE_FLOOR_S == 90.0


def test_reserve_env_override_wins(monkeypatch):
    monkeypatch.setenv("PG_STORM_OUTLINE_TIME_RESERVE_S", "150")
    assert _resolve_outline_time_reserve() == 150.0  # LAW VI: explicit wins outright


def test_reserve_negative_clamps_to_zero(monkeypatch):
    monkeypatch.setenv("PG_STORM_OUTLINE_TIME_RESERVE_S", "-30")
    assert _resolve_outline_time_reserve() == 0.0


def test_reserve_garbage_falls_back_to_floor(monkeypatch):
    monkeypatch.setenv("PG_STORM_OUTLINE_TIME_RESERVE_S", "not-a-number")
    assert _resolve_outline_time_reserve() == _STORM_OUTLINE_TIME_RESERVE_FLOOR_S


def test_outline_min_viable_is_named_constant():
    # BUG-9: the historical magic 15.0 is now a named constant (LAW VI).
    assert storm._STORM_OUTLINE_MIN_VIABLE_S == 15.0


# ───────────────────────── helpers ─────────────────────────


def _make_personas(n):
    return [
        storm.StormPersona(
            perspective=f"Scientific{i}",
            name=f"Dr. Test {i}",
            expertise=f"unique expertise number {i} with distinct vocabulary {i}",
            question_focus=f"focus {i}",
        )
        for i in range(n)
    ]


def _base_state():
    return {
        "original_query": "what is the budget reservation behaviour",
        "region": "us",
        "web_results": [],
        "academic_results": [],
    }


# ───────────────────────── REGRESSION: reserve carved out of interview budget ─────────────────────────


def test_regression_interview_budget_carves_out_outline_reserve(monkeypatch):
    """OLD BUG: interview phase divided the WHOLE budget -> nothing left for Phase 3.

    NEW: per-persona budget == (MAX - elapsed - reserve) / n_personas, strictly less than the
    old whole-budget value by ~reserve/n. We capture the budget actually handed to each
    interview and assert the reserve was carved out.
    """
    monkeypatch.setenv("PG_STORM_OUTLINE_TIME_RESERVE_S", "120")
    # Large total + few personas so the per-persona value clears the 60s floor and the
    # reserve carve-out is observable in the arithmetic.
    monkeypatch.setattr(storm, "PG_STORM_ENABLED", True)
    monkeypatch.setattr(storm, "PG_STORM_MAX_TIME_SECONDS", 6000)
    monkeypatch.setattr(storm, "PG_STORM_PERSPECTIVES_COUNT", 2)

    n_personas = 2
    captured_budgets = []

    async def _fake_discover(client, query, existing_context, target_count):
        return _make_personas(n_personas)

    async def _fake_conduct(client, persona, query, region, max_rounds, time_budget_remaining):
        captured_budgets.append(time_budget_remaining)
        conv = StormConversation(
            perspective=persona.perspective,
            persona_name=persona.name,
            rounds=[{"question": "q", "answer": "a", "sources": [], "key_findings": []}],
        )
        return conv, []

    async def _fake_outline(client, query, conversations):
        # A "real" outline (non-fallback) — one section, not labeled degraded.
        return [{"title": "Real Section", "order": 1}]

    monkeypatch.setattr(storm, "_discover_perspectives", _fake_discover)
    monkeypatch.setattr(storm, "_conduct_interview", _fake_conduct)
    monkeypatch.setattr(storm, "_generate_outline_from_conversations", _fake_outline)

    result = asyncio.run(run_storm_interviews(client=object(), state=_base_state()))

    assert captured_budgets, "interviews never ran"
    # All personas share the same pre-allocated per-persona budget.
    per_persona = captured_budgets[0]

    # Reserve-aware expectation: (6000 - elapsed - 120) / 2. elapsed is tiny (no real LLM),
    # so the value sits just under (6000 - 120)/2 = 2940. The OLD (buggy) value would have
    # been ~6000/2 = 3000. Assert we are firmly on the reserve-aware side.
    old_whole_budget = 6000 / n_personas          # 3000.0  (pre-fix)
    reserve_aware_cap = (6000 - 120) / n_personas  # 2940.0  (post-fix, ignoring tiny elapsed)
    assert per_persona <= reserve_aware_cap + 1.0, (
        f"per-persona budget {per_persona} did not carve out the 120s reserve"
    )
    assert per_persona < old_whole_budget - 50.0, (
        f"per-persona budget {per_persona} looks like the OLD whole-budget division"
    )
    # The real outline ran (no degrade label).
    assert result["storm_outline"] == [{"title": "Real Section", "order": 1}]
    assert all("storm_outline_degraded" not in s for s in result["storm_outline"])


# ───────────────────────── DISCLOSURE: degrade is labeled, not silent ─────────────────────────


def test_outline_time_reserve_unmet_is_disclosed_on_fallback(monkeypatch):
    """When the interview phase overruns even the reserve, the fallback outline is LABELED.

    We force ``remaining <= _STORM_OUTLINE_MIN_VIABLE_S`` deterministically: the total budget
    (50s) clears the pre-interview skip guard (remaining > 30 at start), the interview runs
    fast, then the MIN_VIABLE floor is set ABOVE the remaining budget (60 > ~50) so the Phase 3
    guard trips without depending on wall-clock burn. We then assert the fallback sections carry
    the disclosure flag rather than silently masquerading as a real outline.
    """
    monkeypatch.setenv("PG_STORM_OUTLINE_TIME_RESERVE_S", "5")
    monkeypatch.setattr(storm, "PG_STORM_ENABLED", True)
    # 50s clears the pre-interview skip guard (remaining <= 30 -> skip); MIN_VIABLE set above
    # the remaining budget so Phase 3 deterministically takes the DISCLOSED fallback path.
    monkeypatch.setattr(storm, "PG_STORM_MAX_TIME_SECONDS", 50)
    monkeypatch.setattr(storm, "PG_STORM_PERSPECTIVES_COUNT", 1)
    monkeypatch.setattr(storm, "_STORM_OUTLINE_MIN_VIABLE_S", 60.0)

    async def _fake_discover(client, query, existing_context, target_count):
        return _make_personas(1)

    async def _fake_conduct(client, persona, query, region, max_rounds, time_budget_remaining):
        conv = StormConversation(
            perspective=persona.perspective,
            persona_name=persona.name,
            rounds=[{"question": "q", "answer": "a", "sources": [], "key_findings": ["finding one is long enough"]}],
        )
        return conv, []

    # Sentinel: a real-outline patch that, if ever called, would FAIL the test (we must degrade).
    real_outline_called = {"hit": False}

    async def _fake_outline(client, query, conversations):
        real_outline_called["hit"] = True
        return [{"title": "Should Not Run", "order": 1}]

    monkeypatch.setattr(storm, "_discover_perspectives", _fake_discover)
    monkeypatch.setattr(storm, "_conduct_interview", _fake_conduct)
    monkeypatch.setattr(storm, "_generate_outline_from_conversations", _fake_outline)

    result = asyncio.run(run_storm_interviews(client=object(), state=_base_state()))

    outline = result["storm_outline"]
    assert outline, "fallback outline must still produce sections (disclose, don't drop)"
    assert not real_outline_called["hit"], "should have degraded to the fallback outline"
    # DISCLOSURE: every fallback section is labeled — not a silent degrade.
    assert all(s.get("storm_outline_degraded") is True for s in outline)
    assert all(
        s.get("storm_outline_degrade_reason") == "outline_time_reserve_unmet" for s in outline
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
