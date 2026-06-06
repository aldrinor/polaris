"""I-ready-017 FX-01 (#1105, faithfulness P0) — refuse to promote a TRUNCATED reasoning trace.

The drb_72 held run shipped the generator's token-starved chain-of-thought SCRATCHPAD into
report.md as VERIFIED prose: content was empty, the model spent its whole budget on reasoning, and
the planning monologue ENDED with a period ("...124 more words.") which defeated the I-bug-089
"ends mid-sentence" heuristic, so it was promoted to content and every faithfulness gate passed it.

FX-01 adds a DETERMINISTIC truncation signal (equivalent to finish_reason=='length'): if the
response consumed (essentially) its entire output OR reasoning budget, the model never finished, so
the reasoning is NOT promoted regardless of terminal punctuation. A legitimate reasoning-first
response that finished BELOW the budget cap STILL promotes (I-bug-088 unchanged).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.polaris_graph.llm.openrouter_client import (
    LLMResponse,
    OpenRouterClient,
    ReasoningFirstTruncationError,
)


def _resp(*, content: str, reasoning: str, output_tokens: int) -> LLMResponse:
    return LLMResponse(
        content=content,
        reasoning=reasoning,
        input_tokens=10,
        output_tokens=output_tokens,
        reasoning_tokens=output_tokens,
        model="deepseek/deepseek-v4-pro",
        duration_ms=100.0,
    )


# A period-terminated planning monologue — the exact shape that defeated the old heuristic.
_SCRATCHPAD = (
    "We can split it: 'Strong complementarities increase productivity.' But that might be too "
    "choppy. Final attempt: I'll use the exact phrase. That's three sentences from the thesis. "
    "Still 176. I need to add about 124 more words."
)


@pytest.mark.asyncio
async def test_fx01_ceiling_truncated_scratchpad_not_promoted() -> None:
    """At the token ceiling (output_tokens >= max_tokens) + period-terminated -> MUST raise, not promote."""
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    truncated = _resp(content="", reasoning=_SCRATCHPAD, output_tokens=100)  # == max_tokens below
    with patch.object(client, "_call", new=AsyncMock(return_value=truncated)):
        with pytest.raises(ReasoningFirstTruncationError):
            await client.generate(prompt="x", max_tokens=100)
    await client.close()


@pytest.mark.asyncio
async def test_fx01_legit_reasoning_first_below_ceiling_still_promotes() -> None:
    """A complete reasoning-first answer that finished BELOW the budget cap STILL promotes (I-bug-088)."""
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    legit = _resp(
        content="",
        reasoning=(
            "Tirzepatide is a dual GIP/GLP-1 receptor agonist. In SURPASS-2 it reduced HbA1c by "
            "approximately 2 percent versus the semaglutide 1mg comparator, with weight loss of "
            "7 to 12 kilograms across doses. This is the complete, finished answer."
        ),  # >100 chars so it reaches the promotion branch; ends complete
        output_tokens=25,  # well below max_tokens -> NOT truncated
    )
    with patch.object(client, "_call", new=AsyncMock(return_value=legit)):
        result = await client.generate(prompt="x", max_tokens=4096)
    assert result.content, "a below-ceiling reasoning-first answer must still be promoted (I-bug-088)"
    await client.close()
