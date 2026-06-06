"""FX-19 (I-ready-017 #1127): PG_AMPLIFICATION_VARIANTS is RETIRED from the advertised slate.

The knob is consumed ONLY in the legacy static branch of `execute_searches`
(searcher.py amplification block), which is unreachable on the agentic slate — the function
returns `execute_agentic_search(...)` early when `PG_AGENTIC_SEARCH_ENABLED` is on. These offline
behavioral tests PROVE that claim (the benchmark runs agentic, so the knob is inert there) and that
the doc/comment-only RETIRE did NOT sever the legacy non-agentic lane that still uses it.
No network. FX-19 makes no code-logic change — comments + advertised-slate doc annotation only.
"""
from __future__ import annotations

import asyncio

import src.polaris_graph.agents.searcher as searcher


def _state(sub_queries):
    return {"sub_queries": list(sub_queries), "region": "global", "original_query": "q"}


def test_amplifier_unreachable_under_agentic_slate(monkeypatch):
    """Core RETIRE proof: with PG_AGENTIC_SEARCH_ENABLED=1, execute_searches hands off to the agentic
    loop BEFORE the amplification block, so PG_AMPLIFICATION_VARIANTS is never consulted."""
    monkeypatch.setattr(searcher, "PG_AGENTIC_SEARCH_ENABLED", True)

    agentic_called = {"n": 0}

    async def _fake_agentic(state, client):
        agentic_called["n"] += 1
        return {"web_results": [], "academic_results": []}

    monkeypatch.setattr(searcher, "execute_agentic_search", _fake_agentic)

    def _boom():
        raise AssertionError("_import_amplifier reached under the agentic slate — knob is NOT inert!")

    monkeypatch.setattr(searcher, "_import_amplifier", _boom)

    out = asyncio.run(searcher.execute_searches(_state(["a", "b"]), client=object()))
    assert agentic_called["n"] == 1                 # agentic path taken
    assert out == {"web_results": [], "academic_results": []}
    # _import_amplifier never raised -> the amplification block (and the variants knob) was skipped.


def test_legacy_static_path_still_consults_variants_knob(monkeypatch):
    """Regression guard: with PG_AGENTIC_SEARCH_ENABLED=0 the legacy lane still enters the
    amplification block and PG_AMPLIFICATION_VARIANTS still governs the cap (doc/comment-only RETIRE
    did not delete the legacy behavior)."""
    monkeypatch.setattr(searcher, "PG_AGENTIC_SEARCH_ENABLED", False)
    monkeypatch.setattr(searcher, "PG_AMPLIFICATION_ENABLED", True)
    monkeypatch.setattr(searcher, "PG_AMPLIFICATION_VARIANTS", 2)
    monkeypatch.setattr(searcher, "PG_CITATION_CHASE_ENABLED", False)

    monkeypatch.setattr(searcher, "_import_search_tools", lambda: (object(), object()))

    amplifier_called = {"n": 0}

    def _fake_import_amplifier():
        def _amplify(sub_queries, region=None):
            amplifier_called["n"] += 1
            # return more than the cap so we can prove the cap (original_count * VARIANTS) is applied
            return [f"v{i}" for i in range(10)]
        return _amplify

    monkeypatch.setattr(searcher, "_import_amplifier", _fake_import_amplifier)

    seen_web_queries = {}

    async def _fake_web(web_search_fn, web_queries, region, client=None, original_query=None):
        seen_web_queries["q"] = list(web_queries)
        return []

    async def _fake_academic(academic_search_fn, academic_queries):
        return []

    async def _fake_exa(sub_queries):
        return []

    async def _fake_ddg(web_queries, web_results, region):
        return web_results

    monkeypatch.setattr(searcher, "_adaptive_web_search", _fake_web)
    monkeypatch.setattr(searcher, "_run_academic_searches", _fake_academic)
    monkeypatch.setattr(searcher, "_run_exa_searches", _fake_exa)
    monkeypatch.setattr(searcher, "_run_ddg_fallback_for_zeros", _fake_ddg)

    out = asyncio.run(searcher.execute_searches(_state(["only-one"]), client=None))
    assert amplifier_called["n"] == 1                          # legacy lane DID consult the amplifier
    # original_count=1, VARIANTS=2 -> cap=2: the 10 amplified queries are trimmed to 2.
    assert seen_web_queries["q"] == ["v0", "v1"]
    assert out["status"] == "analyzing"
