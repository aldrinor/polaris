"""Unit tests for scripts/operational_readiness_preflight.py (the will-it-die-from-a-stupid-mistake
config preflight). Pure-function tests over SYNTHETIC effective configs — no network, no spend, no run.

NON-BLANKET PROOF: a GOOD synthetic config is GO; a starved-token / flag-off / short-seam / banned-cap
synthetic config each flips it NO-GO on the SPECIFIC check that owns the defect. A real-slate resolution
test proves the operator-locked Gate-B config is GREEN today (the regression-guard baseline)."""

from __future__ import annotations

import os

import scripts.operational_readiness_preflight as op


# --------------------------------------------------------------------------------------------
# Synthetic fixtures — a hand-built "effective config" that mirrors a healthy --pathB-gate run.
# --------------------------------------------------------------------------------------------

def _good_cfg() -> dict:
    return {
        # D-1 breadth/quality flags (ON)
        "PG_BREADTH_ENRICHMENT_ENABLED": "1",
        "PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS": "1",
        "PG_RETRIEVAL_RELEVANCE_GATE": "1",
        # D-3 token budgets (generous)
        "PG_SECTION_MAX_TOKENS": "64000",
        "PG_D8_VERDICT_MAX_TOKENS": "16384",
        "PG_MIRROR_MAX_TOKENS": "131072",
        "PG_SENTINEL_DECOMPOSITION_MAX_TOKENS": "131072",
        "PG_ENTAILMENT_MAX_TOKENS": "131072",
        # D-4 timeouts (ordered, seam raised)
        "PG_GENERATOR_LLM_TIMEOUT_SECONDS": "6500",
        "PG_SECTION_WALLCLOCK_SECONDS": "9000",
        "PG_RUN_WALL_CLOCK_SEC": "10800",
        "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS": "7200",
        # D-5 caps
        "PG_SWEEP_FETCH_CAP": "740",
        "PG_CAPPED_FINDING_DEDUP": "0",
        "PG_LIVE_MAX_EV_TO_GEN": "1500",
        # D-6 disclosure-wiring flags
        "PG_SWEEP_CREDIBILITY_REDESIGN": "1",
        "PG_CREDIBILITY_LLM_TIERING": "1",
        "PG_REDACT_HELD_UNSUPPORTED": "1",
        "PG_ALWAYS_RELEASE": "1",
    }


def _good_meta() -> op.SlateMeta:
    return op.SlateMeta(
        slate={
            "PG_BREADTH_ENRICHMENT_ENABLED": "1",
            "PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS": "1",
            "PG_RETRIEVAL_RELEVANCE_GATE": "1",
            "PG_CAPPED_FINDING_DEDUP": "0",
        },
        force_on=frozenset({"PG_BREADTH_ENRICHMENT_ENABLED", "PG_RETRIEVAL_RELEVANCE_GATE"}),
        force_exact=frozenset({"PG_CAPPED_FINDING_DEDUP"}),
        required=("PG_BREADTH_ENRICHMENT_ENABLED", "PG_RETRIEVAL_RELEVANCE_GATE"),
        required_off=(),
    )


_GOOD_LINEUP = {"mirror": "z-ai/glm-5.2", "sentinel": "minimax/minimax-m2", "judge": "moonshotai/kimi-k2.6"}
_GOOD_GENERATOR = "z-ai/glm-5.2"
_GOOD_LOCK = {
    "required_roles": {
        "generator": {"model_slug": "z-ai/glm-5.2"},
        "judge": {"model_slug": "qwen/qwen3.6-35b-a3b"},
    }
}
_GOOD_FAMILIES = {"generator": "z-ai", "mirror": "z-ai", "sentinel": "minimax", "judge": "moonshotai"}


