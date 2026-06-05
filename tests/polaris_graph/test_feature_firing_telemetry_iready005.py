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
    assert t["firing_status"] == "not_enabled"
    assert t["questions_added"] == 0 and t["interviews"] == 0


def test_no_warning_when_feature_off():
    # OFF (not enabled) -> no warning regardless of fired.
    assert feature_firing_warning(make_feature_telemetry("agentic_search")) is None


def test_no_warning_when_enabled_and_fired():
    t = make_feature_telemetry("storm_query_expansion")
    t.update({"enabled": True, "fired": True, "firing_status": "fired"})
    assert feature_firing_warning(t) is None


def test_warns_when_force_enabled_but_did_not_fire():
    # The silent-degrade the operator's no-downgrade directive forbids: enabled but not fired.
    t = make_feature_telemetry("agentic_search")
    t.update({"enabled": True, "fired": False, "firing_status": "attempted_empty"})
    w = feature_firing_warning(t)
    assert w is not None
    assert "agentic_search" in w and "did NOT fire" in w
    # also fires when the block errored
    t["firing_status"] = "error"
    assert feature_firing_warning(t) is not None


def test_attach_tool_utilization_stamps_telemetry_on_every_manifest_path(monkeypatch, tmp_path):
    # Codex iter-1 P1: the firing keys must land on EVERY manifest write path (abort/budget/error too),
    # not just success. _attach_tool_utilization is the single hook before every manifest.json write; it
    # stamps the telemetry from _FEATURE_TELEMETRY_CTX. With the tracker OFF it is otherwise a no-op, so
    # this isolates the feature-key stamping.
    import scripts.run_honest_sweep_r3 as m
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    storm = make_feature_telemetry("storm_query_expansion", enabled=True, fired=True, firing_status="fired")
    agentic = make_feature_telemetry("agentic_search", enabled=True, fired=False, firing_status="enabled_not_reached")
    tok = m._FEATURE_TELEMETRY_CTX.set({"storm_query_expansion": storm, "agentic_search": agentic})
    try:
        # NB: the dict passed to _attach_tool_utilization is a MANIFEST (its "status" is the manifest's
        # pipeline status) — distinct from the per-feature telemetry's "firing_status".
        out = m._attach_tool_utilization({"status": "abort_no_sources"}, tmp_path)
    finally:
        m._FEATURE_TELEMETRY_CTX.reset(tok)
    # an ABORT manifest now carries the firing telemetry — the operator can prove STORM fired even on abort
    assert out["storm_query_expansion"]["fired"] is True
    assert out["agentic_search"]["firing_status"] == "enabled_not_reached"


def test_attach_tool_utilization_no_telemetry_when_ctx_unset(monkeypatch, tmp_path):
    # When the ContextVar is unset (non-run_one_query caller), no feature keys are added (byte-identical).
    import scripts.run_honest_sweep_r3 as m
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    m._FEATURE_TELEMETRY_CTX.set(None)
    out = m._attach_tool_utilization({"status": "success"}, tmp_path)
    assert "storm_query_expansion" not in out and "agentic_search" not in out


def test_run_one_query_outer_try_has_ctx_clearing_finally():
    # Codex iter-3/iter-4 P1: the per-exit-site clears kept missing direct-return paths (cancel-return,
    # abort_verifier_degraded). The guaranteed clear is a `finally` on run_one_query's OUTER try — the
    # same try whose excepts write error_unexpected / abort_budget_exceeded. Because every abort-return
    # AND the success manifest write live inside that try, and the post-try teardown writes no manifest,
    # the finally is the single clear that runs on EVERY exit without ever stripping telemetry off a
    # manifest. Structural (AST) check — mirrors test_manifest_contract / test_four_role_budget_cap,
    # which is why the orchestrator body must stay in `run_one_query` (no wrapper rename).
    import ast
    import inspect

    import scripts.run_honest_sweep_r3 as m

    src = inspect.getsource(m.run_one_query)
    # getsource keeps the original indentation; dedent so ast can parse the def standalone.
    import textwrap

    tree = ast.parse(textwrap.dedent(src))
    func = next(
        (n for n in ast.walk(tree)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_one_query"),
        None,
    )
    assert func is not None, "run_one_query not found"
    # The outer orchestration try = the top-level Try whose body writes the error_unexpected /
    # abort_budget_exceeded manifests (NOT the early `except Exception: pass` synthesis-reset try, which
    # is also a top-level try but is a no-op guard). Identify it by its source segment, then assert it
    # carries a `finally` that clears _FEATURE_TELEMETRY_CTX. dedent shifts line numbers, so segment off
    # the dedented `src` consistently.
    outer_try = None
    for node in func.body:
        if isinstance(node, ast.Try):
            seg = ast.get_source_segment(textwrap.dedent(src), node) or ""
            if "error_unexpected" in seg and "BudgetExceededError" in seg:
                outer_try = node
                break
    assert outer_try is not None, (
        "expected the outer orchestration try (the one writing error_unexpected / "
        "abort_budget_exceeded) in run_one_query"
    )
    assert outer_try.finalbody, "outer try must have a `finally` clause"
    finally_src = ast.dump(ast.Module(body=outer_try.finalbody, type_ignores=[]))
    assert "_FEATURE_TELEMETRY_CTX" in finally_src and "set" in finally_src, (
        "the outer try's finally must clear _FEATURE_TELEMETRY_CTX (set it to None) — the single "
        "guaranteed clear on every exit"
    )


def test_stale_telemetry_does_not_leak_after_clear(monkeypatch, tmp_path):
    # Behavioral: after a run "ends" (ContextVar cleared to None), a subsequent _attach call must NOT
    # carry the prior run's telemetry.
    import scripts.run_honest_sweep_r3 as m
    monkeypatch.setenv("PG_ENABLE_TOOL_TRACKER", "0")
    prior = make_feature_telemetry("storm_query_expansion", enabled=True, fired=True, firing_status="fired")
    m._FEATURE_TELEMETRY_CTX.set({"storm_query_expansion": prior, "agentic_search": prior})
    m._FEATURE_TELEMETRY_CTX.set(None)   # the teardown clear
    out = m._attach_tool_utilization({"status": "success"}, tmp_path)
    assert "storm_query_expansion" not in out   # no stale leak
