"""I-deepfix-001 B3 (#1370) — Codex+Fable gate-fix P1-1: generator provider FANOUT gate.

Request-body-level proof (hermetic, no socket) that the generator provider block built inside
``OpenRouterClient._call_impl`` is:

  * flag OFF (default) => PINNED: order = the ranked healthy chain, ignore = the deny-list,
    allow_fallbacks = False  ==> byte-identical to the pre-B3 pinned routing (the leak is gone), and
  * flag ON (PG_GENERATOR_PROVIDER_FANOUT=1) => UNPINNED: no ``order`` / no ``ignore``,
    allow_fallbacks = True  ==> OpenRouter fans the burst across glm-5.2's healthy endpoints.

The NON-STREAM seam is forced via ``response_format=json_object`` + ``reasoning_enabled=False`` so a
single mockable ``post`` coroutine captures the request body (mirrors test_f02_blank_completion_runaway).
"""

from __future__ import annotations

import asyncio
import copy

import httpx
import pytest

from src.polaris_graph.llm import openrouter_client
from src.polaris_graph.roles import provider_routing as pr

_GEN_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")

_EXPECT_ORDER = ["friendli", "novita", "z-ai", "phala"]
_EXPECT_IGNORE = [
    "deepinfra", "fireworks", "cloudflare", "atlas-cloud", "baidu",
    "gmicloud", "wandb", "siliconflow", "streamlake",
]


def _ok_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [{"message": {"content": "the answer"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
            "model": "z-ai/glm-5.2",
            "provider": "Friendli",
        },
        request=_GEN_REQUEST,
    )


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    # Deterministic generator routing: routing enabled (default), committed config, no env order,
    # no path-B singleton -> the else/elif generator-routing branch is exercised.
    monkeypatch.delenv("PG_OPENROUTER_PROVIDER_ROUTING", raising=False)
    monkeypatch.delenv("PG_PROVIDER_ROUTING_CONFIG", raising=False)
    monkeypatch.delenv("OPENROUTER_PROVIDER_ORDER", raising=False)
    monkeypatch.delenv("OPENROUTER_ALLOW_FALLBACKS", raising=False)  # default "true"
    pr.reset_cache()
    yield
    pr.reset_cache()


def _capture_provider_block(monkeypatch) -> dict:
    """Drive one non-stream _call_impl and return the deep-copied provider block sent to OpenRouter."""
    client = openrouter_client.OpenRouterClient(api_key="test-key-hermetic")
    captured: dict = {}

    async def _fake_post(*_args, **kwargs):
        captured["body"] = copy.deepcopy(kwargs.get("json"))
        return _ok_response()

    monkeypatch.setattr(client._client, "post", _fake_post)
    asyncio.run(
        client._call_impl(
            messages=[{"role": "user", "content": "q"}],
            call_type="contract_slot",
            reasoning_enabled=False,
            response_format={"type": "json_object"},
        )
    )
    return (captured["body"] or {}).get("provider", {}) or {}


def test_flag_off_generator_block_pinned_byte_identical(monkeypatch):
    monkeypatch.delenv(openrouter_client._ENV_GENERATOR_PROVIDER_FANOUT, raising=False)
    prov = _capture_provider_block(monkeypatch)
    assert prov.get("order") == _EXPECT_ORDER
    assert prov.get("ignore") == _EXPECT_IGNORE
    assert prov.get("allow_fallbacks") is False
    assert prov.get("require_parameters") is True


def test_flag_on_generator_block_unpinned_fanout(monkeypatch):
    monkeypatch.setenv(openrouter_client._ENV_GENERATOR_PROVIDER_FANOUT, "1")
    prov = _capture_provider_block(monkeypatch)
    assert "order" not in prov          # unpinned: OpenRouter load-balances
    assert "ignore" not in prov
    assert prov.get("allow_fallbacks") is True
    assert prov.get("require_parameters") is True


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
