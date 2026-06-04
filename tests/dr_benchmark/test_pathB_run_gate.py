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
    resolve_role_provider,
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


def test_preflight_accepts_multi_provider_post_i_bug_946(monkeypatch) -> None:
    """SUPERSEDED by I-bug-946 (#932): multi-provider order is now valid. Each role's actual
    served provider is resolved at preflight via /api/v1/models/<id>/endpoints, so disjoint
    model provider sets (e.g. fireworks for deepseek-v4-pro + novita for gemma) require a
    multi-entry order. The old singleton check raised on this; the new gate enforces only
    that the list is non-empty AND that each role intersects with at least one eligible
    endpoint (see test_preflight_fatal_on_empty_provider_order and
    test_resolve_role_provider_fails_closed_on_no_intersection)."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "deepinfra,fireworks")
    # offline=True skips the resolver; the multi-provider order itself is now accepted.
    pin = preflight([], _pins(), _SALT, offline=True)
    assert pin["openrouter_provider_order"] == "deepinfra,fireworks"


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
        preflight([], _gen_pin(), _SALT, reachability_prober=lambda b: b != "serper",
                  enforce_architecture_coverage=False)


def test_preflight_passes_with_reachable_prober(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    # Codex P2 (iter-1 diff): mock resolve_canonical_slug so this stays a pure-logic test
    # (the suite must not depend on live OpenRouter catalog reachability).
    import scripts.dr_benchmark.pathB_run_gate as gate
    monkeypatch.setattr(gate, "resolve_canonical_slug", lambda slug: None)
    # I-meta-001 (#933) Step 9: this test uses online preflight (offline=False) so we must
    # explicitly opt out of architecture coverage — the unit fixture's 1-role pin is not
    # the locked 4-role architecture by design.
    pin = preflight([], _gen_pin(), _SALT, reachability_prober=lambda b: True,
                    enforce_architecture_coverage=False)
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


# --- I-bug-946 (#932): per-role provider resolution via /api/v1/models/<id>/endpoints ---

class _MockEndpointsResponse:
    """Mock requests.Response carrying an OpenRouter endpoints payload."""
    status_code = 200
    def __init__(self, endpoints: list[dict]) -> None:
        self._payload = {"data": {"endpoints": endpoints}}
    def json(self) -> dict:
        return self._payload
    def raise_for_status(self) -> None:
        return None


def _patch_endpoints(monkeypatch, endpoints: list[dict]) -> None:
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: _MockEndpointsResponse(endpoints))


def test_resolve_role_provider_returns_first_in_order_match(monkeypatch) -> None:
    _patch_endpoints(monkeypatch, [
        {"provider_name": "Novita", "status": 0},
        {"provider_name": "DeepInfra", "status": 0},
    ])
    # Order prefers fireworks (absent), then novita (present) — must return Novita.
    assert resolve_role_provider("google/gemma-4-31b-it", ["fireworks", "novita"]) == "Novita"


def test_resolve_role_provider_fails_closed_on_no_intersection(monkeypatch) -> None:
    _patch_endpoints(monkeypatch, [
        {"provider_name": "Novita", "status": 0},
        {"provider_name": "DeepInfra", "status": 0},
    ])
    with pytest.raises(GateError, match="no intersection"):
        resolve_role_provider("google/gemma-4-31b-it", ["fireworks"])


def test_resolve_role_provider_skips_degraded_endpoints(monkeypatch) -> None:
    """Codex P2#4: status != 0 means degraded/lower-priority; skip from intersection."""
    _patch_endpoints(monkeypatch, [
        {"provider_name": "Fireworks", "status": -5},  # degraded — must skip
        {"provider_name": "Novita", "status": 0},
    ])
    # If fireworks weren't degraded, would return Fireworks. Since it IS degraded, fall to novita.
    assert resolve_role_provider("any/model", ["fireworks", "novita"]) == "Novita"


def test_resolve_role_provider_fails_closed_on_empty_endpoints(monkeypatch) -> None:
    _patch_endpoints(monkeypatch, [])
    with pytest.raises(GateError, match="no endpoints"):
        resolve_role_provider("any/model", ["fireworks"])


def test_resolve_role_provider_case_insensitive_with_catalog_spelling(monkeypatch) -> None:
    """Codex P2#3: order is case-insensitive; pin preserves catalog spelling."""
    _patch_endpoints(monkeypatch, [
        {"provider_name": "Novita", "status": 0},
    ])
    # User typed 'NOVITA' in env; catalog spelling is 'Novita'. Returned pin keeps catalog case.
    assert resolve_role_provider("any/model", ["NOVITA"]) == "Novita"


