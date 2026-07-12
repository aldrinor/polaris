"""P1 degrade-tail REAL-CODE-PATH proof (criterion 3).

The prior proof for the grace 180->600 fix was a standalone asyncio reproduction plus a
constant-value assertion (tests/test_compose_config_guard.py::test_grace_default_parks_wall_for_mega_fetch).
This test drives the ACTUAL seam entry point ``run_outline_agent_or_legacy`` — the real
``asyncio.wait_for(agent.run(), timeout=agent.wall_seconds + grace)`` + except->degrade branch +
``digest_stats['outline_agent']['cp4_used']`` assignment — with a monkeypatched ``agent.run`` that
OVERSHOOTS the wall (a legit in-flight final turn, e.g. a slow mega-fetch, that runs past
``wall_seconds`` but is still making honest progress).

Same overshoot, two grace values:
  * grace too small  -> outer wait_for CANCELS the progressing turn -> cp4_used='agentic-degraded-seed'
  * grace >= 600 (the shipped default) -> the turn COMPLETES -> cp4_used='agentic'

Proving the grace value is the ONLY thing that flips a slow-but-healthy final turn from
degrade-to-seed to a clean agentic completion. Time is compressed (wall=1s, overshoot=2s) so the
mechanism is exercised without a real ~466s fetch.
"""
from __future__ import annotations

import asyncio

import pytest

import src.polaris_graph.outline.outline_agent as oa
from src.polaris_graph.generator.multi_section_generator import OutlineParseResult, SectionPlan


def _canned_parse_result() -> OutlineParseResult:
    return OutlineParseResult(
        plans=[
            SectionPlan(title="Introduction", focus="framing", ev_ids=["ev_1", "ev_2"]),
            SectionPlan(title="Evidence", focus="findings", ev_ids=["ev_2", "ev_3"]),
        ],
        ok=True,
    )


async def _run_with_overshoot(monkeypatch, *, grace_env: str, overshoot_s: float):
    # Force the agentic seam ON and a tiny wall so a controlled overshoot trips the inner wall.
    monkeypatch.setenv("PG_OUTLINE_AGENT", "1")
    monkeypatch.setenv("PG_OUTLINE_AGENT_WALL_SECONDS", "1")
    monkeypatch.setenv("PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS", grace_env)

    # Seed outline: return canned plans (no LLM). _call_outline is imported INSIDE the seam from the
    # generator module, so patch it at its definition module.
    import src.polaris_graph.generator.multi_section_generator as msg

    async def _fake_call_outline(*a, **k):
        return _canned_parse_result(), False, 0, 0

    monkeypatch.setattr(msg, "_call_outline", _fake_call_outline, raising=True)

    # The final in-flight turn overshoots the wall but keeps making progress: sleep past wall_seconds,
    # then return the (already-checkpointed-in-place) workspace exactly as the real loop would.
    async def _fake_run(self):
        await asyncio.sleep(overshoot_s)
        self.workspace.turn = 2  # a couple of honest agentic turns completed before returning
        return self.workspace

    monkeypatch.setattr(oa.OutlineAgent, "run", _fake_run, raising=True)

    evidence = [{"evidence_id": f"ev_{i}", "text": f"row {i}", "url": f"http://x/{i}"} for i in range(1, 4)]
    parse_result, _retry, _in, _out = await oa.run_outline_agent_or_legacy(
        research_question="does the grace park the wall for a slow final turn?",
        evidence=evidence,
        gen_model="test/model",
        outline_temperature=0.3,
        outline_max_tokens=100,
        domain="workforce",
        finding_clusters=[],
        same_work_groups=None,
    )
    return parse_result.digest_stats["outline_agent"]


@pytest.mark.asyncio
async def test_small_grace_degrades_overshooting_turn(monkeypatch):
    # wall=1s + grace=0s => outer timeout=1s; the final turn takes 2s => CANCELLED => degrade-to-seed.
    stats = await _run_with_overshoot(monkeypatch, grace_env="0", overshoot_s=2.0)
    assert stats["degraded_to_seed"] is True
    assert stats["cp4_used"] == "agentic-degraded-seed"
    assert "TimeoutError" in stats["degrade_reason"]


@pytest.mark.asyncio
async def test_default_grace_parks_wall_and_completes_agentic(monkeypatch):
    # Same 2s overshoot, but the SHIPPED default grace (600s) => outer timeout=601s => the turn
    # COMPLETES => clean agentic, no degrade-to-seed (the P1 fix).
    stats = await _run_with_overshoot(
        monkeypatch, grace_env=str(oa.PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS_DEFAULT), overshoot_s=2.0
    )
    assert stats["degraded_to_seed"] is False
    assert stats["cp4_used"] == "agentic"
    assert stats["degrade_reason"] == ""


@pytest.mark.asyncio
async def test_shipped_default_grace_is_600(monkeypatch):
    # Pin the fix: the default that parks the wall for a ~466s mega-fetch is 600 (raised from 180).
    assert oa.PG_OUTLINE_AGENT_RUN_TIMEOUT_GRACE_SECONDS_DEFAULT == 600
