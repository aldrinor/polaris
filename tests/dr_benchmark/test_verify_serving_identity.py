"""Tests for the verifier serving config + identity probe (I-meta-002 PR-8 / M2).

NO network, NO spend: the probe's HTTP client is INJECTED, so every test passes an
``httpx.Client(transport=httpx.MockTransport(...))`` returning canned ``/v1/models``
bodies. Two surfaces are covered:

1. Config shape — ``config/serving/verifier_roles.yaml`` parses, declares exactly the
   3 self-host roles, every ``model_slug`` AND ``vllm_args.served_model_name`` equals
   the lock-pinned slug, each role carries a ``model_source`` (the weights path, NOT
   lock-bound), the Judge has structured/guided decoding enabled, and the Mirror
   serves plain chat (no structured output).
2. Probe — PASSES when served == slug for all 3 roles; FAILS LOUD when a served
   model != the locked slug, when an endpoint is unreachable, when a role's
   base_url env is unset, and when the top-level /v1/models body is a non-object.
   Auth: sends ``Authorization: Bearer <PG_<ROLE>_API_KEY>`` only when that key is
   set, sends NO Authorization header when it is unset, and NEVER falls back to
   ``OPENROUTER_API_KEY``.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import yaml

from scripts.architecture.verify_lock import load_lock
from scripts.dr_benchmark.verify_serving_identity import (
    SELF_HOST_ROLES,
    RoleIdentityReport,
    ServingIdentityError,
    probe_serving_identity,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVING_CONFIG_PATH = _REPO_ROOT / "config" / "serving" / "verifier_roles.yaml"

_MIRROR_BASE = "http://mirror.internal:8001"
_SENTINEL_BASE = "http://sentinel.internal:8002"
_JUDGE_BASE = "http://judge.internal:8003"


@pytest.fixture
def _expected_slugs() -> dict[str, str]:
    """Lock-pinned model_slug per self-host role (the single source of truth)."""
    lock = load_lock()
    return {role: lock["required_roles"][role]["model_slug"] for role in SELF_HOST_ROLES}


@pytest.fixture(autouse=True)
def _role_endpoints(monkeypatch):
    """Configure per-role base_url + api_key env for every test (LAW VI)."""
    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE)
    monkeypatch.setenv("PG_SENTINEL_BASE_URL", _SENTINEL_BASE)
    monkeypatch.setenv("PG_JUDGE_BASE_URL", _JUDGE_BASE)
    monkeypatch.setenv("PG_MIRROR_API_KEY", "mirror-key")
    monkeypatch.setenv("PG_SENTINEL_API_KEY", "sentinel-key")
    # Judge has NO own key here. OPENROUTER_API_KEY is deliberately set to prove the
    # probe NEVER falls back to it (no-leak): the Judge request must carry NO
    # Authorization header despite this being present in the environment.
    monkeypatch.delenv("PG_JUDGE_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-leak-key")
    yield


def _load_serving_config() -> dict:
    return yaml.safe_load(_SERVING_CONFIG_PATH.read_text(encoding="utf-8"))


def _base_for_role(role: str) -> str:
    return {"mirror": _MIRROR_BASE, "sentinel": _SENTINEL_BASE, "judge": _JUDGE_BASE}[role]


def _models_handler(served_by_base: dict[str, str], *, status_code: int = 200):
    """MockTransport handler answering /v1/models per base URL (served id by host).

    ``served_by_base`` maps a base URL -> the served model id that host advertises.
    A base URL absent from the map yields a connect error (simulates unreachable).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        base = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        if base not in served_by_base:
            raise httpx.ConnectError("connection refused", request=request)
        payload = {
            "object": "list",
            "data": [{"id": served_by_base[base], "object": "model", "owned_by": "vllm"}],
        }
        return httpx.Response(status_code, json=payload)

    return handler