def _all_static(cfg: dict, *, raw_env=None, meta=None, lineup=None, generator=None,
                lock=None, families=None, families_error=None, four_role_wired=True) -> list:
    th = op.Thresholds()
    raw_env = cfg if raw_env is None else raw_env
    meta = _good_meta() if meta is None else meta
    lineup = _GOOD_LINEUP if lineup is None else lineup
    generator = _GOOD_GENERATOR if generator is None else generator
    lock = _GOOD_LOCK if lock is None else lock
    families = _GOOD_FAMILIES if (families is None and families_error is None) else families
    results: list = []
    results += op.check_d1_flags(cfg, raw_env, meta, four_role_wired)
    results += op.check_d2_models_static(lineup, generator, lock, families, families_error, th)
    results += op.check_d3_tokens(cfg, th)
    results += op.check_d4_timeouts(cfg, th)
    results += op.check_d5_caps(cfg, raw_env, th)
    results += op.check_d6_fail_loud(cfg, th)
    return results


def _reds(results) -> list:
    return [r.check_id for r in results if r.is_red]


# --------------------------------------------------------------------------------------------
# GOOD config -> GO
# --------------------------------------------------------------------------------------------

def test_good_config_is_go():
    results = _all_static(_good_cfg())
    assert _reds(results) == [], f"unexpected RED on a healthy config: {_reds(results)}"
    assert op.aggregate(results) == "GO"


# --------------------------------------------------------------------------------------------
# Each BAD config -> NO-GO on the OWNING check (non-blanket).
# --------------------------------------------------------------------------------------------

def test_starved_token_no_go():
    cfg = _good_cfg()
    cfg["PG_D8_VERDICT_MAX_TOKENS"] = "512"  # judge starved -> truncates mid-verdict
    results = _all_static(cfg)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert any(r.startswith("D-3.PG_D8_VERDICT_MAX_TOKENS") for r in reds), reds
    # non-blanket: ONLY the starved token check flips; the rest stay GREEN.
    assert reds == ["D-3.PG_D8_VERDICT_MAX_TOKENS"], reds


def test_flag_off_no_go():
    cfg = _good_cfg()
    cfg["PG_BREADTH_ENRICHMENT_ENABLED"] = "0"  # breadth funnel re-asserts -> narrow report
    results = _all_static(cfg)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert reds == ["D-1.PG_BREADTH_ENRICHMENT_ENABLED"], reds


def test_short_seam_wall_no_go():
    cfg = _good_cfg()
    cfg["PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS"] = "300"  # seam tears under the slow kimi judge
    results = _all_static(cfg)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert reds == ["D-4.seam"], reds


def test_banned_span_cap_no_go():
    cfg = _good_cfg()
    raw_env = dict(cfg)
    raw_env["PG_SPAN_PER_SOURCE_CITE_CAP"] = "5"  # the deleted §-1.3 bolt-on re-pinned
    results = _all_static(cfg, raw_env=raw_env)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert reds == ["D-5.span_cite_cap"], reds


def test_capped_finding_dedup_on_no_go():
    cfg = _good_cfg()
    cfg["PG_CAPPED_FINDING_DEDUP"] = "1"  # the §-1.3 re-cap-to-max_ev re-armed
    results = _all_static(cfg)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert reds == ["D-5.capped_finding_dedup"], reds


def test_topic_gate_hard_drop_no_go():
    cfg = _good_cfg()
    raw_env = dict(cfg)
    raw_env["PG_SCOPE_TOPIC_GATE_HARD_DROP"] = "1"  # the banned scope hard-filter re-armed
    results = _all_static(cfg, raw_env=raw_env)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert reds == ["D-1.PG_SCOPE_TOPIC_GATE_HARD_DROP"], reds


def test_inverted_timeout_ordering_no_go():
    cfg = _good_cfg()
    cfg["PG_RUN_WALL_CLOCK_SEC"] = "5000"  # run-wall below the section backstop -> inverted
    results = _all_static(cfg)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    # both the ordering check and the seam<=run_wall bound fire on an inverted run-wall.
    assert "D-4.ordering" in reds, reds


def test_wrong_judge_model_no_go():
    results = _all_static(_good_cfg(), lineup={**_GOOD_LINEUP, "judge": "qwen/qwen3.6-35b-a3b"})
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert "D-2.model.judge" in reds, reds


