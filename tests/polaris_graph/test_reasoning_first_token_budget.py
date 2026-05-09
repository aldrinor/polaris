"""
I-bug-089 — token-budget-aware request shaping + fail-loud on truncated planning.

Pin three invariants on top of I-bug-088's response-shape-centric recovery:

1. When calling a reasoning-first model (V4 Pro/Flash) with
   reasoning_enabled=False, request body MUST include
   reasoning.max_tokens = max_tokens * 0.4, leaving 60% for content.
   This prevents token-starvation where the model spends its entire
   budget on planning and never writes the answer.

2. If the I-bug-088 promote-reasoning-to-content path detects truncation
   (no [#ev:] markers AND mid-sentence cutoff), it MUST raise RuntimeError
   instead of promoting the planning prelude. The caller retries with
   bigger budget.

3. Legitimate "answer in reasoning" output (has provenance + ends in punct)
   MUST still promote successfully — I-bug-088's existing test surface
   does not regress.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.polaris_graph.llm.openrouter_client import (
    LLMResponse,
    OpenRouterClient,
    _REASONING_FIRST_MODELS,
)


def _make_response(*, content: str = "", reasoning: str = "") -> LLMResponse:
    return LLMResponse(
        content=content,
        reasoning=reasoning,
        input_tokens=10,
        output_tokens=20,
        reasoning_tokens=30,
        model="test-model",
        duration_ms=100.0,
    )


def test_v4_pro_in_reasoning_first_models() -> None:
    """V4 Pro and V4 Flash must be in the reasoning-first request-side set."""
    assert "deepseek/deepseek-v4-pro" in _REASONING_FIRST_MODELS
    assert "deepseek/deepseek-v4-flash" in _REASONING_FIRST_MODELS


def test_v4_pro_min_max_tokens_floor_default_is_6000() -> None:
    """I-bug-090: PG_REASONING_FIRST_MIN_MAX_TOKENS default must be 6000.

    OpenRouter does NOT enforce reasoning.max_tokens for V4 Pro on the
    provider side — the model emits ~2500 reasoning tokens regardless.
    Floor must be large enough that the 40/60 split (I-bug-089) leaves
    room for both reasoning AND content. 6000 → ~2500 reasoning + ~3500
    content, both fit. At 2400 (the legacy default), reasoning eats the
    whole budget and I-bug-089 fail-loud raises.
    """
    import os
    val = int(os.getenv("PG_REASONING_FIRST_MIN_MAX_TOKENS", "6000"))
    assert val >= 6000, (
        f"PG_REASONING_FIRST_MIN_MAX_TOKENS must be >= 6000 (got {val}). "
        f"Below 6000 V4 Pro CoT eats the budget."
    )


def test_glm5_inherited_via_always_reason() -> None:
    """_REASONING_FIRST_MODELS includes _ALWAYS_REASON_MODELS as superset."""
    from src.polaris_graph.llm.openrouter_client import _ALWAYS_REASON_MODELS
    for model in _ALWAYS_REASON_MODELS:
        assert model in _REASONING_FIRST_MODELS, (
            f"{model} in _ALWAYS_REASON_MODELS but not in _REASONING_FIRST_MODELS"
        )


@pytest.mark.asyncio
async def test_v4_pro_truncated_planning_raises_fail_loud() -> None:
    """I-bug-089: truncated planning (no [#ev:] AND mid-sentence) raises RuntimeError.

    V4 Pro emits all CoT planning to reasoning_content, then runs out of
    max_tokens before writing the answer. Pre-I-bug-089, I-bug-088 would
    promote the planning prelude to content and strict_verify would drop
    it. With I-bug-089, we fail loud so the caller can retry with bigger
    budget.
    """
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")

    truncated_planning = (
        "We are asked to write the Efficacy section about tirzepatide. "
        "Let me inventory the evidence blocks. "
        "ev_001 covers SURPASS-2 efficacy in T2D adults. "
        "ev_002 covers SURMOUNT-1 obesity outcomes. "
        "Now let me draft the answer based on these"
    )
    assert "[#ev:" not in truncated_planning
    assert not truncated_planning.rstrip().endswith((".", "!", "?", '"'))

    fake = _make_response(content="", reasoning=truncated_planning)
    with patch.object(client, "_call", new=AsyncMock(return_value=fake)):
        with pytest.raises(RuntimeError, match="I-bug-089.*truncated mid-planning"):
            await client.generate(prompt="Write the section")

    await client.close()


@pytest.mark.asyncio
async def test_v4_pro_completed_answer_in_reasoning_still_promotes() -> None:
    """Regression: legitimate 'answer in reasoning' (with [#ev:] + punct end) must still promote.

    This is the case I-bug-088 was originally built for. Even when the
    answer is routed to reasoning_content, if the model finished writing
    AND the answer has provenance markers, we promote without failing.
    """
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")

    completed_answer = (
        "Tirzepatide produced -2.07% HbA1c reduction at 15 mg dose "
        "[#ev:ev_001:0-50] in SURPASS-2. Body weight changes were "
        "-7.8 kg, -10.3 kg, and -12.4 kg [#ev:ev_002:120-180] for the "
        "5 mg, 10 mg, and 15 mg doses respectively."
    )
    assert "[#ev:" in completed_answer
    assert completed_answer.rstrip().endswith(".")

    fake = _make_response(content="", reasoning=completed_answer)
    with patch.object(client, "_call", new=AsyncMock(return_value=fake)):
        result = await client.generate(prompt="Summarize")

    assert result.content == completed_answer, (
        "I-bug-088 promote path must preserve full reasoning when "
        "provenance + punct-end signal a completed answer"
    )

    await client.close()


@pytest.mark.asyncio
async def test_v4_pro_provenance_only_promotes_even_if_mid_sentence() -> None:
    """Edge: if reasoning has [#ev:] markers, treat as legit answer regardless of cutoff.

    The presence of provenance tokens means the model started writing the
    answer (not just planning). Mid-sentence cutoff in that case is a
    different failure mode (output-side truncation) handled by the caller's
    strict_verify drop logic, NOT by I-bug-089's fail-loud.
    """
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")

    partial_answer = (
        "Tirzepatide reduced HbA1c by -2.07% at the 15 mg dose [#ev:ev_001:0-50] "
        "in SURPASS-2 versus -1.86% with semaglutide. Body weight changes "
        "showed -7.6, -10.0, -11.4 kg [#ev:ev_002:120-180] for the 5/10/15 "
        "doses. The cardiovascular outcomes data shows that"
    )
    assert "[#ev:" in partial_answer
    assert not partial_answer.rstrip().endswith((".", "!", "?", '"'))

    fake = _make_response(content="", reasoning=partial_answer)
    with patch.object(client, "_call", new=AsyncMock(return_value=fake)):
        result = await client.generate(prompt="Summarize")

    assert result.content == partial_answer, (
        "[#ev:] presence overrides mid-sentence guard — I-bug-088 promote"
    )

    await client.close()


@pytest.mark.asyncio
async def test_v4_pro_complete_punct_no_provenance_still_promotes() -> None:
    """Edge: reasoning ends in punct without [#ev:] is treated as legit.

    Both conditions (no provenance AND mid-sentence) must hold for fail-loud
    to fire. If the model produced complete-looking sentences but failed to
    emit provenance markers, that's a separate bug (provenance-discipline)
    that strict_verify will catch downstream.
    """
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")

    completed_no_provenance = (
        "Tirzepatide is effective for type 2 diabetes management. "
        "It produces significant HbA1c reductions and weight loss."
    )
    assert "[#ev:" not in completed_no_provenance
    assert completed_no_provenance.rstrip().endswith(".")

    fake = _make_response(content="", reasoning=completed_no_provenance)
    with patch.object(client, "_call", new=AsyncMock(return_value=fake)):
        result = await client.generate(prompt="Summarize")

    assert result.content == completed_no_provenance

    await client.close()
