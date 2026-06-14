"""I-arch-003 (#1253) — reasoning-ON path must also floor reasoning-first max_tokens.

The forensic audit found that openrouter_client._call's budget logic is a 3-way `elif`
chain: branch 1 (GLM `_ALWAYS_REASON`) -> 4096 floor; branch 2 (`elif reasoning_enabled`)
-> historically NO floor; branch 3 (`elif self.model in _REASONING_FIRST_MODELS`) -> 32768
floor. So a reasoning-first model (deepseek-v4-pro) reached via `reason()` or
`generate_structured(reasoning_enabled=True)` took branch 2 and was NEVER floored — a small
caller max_tokens (evidence_deepener 2000/500, STORM outline 4096) was consumed entirely by
V4-Pro's ~17-18k reasoning tokens, returning empty content (silent capability loss).

The fix mirrors branch 3's floor+cap into branch 2 for `_REASONING_FIRST_MODELS`. These tests
pin that the reasoning-ON path now floors to 32768 for deepseek and leaves GLM (branch 1) and
non-reasoning-first models untouched — WITHOUT a network call (the request body is captured
at the `_read_stream` boundary).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.polaris_graph.llm.openrouter_client import (
    OpenRouterClient,
    _ALWAYS_REASON_MODELS,
    _REASONING_FIRST_MODELS,
)


def _fake_stream_return():
    # (content_text, reasoning_text, stream_usage, stream_served) — matches the streaming
    # unpack in _call (openrouter_client.py ~1817). Non-empty content ending in punctuation so
    # the I-bug-089 promotion guard does not fire.
    return (
        "done.",
        "",
        {"finish_reason": "stop", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "TestProvider",
    )


def _capture_body():
    captured: dict = {}

    async def fake_read_stream(body, timeout):  # noqa: ANN001
        captured["body"] = body
        return _fake_stream_return()

    return captured, fake_read_stream


@pytest.mark.asyncio
@pytest.mark.parametrize("max_tokens_in", [500, 2000, 4096])
async def test_reason_floors_reasoning_first_to_32768(max_tokens_in, monkeypatch) -> None:
    """reason() on deepseek-v4-pro (branch 2) must floor max_tokens to >= 32768."""
    monkeypatch.delenv("PG_REASONING_FIRST_MIN_MAX_TOKENS", raising=False)
    monkeypatch.delenv("PG_REASONING_FIRST_HARD_CAP", raising=False)
    model = "deepseek/deepseek-v4-pro"
    assert model in _REASONING_FIRST_MODELS and model not in _ALWAYS_REASON_MODELS

    client = OpenRouterClient(model=model)
    captured, fake_read_stream = _capture_body()
    with patch.object(client, "_read_stream", new=AsyncMock(side_effect=fake_read_stream)):
        await client.reason(prompt="x", effort="high", max_tokens=max_tokens_in)

    body = captured["body"]
    assert body.get("reasoning", {}).get("enabled") is True, "reason() must enable reasoning (branch 2)"
    assert body["max_tokens"] >= 32768, (
        f"I-arch-003: reasoning-ON path must floor reasoning-first max_tokens to 32768 "
        f"(got {body['max_tokens']} from caller {max_tokens_in}) — branch 2 was un-floored"
    )
    await client.close()


@pytest.mark.asyncio
async def test_reason_hard_caps_reasoning_first_at_384000(monkeypatch) -> None:
    """The branch-2 floor block must also cap at 384000 (mirrors branch 3)."""
    monkeypatch.delenv("PG_REASONING_FIRST_HARD_CAP", raising=False)
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    captured, fake_read_stream = _capture_body()
    with patch.object(client, "_read_stream", new=AsyncMock(side_effect=fake_read_stream)):
        await client.reason(prompt="x", effort="high", max_tokens=900000)

    assert captured["body"]["max_tokens"] == 384000, "branch-2 cap must clamp to 384000"
    await client.close()


@pytest.mark.asyncio
async def test_reason_does_not_floor_non_reasoning_first_model(monkeypatch) -> None:
    """Narrowness: a NON-reasoning-first model on branch 2 keeps its small budget (no 32768 floor)."""
    monkeypatch.delenv("PG_REASONING_FIRST_MIN_MAX_TOKENS", raising=False)
    model = "qwen/qwen3.5-plus"
    assert model not in _REASONING_FIRST_MODELS
    client = OpenRouterClient(model=model)
    captured, fake_read_stream = _capture_body()
    with patch.object(client, "_read_stream", new=AsyncMock(side_effect=fake_read_stream)):
        await client.reason(prompt="x", effort="high", max_tokens=500)

    assert captured["body"]["max_tokens"] == 500, (
        "the floor is narrow to _REASONING_FIRST_MODELS; a non-reasoning-first model must keep 500"
    )
    await client.close()
