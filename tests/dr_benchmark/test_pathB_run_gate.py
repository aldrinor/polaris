"""Fixtures for the Path-B run gate (I-safety-002b / #925). Pure logic, no live system."""

from __future__ import annotations

import os

import pytest

from scripts.dr_benchmark.pathB_run_gate import (
    GateError,
    LLMCall,
    RolePin,
    assert_post_run,
    build_effective_config,
    effective_config_hash,
    is_secret_var,
    preflight,
    resolve_canonical_slug,
    served_identity,
)

_SALT = b"pathB-test-salt"


# --- secret detection: credentials redacted, *_MAX_TOKENS knobs are NOT secrets ---
def test_is_secret_var() -> None:
    assert is_secret_var("OPENROUTER_API_KEY") is True
    assert is_secret_var("SERPER_API_KEY") is True
    assert is_secret_var("SEMANTIC_SCHOLAR_API_KEY") is True
    # the trap: many PG_*_MAX_TOKENS knobs must NOT be treated as secrets
    assert is_secret_var("PG_SECTION_MAX_TOKENS") is False
    assert is_secret_var("PG_VERIFY_MAX_TOKENS") is False
    assert is_secret_var("PG_SECTION_TOKEN_BUDGET") is False
    assert is_secret_var("PG_V30_ENABLED") is False


def test_effective_config_redacts_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-super-secret-value-123")
    monkeypatch.setenv("PG_V30_ENABLED", "1")
    cfg = build_effective_config(["OPENROUTER_API_KEY", "PG_V30_ENABLED"], _SALT)
    # secret: NO value, only presence + length + salted hmac
    assert cfg["OPENROUTER_API_KEY"]["secret"] is True
    assert "value" not in cfg["OPENROUTER_API_KEY"]
    assert cfg["OPENROUTER_API_KEY"]["present"] is True
    assert cfg["OPENROUTER_API_KEY"]["length"] == len("sk-super-secret-value-123")
    assert "sk-super-secret" not in str(cfg["OPENROUTER_API_KEY"])
    # non-secret: value retained
    assert cfg["PG_V30_ENABLED"]["value"] == "1"


# --- served-identity surrogate: stable, excludes volatile fields ---
def test_served_identity_excludes_volatile() -> None:
    base = {"provider_name": "deepinfra", "model": "deepseek-v4-pro", "system_fingerprint": "fp_abc"}
    a = dict(base, id="req-1", created=111, usage={"total_tokens": 10}, latency_ms=900, cost=0.02)
    b = dict(base, id="req-2", created=222, usage={"total_tokens": 99}, latency_ms=50, cost=0.5)
    # same stable identity despite different volatile metadata
    assert served_identity(a) == served_identity(b)
    # different provider -> different identity
    c = dict(base, provider_name="other")
    assert served_identity(c) != served_identity(a)


# --- preflight fatal assertions ---
def _full_power_env(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra")
    monkeypatch.setenv("SERPER_API_KEY", "x")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "y")


_GEN_SLUG = "deepseek/deepseek-v4-pro"
_EVAL_SLUG = "google/gemma-4-31b-it"


def _pins() -> list[RolePin]:
    return [
        RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model")),
        RolePin("evaluator", _EVAL_SLUG, "deepinfra", ("provider_name", "model")),
    ]


