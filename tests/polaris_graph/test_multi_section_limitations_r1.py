"""
R-1 regression tests: multi-section generator now emits a Limitations paragraph.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    MultiSectionResult,
    _call_limitations,
)


@pytest.mark.asyncio
async def test_r1_call_limitations_produces_paragraph() -> None:
    """Stub the OpenRouterClient so no network call happens; assert the
    fallback prepend logic works."""
    class _FakeResponse:
        content = "Only 9% of the corpus is T1 primary. Sources disagree on weight-loss magnitude. Evidence horizon begins 2010-01-01."
        input_tokens = 150
        output_tokens = 80

    class _FakeClient:
        def __init__(self, *_, **__):
            pass
        async def generate(self, **_):
            return _FakeResponse()
        async def close(self):
            pass

    with patch(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient",
        _FakeClient,
    ):
        text, in_tok, out_tok = await _call_limitations(
            tier_fractions={"T1": 0.09, "T2": 0.21, "T3": 0.15},
            contradictions=[{
                "subject": "semaglutide",
                "predicate": "weight loss",
                "relative_difference": 0.168,
            }],
            date_range={"start": "2010-01-01", "end": None},
            model="deepseek/deepseek-v3.2-exp",
            temperature=0.3,
            max_tokens=400,
        )
    assert text.startswith("Limitations:")
    assert "9% of the corpus" in text
    assert in_tok == 150
    assert out_tok == 80


@pytest.mark.asyncio
async def test_r1_empty_response_falls_back_deterministic() -> None:
    """If the model returns empty or too-short content, deterministic
    fallback assembles a Limitations paragraph from the telemetry."""
    class _FakeResponse:
        content = ""
        input_tokens = 50
        output_tokens = 0

    class _FakeClient:
        def __init__(self, *_, **__):
            pass
        async def generate(self, **_):
            return _FakeResponse()
        async def close(self):
            pass

    with patch(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient",
        _FakeClient,
    ):
        text, in_tok, out_tok = await _call_limitations(
            tier_fractions={"T1": 0.09},
            contradictions=[{
                "subject": "semaglutide",
                "predicate": "weight loss",
            }],
            date_range={"start": "2010-01-01", "end": None},
            model="deepseek/deepseek-v3.2-exp",
            temperature=0.3,
            max_tokens=400,
        )
    assert text.startswith("Limitations:")
    # Deterministic assembly should mention specific fields:
    assert "9%" in text
    assert "semaglutide" in text
    assert "2010-01-01" in text


@pytest.mark.asyncio
async def test_r1_llm_exception_falls_back_deterministic() -> None:
    """If the LLM call raises, we still emit a Limitations paragraph."""
    class _FakeClient:
        def __init__(self, *_, **__):
            pass
        async def generate(self, **_):
            raise RuntimeError("network failure")
        async def close(self):
            pass

    with patch(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient",
        _FakeClient,
    ):
        text, _, _ = await _call_limitations(
            tier_fractions={"T1": 0.20},
            contradictions=[],
            date_range=None,
            model="deepseek/deepseek-v3.2-exp",
            temperature=0.3,
            max_tokens=400,
        )
    assert text.startswith("Limitations:")
    assert "20%" in text


def test_r1_multi_section_result_has_limitations_fields() -> None:
    """The dataclass carries the new limitations_text / token fields."""
    r = MultiSectionResult(
        sections=[], outline=[], bibliography=[],
        total_words=0, total_sentences_verified=0,
        total_sentences_dropped=0,
        total_input_tokens=0, total_output_tokens=0,
    )
    assert r.limitations_text == ""
    assert r.limitations_input_tokens == 0
    assert r.limitations_output_tokens == 0


@pytest.mark.asyncio
async def test_r1_llm_output_missing_prefix_gets_prepended() -> None:
    """If the model produces content that doesn't start with
    'Limitations:', the orchestrator prepends it automatically."""
    class _FakeResponse:
        content = (
            "The corpus is 9% T1 which constrains confidence. "
            "Sources disagree on weight-loss magnitude. "
            "Evidence horizon begins 2010."
        )
        input_tokens = 100
        output_tokens = 40

    class _FakeClient:
        def __init__(self, *_, **__):
            pass
        async def generate(self, **_):
            return _FakeResponse()
        async def close(self):
            pass

    with patch(
        "src.polaris_graph.llm.openrouter_client.OpenRouterClient",
        _FakeClient,
    ):
        text, _, _ = await _call_limitations(
            tier_fractions={"T1": 0.09},
            contradictions=[],
            date_range={"start": "2010-01-01", "end": None},
            model="deepseek/deepseek-v3.2-exp",
            temperature=0.3,
            max_tokens=400,
        )
    assert text.startswith("Limitations:")
    assert "The corpus is 9% T1" in text
