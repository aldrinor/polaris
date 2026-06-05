"""I-ready-005 (#1076) P1 — per-feature firing telemetry + the no-silent-degrade warning (offline, pure).

The benchmark forces STORM + agentic ON; the operator must be able to PROVE each fired (not just that its
flag was set). These tests cover the manifest telemetry shape + the forced-ON-but-didn't-fire warning.
"""

from __future__ import annotations

from scripts.run_honest_sweep_r3 import feature_firing_warning, make_feature_telemetry


def test_default_telemetry_shape_not_enabled():
    t = make_feature_telemetry("storm_query_expansion", questions_added=0, interviews=0)
    assert t["feature"] == "storm_query_expansion"
    assert t["enabled"] is False and t["fired"] is False
    assert t["status"] == "not_enabled"
    assert t["questions_added"] == 0 and t["interviews"] == 0


def test_no_warning_when_feature_off():
    # OFF (not enabled) -> no warning regardless of fired.
    assert feature_firing_warning(make_feature_telemetry("agentic_search")) is None


def test_no_warning_when_enabled_and_fired():
    t = make_feature_telemetry("storm_query_expansion")
    t.update({"enabled": True, "fired": True, "status": "fired"})
    assert feature_firing_warning(t) is None


def test_warns_when_force_enabled_but_did_not_fire():
    # The silent-degrade the operator's no-downgrade directive forbids: enabled but not fired.
    t = make_feature_telemetry("agentic_search")
    t.update({"enabled": True, "fired": False, "status": "attempted_empty"})
    w = feature_firing_warning(t)
    assert w is not None
    assert "agentic_search" in w and "did NOT fire" in w
    # also fires when the block errored
    t["status"] = "error"
    assert feature_firing_warning(t) is not None


def test_manifest_keys_are_wired_in_source():
    # The sweep must write both per-feature firing keys to the manifest (structural guard against a
    # future edit silently dropping them — the whole point is proving utilization).
    import inspect
    import scripts.run_honest_sweep_r3 as m
    src = inspect.getsource(m)
    assert 'manifest["storm_query_expansion"] = _storm_telemetry' in src
    assert 'manifest["agentic_search"] = _agentic_telemetry' in src
