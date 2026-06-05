"""I-ready-003 (#1074) P1 — the post-fetch loop budget must SCALE with fetch_cap (offline, pure).

A FIXED loop budget silently truncated the corpus at full cap (the slate raised fetch_cap 25x without
scaling this wall-clock budget). These tests prove the budget now scales, stays byte-identical for small
caps, and a conservative operator env cannot silently win.
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.retrieval.live_retriever import _post_fetch_loop_budget


def _clear(monkeypatch):
    monkeypatch.delenv("PG_POST_FETCH_LOOP_BUDGET", raising=False)
    monkeypatch.delenv("PG_POST_FETCH_PER_URL_BUDGET", raising=False)


def test_small_cap_uses_env_floor_byte_identical(monkeypatch):
    # At a small cap the 900s floor wins -> identical to the pre-fix behavior.
    _clear(monkeypatch)
    assert _post_fetch_loop_budget(40) == 900.0          # 40*4=160 < 900 floor
    assert _post_fetch_loop_budget(100) == 900.0         # 100*4=400 < 900 floor


def test_full_cap_scales_with_fetch_cap(monkeypatch):
    # At the 1000-URL benchmark cap the fetch_cap term dominates -> 4000s (was a fixed budget).
    _clear(monkeypatch)
    assert _post_fetch_loop_budget(1000) == 4000.0       # 1000*4
    assert _post_fetch_loop_budget(500) == 2000.0        # 500*4 > 900 floor


def test_conservative_env_cannot_silently_throttle(monkeypatch):
    # A conservative operator PG_POST_FETCH_LOOP_BUDGET=600 MUST NOT win at full cap — the fetch_cap
    # term floors it (this is the no-silent-downgrade guarantee).
    _clear(monkeypatch)
    monkeypatch.setenv("PG_POST_FETCH_LOOP_BUDGET", "600")
    assert _post_fetch_loop_budget(1000) == 4000.0       # max(600, 4000)
    # but a HIGHER explicit operator value is kept (no downgrade either direction).
    monkeypatch.setenv("PG_POST_FETCH_LOOP_BUDGET", "9000")
    assert _post_fetch_loop_budget(1000) == 9000.0       # max(9000, 4000)


def test_per_url_budget_is_tunable(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PG_POST_FETCH_PER_URL_BUDGET", "6")
    assert _post_fetch_loop_budget(1000) == 6000.0


def test_slate_sets_the_scaled_budget():
    # The Gate-B slate carries the scaled budget + per-URL knob so a benchmark run is coherent.
    from scripts.dr_benchmark.run_gate_b import _FULL_CAPABILITY_BENCHMARK_SLATE as S
    assert int(S["PG_POST_FETCH_LOOP_BUDGET"]) >= 4000
    assert int(S["PG_POST_FETCH_PER_URL_BUDGET"]) >= 3