def test_family_collision_no_go():
    results = _all_static(
        _good_cfg(), families=None,
        families_error="RuntimeError: 4-role family collision — judge shares family z-ai",
    )
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert "D-2.families" in reds, reds


def test_four_role_mode_not_wired_no_go():
    results = _all_static(_good_cfg(), four_role_wired=False)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert "D-1.PG_FOUR_ROLE_MODE" in reds, reds


def test_silent_degrade_no_go():
    cfg = _good_cfg()
    cfg["PG_SWEEP_CREDIBILITY_REDESIGN"] = "0"  # credibility degrade would be SILENT
    results = _all_static(cfg)
    reds = _reds(results)
    assert op.aggregate(results) == "NO-GO"
    assert reds == ["D-6.PG_SWEEP_CREDIBILITY_REDESIGN"], reds


# --------------------------------------------------------------------------------------------
# Effective-config resolver replicates apply()'s FORCE / FLOOR / setdefault semantics.
# --------------------------------------------------------------------------------------------

def test_resolver_force_floor_setdefault():
    meta = op.SlateMeta(
        slate={"PG_FORCE_ON_FLAG": "1", "PG_FORCE_EXACT": "0", "PG_FLOOR": "740"},
        force_on=frozenset({"PG_FORCE_ON_FLAG"}),
        force_exact=frozenset({"PG_FORCE_EXACT"}),
        required=(),
        required_off=(),
    )
    # force-on/exact win over a stray operator value; floor raises a low value but keeps a higher one;
    # a non-slate key carries through untouched.
    env = {"PG_FORCE_ON_FLAG": "0", "PG_FORCE_EXACT": "1", "PG_FLOOR": "100", "PG_OTHER": "x"}
    eff = op.resolve_effective_config(env, meta)
    assert eff["PG_FORCE_ON_FLAG"] == "1"     # stray =0 overridden
    assert eff["PG_FORCE_EXACT"] == "0"       # stray =1 overridden
    assert eff["PG_FLOOR"] == "740"           # raised from 100 to slate floor
    assert eff["PG_OTHER"] == "x"             # carried through

    eff_high = op.resolve_effective_config({"PG_FLOOR": "1200"}, meta)
    assert eff_high["PG_FLOOR"] == "1200"     # a higher operator value is KEPT (no downgrade)


# --------------------------------------------------------------------------------------------
# Live /models ping check is pure over a synthetic ping dict (no network in the test).
# --------------------------------------------------------------------------------------------

_SLUGS = {"generator": "z-ai/glm-5.2", "mirror": "z-ai/glm-5.2",
          "sentinel": "minimax/minimax-m2", "judge": "moonshotai/kimi-k2.6"}


def test_live_ping_all_served_enough_providers_green():
    th = op.Thresholds()
    ping = {"reachable": True, "served": {r: True for r in _SLUGS}, "judge_providers": 21, "error": None}
    results = op.check_d2_models_live(ping, _SLUGS, "moonshotai/kimi-k2.6", th, require_live=False)
    assert [r for r in results if r.is_red] == []
    assert all(r.static_or_live == op.LIVE for r in results)


def test_live_ping_slug_not_served_red():
    th = op.Thresholds()
    served = {r: True for r in _SLUGS}
    served["judge"] = False
    ping = {"reachable": True, "served": served, "judge_providers": 21, "error": None}
    results = op.check_d2_models_live(ping, _SLUGS, "moonshotai/kimi-k2.6", th, require_live=False)
    assert any(r.check_id == "D-2.ping.served.judge" and r.is_red for r in results)


def test_live_ping_too_few_providers_red():
    th = op.Thresholds()
    ping = {"reachable": True, "served": {r: True for r in _SLUGS}, "judge_providers": 5, "error": None}
    results = op.check_d2_models_live(ping, _SLUGS, "moonshotai/kimi-k2.6", th, require_live=False)
    assert any(r.check_id == "D-2.ping.judge_providers" and r.is_red for r in results)


