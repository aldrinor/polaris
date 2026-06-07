"""I-ready-017 FL-05b (#1137) — offline tests for activating the FL-05 (#1124) run-health backstop
in the Gate-B full-capability slate.

NO network, NO spend. Covers:
  * the slate FORCE-ONs PG_RUN_HEALTH_GATE even when the process env presets it to "0"
    (a conservative .env=0 must NOT win — operator no-downgrade directive);
  * the fail-closed preflight raises RuntimeError naming PG_RUN_HEALTH_GATE if it is off after the
    slate is applied (a paid run can never start with the backstop silently disabled);
  * BEHAVIORAL (§-1.1): the activated flag actually changes compute_run_health_gate's decision — a
    would-be-SUCCESS run whose force-enabled STORM did NOT fire (firing_status=attempted_empty)
    overrides to abort_discovery_degraded ONLY when the gate is on; an already-held status is
    untouched. This proves the activation is wired to real behavior, not just a string in a set.

FL-05 only PROMOTES the existing advisory firing-warning to a gating abort of a would-be success — it
never weakens a faithfulness gate (strict_verify / provenance / 4-role / two-family all unchanged).

Hermetic: env snapshotted/restored so a forced flag does not leak into sibling tests.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from scripts.dr_benchmark.run_gate_b import (
    _BENCHMARK_FORCE_ON_FLAGS,
    _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
    _FULL_CAPABILITY_BENCHMARK_SLATE,
    apply_full_capability_benchmark_slate,
    load_locked_questions,
    preflight_full_capability,
    run_gate_b_query,
)
from scripts.run_honest_sweep_r3 import compute_run_health_gate, make_feature_telemetry

_FLAG = "PG_RUN_HEALTH_GATE"


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


# --------------------------------------------------------------------------- presence in the slate

def test_run_health_gate_in_slate_force_on_and_required():
    """FL-05b wires the flag into all three structures (the activation contract)."""
    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(_FLAG) == "1"
    assert _FLAG in _BENCHMARK_FORCE_ON_FLAGS
    assert _FLAG in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS


# --------------------------------------------------------------------------- force-on over preset 0

def test_slate_force_ons_run_health_gate_over_preset_zero():
    """An explicit PG_RUN_HEALTH_GATE=0 in the process env must NOT survive the slate (the I-cap-005
    P1-1 force-on pattern: a conservative operator value cannot silently disable the backstop)."""
    os.environ[_FLAG] = "0"
    apply_full_capability_benchmark_slate()
    assert os.environ.get(_FLAG) == "1", "slate must force PG_RUN_HEALTH_GATE on over preset 0"


def test_run_gate_b_query_force_ons_run_health_gate(monkeypatch):
    """End-to-end through run_gate_b_query (run_one_query faked — no pipeline, no spend): the flag is on
    after the query path applies the slate."""
    os.environ[_FLAG] = "0"

    async def _fake_run_one_query(q, out_root, **kwargs):
        return {"status": "success", "slug": q["slug"]}

    monkeypatch.setattr("scripts.run_honest_sweep_r3.run_one_query", _fake_run_one_query)
    q = load_locked_questions(("drb_72_ai_labor",))[0]
    summary = asyncio.run(
        run_gate_b_query(q, Path("outputs/__test_unused__"), transport=object())
    )
    assert summary["status"] == "success"
    assert os.environ.get(_FLAG) == "1", "run_gate_b_query must force PG_RUN_HEALTH_GATE on"


# --------------------------------------------------------------------------- fail-closed preflight

def test_preflight_fails_closed_when_run_health_gate_off():
    """Slate applied but the backstop forced back off → preflight must raise naming the flag, aborting
    BEFORE any spend. Satisfy every OTHER required flag so the failure isolates to PG_RUN_HEALTH_GATE."""
    apply_full_capability_benchmark_slate()
    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
        os.environ[flag] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ[_FLAG] = "0"  # the one under test

    with pytest.raises(RuntimeError) as exc:
        preflight_full_capability()
    assert _FLAG in str(exc.value)


# --------------------------------------------------------------------------- §-1.1 behavioral proof

def _degraded_success_telemetries():
    """A force-enabled STORM that did NOT fire (silent fallback to the Serper/S2 baseline) + an
    agentic feature that fired fine — the exact 2026-06-05 drb_72 smoke shape."""
    storm = make_feature_telemetry("storm", enabled=True, fired=False, firing_status="attempted_empty")
    agentic = make_feature_telemetry("agentic", enabled=True, fired=True, firing_status="fired")
    return [storm, agentic]


def test_activated_gate_aborts_would_be_success_degraded_run():
    """With the gate ON (as the slate sets it), a would-be-SUCCESS run whose force-enabled STORM did not
    fire overrides to abort_discovery_degraded. This is the backfire-guard the activation buys."""
    out = compute_run_health_gate(
        _degraded_success_telemetries(), unified_status="success", gate_on=True
    )
    assert out["override_status"] == "abort_discovery_degraded"
    assert out["discovery_llm_degraded"] is True
    assert out["discovery_rounds_on_fallback"] == 1


def test_gate_off_ships_degraded_run_as_success():
    """The pre-FL-05b default: with the gate OFF, the SAME degraded run still ships as success (the
    silent downgrade FL-05b closes). Observability fields still surface, but no override."""
    out = compute_run_health_gate(
        _degraded_success_telemetries(), unified_status="success", gate_on=False
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is True  # surfaced even when not gating


def test_activated_gate_never_overrides_an_already_held_status():
    """FL-05 only overrides a would-be SUCCESS. The 2026-06-05 smoke ended abort_four_role_release_held
    (D8 gate already held) — FL-05b must NOT touch that (no double-abort / status clobber)."""
    out = compute_run_health_gate(
        _degraded_success_telemetries(),
        unified_status="abort_four_role_release_held",
        gate_on=True,
    )
    assert out["override_status"] is None


def test_activated_gate_passes_a_clean_run():
    """All force-enabled discovery features fired → no override even with the gate on (no false abort)."""
    storm = make_feature_telemetry("storm", enabled=True, fired=True, firing_status="fired")
    agentic = make_feature_telemetry("agentic", enabled=True, fired=True, firing_status="fired")
    out = compute_run_health_gate([storm, agentic], unified_status="success", gate_on=True)
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False
