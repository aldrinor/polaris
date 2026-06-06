"""I-ready-017 FX-01 (#1105, faithfulness P0) — refuse to promote a TRUNCATED reasoning trace.

The drb_72 held run shipped the generator's token-starved chain-of-thought SCRATCHPAD into
report.md as VERIFIED prose: content was empty, the model spent its whole budget on reasoning, and
the planning monologue ENDED with a period ("...124 more words.") which defeated the I-bug-089
"ends mid-sentence" heuristic, so it was promoted to content and every faithfulness gate passed it.

FX-01 threads the provider's ``finish_reason`` from the SSE stream all the way into
``LLMResponse.finish_reason`` and refuses to promote reasoning->content when
``finish_reason == "length"`` (the canonical, floor-independent token-ceiling truncation signal).

WHY THESE TESTS DO NOT MOCK ``_call``
-------------------------------------
The previous version of this guard used a caller-param token ceiling
(``output_tokens >= max_tokens``). A LIVE §-1.1 micro-run proved that heuristic was CONFOUNDED:
``_call_impl`` floors ``max_tokens`` to ``PG_REASONING_FIRST_MIN_MAX_TOKENS`` (16384) for
reasoning-first models and V4 Pro reasons until the OVERALL ceiling, so a ``generate(max_tokens=80)``
returned 10302 chars of COMPLETE content — ``output_tokens`` hugely exceeded the param yet nothing
was truncated. A test that mocks ``_call`` and hand-sets ``output_tokens`` cannot catch that class of
bug. So each test below drives a FAKE OpenRouter SSE byte-stream through the REAL
``_read_stream`` -> ``_accumulate_sse`` -> ``_call`` -> ``_generate_impl`` promotion path. That
exercises the actual finish_reason threading, not a stand-in.
"""
from __future__ import annotations

import json

import httpx
import pytest

from src.polaris_graph.llm.openrouter_client import (
    OpenRouterClient,
    ReasoningFirstTruncationError,
    reset_run_cost,
)

# A period-terminated planning monologue — the exact shape that defeated the old terminal-
# punctuation heuristic. With FX-01 it is caught ONLY because finish_reason == "length".
_SCRATCHPAD = (
    "We can split it: 'Strong complementarities increase productivity.' But that might be too "
    "choppy. Final attempt: I'll use the exact phrase. That's three sentences from the thesis. "
    "Still 176. I need to add about 124 more words."
)


# ----------------------------------------------------------------------------------------------
# Fake OpenRouter SSE transport — overrides client._client.stream so the REAL streaming code path
# (content_type=text/event-stream -> _accumulate_sse) runs against scripted chunks.
# ----------------------------------------------------------------------------------------------
def _sse_lines(*, reasoning: str = "", content: str = "",
               finish_reason: str | None = "stop",
               completion_tokens: int = 500,
               reasoning_tokens: int | None = None) -> list[str]:
    """Build a minimal OpenRouter SSE line sequence: delta chunk(s) + a final chunk carrying
    finish_reason and usage, then the [DONE] terminator (matching real OpenRouter framing)."""
    lines: list[str] = []
    if reasoning:
        lines.append("data: " + json.dumps(
            {"choices": [{"delta": {"reasoning_content": reasoning}, "finish_reason": None}]}
        ))
    if content:
        lines.append("data: " + json.dumps(
            {"choices": [{"delta": {"content": content}, "finish_reason": None}]}
        ))
    usage: dict = {"prompt_tokens": 12, "completion_tokens": completion_tokens}
    if reasoning_tokens is not None:
        usage["completion_tokens_details"] = {"reasoning_tokens": reasoning_tokens}
    lines.append("data: " + json.dumps(
        {"choices": [{"delta": {}, "finish_reason": finish_reason}], "usage": usage}
    ))
    lines.append("data: [DONE]")
    return lines


class _FakeSSEResponse:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self.headers = {"content-type": "text/event-stream"}

    def raise_for_status(self) -> None:
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return b""


class _FakeStreamCM:
    def __init__(self, resp: _FakeSSEResponse) -> None:
        self._resp = resp

    async def __aenter__(self) -> _FakeSSEResponse:
        return self._resp

    async def __aexit__(self, *exc) -> bool:
        return False