def _gen_pin() -> list[RolePin]:
    """Single-role pin for targeted failure tests (avoids the all-roles-present check masking)."""
    return [RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model"))]


def test_preflight_passes_full_power(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight(["PG_V30_ENABLED"], _pins(), _SALT, offline=True)
    assert pin["openrouter_allow_fallbacks"] is False
    assert pin["effective_config_hash"]


def test_preflight_fatal_on_fallbacks_true(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "true")
    with pytest.raises(GateError, match="ALLOW_FALLBACKS"):
        preflight([], _pins(), _SALT, offline=True)


def test_preflight_fatal_on_multi_provider(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra,fireworks")
    with pytest.raises(GateError, match="singleton"):
        preflight([], _pins(), _SALT, offline=True)


def test_preflight_fatal_on_missing_retrieval_cred(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    with pytest.raises(GateError, match="retrieval credentials"):
        preflight([], _pins(), _SALT, offline=True)


def test_preflight_fatal_on_no_surrogate_fields(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    bad = [RolePin("generator", _GEN_SLUG, "deepinfra", ())]
    with pytest.raises(GateError, match="surrogate"):
        preflight([], bad, _SALT, offline=True)


def test_preflight_fatal_on_short_model_slug(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    bad = [RolePin("generator", "deepseek-v4-pro", "deepinfra", ("model",))]  # no provider/ prefix
    with pytest.raises(GateError, match="FULL slug"):
        preflight([], bad, _SALT, offline=True)


def test_preflight_fatal_on_unreachable_backend(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    with pytest.raises(GateError, match="unreachable"):
        preflight([], _gen_pin(), _SALT, reachability_prober=lambda b: b != "serper")


def test_preflight_passes_with_reachable_prober(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    # Codex P2 (iter-1 diff): mock resolve_canonical_slug so this stays a pure-logic test
    # (the suite must not depend on live OpenRouter catalog reachability).
    import scripts.dr_benchmark.pathB_run_gate as gate
    monkeypatch.setattr(gate, "resolve_canonical_slug", lambda slug: None)
    pin = preflight([], _gen_pin(), _SALT, reachability_prober=lambda b: True)
    assert pin["reachability_checked"] is True


# --- post-run fatal assertions ---
def _good_call(role: str) -> LLMCall:
    model = _GEN_SLUG if role == "generator" else _EVAL_SLUG
    return LLMCall(
        call_id=f"c-{role}", role=role, prompt_messages_present=True, request_hash="h",
        response_metadata={"provider_name": "deepinfra", "model": model},
    )


def test_post_run_passes(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight(["PG_V30_ENABLED"], _pins(), _SALT, offline=True)
    res = assert_post_run(pin, ["PG_V30_ENABLED"], _SALT,
                          [_good_call("generator"), _good_call("evaluator")], {"serper", "semantic_scholar"})
    assert set(res["served_identity_by_role"]) == {"generator", "evaluator"}


def test_post_run_fatal_on_missing_role(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight([], _pins(), _SALT, offline=True)  # pins generator+evaluator
    with pytest.raises(GateError, match="no captured LLM call"):
        assert_post_run(pin, [], _SALT, [_good_call("generator")], {"serper", "semantic_scholar"})  # evaluator missing


def test_post_run_fatal_on_incomplete_capture(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight([], _gen_pin(), _SALT, offline=True)
    bad = [LLMCall("c1", "generator", True, None, {"provider_name": "deepinfra", "model": _GEN_SLUG})]
    with pytest.raises(GateError, match="incomplete capture"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


def test_post_run_fatal_on_missing_surrogate_field(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pins = [RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model", "system_fingerprint"))]
    pin = preflight([], pins, _SALT, offline=True)
    bad = [LLMCall("c1", "generator", True, "h", {"provider_name": "deepinfra", "model": _GEN_SLUG})]
    with pytest.raises(GateError, match="surrogate field"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


def test_post_run_fatal_on_provider_drift(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight([], _gen_pin(), _SALT, offline=True)
    bad = [LLMCall("c1", "generator", True, "h", {"provider_name": "FALLBACK", "model": _GEN_SLUG})]
    with pytest.raises(GateError, match="served provider"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


# I-bug-944 (#925 smoke #13): provider compare is case-insensitive (OpenRouter returns
# "Fireworks" / "DeepInfra" with title case; the pin env var is lower-case by convention).
def test_post_run_passes_on_provider_case_difference(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight([], _gen_pin(), _SALT, offline=True)
    # Pinned "deepinfra" (lower); served "DeepInfra" (title) — same identity, must pass.
    good = [LLMCall("c1", "generator", True, "h", {"provider_name": "DeepInfra", "model": _GEN_SLUG})]
    res = assert_post_run(pin, [], _SALT, good, {"serper", "semantic_scholar"})
    assert "generator" in res["served_identity_by_role"]


def test_post_run_fatal_on_model_drift(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight([], _gen_pin(), _SALT, offline=True)
    bad = [LLMCall("c1", "generator", True, "h", {"provider_name": "deepinfra", "model": "deepseek/deepseek-v3.2"})]
    with pytest.raises(GateError, match="matches neither"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


# I-bug-945 (#931 smoke #14): OpenRouter chat-completions returns the canonical_slug as the
# served `model` while the env pin holds the alias. Preflight resolves alias→canonical_slug
# via GET /api/v1/models so assert_post_run accepts either form (alias OR canonical_slug),
# while the persisted pin records BOTH as the pre-registration anchor.
def test_post_run_passes_when_served_model_is_canonical_slug(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    canonical = "deepseek/deepseek-v4-pro-20260423"
    pins = [RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model"), canonical_slug=canonical)]
    pin = preflight([], pins, _SALT, offline=True)
    # Served `model` is the dated canonical_slug; pin's alias is `deepseek/deepseek-v4-pro`.
    good = [LLMCall("c1", "generator", True, "h", {"provider_name": "deepinfra", "model": canonical})]
    res = assert_post_run(pin, [], _SALT, good, {"serper", "semantic_scholar"})
    assert "generator" in res["served_identity_by_role"]


def test_post_run_fatal_when_served_matches_neither_alias_nor_canonical(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pins = [RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model"), canonical_slug="deepseek/deepseek-v4-pro-20260423")]
    pin = preflight([], pins, _SALT, offline=True)
    # Served `model` is a different family entirely — must FAIL.
    bad = [LLMCall("c1", "generator", True, "h", {"provider_name": "deepinfra", "model": "deepseek/deepseek-v3.2"})]
    with pytest.raises(GateError, match="matches neither pinned alias"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


def test_post_run_surrogate_stable_across_mixed_alias_and_canonical(monkeypatch) -> None:
    """Codex P2#4: same role mixing alias + canonical_slug must produce a single surrogate
    value (raw-model drift is identity-preserving once normalized; the gate must not false-
    fail on the mid-run drift check)."""
    _full_power_env(monkeypatch)
    canonical = "deepseek/deepseek-v4-pro-20260423"
    pins = [RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model"), canonical_slug=canonical)]
    pin = preflight([], pins, _SALT, offline=True)
    calls = [
        LLMCall("c1", "generator", True, "h", {"provider_name": "deepinfra", "model": _GEN_SLUG}),
        LLMCall("c2", "generator", True, "h", {"provider_name": "deepinfra", "model": canonical}),
    ]
    res = assert_post_run(pin, [], _SALT, calls, {"serper", "semantic_scholar"})
    assert "generator" in res["served_identity_by_role"]


def test_resolve_canonical_slug_returns_dated_snapshot(monkeypatch) -> None:
    """Resolver hits OpenRouter /api/v1/models and exact-matches on `id`."""
    class _R:
        status_code = 200
        def json(self) -> dict:
            return {"data": [
                {"id": "other/model", "canonical_slug": "other/model-20260101"},
                {"id": "deepseek/deepseek-v4-pro", "canonical_slug": "deepseek/deepseek-v4-pro-20260423"},
            ]}
        def raise_for_status(self) -> None: ...
    import scripts.dr_benchmark.pathB_run_gate as gate
    monkeypatch.setattr(gate, "__name__", gate.__name__)  # no-op anchor for the lambda below
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _R())
    assert resolve_canonical_slug("deepseek/deepseek-v4-pro") == "deepseek/deepseek-v4-pro-20260423"


def test_resolve_canonical_slug_returns_none_when_alias_equals_canonical(monkeypatch) -> None:
    """When the catalog reports id == canonical_slug, return None (no dated suffix needed)."""
    class _R:
        status_code = 200
        def json(self) -> dict:
            return {"data": [{"id": "x/y", "canonical_slug": "x/y"}]}
        def raise_for_status(self) -> None: ...
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _R())
    assert resolve_canonical_slug("x/y") is None


def test_resolve_canonical_slug_fail_closed_on_unknown_alias(monkeypatch) -> None:
    """Codex P2#2: if the alias isn't in the OpenRouter catalog, FAIL CLOSED."""
    class _R:
        status_code = 200
        def json(self) -> dict:
            return {"data": [{"id": "real/model", "canonical_slug": "real/model-20260101"}]}
        def raise_for_status(self) -> None: ...
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _R())
    with pytest.raises(GateError, match="alias unknown"):
        resolve_canonical_slug("does-not/exist")


def test_preflight_persisted_pin_includes_canonical_slug(monkeypatch) -> None:
    """The serialized pin must carry canonical_slug so pathB_gate_pin.json is the audit anchor."""
    _full_power_env(monkeypatch)
    canonical = "deepseek/deepseek-v4-pro-20260423"
    pins = [RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model"), canonical_slug=canonical)]
    pin = preflight([], pins, _SALT, offline=True)
    assert pin["role_pins"][0]["canonical_slug"] == canonical


def test_post_run_fatal_on_served_identity_drift(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pins = [RolePin("generator", _GEN_SLUG, "deepinfra", ("provider_name", "model", "system_fingerprint"))]
    pin = preflight([], pins, _SALT, offline=True)
    # two generator calls with DIFFERENT system_fingerprint -> surrogate drift
    calls = [
        LLMCall("c1", "generator", True, "h", {"provider_name": "deepinfra", "model": _GEN_SLUG, "system_fingerprint": "fp_a"}),
        LLMCall("c2", "generator", True, "h", {"provider_name": "deepinfra", "model": _GEN_SLUG, "system_fingerprint": "fp_b"}),
    ]
    with pytest.raises(GateError, match="surrogate drifted"):
        assert_post_run(pin, [], _SALT, calls, {"serper", "semantic_scholar"})


def test_post_run_fatal_on_backend_not_attempted(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    pin = preflight([], _pins(), _SALT, offline=True)
    calls = [_good_call("generator"), _good_call("evaluator")]
    with pytest.raises(GateError, match="never attempted"):
        assert_post_run(pin, [], _SALT, calls, {"serper"})  # missing semantic_scholar


def test_post_run_fatal_on_config_drift(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_V30_ENABLED", "1")
    pin = preflight(["PG_V30_ENABLED"], _pins(), _SALT, offline=True)
    monkeypatch.setenv("PG_V30_ENABLED", "0")  # drift
    calls = [_good_call("generator"), _good_call("evaluator")]
    with pytest.raises(GateError, match="drift"):
        assert_post_run(pin, ["PG_V30_ENABLED"], _SALT, calls, {"serper", "semantic_scholar"})


def test_full_control_surface_includes_retrieval_creds() -> None:
    from pathlib import Path
    from scripts.dr_benchmark.pathB_run_gate import full_control_surface
    surface = full_control_surface([Path("scripts/dr_benchmark")])
    assert "SERPER_API_KEY" in surface and "SEMANTIC_SCHOLAR_API_KEY" in surface
