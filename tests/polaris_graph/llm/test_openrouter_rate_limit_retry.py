"""Bounded, rate-limit-specific retry behavior for the OpenRouter client."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.polaris_graph.llm import openrouter_client


_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
_MODEL = openrouter_client.OPENROUTER_MODEL


def _response(status_code: int, *, retry_after: str | None = None) -> httpx.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    payload = (
        {
            "choices": [{"message": {"content": "answer"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": 0.0},
            "model": _MODEL,
        }
        if status_code == 200
        else {"error": {"message": "transport fault"}}
    )
    return httpx.Response(
        status_code,
        headers=headers,
        json=payload,
        request=_REQUEST,
    )


def _run(client: openrouter_client.OpenRouterClient):
    return asyncio.run(
        client._call_impl(
            messages=[{"role": "user", "content": "question"}],
            call_type="section",
            reasoning_enabled=False,
            response_format={"type": "json_object"},
        )
    )


def _client(monkeypatch, effects: list[httpx.Response | Exception]):
    client = openrouter_client.OpenRouterClient(api_key="test-key", model=_MODEL)
    calls = {"count": 0}

    async def post(*_args, **_kwargs):
        effect = effects[min(calls["count"], len(effects) - 1)]
        calls["count"] += 1
        if isinstance(effect, Exception):
            raise effect
        effect.raise_for_status()
        return effect

    monkeypatch.setattr(client._client, "post", post)
    return client, calls


def test_429_budget_exceeds_general_budget_and_honors_retry_after(monkeypatch):
    monkeypatch.setenv("PG_RATE_LIMIT_MAX_RETRIES", "4")
    monkeypatch.setenv("PG_RATE_LIMIT_RETRY_AFTER_CAP_S", "1.2")
    monkeypatch.setenv("PG_RATE_LIMIT_JITTER_S", "1.0")
    sleeps: list[float] = []
    jitter_bounds: list[tuple[float, float]] = []

    async def sleep(seconds: float):
        sleeps.append(seconds)

    def uniform(start: float, stop: float) -> float:
        jitter_bounds.append((start, stop))
        return stop

    monkeypatch.setattr(openrouter_client.asyncio, "sleep", sleep)
    monkeypatch.setattr(openrouter_client.random, "uniform", uniform)
    client, calls = _client(
        monkeypatch,
        [
            _response(429, retry_after="1"),
            _response(429, retry_after="1"),
            _response(429, retry_after="1"),
            _response(429, retry_after="1"),
            _response(200),
        ],
    )

    result = _run(client)

    assert result.content == "answer"
    assert calls["count"] == 5 > openrouter_client.MAX_RETRIES + 1
    assert sleeps == pytest.approx([1.2, 1.2, 1.2, 1.2])
    assert all(start == 0.0 and stop == pytest.approx(0.2) for start, stop in jitter_bounds)
    assert all(wait <= 1.2 for wait in sleeps)


def test_timeout_keeps_general_retry_budget_when_429_budget_is_larger(monkeypatch):
    monkeypatch.setenv("PG_RATE_LIMIT_MAX_RETRIES", "40")

    async def sleep(_seconds: float):
        return None

    monkeypatch.setattr(openrouter_client.asyncio, "sleep", sleep)
    client, calls = _client(
        monkeypatch,
        [httpx.ReadTimeout("read timed out", request=_REQUEST)],
    )

    with pytest.raises(httpx.ReadTimeout):
        _run(client)

    assert calls["count"] == openrouter_client.MAX_RETRIES + 1


def test_structural_404_still_fails_without_rate_limit_retries(monkeypatch):
    monkeypatch.setenv("PG_RATE_LIMIT_MAX_RETRIES", "40")
    response = httpx.Response(
        404,
        json={"error": {"message": "No endpoints found"}},
        request=_REQUEST,
    )
    client, calls = _client(monkeypatch, [response])

    with pytest.raises(openrouter_client.NoEndpointError):
        _run(client)

    assert calls["count"] == 1


def test_429_unset_uses_legacy_attempt_count(monkeypatch):
    monkeypatch.delenv("PG_RATE_LIMIT_MAX_RETRIES", raising=False)

    async def sleep(_seconds: float):
        return None

    monkeypatch.setattr(openrouter_client.asyncio, "sleep", sleep)
    monkeypatch.setattr(openrouter_client.random, "uniform", lambda _start, _stop: 0.0)
    client, calls = _client(monkeypatch, [_response(429, retry_after="1")])

    with pytest.raises(httpx.HTTPStatusError):
        _run(client)

    assert calls["count"] == openrouter_client.MAX_RETRIES + 1
