"""I-arch-004 F20 (#1255): the reasoning-capable seams (`reason()` / `generate_structured()`)
must size their per-call timeout off the GENERATOR budget for a reasoning-first model — instead
of the small per-method default (LONG=180s for reason, DEFAULT=90s for structured) that used to
SHADOW the generous generator timeout and kill the call mid-reasoning.

The pre-F20 bug: `reason()` resolved `timeout or LONG_TIMEOUT_SECONDS` and
`generate_structured()` resolved `timeout or DEFAULT_TIMEOUT_SECONDS`. On a reasoning-first model
(DeepSeek V4 Pro / GLM-5.1 / MiniMax-M2) one call can take MINUTES — the small clock truncated the
reasoning -> empty/partial content. `generate()` already passed None through so `_call_impl`
resolved `GENERATOR_TIMEOUT_SECONDS`; these tests prove `reason()` and `generate_structured()` now
get the SAME generous derivation via `_resolve_call_timeout`, WITHOUT regressing the non-reasoning
floor (verifier/judge/side-judge calls on non-reasoning-first models keep their original floor).

These tests capture the `timeout` actually handed to `_read_stream` (the wire layer) — a true
behavioral assertion of the derivation, no network.
"""

import asyncio

import pytest

from src.polaris_graph.llm.openrouter_client import (
    DEFAULT_TIMEOUT_SECONDS,
    GENERATOR_TIMEOUT_SECONDS,
    LONG_TIMEOUT_SECONDS,
    OpenRouterClient,
    _resolve_call_timeout,
    get_generator_timeout_seconds,
    set_generator_timeout_seconds,
)

_REASONING_FIRST = "deepseek/deepseek-v4-pro"
_NON_REASONING = "meta-llama/llama-3.1-8b-instruct"

from pydantic import BaseModel


class _TinySchema(BaseModel):
    answer: str


def _capture_stream_timeout(coro_factory):
    """Run an OpenRouterClient coroutine with `_read_stream` stubbed to record its timeout.

    `coro_factory(client)` returns the awaitable to drive. The stub returns a valid non-empty
    4-tuple (content, reasoning, usage, served_dict) so the call completes without the
    empty-content retry leg. `served` MUST be a dict — `_call_impl` does `(served or {}).get(...)`.
    """
    captured = {}

    async def _fake_read_stream(body, timeout):
        captured["timeout"] = timeout
        return ('{"answer": "ok"}', "", {"total_tokens": 8}, {"provider": "stub"})

    async def _drive():
        client = OpenRouterClient(api_key="test-key", model=_capture_stream_timeout.model)
        client._read_stream = _fake_read_stream  # type: ignore[assignment]
        await coro_factory(client)

    asyncio.run(_drive())
    return captured["timeout"]


# ───────────────────────── _resolve_call_timeout (the helper) ─────────────────────────

def test_helper_reasoning_first_uses_live_generator_timeout():
    """Reasoning-first model + no explicit timeout -> the LIVE generator budget."""
    resolved = _resolve_call_timeout(_REASONING_FIRST, None, LONG_TIMEOUT_SECONDS)
    assert resolved == get_generator_timeout_seconds()
    assert resolved == GENERATOR_TIMEOUT_SECONDS


def test_helper_non_reasoning_keeps_floor_no_regression():
    """Non-reasoning model + no explicit -> the method's own floor (byte-identical pre-F20)."""
    assert _resolve_call_timeout(_NON_REASONING, None, LONG_TIMEOUT_SECONDS) == LONG_TIMEOUT_SECONDS
    assert (
        _resolve_call_timeout(_NON_REASONING, None, DEFAULT_TIMEOUT_SECONDS)
        == DEFAULT_TIMEOUT_SECONDS
    )


def test_helper_explicit_timeout_always_wins():
    """An explicit caller timeout overrides the model-derived default for either model."""
    assert _resolve_call_timeout(_REASONING_FIRST, 42.0, LONG_TIMEOUT_SECONDS) == 42.0
    assert _resolve_call_timeout(_NON_REASONING, 7.0, DEFAULT_TIMEOUT_SECONDS) == 7.0


def test_helper_honors_runtime_generator_timeout_override():
    """Reads the LIVE global so the Gate-B slate's set_generator_timeout_seconds() is honored,
    not a value frozen at import (the whole reason the setter exists)."""
    original = get_generator_timeout_seconds()
    try:
        set_generator_timeout_seconds(12345)
        assert _resolve_call_timeout(_REASONING_FIRST, None, LONG_TIMEOUT_SECONDS) == 12345
    finally:
        set_generator_timeout_seconds(original)


# ───────────────────────── reason() wire behavior ─────────────────────────

def test_reason_reasoning_first_gets_generator_timeout():
    _capture_stream_timeout.model = _REASONING_FIRST
    resolved = _capture_stream_timeout(lambda c: c.reason(prompt="q", system="s"))
    assert resolved == GENERATOR_TIMEOUT_SECONDS, (
        f"reason() on a reasoning-first model must get the generous "
        f"{GENERATOR_TIMEOUT_SECONDS}s budget; got {resolved} (the 180s shadow is back)"
    )
    assert resolved != LONG_TIMEOUT_SECONDS


def test_reason_non_reasoning_keeps_long_floor():
    _capture_stream_timeout.model = _NON_REASONING
    resolved = _capture_stream_timeout(lambda c: c.reason(prompt="q", system="s"))
    assert resolved == LONG_TIMEOUT_SECONDS, (
        f"reason() on a non-reasoning model must keep the LONG floor "
        f"({LONG_TIMEOUT_SECONDS}s); got {resolved} (a regression)"
    )


def test_reason_explicit_timeout_wins():
    _capture_stream_timeout.model = _REASONING_FIRST
    resolved = _capture_stream_timeout(lambda c: c.reason(prompt="q", timeout=33.0))
    assert resolved == 33.0


# ───────────────────────── generate_structured() wire behavior ─────────────────────────

def test_generate_structured_reasoning_first_gets_generator_timeout():
    _capture_stream_timeout.model = _REASONING_FIRST
    resolved = _capture_stream_timeout(
        lambda c: c.generate_structured(prompt="q", schema=_TinySchema)
    )
    assert resolved == GENERATOR_TIMEOUT_SECONDS, (
        f"generate_structured() on a reasoning-first model must get the generous "
        f"{GENERATOR_TIMEOUT_SECONDS}s budget; got {resolved} (the 90s shadow is back)"
    )
    assert resolved != DEFAULT_TIMEOUT_SECONDS


def test_generate_structured_non_reasoning_keeps_default_floor():
    _capture_stream_timeout.model = _NON_REASONING
    resolved = _capture_stream_timeout(
        lambda c: c.generate_structured(prompt="q", schema=_TinySchema)
    )
    assert resolved == DEFAULT_TIMEOUT_SECONDS, (
        f"generate_structured() on a non-reasoning model must keep the DEFAULT floor "
        f"({DEFAULT_TIMEOUT_SECONDS}s); got {resolved} (a regression)"
    )


def test_generate_structured_explicit_timeout_wins():
    _capture_stream_timeout.model = _REASONING_FIRST
    resolved = _capture_stream_timeout(
        lambda c: c.generate_structured(prompt="q", schema=_TinySchema, timeout=21.0)
    )
    assert resolved == 21.0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