def _install_fake_stream(client: OpenRouterClient, *responses: list[str]) -> None:
    """Replace client._client.stream with one that serves each SSE line-set in order across
    successive calls (the last is reused if calls outnumber responses) — supports the retry test."""
    queue = list(responses)

    def _stream(method, url, **kwargs):  # mirrors httpx.AsyncClient.stream signature
        lines = queue.pop(0) if len(queue) > 1 else queue[0]
        return _FakeStreamCM(_FakeSSEResponse(lines))

    client._client.stream = _stream  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_fx01_floored_low_param_success_not_false_positive() -> None:
    """THE CONFOUND the old param-ceiling false-positived on: the caller passes a tiny max_tokens,
    but the reasoning-first floor lets the model produce a large COMPLETE answer (finish_reason=
    'stop'). output_tokens >> the caller's param, yet nothing is truncated -> MUST promote, not raise."""
    reset_run_cost()
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    big_complete = ("Tirzepatide is a dual GIP/GLP-1 receptor agonist that lowers HbA1c. " * 30).strip()
    _install_fake_stream(client, _sse_lines(
        reasoning=big_complete, finish_reason="stop",
        completion_tokens=9000, reasoning_tokens=9000,
    ))
    result = await client.generate(prompt="x", max_tokens=80)
    assert result.content, "finish_reason='stop' must promote despite output_tokens >> param max_tokens"
    assert result.finish_reason == "stop", "FX-01 threading: finish_reason must reach LLMResponse"
    await client.close()


@pytest.mark.asyncio
async def test_fx01_length_truncation_period_terminated_refused() -> None:
    """The exact drb_72 failure: a token-starved planning monologue that ENDS WITH A PERIOD
    (defeating the terminal-punctuation heuristic) but finish_reason=='length'. MUST raise."""
    reset_run_cost()
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    _install_fake_stream(client, _sse_lines(
        reasoning=_SCRATCHPAD, finish_reason="length",
        completion_tokens=16384, reasoning_tokens=16384,
    ))
    with pytest.raises(ReasoningFirstTruncationError):
        await client.generate(prompt="x", max_tokens=16384)
    await client.close()


@pytest.mark.asyncio
async def test_fx01_retry_length_truncation_refused() -> None:
    """The NEW Codex P0: the COT-2 RETRY leg also promotes reasoning->content. First attempt
    returns sparse reasoning (<100 chars) -> routes to retry; the retry returns a >=100-char
    period-terminated monologue with finish_reason=='length'. The retry guard MUST raise."""
    reset_run_cost()
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    _install_fake_stream(
        client,
        _sse_lines(reasoning="short.", finish_reason="length",
                   completion_tokens=16384, reasoning_tokens=16384),
        _sse_lines(reasoning=_SCRATCHPAD, finish_reason="length",
                   completion_tokens=16384, reasoning_tokens=16384),
    )
    with pytest.raises(ReasoningFirstTruncationError):
        await client.generate(prompt="x", max_tokens=16384)
    await client.close()


@pytest.mark.asyncio
async def test_fx01_legit_reasoning_first_stop_still_promotes() -> None:
    """I-bug-088 unchanged: a complete reasoning-first answer (finish_reason=='stop', >100 chars)
    promotes to content."""
    reset_run_cost()
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    answer = (
        "In SURPASS-2 tirzepatide reduced HbA1c by about 2 percent versus the semaglutide 1mg "
        "comparator, with weight loss of 7 to 12 kilograms across doses. This is the complete answer."
    )
    _install_fake_stream(client, _sse_lines(
        reasoning=answer, finish_reason="stop", completion_tokens=400, reasoning_tokens=400,
    ))
    result = await client.generate(prompt="x", max_tokens=4096)
    assert result.content, "a complete finish_reason='stop' answer must still promote (I-bug-088)"
    await client.close()


@pytest.mark.asyncio
async def test_fx01_heuristic_fallback_when_no_finish_reason() -> None:
    """When the provider reports NO finish_reason (None), fall back to the I-bug-089 heuristic:
    [#ev:]-absent AND ends mid-sentence -> refuse to promote."""
    reset_run_cost()
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    midsentence = (
        "We can split the thesis into three sentences and then add about 124 more words to reach "
        "the target length, so the next step is going to be to"  # ends mid-sentence, no [#ev:]
    )
    _install_fake_stream(client, _sse_lines(
        reasoning=midsentence, finish_reason=None,
        completion_tokens=9000, reasoning_tokens=9000,
    ))
    with pytest.raises(ReasoningFirstTruncationError):
        await client.generate(prompt="x", max_tokens=9000)
    await client.close()