def test_resolve_role_provider_treats_missing_status_as_eligible(monkeypatch) -> None:
    """Some endpoints omit the status field entirely; treat as status==0 (eligible)."""
    _patch_endpoints(monkeypatch, [
        {"provider_name": "Fireworks"},  # no status field
    ])
    assert resolve_role_provider("any/model", ["fireworks"]) == "Fireworks"


def test_preflight_pins_per_role_from_resolution(monkeypatch) -> None:
    """End-to-end: preflight populates provider_name per role from endpoint resolution."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "fireworks,novita")
    # Pre-injected RolePins so offline=True path skips the resolver entirely; this test
    # asserts that the role_pin's provider_name flows through to the persisted pin.
    pins = [
        RolePin("generator", _GEN_SLUG, "Fireworks", ("provider_name", "model")),
        RolePin("evaluator", _EVAL_SLUG, "Novita", ("provider_name", "model")),
    ]
    pin = preflight([], pins, _SALT, offline=True)
    assert pin["role_pins"][0]["provider_name"] == "Fireworks"
    assert pin["role_pins"][1]["provider_name"] == "Novita"


def test_preflight_accepts_multi_provider_order(monkeypatch) -> None:
    """Multi-entry provider_order is now valid (was rejected as non-singleton pre-I-bug-946)."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "fireworks,novita")
    pins = [RolePin("generator", _GEN_SLUG, "Fireworks", ("provider_name", "model"))]
    pin = preflight([], pins, _SALT, offline=True)
    assert pin["openrouter_provider_order"] == "fireworks,novita"


def test_preflight_fatal_on_empty_provider_order(monkeypatch) -> None:
    _full_power_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "")
    with pytest.raises(GateError, match="at least one candidate provider"):
        preflight([], _gen_pin(), _SALT, offline=True)


