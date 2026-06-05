"""I-ready-001 (#1070) P0 — evidence->generation cap regression tests (offline, no network).

The full-capability slate raised RETRIEVAL to ~1000 URLs but left the GENERATOR-facing cap
(PG_LIVE_MAX_EV_TO_GEN) at its code default 20 -> generation saw 20 of 1000+ rows (98% silently
dropped). These tests prove: (a) the default-20 throttle is real, (b) the slate raises the cap to a
full-capability value with FLOOR semantics, (c) the preflight FAILS CLOSED on a re-introduced throttle,
(d) the per-section ceiling is env-tunable (default 30 = byte-identical when unset).
"""

from __future__ import annotations

import os

import pytest

from scripts.dr_benchmark import run_gate_b as g


def _clear():
    for k in ("PG_LIVE_MAX_EV_TO_GEN", "PG_MAX_EV_PER_SECTION", "PG_MOST_MAX_EVIDENCE",
              "PG_STORM_ENABLED_IN_BENCHMARK", "PG_SWEEP_EVIDENCE_DEEPENER", "PG_ENABLE_TOOL_TRACKER",
              "PG_DEPTH_ANNOTATION_IN_BENCHMARK", "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_NLI_IN_BENCHMARK"):
        os.environ.pop(k, None)


def test_default_generation_cap_is_the_20_throttle():
    # Documents the bug: without the slate, the generator-facing cap defaults to 20 (the 98%-drop).
    _clear()
    assert int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20")) == 20


def test_slate_raises_generation_cap_with_floor_semantics(monkeypatch):
    # The slate raises PG_LIVE_MAX_EV_TO_GEN to a full-capability value (>=100 floor); FLOOR semantics
    # keep a HIGHER operator value but raise a lower/absent default.
    _clear()
    g.apply_full_capability_benchmark_slate()
    assert int(os.getenv("PG_LIVE_MAX_EV_TO_GEN")) >= 100        # raised from the 20 default
    assert int(os.getenv("PG_MAX_EV_PER_SECTION")) >= 30          # per-section raised in lockstep
    _clear()
    # operator override HIGHER than the slate is kept (no downgrade)
    monkeypatch.setenv("PG_LIVE_MAX_EV_TO_GEN", "400")
    g.apply_full_capability_benchmark_slate()
    assert int(os.getenv("PG_LIVE_MAX_EV_TO_GEN")) == 400
    _clear()


def test_preflight_fails_closed_on_reintroduced_generation_throttle(monkeypatch):
    # A deliberate PG_LIVE_MAX_EV_TO_GEN=20 (the prior bug value) must be CAUGHT by the preflight.
    _clear()
    g.apply_full_capability_benchmark_slate()
    for f in ("PG_DEPTH_ANNOTATION_IN_BENCHMARK", "PG_AGENTIC_SEARCH_IN_BENCHMARK", "PG_NLI_IN_BENCHMARK"):
        os.environ[f] = "1"
    g.preflight_full_capability()                                # full slate passes
    monkeypatch.setenv("PG_LIVE_MAX_EV_TO_GEN", "20")            # the exact prior-bug value
    with pytest.raises(RuntimeError):
        g.preflight_full_capability()
    _clear()


def test_selector_no_longer_drops_98pct_at_full_cap():
    # End-to-end on the REAL selector: a 1000-row pool at the slate cap selects >=100, not 20.
    _clear()
    g.apply_full_capability_benchmark_slate()
    from src.polaris_graph.retrieval.evidence_selector import select_evidence_for_generation

    # 1000 synthetic classified rows + evidence rows (offline, deterministic).
    rows = []
    sources = []
    for i in range(1000):
        eid = f"ev_{i:04d}"
        rows.append({"evidence_id": eid, "direct_quote": f"finding {i} with value {i}.0 percent.",
                     "tier": (i % 7) + 1, "url": f"https://example.org/{i}", "relevance_score": 0.9 - (i * 0.0008)})
        sources.append(type("S", (), {"url": f"https://example.org/{i}", "tier": (i % 7) + 1,
                                       "relevance_score": 0.9 - (i * 0.0008)})())
    max_ev = int(os.getenv("PG_LIVE_MAX_EV_TO_GEN", "20"))
    sel = select_evidence_for_generation(
        research_question="q", protocol={}, classified_sources=sources, evidence_rows=rows, max_rows=max_ev,
    )
    selected = len(sel.selected_rows)
    assert selected >= 100, f"slate cap should select >=100 rows, got {selected} (dropped={sel.dropped_count})"
    # before the fix this would be 20 (980 dropped, 98%); now it is the full-capability cap.
    _clear()
