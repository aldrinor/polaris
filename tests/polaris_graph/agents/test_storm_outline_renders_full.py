"""§-1.4 behavioral replay-harness — STORM outline renders FULL + provably generator-routed
(I-beatboth-006 #1283 Fix B + Fix D). Offline, mocked structured call, NO network, NO spend.

Acceptance = the effect ACTUALLY FIRES (committed+green+Codex-approve != wired):

  Fix B (never-starved outline budget): `PG_STORM_OUTLINE_MAX_TOKENS` rides the call at the raised
  64000 reference (§9.1.8 — never starve). A non-truncated structured response returns the REAL 8-15
  thematic clusters, NOT the one-section-per-perspective `_fallback_outline`. PRE-FIX the in-code
  default was 32768 (and .env forced 16384, half the floor) -> a reasoning-first generator could
  truncate the outline JSON -> silent fall to fallback.

  Fix D (provably generator-routed): with `set_role_providers({"generator": <singleton>})` active and
  the outline call wrapped in `llm_role("generator")`, `current_role_provider()` resolves the
  GENERATOR SINGLETON at outline-call time (the EXACT provider the sections ride) — NOT the deepseek
  `role_provider_routing("generator")` chain. PRE-FIX (un-tagged) `current_role_provider()` returns
  None at outline-call time -> the resolver falls to the deepseek chain. This harness PROVES the tag
  is load-bearing: it FAILS on the un-tagged baseline and PASSES on the tagged fix.

FAITHFULNESS: the STORM outline is an ORGANIZATIONAL scaffold (its fallback is already a disclosed
degrade). Widening the budget + fixing the route only converts a silent truncate-to-fallback / mis-
route into the real full outline on the correct provider — no verify gate, no claim, is touched.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from src.polaris_graph.agents import storm_interviews as si
from src.polaris_graph.agents.storm_interviews import (
    StormConversation,
    StormOutlinePlan,
    _generate_outline_from_conversations,
)
from src.polaris_graph.benchmark import benchmark_run_capture as _pathb_capture

_GENERATOR_SINGLETON = "Friendli"  # the gate-resolved GLM-5.2 served provider (the sections' provider).
_QUERY = "What are the cardiovascular outcomes of GLP-1 receptor agonists?"


# A banked multi-perspective conversation fixture (no network — the conversations are pre-built).
def _banked_conversations() -> list[StormConversation]:
    return [
        StormConversation(
            perspective="Scientific",
            persona_name="Dr. Mechanism",
            rounds=[
                {"question": "What is the mechanism?", "answer": "GLP-1 RAs reduce MACE.",
                 "key_findings": ["MACE reduction", "weight loss"], "sources": ["s1"]},
            ],
        ),
        StormConversation(
            perspective="Clinical",
            persona_name="Dr. Trial",
            rounds=[
                {"question": "What do the trials show?", "answer": "SUSTAIN-6 showed benefit.",
                 "key_findings": ["SUSTAIN-6", "LEADER"], "sources": ["s2"]},
            ],
        ),
    ]


def _real_outline_plan() -> StormOutlinePlan:
    """A REAL multi-cluster outline (10 distinct thematic sections) — NOT one-per-perspective.

    Built from DICTS, not pre-constructed StormOutlineSection objects: the plan's
    `filter_invalid_sections` validator (mode='before') keeps ONLY `dict` items (it skips non-dicts),
    so passing model instances would silently drop every section to a 0-section plan. Dicts mirror the
    real LLM structured-output shape the validator consumes."""
    return StormOutlinePlan(
        sections=[
            {
                "title": f"Thematic cluster {i}",
                "description": f"Cluster {i} synthesis across perspectives.",
                "evidence_summary": f"Findings for cluster {i}.",
                "perspectives": ["Scientific", "Clinical"],
                "order": i,
            }
            for i in range(1, 11)
        ]
    )


def _is_fallback_shape(sections: list[dict], conversations: list[StormConversation]) -> bool:
    """The fallback is exactly one section per perspective, titled '<Perspective> Perspective'."""
    if len(sections) != len(conversations):
        return False
    fallback_titles = {f"{c.perspective.replace('_', ' ')} Perspective" for c in conversations}
    return {s["title"] for s in sections} == fallback_titles


class _CapturingClient:
    """A fake OpenRouterClient whose `generate_structured` records the role/provider resolved AT
    CALL TIME (so we can prove the outline call ran under the `generator` role) and returns a real
    multi-cluster plan. NO network, NO spend."""

    def __init__(self, plan: StormOutlinePlan) -> None:
        self._plan = plan
        self.captured_max_tokens: int | None = None
        self.captured_role: str | None = None
        self.captured_resolved_provider: str | None = None
        self.call_count = 0

    async def generate_structured(self, *, prompt, schema, max_tokens, reasoning_enabled):
        self.call_count += 1
        self.captured_max_tokens = max_tokens
        # Resolve EXACTLY as openrouter_client does at body-build time (current_role_provider reads
        # the ambient _ROLE contextvar set by llm_role + the _ROLE_PROVIDER mapping set by the gate).
        self.captured_role = _pathb_capture.current_llm_role()
        self.captured_resolved_provider = _pathb_capture.current_role_provider()
        return self._plan


def _run_outline(client) -> list[dict]:
    return asyncio.run(
        _generate_outline_from_conversations(client, _QUERY, _banked_conversations())
    )


@pytest.fixture
def _gate_role_providers():
    """Activate the gate's per-role resolved provider mapping (generator -> the GLM-5.2 singleton)
    for the duration of the test, then reset it (never leaks past the gate scope)."""
    token = _pathb_capture.set_role_providers({"generator": _GENERATOR_SINGLETON})
    try:
        yield
    finally:
        _pathb_capture.reset_role_providers(token)


# =====================================================================================================
# Fix B — the outline renders FULL (real clusters, raised budget), never the fallback.
# =====================================================================================================


def test_outline_rides_the_raised_64000_budget():
    """Fix B: the outline call carries the raised PG_STORM_OUTLINE_MAX_TOKENS (default 64000), never
    the starved 16384/32768. PRE-FIX the in-code default was 32768; POST-FIX it is 64000."""
    # Module default (env unset) is the raised reference.
    assert si.PG_STORM_OUTLINE_MAX_TOKENS == 64000
    client = _CapturingClient(_real_outline_plan())
    _run_outline(client)
    assert client.captured_max_tokens == 64000, (
        "the outline call must ride the raised 64000 budget so the multi-perspective JSON is never "
        "starved into a truncate-to-fallback"
    )


def test_outline_returns_real_clusters_not_fallback():
    """Fix B: a non-truncated structured response yields the REAL 8-15 thematic clusters, NOT the
    one-section-per-perspective `_fallback_outline`."""
    conversations = _banked_conversations()
    client = _CapturingClient(_real_outline_plan())
    sections = asyncio.run(_generate_outline_from_conversations(client, _QUERY, conversations))
    assert len(sections) == 10, "the real outline returns the LLM's thematic clusters"
    assert not _is_fallback_shape(sections, conversations), (
        "the outline must NOT be the one-section-per-perspective disclosed fallback"
    )


# =====================================================================================================
# Fix D — the outline is PROVABLY generator-routed (under the tag) vs un-routed (the pre-fix baseline).
# =====================================================================================================


def test_outline_resolves_generator_singleton_under_role_tag(_gate_role_providers):
    """Fix D: with the gate's role-provider mapping active, the outline call resolves the GENERATOR
    SINGLETON at call time (the EXACT provider the sections ride) — because Fix D wraps the call in
    `llm_role("generator")`. This is the load-bearing routability proof."""
    client = _CapturingClient(_real_outline_plan())
    _run_outline(client)
    assert client.captured_role == "generator", (
        "PRE-FIX FAILURE: the outline call did not run under the 'generator' role tag, so "
        "current_role_provider() would fall to the deepseek role_provider_routing chain. POST-FIX "
        "Fix D wraps the call in llm_role('generator')."
    )
    assert client.captured_resolved_provider == _GENERATOR_SINGLETON, (
        "the outline must resolve the SAME generator singleton the sections ride (gate-enforced "
        "single-valued served identity), not the deepseek chain"
    )


def test_untagged_baseline_does_not_resolve_the_singleton(_gate_role_providers):
    """Fix D load-bearing proof: WITHOUT the `llm_role('generator')` tag (the pre-fix behavior),
    current_role_provider() returns None at call time -> the resolver falls to the deepseek chain.
    This asserts the tag is what makes the route correct, so the harness FAILS on the un-tagged
    baseline and PASSES on the tagged fix."""
    # Resolve under NO role tag (simulating the pre-fix call site).
    resolved_without_tag = _pathb_capture.current_role_provider()
    assert resolved_without_tag is None, (
        "without the generator role tag the gate mapping does NOT resolve a provider, so the "
        "resolver falls to the deepseek role_provider_routing('generator') chain (the bug Fix D "
        "closes). The tag is load-bearing."
    )


def test_role_tag_does_not_leak_past_the_outline_call(_gate_role_providers):
    """Fix D scope: the `llm_role('generator')` ctx-mgr is scoped to JUST the outline call — the role
    is restored after, so STORM's other calls are not silently tagged generator."""
    assert _pathb_capture.current_llm_role() is None  # no ambient role before
    client = _CapturingClient(_real_outline_plan())
    _run_outline(client)
    assert _pathb_capture.current_llm_role() is None, (
        "the role tag must not leak past the scoped outline call"
    )


def test_gate_off_outline_still_renders_full_no_route_dependency():
    """Fix D gate-OFF behavior: with NO gate mapping active, the role tag resolves to None (falls back
    to the env path) — the worst case is a sub-optimal provider ORDER, never a 404, and the outline
    still renders full. The campaign always runs gated; this proves no hard route dependency."""
    assert _pathb_capture.current_role_provider() is None  # no gate mapping -> None
    client = _CapturingClient(_real_outline_plan())
    sections = _run_outline(client)
    assert len(sections) == 10, "gate-OFF the outline still renders the full real clusters"
    # Under the tag but with NO gate mapping, the resolved provider is None (env path), never a crash.
    assert client.captured_role == "generator"
    assert client.captured_resolved_provider is None
