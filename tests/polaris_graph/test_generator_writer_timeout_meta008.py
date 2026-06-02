"""I-meta-008 FULL-POWER: prove the reasoning-first WRITER timeout reaches the wire.

Regression guard for the Codex novel_p0 caught on the full-power fix: `generate()`
used to substitute `DEFAULT_TIMEOUT_SECONDS` before calling `_call`, so the
`GENERATOR_TIMEOUT_SECONDS` branch inside `_call_impl` was dead code on the live
writer path and DeepSeek V4 Pro sections were killed at 90s/600s.

These tests capture the `timeout` actually handed to `_read_stream` (the wire layer)
for `deepseek/deepseek-v4-pro` when the caller omits `timeout`, and assert it is the
generous generator budget — not the cheap shared default.
"""

import asyncio

from src.polaris_graph.llm.openrouter_client import (
    DEFAULT_TIMEOUT_SECONDS,
    GENERATOR_TIMEOUT_SECONDS,
    OpenRouterClient,
)

_REASONING_FIRST_WRITER = "deepseek/deepseek-v4-pro"
_NON_REASONING_MODEL = "meta-llama/llama-3.1-8b-instruct"


def _run_generate_capturing_stream_timeout(model: str, explicit_timeout=None):
    """Drive client.generate() with `_read_stream` stubbed to record its timeout.

    Returns the float timeout that `_call_impl` resolved and passed to the wire.
    The stub returns a valid non-empty 4-tuple so generate() completes without
    triggering the empty-content retry leg.
    """
    captured = {}

    async def _fake_read_stream(body, timeout):
        captured["timeout"] = timeout
        # (content, reasoning, usage, served_provider)
        return ("verified writer content", "", {"total_tokens": 8}, "deepseek")

    async def _drive():
        client = OpenRouterClient(api_key="test-key", model=model)
        client._read_stream = _fake_read_stream  # type: ignore[assignment]
        await client.generate(prompt="hello", system="sys", timeout=explicit_timeout)

    asyncio.run(_drive())
    return captured["timeout"]


def test_reasoning_first_writer_uses_generator_timeout_when_caller_omits_it():
    """V4 Pro + no explicit timeout → GENERATOR_TIMEOUT_SECONDS reaches the wire."""
    resolved = _run_generate_capturing_stream_timeout(_REASONING_FIRST_WRITER)
    assert resolved == GENERATOR_TIMEOUT_SECONDS, (
        f"reasoning-first writer must get the generous {GENERATOR_TIMEOUT_SECONDS}s "
        f"budget; got {resolved}. The generate()->_call->_call_impl pass-through is broken."
    )
    # And it must NOT be the cheap shared default that killed the run.
    assert resolved != DEFAULT_TIMEOUT_SECONDS


def test_non_reasoning_model_keeps_standard_default_no_regression():
    """A non-reasoning-first model with no explicit timeout still resolves the
    standard default — the pass-through change introduced no regression."""
    resolved = _run_generate_capturing_stream_timeout(_NON_REASONING_MODEL)
    assert resolved == DEFAULT_TIMEOUT_SECONDS, (
        f"non-reasoning model should keep {DEFAULT_TIMEOUT_SECONDS}s; got {resolved}"
    )


def test_explicit_caller_timeout_always_wins():
    """An explicit caller timeout overrides the model-derived default for either model."""
    resolved = _run_generate_capturing_stream_timeout(
        _REASONING_FIRST_WRITER, explicit_timeout=42.0
    )
    assert resolved == 42.0, f"explicit timeout must win; got {resolved}"