def _capturing_models_handler(served_by_base: dict[str, str], captured: dict[str, object]):
    """Like ``_models_handler`` but records the Authorization header per base URL.

    ``captured`` is filled in-place: ``captured[base]`` is the request's
    ``Authorization`` header value, or ``None`` when the request carried no
    Authorization header at all (the no-key / no-leak case).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        base = f"{request.url.scheme}://{request.url.host}:{request.url.port}"
        captured[base] = request.headers.get("Authorization")  # None if absent
        if base not in served_by_base:
            raise httpx.ConnectError("connection refused", request=request)
        payload = {
            "object": "list",
            "data": [{"id": served_by_base[base], "object": "model", "owned_by": "vllm"}],
        }
        return httpx.Response(200, json=payload)

    return handler


def _make_client(handler) -> httpx.Client:
    """Build an INJECTED MockTransport client (no network)."""
    return httpx.Client(transport=httpx.MockTransport(handler))


# ======================================================================================
# Config-shape tests
# ======================================================================================
def test_serving_config_parses_and_has_exactly_the_three_roles():
    config = _load_serving_config()
    assert "roles" in config
    assert sorted(config["roles"]) == sorted(SELF_HOST_ROLES)
    # The generator must NOT be served here (it runs on OpenRouter).
    assert "generator" not in config["roles"]


def test_serving_config_slugs_match_lock(_expected_slugs):
    config = _load_serving_config()
    for role, expected in _expected_slugs.items():
        block = config["roles"][role]
        assert block["model_slug"] == expected, role
        # served-model-name == locked slug is the M4 served==pinned identity surface.
        assert block["vllm_args"]["served_model_name"] == expected, role


def test_serving_config_declares_model_source_distinct_from_served_name(_expected_slugs):
    """Each role carries a model_source (the weights path); only served_model_name
    is bound to the lock slug. model_source is NOT lock-equality checked, so it may
    legitimately equal OR differ from the served slug (the casing/path differs in
    practice, e.g. CohereLabs/command-a-plus-05-2026-bf16 vs cohere/command-a-plus).
    """
    config = _load_serving_config()
    for role in SELF_HOST_ROLES:
        block = config["roles"][role]
        # model_source MUST be present and a non-empty string (the weights path).
        assert "model_source" in block, role
        assert isinstance(block["model_source"], str) and block["model_source"].strip(), role
        # served_model_name remains the lock-bound id; model_source is independent of it
        # (no lock-equality assertion on model_source — it is the weights location only).
        assert block["vllm_args"]["served_model_name"] == _expected_slugs[role], role


def test_serving_config_env_var_convention_matches_transport():
    config = _load_serving_config()
    for role in SELF_HOST_ROLES:
        block = config["roles"][role]
        assert block["base_url_env"] == f"PG_{role.upper()}_BASE_URL"
        assert block["api_key_env"] == f"PG_{role.upper()}_API_KEY"


def test_serving_config_judge_structured_outputs_enabled_mirror_plain_chat():
    config = _load_serving_config()
    judge_args = config["roles"]["judge"]["vllm_args"]
    assert judge_args["structured_outputs"] is True
    assert judge_args["guided_decoding"] is True
    # Mirror serves plain chat for <co> citations — NO structured-output constraint.
    mirror_args = config["roles"]["mirror"]["vllm_args"]
    assert mirror_args["structured_outputs"] is False
    # I-run11-004: the CERTIFIED MiniMax-M2 decomposition Sentinel requests a JSON object, so its
    # self-host serving config binds structured-outputs (the robust parser also tolerates non-JSON).
    sentinel_args = config["roles"]["sentinel"]["vllm_args"]
    assert sentinel_args["structured_outputs"] is True


def test_serving_config_gpu_specs_per_role():
    config = _load_serving_config()
    mirror_gpu = config["roles"]["mirror"]["gpu"]
    assert mirror_gpu["count"] == 8 and mirror_gpu["kind"] == "H100"
    sentinel_gpu = config["roles"]["sentinel"]["gpu"]
    # I-run11-004: Sentinel is now MiniMax-M2 (~229B MoE) — a 1xA100 80GB is infeasible (~458GB bf16),
    # so the sovereign self-host topology is an 8x80GB-class box @ fp8 (PENDING GPU procurement #90;
    # the benchmark stage routes the Sentinel via OpenRouter). Codex diff-gate iter-2 P1-3.
    assert sentinel_gpu["count"] == 8 and sentinel_gpu["kind"] == "H100"
    assert config["roles"]["sentinel"]["vllm_args"]["quantization"] == "fp8"
    judge_gpu = config["roles"]["judge"]["gpu"]
    assert judge_gpu["count"] == 1 and judge_gpu["kind"] == "H100"
    # Judge runs fp8 (the lock's vast_self_host_fp8 route).
    assert config["roles"]["judge"]["vllm_args"]["quantization"] == "fp8"


def test_serving_config_has_no_secrets():
    # No API key values in the file — only the NAME of the env var each role reads.
    raw = _SERVING_CONFIG_PATH.read_text(encoding="utf-8")
    lowered = raw.lower()
    assert "api_key:" not in lowered  # only api_key_env: <NAME> is allowed
    assert "bearer " not in lowered


# ======================================================================================
# Probe PASS — served == slug for all 3 roles (injected stub, no network)
# ======================================================================================
def test_probe_passes_when_all_served_match_lock(_expected_slugs):
    served_by_base = {_base_for_role(role): _expected_slugs[role] for role in SELF_HOST_ROLES}
    client = _make_client(_models_handler(served_by_base))

    reports = probe_serving_identity(http_client=client)

    assert len(reports) == len(SELF_HOST_ROLES)
    by_role = {r.role: r for r in reports}
    for role, expected in _expected_slugs.items():
        report = by_role[role]
        assert isinstance(report, RoleIdentityReport)
        assert report.reachable is True
        assert report.served_model == expected
        assert report.matches_lock is True


# ======================================================================================
# Probe AUTH — Authorization header sent iff PG_<ROLE>_API_KEY is set; never the
# OpenRouter key (no-leak)
# ======================================================================================
def test_probe_sends_bearer_when_role_api_key_set(_expected_slugs):
    """Mirror + Sentinel have PG_<ROLE>_API_KEY set -> request carries that exact key."""
    served_by_base = {_base_for_role(role): _expected_slugs[role] for role in SELF_HOST_ROLES}
    captured: dict[str, object] = {}
    client = _make_client(_capturing_models_handler(served_by_base, captured))

    probe_serving_identity(http_client=client)

    assert captured[_MIRROR_BASE] == "Bearer mirror-key"
    assert captured[_SENTINEL_BASE] == "Bearer sentinel-key"


def test_probe_sends_no_authorization_when_key_unset_and_never_uses_openrouter(_expected_slugs):
    """Judge has NO PG_JUDGE_API_KEY; OPENROUTER_API_KEY is present in env.

    The Judge request MUST carry NO Authorization header — the probe must never
    fall back to the OpenRouter key (no-leak to a self-host box, Codex P2).
    """
    served_by_base = {_base_for_role(role): _expected_slugs[role] for role in SELF_HOST_ROLES}
    captured: dict[str, object] = {}
    client = _make_client(_capturing_models_handler(served_by_base, captured))

    probe_serving_identity(http_client=client)

    # No Authorization header at all for the keyless Judge role.
    assert captured[_JUDGE_BASE] is None
    # And the OpenRouter key (set in the autouse fixture) leaked to NO role.
    assert all(value != "Bearer must-not-leak-key" for value in captured.values())


# ======================================================================================
# Probe FAIL LOUD — non-object top-level /v1/models body (structured error, not AttributeError)
# ======================================================================================
def test_probe_fails_loud_on_non_object_models_body():
    """A top-level JSON list (not an object) must raise ServingIdentityError, not
    AttributeError from raw.get on a non-dict (Codex P2)."""

    def handler(request: httpx.Request) -> httpx.Response:
        # /v1/models body is a JSON list, not the expected object.
        return httpx.Response(200, json=["not", "an", "object"])

    client = _make_client(handler)
    with pytest.raises(ServingIdentityError, match="non-object body"):
        probe_serving_identity(http_client=client)


# ======================================================================================
# Probe FAIL LOUD — wrong served model
# ======================================================================================
def test_probe_fails_loud_when_a_served_model_mismatches_lock(_expected_slugs):
    served_by_base = {_base_for_role(role): _expected_slugs[role] for role in SELF_HOST_ROLES}
    # Sentinel box serves the WRONG model.
    served_by_base[_SENTINEL_BASE] = "some/other-model"
    client = _make_client(_models_handler(served_by_base))

    with pytest.raises(ServingIdentityError, match="does NOT match the locked slug"):
        probe_serving_identity(http_client=client)


# ======================================================================================
# Probe FAIL LOUD — unreachable endpoint
# ======================================================================================
def test_probe_fails_loud_when_endpoint_unreachable(_expected_slugs):
    served_by_base = {_base_for_role(role): _expected_slugs[role] for role in SELF_HOST_ROLES}
    # Judge box is absent from the map -> the handler raises a ConnectError.
    del served_by_base[_JUDGE_BASE]
    client = _make_client(_models_handler(served_by_base))

    with pytest.raises(ServingIdentityError, match="unreachable"):
        probe_serving_identity(http_client=client)


def test_probe_fails_loud_on_non_200_status(_expected_slugs):
    served_by_base = {_base_for_role(role): _expected_slugs[role] for role in SELF_HOST_ROLES}
    client = _make_client(_models_handler(served_by_base, status_code=503))

    with pytest.raises(ServingIdentityError, match="HTTP 503"):
        probe_serving_identity(http_client=client)


def test_probe_fails_loud_on_malformed_models_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"object": "list", "data": []})

    client = _make_client(handler)
    with pytest.raises(ServingIdentityError, match="no model list"):
        probe_serving_identity(http_client=client)


# ======================================================================================
# Probe FAIL LOUD — unset base_url env
# ======================================================================================
def test_probe_fails_loud_when_role_base_url_env_unset(monkeypatch, _expected_slugs):
    monkeypatch.delenv("PG_MIRROR_BASE_URL", raising=False)
    served_by_base = {_base_for_role(role): _expected_slugs[role] for role in SELF_HOST_ROLES}
    client = _make_client(_models_handler(served_by_base))

    with pytest.raises(ServingIdentityError, match="PG_MIRROR_BASE_URL is not set"):
        probe_serving_identity(http_client=client)