def test_live_ping_unreachable_is_pending_not_red_by_default():
    th = op.Thresholds()
    ping = {"reachable": False, "served": {}, "judge_providers": None, "error": "ConnectError: boom"}
    soft = op.check_d2_models_live(ping, _SLUGS, "moonshotai/kimi-k2.6", th, require_live=False)
    assert soft[0].is_pending and not soft[0].is_red
    hard = op.check_d2_models_live(ping, _SLUGS, "moonshotai/kimi-k2.6", th, require_live=True)
    assert hard[0].is_red  # --require-live-ping promotes an unreachable ping to NO-GO


def test_aggregate_only_red_gates():
    # INFO + LIVE-PENDING never flip the verdict; a single RED does.
    info = op.CheckResult("x.info", "i", op.INFO, op.LIVE, "")
    pend = op.CheckResult("x.pend", "p", op.PENDING, op.LIVE, "")
    green = op.CheckResult("x.g", "g", op.GREEN, op.STATIC, "")
    assert op.aggregate([info, pend, green]) == "GO"
    red = op.CheckResult("x.r", "r", op.RED, op.STATIC, "")
    assert op.aggregate([info, pend, green, red]) == "NO-GO"


# --------------------------------------------------------------------------------------------
# Regression-guard: the REAL operator-locked Gate-B slate resolves GREEN today (no RED).
# Runs against the actual run_gate_b constants with a CLEAN env (no operator overrides).
# --------------------------------------------------------------------------------------------

def test_real_slate_static_is_green(monkeypatch):
    for var in (
        "PG_GENERATOR_MODEL", "OPENROUTER_DEFAULT_MODEL", "PG_MIRROR_MODEL", "PG_SENTINEL_MODEL",
        "PG_BENCHMARK_JUDGE_MODEL", "PG_JUDGE_MODEL", "PG_SCOPE_TOPIC_GATE_HARD_DROP",
        "PG_SPAN_PER_SOURCE_CITE_CAP", "PG_FOUR_ROLE_TRANSPORT",
    ):
        monkeypatch.delenv(var, raising=False)
    # P2(b): clear ALL ambient PG_OPREADY_* so Thresholds() is the CLEAN slate baseline — an operator
    # /CI override (e.g. a lowered floor or a different expected slug) must not silently shift the
    # regression-guard baseline.
    for var in list(os.environ):
        if var.startswith("PG_OPREADY_"):
            monkeypatch.delenv(var, raising=False)
    th = op.Thresholds()
    # CLEAN env ({}) => the resolver sees only the slate (no stray operator overrides).
    results, ctx = op.run_static_checks({}, th)
    reds = [r.check_id for r in results if r.is_red]
    assert reds == [], f"the operator-locked Gate-B slate is NOT GREEN today: {reds}"
    assert op.aggregate(results) == "GO"
    # the resolved verifier lineup matches the operator expectation.
    assert ctx["judge_slug"] == th.expect_judge


# --------------------------------------------------------------------------------------------
# P0 — the harness leaves os.environ BYTE-IDENTICAL (importing run_gate_b mutates it via
# load_dotenv + apply_native_thread_safety_clamp; run_static_checks must restore it).
# --------------------------------------------------------------------------------------------

def test_process_env_byte_identical_restores_mutation(monkeypatch):
    # Direct mechanism test (robust regardless of the import-cache state): a mutation INSIDE the guard
    # is fully undone on exit — added keys dropped, changed keys restored, removed keys re-set.
    monkeypatch.setenv("PG_OPREADY_TEST_PREEXISTING", "orig")
    monkeypatch.setenv("PG_OPREADY_TEST_REMOVED", "present")
    monkeypatch.delenv("PG_OPREADY_TEST_ADDED", raising=False)
    before = dict(os.environ)
    with op._process_env_byte_identical():
        os.environ["PG_OPREADY_TEST_ADDED"] = "x"               # added inside
        os.environ["PG_OPREADY_TEST_PREEXISTING"] = "mutated"   # changed inside
        del os.environ["PG_OPREADY_TEST_REMOVED"]               # removed inside
    assert dict(os.environ) == before


