"""I-ready-018 (#1100 keystone) — generate_structured must not 404 on reasoning-first models.

The drb_72 forensic run (outputs/audits/I-ready-017/) proved that
``generate_structured(reasoning_enabled=False)`` against the reasoning-first deepseek
default attached ``response_format={json_schema, strict:true}`` WHILE ``_call()`` forced a
reasoning block (deepseek is in ``_REASONING_FIRST_MODELS``). With provider
``require_parameters:true`` + the generator provider pin, OpenRouter served no endpoint and
returned ``404 "No endpoints found"`` — silently swallowed into template fallbacks, killing
STORM persona-gen and every agentic-searcher round-analysis (discovery 100% dead from LLM
call #1, while the SAME slug served 31 successful ``generate()`` calls in the same run).

The keystone fix aligns the ``generate_structured`` skip-response_format gate
(``openrouter_client.py`` ~2598) from the GLM-only ``_ALWAYS_REASON_MODELS`` to the
request-side ``_REASONING_FIRST_MODELS`` (which includes deepseek-v4-pro/-v4-flash), so those
models skip the strict schema and use the model-agnostic prompt-based-JSON / reasoning-extraction
recovery path. These tests pin that gate WITHOUT a network call.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from src.polaris_graph.llm.openrouter_client import (
    LLMResponse,
    OpenRouterClient,
    _ALWAYS_REASON_MODELS,
    _REASONING_FIRST_MODELS,
)


class _Tiny(BaseModel):
    ok: bool


def _json_response() -> LLMResponse:
    return LLMResponse(
        content='{"ok": true}',
        reasoning="",
        input_tokens=5,
        output_tokens=5,
        reasoning_tokens=0,
        model="test-model",
        duration_ms=10.0,
    )


def _capture_call():
    captured: dict = {}

    async def fake_call(*args, **kwargs):
        captured["response_format"] = kwargs.get("response_format")
        return _json_response()

    return captured, fake_call


@pytest.mark.asyncio
@pytest.mark.parametrize("model", ["deepseek/deepseek-v4-pro", "deepseek/deepseek-v4-flash"])
async def test_reasoning_first_model_skips_strict_response_format(model, monkeypatch) -> None:
    """The 404 trigger: a reasoning-first model must NOT receive strict json_schema."""
    monkeypatch.setenv("PG_STRICT_JSON_SCHEMA", "1")
    assert model in _REASONING_FIRST_MODELS, "test premise: model is reasoning-first"
    assert model not in _ALWAYS_REASON_MODELS, (
        "test premise: the deepseek default is reasoning-first but was NOT in the legacy GLM-only "
        "_ALWAYS_REASON_MODELS — exactly the gap that 404'd before I-ready-018"
    )

    client = OpenRouterClient(model=model)
    captured, fake_call = _capture_call()
    with patch.object(client, "_call", new=AsyncMock(side_effect=fake_call)):
        result = await client.generate_structured(prompt="x", schema=_Tiny, reasoning_enabled=False)

    assert result.ok is True
    assert captured["response_format"] is None, (
        "I-ready-018 keystone: a reasoning-first model must NOT receive strict json_schema "
        "response_format — sending it alongside the forced reasoning block 404s the discovery LLM"
    )
    await client.close()


@pytest.mark.asyncio
async def test_non_reasoning_first_model_still_gets_strict_schema(monkeypatch) -> None:
    """Narrowness guard: a model that is NOT reasoning-first must STILL get strict json_schema.

    The fix must not disable strict-schema enforcement for models that support it
    (the docstring cites Qwen 3.5 Plus as a strict-schema-capable model).
    """
    monkeypatch.setenv("PG_STRICT_JSON_SCHEMA", "1")
    model = "qwen/qwen3.5-plus"
    assert model not in _REASONING_FIRST_MODELS, "test premise: model is NOT reasoning-first"

    client = OpenRouterClient(model=model)
    captured, fake_call = _capture_call()
    with patch.object(client, "_call", new=AsyncMock(side_effect=fake_call)):
        await client.generate_structured(prompt="x", schema=_Tiny, reasoning_enabled=False)

    assert captured["response_format"] is not None, (
        "non-reasoning-first model must still get strict json_schema — the I-ready-018 fix is narrow"
    )
    assert captured["response_format"]["type"] == "json_schema"
    await client.close()


@pytest.mark.asyncio
async def test_explicit_reasoning_enabled_skips_schema_for_any_model(monkeypatch) -> None:
    """Regression: reasoning_enabled=True must skip strict schema for ANY model (unchanged)."""
    monkeypatch.setenv("PG_STRICT_JSON_SCHEMA", "1")
    client = OpenRouterClient(model="qwen/qwen3.5-plus")
    captured, fake_call = _capture_call()
    with patch.object(client, "_call", new=AsyncMock(side_effect=fake_call)):
        await client.generate_structured(prompt="x", schema=_Tiny, reasoning_enabled=True)

    assert captured["response_format"] is None, (
        "reasoning_enabled=True is incompatible with strict json_schema for any model"
    )
    await client.close()
