"""I-wire-005 B-B (#1319): the Phase-7 quantified-spec Writer budgets are WIRED into the
authoritative Gate-B slate — force-EXACT + floor-guarded — so a partial deploy or a stray
operator/.env value cannot silently starve the spec call and no-op the differentiator on the paid
run (the deploy-consistency half of the B-B hypothesis).

B4 (#1317) lived ONLY in the run_honest_sweep_r3 closure default (PG_QUANTIFIED_SPEC_MAX_TOKENS=
32768) and was NEVER pinned in the slate, so a conservative .env / partial deploy could leave the
spec Writer starved while the preflight still passed. This pins BOTH the content budget (32768)
AND the reasoning cap (8192) that reserves content on the reasoning-first GLM-5.2 generator.

NO network, NO spend. Hermetic: env snapshotted/restored. Mirrors
tests/dr_benchmark/test_slate_cited_span_fx03_iready017.py conventions.
"""
from __future__ import annotations

import os

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_EXACT_FLAGS,
    _BENCHMARK_PREFLIGHT_FLOORS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    apply_full_capability_benchmark_slate,
)

_MAX = "PG_QUANTIFIED_SPEC_MAX_TOKENS"
_REASON = "PG_QUANTIFIED_SPEC_REASONING_MAX_TOKENS"


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def test_both_budgets_are_in_slate_force_exact_and_floor_guarded():
    """Static wiring: both budgets are in the slate at their chosen values, force-EXACT (a stray
    value cannot raise OR lower them), and floor-guarded (a value below the floor fails the
    fail-closed preflight)."""
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_MAX) == "32768"
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_REASON) == "8192"
    assert _MAX in _BENCHMARK_FORCE_EXACT_FLAGS
    assert _REASON in _BENCHMARK_FORCE_EXACT_FLAGS
    assert _BENCHMARK_PREFLIGHT_FLOORS.get(_MAX) == 32768
    assert _BENCHMARK_PREFLIGHT_FLOORS.get(_REASON) == 8192


def test_slate_force_sets_both_over_a_stray_low_value():
    """apply() must FORCE both budgets to the slate value even when the process env presets them to a
    starvation value (a conservative .env or partial deploy must NOT survive)."""
    os.environ[_MAX] = "4000"     # the pre-B4 starvation budget
    os.environ[_REASON] = "100"   # a runaway-reasoning starvation cap
    apply_full_capability_benchmark_slate()
    assert os.environ[_MAX] == "32768"
    assert os.environ[_REASON] == "8192"


def test_floor_guard_values_match_slate_so_force_exact_passes_preflight():
    """The floor must equal the force-exact slate value, so the force-EXACT-set value (== floor)
    satisfies the >= floor preflight check (no self-inflicted fail-closed)."""
    assert int(_FULL_CAPABILITY_BENCHMARK_SLATE[_MAX]) == _BENCHMARK_PREFLIGHT_FLOORS[_MAX]
    assert int(_FULL_CAPABILITY_BENCHMARK_SLATE[_REASON]) == _BENCHMARK_PREFLIGHT_FLOORS[_REASON]
