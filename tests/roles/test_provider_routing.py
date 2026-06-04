"""I-run11-007 (#1051): OpenRouter provider-routing + empty-response failover tests.

SPEND-FREE: the empty-retry test injects an `httpx.MockTransport`, so no socket / no LLM / no spend.
Routing is exercised against a DETERMINISTIC fixture config (not the live-data file), and the
autouse disable from `conftest.py` is overridden per-test by re-enabling + pointing at the fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.polaris_graph.roles import provider_routing
from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport
from src.polaris_graph.roles.provider_routing import (
    apply_provider_routing,
    role_provider_routing,
)
from src.polaris_graph.roles.role_transport import RoleRequest

_FIXTURE = str(Path(__file__).parent.parent / "fixtures" / "openrouter_provider_routing_fixture.yaml")
_MIRROR_SLUG = "z-ai/glm-5.1"


@pytest.fixture
def _routing_on(monkeypatch):
    """Re-enable routing (the dir conftest disables it) against the deterministic fixture config."""
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "1")
    monkeypatch.setenv("PG_PROVIDER_ROUTING_CONFIG", _FIXTURE)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.delenv("PG_MIRROR_MODEL", raising=False)
    provider_routing.reset_cache()
    yield
    provider_routing.reset_cache()


def test_loader_reads_fixture(_routing_on):
    assert role_provider_routing("mirror") == {
        "order": ["friendli", "fireworks", "deepinfra"],
        "ignore": ["phala", "together"],
    }
    assert role_provider_routing("sentinel") == {"order": ["novita", "minimax"], "ignore": []}


def test_disabled_returns_none(monkeypatch):
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "0")
    monkeypatch.setenv("PG_PROVIDER_ROUTING_CONFIG", _FIXTURE)
    provider_routing.reset_cache()
    assert role_provider_routing("mirror") is None


def test_apply_builds_block_reasoning_role(_routing_on):
    block = apply_provider_routing({"require_parameters": True}, "mirror")
    assert block["order"] == ["friendli", "fireworks", "deepinfra"]
    assert block["ignore"] == ["phala", "together"]
    assert block["allow_fallbacks"] is False
    # require_parameters preserved
    assert block["require_parameters"] is True


def test_apply_noop_when_unconfigured_role(_routing_on):
    # a role absent from the config leaves the block untouched (no order/allow_fallbacks injected)
    block = apply_provider_routing({"require_parameters": True}, "nonexistent_role")
    assert block == {"require_parameters": True}


# --------------------------------------------------------------------------------------
# The crux of #1051: OpenRouter does NOT fall back on an empty 200, so the transport must
# exclude the blanked provider and retry on the NEXT healthy provider itself.
# --------------------------------------------------------------------------------------
def _sequence_handler(responses):
    state = {"bodies": [], "i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        state["bodies"].append(json.loads(request.content.decode("utf-8")))
        payload = responses[min(state["i"], len(responses) - 1)]
        state["i"] += 1
        return httpx.Response(200, json=payload)

    return handler, state


def _completion(provider: str, content: str):
    return {
        "model": _MIRROR_SLUG,
        "provider": provider,
        "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 3},
    }


def test_empty_response_excludes_provider_and_retries(_routing_on):
    # 1st provider returns an empty 200 (the blank); the served `provider` is the DISPLAY name
    # "Friendli" — the retry must exclude the routing SLUG "friendli" (Codex iter-1 P1), not the
    # display form, so OpenRouter actually advances to the next healthy provider.
    handler, state = _sequence_handler([
        _completion("Friendli", ""),                      # blank (DISPLAY name) -> exclude slug + retry
        _completion("Fireworks", "<co>x</co:d1>"),        # healthy fallback
    ])
    transport = OpenRouterRoleTransport(httpx.Client(transport=httpx.MockTransport(handler)))
    req = RoleRequest(role="mirror", model_slug=_MIRROR_SLUG, prompt="decide", params={})

    resp = transport.complete(req)

    # it recovered on the 2nd provider, not a blank crash
    assert resp.raw_text == "<co>x</co:d1>"
    assert len(state["bodies"]) == 2
    # 1st attempt: routed to the ranked order, friendli NOT yet ignored
    assert "friendli" not in (state["bodies"][0]["provider"].get("ignore") or [])
    # 2nd attempt: the blanked provider's SLUG (friendli, mapped from display "Friendli") is ignored
    assert "friendli" in state["bodies"][1]["provider"]["ignore"]
    # the pre-configured ignores survive the retry too
    assert "phala" in state["bodies"][1]["provider"]["ignore"]


def test_served_display_name_maps_to_slug(_routing_on):
    # the camelCase / spaced display names a naive lower/space-fold would mis-map
    from src.polaris_graph.roles.provider_routing import slug_for_provider

    assert slug_for_provider("AtlasCloud") == "atlas-cloud"   # alias map (naive fold -> 'atlascloud')
    assert slug_for_provider("Io Net") == "io-net"
    assert slug_for_provider("Friendli") == "friendli"
    # not in the map -> best-effort fold
    assert slug_for_provider("SomeNewProvider") == "somenewprovider"
    assert slug_for_provider(None) is None
