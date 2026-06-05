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


def test_attach_tool_utilization_stamps_telemetry_on_every_manifest_path(monkeypatch, tmp_path):
    # Codex iter-1 P1: the firing keys must land on EVERY manifest write path (abort/budget/error too),
    # not just success. _attach_tool_utilization is the single hook before every manifest.json write; it
    # stamps the telemetry from _FEATURE_TELEMETRY_CTX. With the tracker OFF it is otherwise a no-op, so
    # this isolates the feature-key stamping.
    import scripts.run_honest_sweep_r3 as m
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    storm = make_feature_telemetry("storm_query_expansion", enabled=True, fired=True, status="fired")
    agentic = make_feature_telemetry("agentic_search", enabled=True, fired=False, status="enabled_not_reached")
    tok = m._FEATURE_TELEMETRY_CTX.set({"storm_query_expansion": storm, "agentic_search": agentic})
    try:
        out = m._attach_tool_utilization({"status": "abort_no_sources"}, tmp_path)
    finally:
        m._FEATURE_TELEMETRY_CTX.reset(tok)
    # an ABORT manifest now carries the firing telemetry — the operator can prove STORM fired even on abort
    assert out["storm_query_expansion"]["fired"] is True
    assert out["agentic_search"]["status"] == "enabled_not_reached"


def test_attach_tool_utilization_no_telemetry_when_ctx_unset(monkeypatch, tmp_path):
    # When the ContextVar is unset (non-run_one_query caller), no feature keys are added (byte-identical).
    import scripts.run_honest_sweep_r3 as m
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    m._FEATURE_TELEMETRY_CTX.set(None)
    out = m._attach_tool_utilization({"status": "success"}, tmp_path)
    assert "storm_query_expansion" not in out and "agentic_search" not in out


def test_run_one_query_wrapper_clears_ctx_on_every_exit(monkeypatch):
    # Codex iter-3 P1: the per-exit-site clears kept missing direct-return paths (cancel-return,
    # abort_verifier_degraded). The run_one_query WRAPPER's finally is the single guaranteed clear on
    # EVERY exit — normal return AND a propagating exception — so no stale telemetry can leak.
    import asyncio
    import scripts.run_honest_sweep_r3 as m

    async def _impl_returns(q, out_root, **kw):
        m._FEATURE_TELEMETRY_CTX.set({"storm_query_expansion": {"fired": True}, "agentic_search": {}})
        return {"status": "ok"}

    async def _impl_raises(q, out_root, **kw):
        m._FEATURE_TELEMETRY_CTX.set({"storm_query_expansion": {"fired": True}, "agentic_search": {}})
        raise RuntimeError("boom")

    monkeypatch.setattr(m, "_run_one_query_impl", _impl_returns)
    asyncio.run(m.run_one_query({"domain": "d", "slug": "s", "question": "q"}, "."))
    assert m._FEATURE_TELEMETRY_CTX.get() is None, "ctx must be cleared on normal return"

    monkeypatch.setattr(m, "_run_one_query_impl", _impl_raises)
    with __import__("pytest").raises(RuntimeError):
        asyncio.run(m.run_one_query({"domain": "d", "slug": "s", "question": "q"}, "."))
    assert m._FEATURE_TELEMETRY_CTX.get() is None, "ctx must be cleared even on a propagating exception"


def test_stale_telemetry_does_not_leak_after_clear(monkeypatch, tmp_path):
    # Behavioral: after a run "ends" (ContextVar cleared to None), a subsequent _attach call must NOT
    # carry the prior run's telemetry.
    import scripts.run_honest_sweep_r3 as m
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    prior = make_feature_telemetry("storm_query_expansion", enabled=True, fired=True, status="fired")
    m._FEATURE_TELEMETRY_CTX.set({"storm_query_expansion": prior, "agentic_search": prior})
    m._FEATURE_TELEMETRY_CTX.set(None)   # the teardown clear
    out = m._attach_tool_utilization({"status": "success"}, tmp_path)
    assert "storm_query_expansion" not in out   # no stale leak