def test_preflight_fatal_on_divergent_entailment_model(monkeypatch) -> None:
    """Codex P2#3 iter-2: PG_ENTAILMENT_MODEL must equal PG_EVALUATOR_MODEL or be unset."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-2-27b-it")
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")
    with pytest.raises(GateError, match="PG_ENTAILMENT_MODEL"):
        preflight([], _gen_pin(), _SALT, offline=True)


def test_preflight_online_resolves_per_role_distinct_providers(monkeypatch) -> None:
    """Codex iter-1 diff P1#1 regression: online preflight (offline=False) MUST always
    overwrite provider_name from the resolver, even when RolePin pre-seeds a value. Without
    this, _role_pins's old env-first-entry seed would silently bypass per-role resolution
    and pin both roles to the first env provider (the smoke-#15 bug, in a different shape)."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_PROVIDER_ORDER", "fireworks,novita")
    # Mock the endpoint resolver to return distinct providers per model: Fireworks for the
    # generator's model (deepseek-v4-pro) and Novita for the evaluator's (gemma).
    import requests
    def _mock_get(url, *args, **kwargs):
        if "deepseek-v4-pro" in url:
            return _MockEndpointsResponse([
                {"provider_name": "Fireworks", "status": 0},
                {"provider_name": "Novita", "status": 0},
            ])
        if "gemma-4-31b-it" in url:
            return _MockEndpointsResponse([
                {"provider_name": "Novita", "status": 0},
                {"provider_name": "DeepInfra", "status": 0},
            ])
        # Models endpoint for canonical_slug resolution (I-bug-945) — return a benign list.
        return _MockEndpointsResponse_models()
    class _MockEndpointsResponse_models:
        status_code = 200
        def __init__(self) -> None: pass
        def json(self):
            return {"data": [
                {"id": _GEN_SLUG, "canonical_slug": _GEN_SLUG + "-x"},
                {"id": _EVAL_SLUG, "canonical_slug": _EVAL_SLUG + "-y"},
            ]}
        def raise_for_status(self) -> None: ...
    monkeypatch.setattr(requests, "get", _mock_get)
    # _role_pins() seeds provider_name="" (post-Codex-iter-1 fix); preflight must overwrite.
    pins = [
        RolePin("generator", _GEN_SLUG, "", ("provider_name", "model")),
        RolePin("evaluator", _EVAL_SLUG, "", ("provider_name", "model")),
    ]
    pin = preflight([], pins, _SALT, offline=False, reachability_prober=lambda b: True,
                    enforce_architecture_coverage=False)
    by_role = {rp["role"]: rp["provider_name"] for rp in pin["role_pins"]}
    assert by_role["generator"] == "Fireworks"
    assert by_role["evaluator"] == "Novita"


def test_preflight_fatal_when_only_entailment_model_diverges(monkeypatch) -> None:
    """Codex iter-1 diff P2#2: if ONLY PG_ENTAILMENT_MODEL is set away from the default and
    PG_EVALUATOR_MODEL is unset (so the evaluator uses default = gemma-4-31b-it), the gate
    must STILL fail closed — effective values still differ."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-2-27b-it")
    monkeypatch.delenv("PG_EVALUATOR_MODEL", raising=False)
    with pytest.raises(GateError, match="effective PG_ENTAILMENT_MODEL"):
        preflight([], _gen_pin(), _SALT, offline=True)


def test_get_role_provider_explicit_lookup_ignores_ambient_role() -> None:
    """Codex iter-1 diff P1#2 regression: get_role_provider(role) MUST NOT read ambient _ROLE.
    The entailment judge fires under _ROLE=='generator' but posts the evaluator model; it
    must explicitly request the evaluator provider."""
    from src.polaris_graph.benchmark import pathB_capture as _pb
    token_rp = _pb.set_role_providers({"generator": "Fireworks", "evaluator": "Novita"})
    try:
        with _pb.llm_role("generator"):
            # Under generator scope, explicit evaluator lookup must still return Novita.
            assert _pb.get_role_provider("evaluator") == "Novita"
            # And current_role_provider (ambient-based) returns Fireworks per spec.
            assert _pb.current_role_provider() == "Fireworks"
    finally:
        _pb.reset_role_providers(token_rp)


def test_preflight_freezes_smokes_when_lock_pending_signature(monkeypatch) -> None:
    """I-meta-001 (#933) Step 9: when lock status is codex_approved_pending_operator_signature
    AND enforce_architecture_coverage=True (default for production / online preflight),
    the gate MUST refuse to PASS — smokes are structurally frozen until lock is promoted."""
    _full_power_env(monkeypatch)
    import scripts.dr_benchmark.pathB_run_gate as gate
    monkeypatch.setattr(gate, "resolve_canonical_slug", lambda slug: None)
    with pytest.raises(GateError, match="codex_approved_pending_operator_signature"):
        preflight([], _gen_pin(), _SALT, reachability_prober=lambda b: True,
                  enforce_architecture_coverage=True)


def test_preflight_architecture_coverage_can_be_explicitly_disabled(monkeypatch) -> None:
    """Tests/legacy code can opt out of the architecture coverage check explicitly."""
    _full_power_env(monkeypatch)
    import scripts.dr_benchmark.pathB_run_gate as gate
    monkeypatch.setattr(gate, "resolve_canonical_slug", lambda slug: None)
    pin = preflight([], _gen_pin(), _SALT, reachability_prober=lambda b: True,
                    enforce_architecture_coverage=False)
    assert pin["architecture_coverage"]["status"] == "skipped"


def test_role_provider_contextvar_set_get_reset() -> None:
    """The pathB_capture ContextVar must roundtrip: set → get-by-role → reset."""
    from src.polaris_graph.benchmark import pathB_capture as _pb
    # Outside any role/gate scope, get returns None.
    assert _pb.current_role_provider() is None
    token_rp = _pb.set_role_providers({"generator": "Fireworks", "evaluator": "Novita"})
    try:
        # Without a role contextvar set, still None (no role to look up).
        assert _pb.current_role_provider() is None
        with _pb.llm_role("generator"):
            assert _pb.current_role_provider() == "Fireworks"
        with _pb.llm_role("evaluator"):
            assert _pb.current_role_provider() == "Novita"
        with _pb.llm_role("unknown_role"):
            assert _pb.current_role_provider() is None
    finally:
        _pb.reset_role_providers(token_rp)
    assert _pb.current_role_provider() is None


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


# --- I-meta-002 PR-9/M4: self-host served==pinned (NO NETWORK, stub metadata) -------------
# The runtime lock pins three self-hosted vLLM verifier roles (serving_route: vast_self_host*).
# I-run11-004:
#   mirror   -> z-ai/glm-5.1        (vast_self_host_bf16)
#   sentinel -> minimax/minimax-m2  (vast_self_host)  — CERTIFIED decomposition detector
#   judge    -> qwen/qwen3.6-35b-a3b (vast_self_host_fp8)
# Preflight branches on serving_route (NO OpenRouter resolution; validate PG_<ROLE>_BASE_URL);
# assert_post_run consumes the M1 _pathb_served {endpoint, model} (flattened by
# build_response_metadata onto top-level model+endpoint keys) and fails closed on a wrong
# model / wrong box. These tests inject stub captured-metadata dicts — no real endpoint.

_MIRROR_SLUG = "z-ai/glm-5.1"
_SENTINEL_SLUG = "minimax/minimax-m2"
_MIRROR_BASE_URL = "http://10.0.0.5:8000"


def _self_host_pin(role: str, slug: str) -> RolePin:
    """A self-host RolePin: surrogate_fields are unused by the self-host branch, but the
    preflight no-empty-surrogate guard still requires them non-empty (matches _role_pins())."""
    return RolePin(role, slug, "", ("provider_name", "model"))


def test_preflight_self_host_passes_when_base_url_set(monkeypatch) -> None:
    """A self-host role (mirror) passes preflight when PG_MIRROR_BASE_URL is set; NO OpenRouter
    resolution fires (offline=True keeps the generator path off-network too)."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL + "/")  # trailing slash tolerated
    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    rp = pin["role_pins"][0]
    assert rp["serving_route"] == "vast_self_host_bf16"
    assert rp["base_url"] == _MIRROR_BASE_URL  # trailing slash stripped at pin time
    # Self-host role is NOT resolved via OpenRouter: provider_name stays empty.
    assert rp["provider_name"] == ""


def test_preflight_self_host_fatal_when_base_url_unset(monkeypatch) -> None:
    """Fail-closed (LAW VI): a self-host role with no PG_<ROLE>_BASE_URL is a deployment error."""
    _full_power_env(monkeypatch)
    monkeypatch.delenv("PG_SENTINEL_BASE_URL", raising=False)
    pins = [_self_host_pin("sentinel", _SENTINEL_SLUG)]
    with pytest.raises(GateError, match="PG_SENTINEL_BASE_URL"):
        preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)


def test_post_run_self_host_passes_when_model_and_endpoint_match(monkeypatch) -> None:
    """assert_post_run passes when served model == pinned slug AND served endpoint == base_url.
    The served metadata carries ONLY model+endpoint (the flattened _pathb_served, no provider)."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    # Served endpoint reported WITH a trailing slash — must still match (trailing-slash tolerant).
    good = [LLMCall("c1", "mirror", True, "h",
                    {"model": _MIRROR_SLUG, "endpoint": _MIRROR_BASE_URL + "/"})]
    res = assert_post_run(pin, [], _SALT, good, {"serper", "semantic_scholar"})
    assert "mirror" in res["served_identity_by_role"]


def test_post_run_self_host_fatal_on_missing_pathb_served(monkeypatch) -> None:
    """Missing endpoint/model (the _pathb_served block never reached capture) => fatal."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    # Only model present, endpoint absent -> the served-identity block is incomplete.
    bad = [LLMCall("c1", "mirror", True, "h", {"model": _MIRROR_SLUG})]
    with pytest.raises(GateError, match="captured no served identity"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


def test_post_run_self_host_fatal_on_wrong_model(monkeypatch) -> None:
    """A self-host box serving the WRONG model must abort the gate (clinical-safety: a wrong
    verifier model is a silent capability downgrade)."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    bad = [LLMCall("c1", "mirror", True, "h",
                   {"model": "cohere/command-r-plus", "endpoint": _MIRROR_BASE_URL})]
    with pytest.raises(GateError, match="served model"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


def test_post_run_self_host_fatal_on_wrong_endpoint(monkeypatch) -> None:
    """A self-host call served from the WRONG box (endpoint != pinned base_url) must abort."""
    _full_power_env(monkeypatch)
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
    bad = [LLMCall("c1", "mirror", True, "h",
                   {"model": _MIRROR_SLUG, "endpoint": "http://10.0.0.99:8000"})]
    with pytest.raises(GateError, match="served endpoint"):
        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})


def test_post_run_generator_openrouter_path_unchanged(monkeypatch) -> None:
    """The generator (serving_route: openrouter, provider_name present) is UNCHANGED: it still
    goes through the provider+model OpenRouter checks, not the self-host branch."""
    _full_power_env(monkeypatch)
    pin = preflight([], _gen_pin(), _SALT, offline=True, enforce_architecture_coverage=False)
    # generator's serving_route is 'openrouter' in the lock => OpenRouter path.
    assert pin["role_pins"][0]["serving_route"] == "openrouter"
    good = [_good_call("generator")]
    res = assert_post_run(pin, [], _SALT, good, {"serper", "semantic_scholar"})
    assert "generator" in res["served_identity_by_role"]


def test_role_serving_routes_maps_lock(monkeypatch) -> None:
    """The lock-sourced route map carries each role's serving_route (generator openrouter;
    mirror/sentinel/judge vast_self_host*)."""
    from scripts.dr_benchmark.pathB_run_gate import _role_serving_routes
    routes = _role_serving_routes()
    assert routes["generator"] == "openrouter"
    assert routes["mirror"].startswith("vast_self_host")
    assert routes["sentinel"].startswith("vast_self_host")
    assert routes["judge"].startswith("vast_self_host")