def test_run_static_checks_leaves_env_byte_identical(monkeypatch):
    # The READ-ONLY contract end-to-end: pre-clear the native-thread-clamp knobs so a leak from the
    # transitive apply_native_thread_safety_clamp() would be visible, then assert run_static_checks
    # restores os.environ byte-for-byte.
    for var in ("TOKENIZERS_PARALLELISM", "OMP_NUM_THREADS", "MKL_NUM_THREADS",
                "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        monkeypatch.delenv(var, raising=False)
    before = dict(os.environ)
    op.run_static_checks(os.environ, op.Thresholds())
    assert dict(os.environ) == before


# --------------------------------------------------------------------------------------------
# P1 resolver-fidelity — a MALFORMED numeric env floors to the SLATE value (mirrors apply()).
# --------------------------------------------------------------------------------------------

def test_resolver_malformed_numeric_env_mirrors_apply():
    meta = op.SlateMeta(
        slate={"PG_FLOOR": "740"}, force_on=frozenset(), force_exact=frozenset(),
        required=(), required_off=(),
    )
    # production apply() (run_gate_b.py:2337-2341) writes str(int(max(float(value), float(value))))
    # == the FLOORED SLATE value on a malformed numeric env, NOT the raw env string.
    eff = op.resolve_effective_config({"PG_FLOOR": "not-a-number"}, meta)
    assert eff["PG_FLOOR"] == "740"
    # a non-numeric SLATE value (production would crash; preflight must not) carries through.
    meta_str = op.SlateMeta(
        slate={"PG_STRKEY": "auto"}, force_on=frozenset(), force_exact=frozenset(),
        required=(), required_off=(),
    )
    eff_str = op.resolve_effective_config({}, meta_str)
    assert eff_str["PG_STRKEY"] == "auto"


# --------------------------------------------------------------------------------------------
# P1 launch-path + P2(a) AST wiring check (call-node, not a substring).
# --------------------------------------------------------------------------------------------

def test_source_calls_is_ast_not_substring():
    real = "def f():\n    enable_four_role_mode()\n"
    commented = "def f():\n    # enable_four_role_mode()\n    return 1\n"
    string_literal = "def f():\n    x = 'enable_four_role_mode()'\n    return x\n"
    assert op._source_calls(real, None, "enable_four_role_mode")
    assert not op._source_calls(commented, None, "enable_four_role_mode")
    assert not op._source_calls(string_literal, None, "enable_four_role_mode")


def test_source_calls_scoped_to_function():
    src = (
        "def gate_around_question():\n    pass\n\n"
        "def main():\n    apply_full_capability_benchmark_slate()\n"
    )
    # the call lives in main(), NOT in gate_around_question -> scoped search distinguishes them.
    assert not op._source_calls(src, "gate_around_question", "apply_full_capability_benchmark_slate")
    assert op._source_calls(src, "main", "apply_full_capability_benchmark_slate")
    assert op._source_calls(src, None, "apply_full_capability_benchmark_slate")


def test_launch_path_checks_present_slate_green_disclosure_info(monkeypatch):
    for var in list(os.environ):
        if var.startswith("PG_OPREADY_"):
            monkeypatch.delenv(var, raising=False)
    results, _ = op.run_static_checks({}, op.Thresholds())
    by = {r.check_id: r for r in results}
    # the canonical entrypoint (run_gate_b.py) DOES apply the slate -> GREEN, gates the verdict.
    assert "D-1.launch_path.slate_applied" in by
    assert by["D-1.launch_path.slate_applied"].status == op.GREEN
    # the --pathB-gate skip is a DISCLOSURE (INFO) — surfaced, never gates.
    assert "D-1.launch_path.pathB_gate_skips_slate" in by
    assert by["D-1.launch_path.pathB_gate_skips_slate"].is_info
