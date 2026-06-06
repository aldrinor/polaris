"""FL-05 (I-ready-017 #1124): run-health gate — force-enabled discovery feature not fired.

A FORCE-ENABLED discovery feature (STORM / agentic) that was turned ON but did NOT fire
(firing_status in {attempted_empty, error}) silently degrades the run to the Serper/S2 baseline; it
must NOT ship as success. `compute_run_health_gate` is the pure decision (always emits the
observability fields; overrides a would-be success → abort_discovery_degraded only when
PG_RUN_HEALTH_GATE is on). Default OFF = byte-identical. Offline, no network.
"""
from __future__ import annotations

from scripts.run_honest_sweep_r3 import (
    UNIFIED_STATUS_VALUES,
    compute_run_health_gate,
    to_unified_status,
)
from src.polaris_graph.audit_ir.regression_lab import KNOWN_STATUS_VALUES


def _feat(name, enabled, firing_status):
    return {"feature": name, "enabled": enabled, "firing_status": firing_status, "fired": firing_status == "fired"}


def test_abort_discovery_degraded_registered_and_prefix_compliant():
    assert "abort_discovery_degraded" in UNIFIED_STATUS_VALUES
    assert to_unified_status("abort_discovery_degraded") == "abort_discovery_degraded"
    assert "abort_discovery_degraded".startswith("abort_")  # manifest-contract prefix scheme


def test_regression_lab_known_statuses_mirror_runner():
    # The documented invariant: regression_lab KNOWN_STATUS_VALUES MUST equal runner.UNIFIED_STATUS_VALUES.
    assert KNOWN_STATUS_VALUES == UNIFIED_STATUS_VALUES
    assert "abort_discovery_degraded" in KNOWN_STATUS_VALUES


def test_force_enabled_not_fired_overrides_success_when_gated():
    for bad in ("attempted_empty", "error"):
        out = compute_run_health_gate(
            [_feat("storm", True, bad), _feat("agentic_search", True, "fired")],
            unified_status="success",
            gate_on=True,
        )
        assert out["override_status"] == "abort_discovery_degraded", bad
        assert out["discovery_llm_degraded"] is True
        assert out["discovery_rounds_on_fallback"] == 1
        assert out["degraded_features"] == [{"feature": "storm", "firing_status": bad}]


def test_healthy_run_not_overridden():
    out = compute_run_health_gate(
        [_feat("storm", True, "fired"), _feat("agentic_search", True, "fired")],
        unified_status="success",
        gate_on=True,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False
    assert out["discovery_rounds_on_fallback"] == 0


def test_gate_off_is_byte_identical_default():
    # default (gate_on=False): degradation is OBSERVED (field emitted) but the run is NOT overridden.
    out = compute_run_health_gate(
        [_feat("storm", True, "attempted_empty")],
        unified_status="success",
        gate_on=False,
    )
    assert out["override_status"] is None        # no new abort on the default path
    assert out["discovery_llm_degraded"] is True  # but still surfaced for the operator


def test_non_success_status_never_overridden():
    # Only a would-be success is overridden; a partial_/abort_ is more specific and is left alone.
    out = compute_run_health_gate(
        [_feat("agentic_search", True, "error")],
        unified_status="partial_thin_corpus",
        gate_on=True,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is True


def test_disabled_feature_is_not_degraded():
    # A feature that was NOT force-enabled (enabled=False) is never a degradation, even if empty.
    out = compute_run_health_gate(
        [_feat("storm", False, "not_enabled"), _feat("agentic_search", False, "attempted_empty")],
        unified_status="success",
        gate_on=True,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False
