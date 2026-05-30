"""Sweep-side deepener adapter (I-meta-002-q1d #942-deepener). Pure helpers + the event-loop-guarded
sync wrapper. NO network / NO real deepener (a FAKE async deepen_fn is injected). The no-laundering
property (thin deepened paper dropped) lives in run_live_retrieval's seed_urls chokepoint — exercised by
test_no_laundering below via a stubbed fetch.
"""

from __future__ import annotations

import asyncio

import pytest

from src.polaris_graph.retrieval.deepener_sweep_adapter import (
    build_deepener_state,
    discovered_urls,
    run_deepener_sync,
    should_trigger_deepener,
)


# --- Stop-RAG trigger predicate (Codex brief-gate required predicate) -----------------------------
def test_trigger_requires_flag_key_and_seed_evidence():
    base = dict(has_s2_key=True, has_seed_evidence=True, adequacy_decision="expand", total_uncovered=2)
    assert should_trigger_deepener(flag_on=True, **base) is True
    assert should_trigger_deepener(flag_on=False, **base) is False  # off by default
    assert should_trigger_deepener(flag_on=True, **{**base, "has_s2_key": False}) is False
    assert should_trigger_deepener(flag_on=True, **{**base, "has_seed_evidence": False}) is False


def test_trigger_only_on_borderline_corpus():
    # Comfortably adequate (proceed) + full coverage → do NOT deepen.
    assert should_trigger_deepener(
        flag_on=True, has_s2_key=True, has_seed_evidence=True,
        adequacy_decision="proceed", total_uncovered=0,
    ) is False
    # proceed but uncovered topics remain → deepen.
    assert should_trigger_deepener(
        flag_on=True, has_s2_key=True, has_seed_evidence=True,
        adequacy_decision="proceed", total_uncovered=1,
    ) is True
    # expand / abort → deepen (try to rescue before the abort gate).
    for dec in ("expand", "abort"):
        assert should_trigger_deepener(
            flag_on=True, has_s2_key=True, has_seed_evidence=True,
            adequacy_decision=dec, total_uncovered=0,
        ) is True


# --- build_deepener_state -------------------------------------------------------------------------
def test_build_deepener_state_shape():
    rows = [
        {"evidence_id": "ev_000", "source_url": "  https://a  "},  # stripped
        {"evidence_id": "ev_001", "url": "https://b"},            # falls back to url
        {"evidence_id": "ev_002"},                                 # no url → dropped
        {"evidence_id": "ev_003", "source_url": "   "},           # whitespace-only → dropped (P1)
    ]
    state = build_deepener_state(rows, "what is X?")
    assert state["iteration_count"] == 0
    assert state["original_query"] == "what is X?"
    assert state["evidence"] == [{"source_url": "https://a"}, {"source_url": "https://b"}]


# --- discovered_urls ------------------------------------------------------------------------------
def test_discovered_urls_dedup_and_cap():
    out = {"deepened_papers": [
        {"url": "https://x"}, {"url": "https://x"}, {"url": "https://y"}, {"url": ""}, {"no_url": 1},
        {"url": "https://z"},
    ]}
    assert discovered_urls(out, cap=2) == ["https://x", "https://y"]
    assert discovered_urls(out, cap=10) == ["https://x", "https://y", "https://z"]
    assert discovered_urls(None, cap=5) == []
    assert discovered_urls({}, cap=5) == []
    # Codex diff-gate iter-1 P1: cap<=0 returns NO urls (never one) and never a negative.
    assert discovered_urls(out, cap=0) == []
    assert discovered_urls(out, cap=-3) == []


# --- run_deepener_sync: event-loop guard (Codex brief-gate iter-1 P1) -----------------------------
async def _fake_deepen(state):
    return {"deepened_papers": [{"url": "https://paper1"}], "deepener_stats": {"rounds": 1}}


def test_run_deepener_sync_no_running_loop():
    # Normal sync sweep path: no running loop → asyncio.run.
    out = run_deepener_sync({"iteration_count": 0, "evidence": [], "original_query": "q"}, deepen_fn=_fake_deepen)
    assert out["deepened_papers"][0]["url"] == "https://paper1"


def test_run_deepener_sync_inside_running_loop_does_not_raise():
    # If a loop is already running (async test / embedded caller), it must NOT raise RuntimeError —
    # the coroutine runs in an isolated thread.
    async def _driver():
        return run_deepener_sync(
            {"iteration_count": 0, "evidence": [], "original_query": "q"}, deepen_fn=_fake_deepen
        )

    out = asyncio.run(_driver())
    assert out["deepener_stats"]["rounds"] == 1


def test_run_deepener_sync_real_path_uses_2arg_signature_and_closes_client(monkeypatch):
    """Regression for the real adapter call shape (Codex brief-gate iter-2 P0): the default path
    (no injected deepen_fn) must construct an OpenRouterClient and call the REAL 2-arg
    deepen_evidence(client, state), then close the client — so a future 1-arg drift is caught."""
    seen: dict = {}

    class _FakeClient:
        def __init__(self, *, model=None):
            seen["model"] = model

        async def close(self):
            seen["closed"] = True

    async def _fake_deepen_evidence(client, state):  # the REAL 2-arg signature
        seen["client"] = client
        seen["state_query"] = state["original_query"]
        return {"deepened_papers": [{"url": "https://p"}]}

    monkeypatch.setattr(
        "src.polaris_graph.agents.evidence_deepener.deepen_evidence", _fake_deepen_evidence
    )
    monkeypatch.setattr(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient", _FakeClient
    )
    out = run_deepener_sync({"iteration_count": 0, "evidence": [], "original_query": "qq"})
    assert isinstance(seen["client"], _FakeClient)   # 2-arg: a client was constructed + passed
    assert seen["state_query"] == "qq"
    assert seen.get("closed") is True                # client closed (no leak)
    assert out["deepened_papers"][0]["url"] == "https://p"


# --- no laundering: a thin deepened paper is dropped by the SAME chokepoint the seed_urls path runs
# (Codex brief-gate iter-1). The deepener feeds discovered URLs as `seed_urls` into run_live_retrieval,
# which fetches each and runs `is_content_starved` (drops thin) + `classify_source_tier` (tier from
# FETCHED content) — exactly the gate exercised by test_bug776_layer4_doi_seeds + test_r5_fix_d_*.
def test_no_laundering_thin_deepened_content_dropped_by_chokepoint():
    from src.polaris_graph.retrieval.live_retriever import is_content_starved

    # Abstract-only / thin fetched content → DROPPED (a deepened paper cannot earn T1 on metadata).
    assert is_content_starved("Short abstract only of a deepened paper.") is True
    assert is_content_starved("a" * 100) is True
    # Substantive fetched full text survives the starvation gate (then earns its tier from
    # classify_source_tier over the fetched content — never from the deepener's say-so).
    assert is_content_starved("Substantive clinical trial full text with real prose. " * 30) is False
