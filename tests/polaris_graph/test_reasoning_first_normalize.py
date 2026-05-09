"""
I-bug-088 — response-shape-centric normalization for reasoning-first models.

Pin the public-method invariant: if a generator call returns content="" with
reasoning_content populated (DeepSeek V4 Pro shape, future Llama 4 reasoning,
etc.) the public LLMResponse.content MUST be non-empty after recovery.

Codex APPROVE'd architectural option: hybrid Option 5 + Option 3 boundary.
Drop reliance on a hardcoded model-family registry as the recovery switch;
recover based on the response shape the provider returns.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.polaris_graph.llm.openrouter_client import (
    LLMResponse,
    OpenRouterClient,
    _ALWAYS_REASON_MODELS,
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


@pytest.mark.asyncio
async def test_v4_pro_reasoning_only_promoted_to_content() -> None:
    """V4 Pro shape: content empty, reasoning has the answer, no </think> tag.

    The pipeline-killing case from /tmp/beat_both_run_20260509_071159.log.
    Without I-bug-088 fix, this falls through to COT-2 retry which produces
    the same shape and then raises. With the fix, the reasoning is promoted
    directly to content.
    """
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")
    assert "deepseek/deepseek-v4-pro" not in _ALWAYS_REASON_MODELS, (
        "Test premise broken: V4 Pro should NOT be in the legacy registry — "
        "I-bug-088 must work without manual registry membership."
    )

    fake_reasoning = (
        "Tirzepatide is a dual GIP/GLP-1 receptor agonist approved for type 2 "
        "diabetes management. The SURPASS trials demonstrated significant "
        "HbA1c reductions of -1.87% to -2.07% across doses of 5mg, 10mg, and "
        "15mg weekly, with weight loss of 7-12kg observed across the trial "
        "program. Cardiovascular outcomes data from SURPASS-CVOT remains "
        "pending."
    )
    reasoning_only_response = _make_response(content="", reasoning=fake_reasoning)

    with patch.object(client, "_call", new=AsyncMock(return_value=reasoning_only_response)):
        result = await client.generate(prompt="Summarize tirzepatide evidence")

    assert result.content, "I-bug-088: V4 Pro reasoning-first call must produce non-empty content"
    assert result.content == fake_reasoning, (
        "Recovery should promote raw reasoning verbatim — preserve it for "
        "downstream provenance/strict_verify"
    )
    assert result.reasoning == fake_reasoning, "Raw reasoning must remain accessible"

    await client.close()


@pytest.mark.asyncio
async def test_content_present_wins_over_reasoning() -> None:
    """Regression: when both fields populated, content takes precedence.

    Models that emit BOTH chain-of-thought AND a clean answer (in content)
    must continue to use the content, not the reasoning.
    """
    client = OpenRouterClient(model="deepseek/deepseek-v3.2-exp")

    response_with_both = _make_response(
        content="Final answer: 42",
        reasoning="Let me think about this... I considered options A, B, C...",
    )

    with patch.object(client, "_call", new=AsyncMock(return_value=response_with_both)):
        result = await client.generate(prompt="What is the answer?")

    assert result.content == "Final answer: 42"
    assert "Let me think" in (result.reasoning or "")

    await client.close()


@pytest.mark.asyncio
async def test_think_tag_extraction_still_wins() -> None:
    """Regression: </think> extraction continues to fire when applicable.

    Models that emit `<think>cot</think>answer` into reasoning_content should
    still go through the </think> extractor, NOT the response-shape-centric
    fall-through. This preserves the cleanest path.
    """
    client = OpenRouterClient(model="some-think-tag-model")

    cot_with_tag = (
        "<think>The user is asking about diabetes drugs. Let me consider...</think>\n"
        "Tirzepatide reduced HbA1c by ~2% in SURPASS-2 vs semaglutide 1mg comparator."
    )
    response_with_tag = _make_response(content="", reasoning=cot_with_tag)

    with patch.object(client, "_call", new=AsyncMock(return_value=response_with_tag)):
        result = await client.generate(prompt="Summarize")

    assert result.content
    assert "<think>" not in result.content
    assert "</think>" not in result.content
    assert "Tirzepatide" in result.content

    await client.close()


@pytest.mark.asyncio
async def test_glm5_legacy_path_preserved() -> None:
    """Regression: GLM-5 family still goes through FIX-GLM5-COT regex stripping.

    I-bug-088 explicitly does NOT remove the legacy registry — that's a
    follow-on cleanup. Models in _ALWAYS_REASON_MODELS continue to use the
    regex-stripping path, which has the GLM-5-specific CoT preamble shape.
    """
    client = OpenRouterClient(model="z-ai/glm-5.1")
    assert "z-ai/glm-5.1" in _ALWAYS_REASON_MODELS

    glm5_reasoning = (
        "1. **Analyze the Request:** The user wants a summary of tirzepatide.\n"
        "2. **Draft the response:** Now let me write the actual report.\n\n"
        "Tirzepatide is a dual GIP/GLP-1 agonist with SURPASS-trial efficacy "
        "data showing -2% HbA1c reductions [CITE:surpass-2]."
    )
    glm_response = _make_response(content="", reasoning=glm5_reasoning)

    with patch.object(client, "_call", new=AsyncMock(return_value=glm_response)):
        result = await client.generate(prompt="Summarize")

    assert result.content, "GLM-5 path must produce non-empty content"
    assert result.reasoning == glm5_reasoning

    await client.close()


@pytest.mark.asyncio
async def test_sparse_reasoning_falls_to_retry_path() -> None:
    """Edge: reasoning under 100 chars is too sparse to be a real answer.

    Below threshold the call falls into the COT-2 retry path (which is the
    correct behavior — empty reasoning indicates a transient provider issue,
    not a reasoning-first model emitting its full answer there).
    """
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")

    sparse = _make_response(content="", reasoning="ok")
    full_after_retry = _make_response(content="The actual answer here.", reasoning="")

    call_mock = AsyncMock(side_effect=[sparse, full_after_retry])
    with patch.object(client, "_call", new=call_mock):
        result = await client.generate(prompt="What?")

    assert call_mock.await_count == 2, "Sparse reasoning must trigger retry"
    assert result.content == "The actual answer here."

    await client.close()


@pytest.mark.asyncio
async def test_both_fields_empty_raises() -> None:
    """Regression: when content AND reasoning are both empty after retry,
    SF-15 fail-loud behavior is preserved (no silent empty-output return).
    """
    client = OpenRouterClient(model="deepseek/deepseek-v4-pro")

    sparse_first = _make_response(content="", reasoning="hi")  # under 100 — triggers retry
    sparse_retry = _make_response(content="", reasoning="ok")  # retry also sparse

    call_mock = AsyncMock(side_effect=[sparse_first, sparse_retry])
    with patch.object(client, "_call", new=call_mock):
        with pytest.raises(RuntimeError, match="content empty after retry"):
            await client.generate(prompt="What?")

    await client.close()
