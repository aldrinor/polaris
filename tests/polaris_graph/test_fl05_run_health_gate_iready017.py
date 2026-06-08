"""FL-05 (I-ready-017 #1124): run-health gate — force-enabled discovery feature not fired.

A FORCE-ENABLED discovery feature (STORM / agentic) that was turned ON but did NOT fire
(firing_status in {attempted_empty, error}) silently degrades the run to the Serper/S2 baseline; it
must NOT ship as success. `compute_run_health_gate` is the pure decision (always emits the
observability fields; overrides a would-be success → abort_discovery_degraded only when
PG_RUN_HEALTH_GATE is on). Default OFF leaves status/control-flow/release unchanged (the two
additive observability fields are still emitted). Offline, no network.
"""
from __future__ import annotations

from typing import get_args

from scripts.run_honest_sweep_r3 import (
    UNIFIED_STATUS_VALUES,
    compute_run_health_gate,
    to_unified_status,
)
from src.polaris_graph.audit_ir.regression_lab import KNOWN_STATUS_VALUES
from src.polaris_v6.schemas.run_status import PipelineStatus


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


def test_abort_discovery_degraded_in_v6_pipeline_status():
    # Codex iter-1 P1: the v6 actor stores manifest.status into pipeline_status for abort_* runs and
    # RunStatusResponse validates against the PipelineStatus Literal — omitting the new status would
    # 500 any GET/list query of an FL-05 abort. Pin it in the schema mirror.
    assert "abort_discovery_degraded" in get_args(PipelineStatus)


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


def test_gate_off_no_abort_but_degradation_observed():
    # default (gate_on=False): status + control flow + the release decision are UNCHANGED (no
    # override), but the degradation is still OBSERVED in the additive observability fields.
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


# --------------------------------------------------------------------------- I-fetch-002 (#1168)
# STORM UNDER-fire: force-on STORM FIRED but produced fewer than the effective-query floor (post-
# validator collapse / thin corpus). The classic FL-05 path above only catches a TOTAL no-fire.


def _storm_fired(effective_query_count):
    t = _feat("storm", True, "fired")
    t["effective_query_count"] = effective_query_count
    return t


def test_storm_under_fire_below_floor_overrides_success():
    # FIRED but 5 effective queries < floor 12 → abort_discovery_degraded (gated, would-be success).
    out = compute_run_health_gate(
        [_storm_fired(5), _feat("agentic_search", True, "fired")],
        unified_status="success",
        gate_on=True,
        storm_min_effective_queries=12,
    )
    assert out["override_status"] == "abort_discovery_degraded"
    assert out["discovery_llm_degraded"] is True
    assert out["discovery_rounds_on_fallback"] == 1
    assert out["degraded_features"] == [
        {"feature": "storm", "firing_status": "under_fired", "effective_query_count": 5}
    ]


def test_storm_at_or_above_floor_not_overridden():
    # 12 effective queries == floor 12 → healthy, no override (>= floor passes).
    out = compute_run_health_gate(
        [_storm_fired(12), _feat("agentic_search", True, "fired")],
        unified_status="success",
        gate_on=True,
        storm_min_effective_queries=12,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False


def test_under_fire_floor_default_disabled_is_byte_compatible():
    # Default floor (0): a FIRED feature with a tiny effective_query_count is NOT flagged, so every
    # pre-existing caller (which never passes the kwarg) is unchanged. count < 0 never fires.
    out = compute_run_health_gate(
        [_storm_fired(1)],
        unified_status="success",
        gate_on=True,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False


def test_under_fire_absent_count_never_false_aborts():
    # A FIRED feature that does NOT publish effective_query_count (e.g. agentic publishes
    # urls_discovered, not effective_query_count) must NEVER trip the floor — absent != 0.
    agentic = _feat("agentic_search", True, "fired")  # no effective_query_count key
    out = compute_run_health_gate(
        [agentic],
        unified_status="success",
        gate_on=True,
        storm_min_effective_queries=12,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is False


def test_under_fire_not_overridden_when_gate_off():
    # Same as the TOTAL-no-fire path: with the gate off, the under-fire is OBSERVED but never aborts.
    out = compute_run_health_gate(
        [_storm_fired(3)],
        unified_status="success",
        gate_on=False,
        storm_min_effective_queries=12,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is True  # surfaced for the operator


def test_under_fire_never_overrides_non_success():
    # Only a would-be success is overridden; a more-specific held/abort status is left alone.
    out = compute_run_health_gate(
        [_storm_fired(2)],
        unified_status="partial_thin_corpus",
        gate_on=True,
        storm_min_effective_queries=12,
    )
    assert out["override_status"] is None
    assert out["discovery_llm_degraded"] is True
