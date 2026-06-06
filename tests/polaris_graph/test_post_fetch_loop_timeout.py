"""I-bug-115 (#554) — the post-retrieval candidate loop is wall-clock-bounded.

`run_live_retrieval`'s post-`parallel_fetch` candidate loop is synchronous.
Its only indefinite-block operation is `_openalex_enrich`, whose
`httpx.Client(timeout=...)` bounds each request *phase* but NOT total request
time — a byte-trickling / wedged OpenAlex response is never hard-bounded, so
one wedged enrich call hangs the whole run with no terminal verdict (#554,
demo-fatal).

Layer 1: `_bounded_openalex_enrich` runs the call in a daemon thread and
abandons it past `PG_OPENALEX_ENRICH_DEADLINE`. Layer 2: an overall
`PG_POST_FETCH_LOOP_BUDGET` wall-clock budget breaks the loop. Layer 3 (not
asserted here): per-candidate progress logging.

No network — the hang is modelled with `time.sleep`; all of
`run_live_retrieval`'s network deps are monkeypatched.
"""

from __future__ import annotations

import sys
import time
import types
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.polaris_graph.retrieval import live_retriever as lr


# ── Layer 1 — _bounded_openalex_enrich unit tests ──────────────────────────


def test_bounded_openalex_enrich_returns_within_deadline(monkeypatch):
    """A wedged _openalex_enrich is abandoned at PG_OPENALEX_ENRICH_DEADLINE;
    the wrapper returns {} within the bound and records the timeout."""
    monkeypatch.setenv("PG_OPENALEX_ENRICH_DEADLINE", "1")
    monkeypatch.setattr(lr, "_openalex_enrich",
                        lambda url, title: time.sleep(3600))

    stats: dict[str, int] = {}
    start = time.monotonic()
    result = lr._bounded_openalex_enrich("https://x.test/a", "title", stats)
    elapsed = time.monotonic() - start

    assert elapsed < 2.5, f"_bounded_openalex_enrich took {elapsed:.1f}s — not bounded"
    assert result == {}
    assert stats.get("enrich_timeouts") == 1


def test_bounded_openalex_enrich_passes_through_success(monkeypatch):
    """A fast _openalex_enrich result passes through untouched."""
    monkeypatch.setenv("PG_OPENALEX_ENRICH_DEADLINE", "30")
    payload = {"openalex_pub_type": "article", "openalex_full_title": "X"}
    monkeypatch.setattr(lr, "_openalex_enrich",
                        lambda url, title: dict(payload))

    result = lr._bounded_openalex_enrich("https://x.test/a", "title")
    assert result == payload


def test_bounded_openalex_enrich_converts_raise_to_empty(monkeypatch):
    """A raising _openalex_enrich is converted to {} — never propagated."""
    monkeypatch.setenv("PG_OPENALEX_ENRICH_DEADLINE", "30")

    def _raises(url, title):
        raise RuntimeError("openalex blew up")

    monkeypatch.setattr(lr, "_openalex_enrich", _raises)
    result = lr._bounded_openalex_enrich("https://x.test/a", "title")
    assert result == {}


# ── helper — stub run_live_retrieval's network deps ────────────────────────


def _stub_pipeline(monkeypatch, n, openalex_impl):
    """Stub serper / s2 / filter / fetch so run_live_retrieval's post-fetch
    loop runs over `n` synthetic candidates with zero network."""
    monkeypatch.setenv("PG_USE_PARALLEL_FETCH", "0")  # serial path
    # FX-18 (#1122) wired openalex_search (default-ON) into run_live_retrieval. This stub is
    # explicitly "zero network", so disable that academic backend here — otherwise it hits the real
    # OpenAlex API and adds non-deterministic candidates (breaks the n-candidate count assertions).
    monkeypatch.setenv("PG_OPENALEX_SEARCH", "0")
    hits = [
        {"url": f"https://example.test/doc-{i}",
         "title": f"Carbon pricing household energy costs study {i}",
         "snippet": "carbon pricing household energy costs"}
        for i in range(n)
    ]
    monkeypatch.setattr(lr, "_serper_search", lambda q, num=10, api_calls=None: list(hits))
    monkeypatch.setattr(lr, "_s2_bulk_search", lambda q, limit=20: [])
    monkeypatch.setattr(
        lr, "filter_search_results",
        lambda candidates, question: types.SimpleNamespace(
            kept=list(candidates), total_kept=len(candidates),
            total_dropped=0,
        ),
    )
    monkeypatch.setattr(
        lr, "_fetch_content",
        lambda url, n_chars, doi_hint="", pmid_hint="": (
            "Carbon pricing raised household energy costs across several "
            "Canadian provinces during the study period; the effect was "
            "partly offset by federal rebates and varied by region and by "
            "household income decile in the published evidence reviewed.",
            True, "Study title", "article", "",
        ),
    )
    monkeypatch.setattr(lr, "_openalex_enrich", openalex_impl)


# ── Layer 1 integration + Layer 2 ──────────────────────────────────────────


def test_run_live_retrieval_bounded_when_openalex_wedges(monkeypatch):
    """run_live_retrieval reaches a terminal verdict (returns) even when
    every _openalex_enrich call wedges — candidates are still classified."""
    monkeypatch.setenv("PG_OPENALEX_ENRICH_DEADLINE", "1")
    _stub_pipeline(monkeypatch, n=4,
                   openalex_impl=lambda url, title: time.sleep(3600))

    start = time.monotonic()
    result = lr.run_live_retrieval(
        research_question="carbon pricing household energy costs Canada",
        protocol=None, domain=None,
    )
    elapsed = time.monotonic() - start

    # 4 candidates x 1s enrich bound, fail-fast after 3 timeouts → well
    # under 15s. Without the bound this run would hang indefinitely.
    assert elapsed < 15.0, f"run_live_retrieval took {elapsed:.1f}s — not bounded"
    assert len(result.classified_sources) == 4


def test_post_fetch_loop_budget_breaks_the_loop(monkeypatch):
    """The overall PG_POST_FETCH_LOOP_BUDGET stops the loop early. Made
    deterministic with a real 0.3s per-candidate enrich delay so the budget
    is reliably crossed regardless of host speed (Codex brief P2-1)."""
    monkeypatch.setenv("PG_POST_FETCH_LOOP_BUDGET", "0.5")
    # I-ready-003 (#1074): the loop budget now SCALES with fetch_cap —
    # max(env floor, fetch_cap * PG_POST_FETCH_PER_URL_BUDGET). Pin the per-URL term tiny so the explicit
    # 0.5s floor wins (fetch_cap * 0.001 stays well under 0.5) and this loop-breaker regression still fires.
    monkeypatch.setenv("PG_POST_FETCH_PER_URL_BUDGET", "0.001")
    _stub_pipeline(
        monkeypatch, n=8,
        openalex_impl=lambda url, title: (time.sleep(0.3) or {}),
    )

    result = lr.run_live_retrieval(
        research_question="carbon pricing household energy costs Canada",
        protocol=None, domain=None,
    )

    # 8 candidates x 0.3s = 2.4s >> 0.5s budget → loop breaks early; the run
    # still returns (terminal verdict) with the candidates processed so far.
    assert 1 <= len(result.classified_sources) < 8
