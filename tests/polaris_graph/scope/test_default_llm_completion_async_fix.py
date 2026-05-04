"""Regression test for the async/sync collision in clinical_classifier.

Bug: `_default_llm_completion` called `OpenRouterClient.generate()` (which
is async) without awaiting it. The returned coroutine was passed to
`_parse_llm_response`, which couldn't parse it, returning ('uncertain',
0.0). The outer try/except in `llm_fallback_classify` then masked the
RuntimeWarning. Net effect: every LLM-fallback classification silently
returned 'uncertain' under real keys, breaking the Sep 6 demo flow.

This test pins the contract: when the async client is mocked to return a
proper LLMResponse-shaped object, _default_llm_completion must invoke it
correctly and return the .content string.
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import MagicMock

import pytest

from polaris_graph.scope import clinical_classifier


class _FakeLLMResponse:
    def __init__(self, content: str):
        self.content = content


def _install_fake_openrouter(monkeypatch, response_text: str):
    """Inject a fake OpenRouterClient module so import succeeds + generate works."""

    async def fake_generate(self, **kwargs):
        return _FakeLLMResponse(response_text)

    fake_client_cls = type(
        "OpenRouterClient",
        (),
        {
            "__init__": lambda self, **kwargs: None,
            "generate": fake_generate,
        },
    )
    fake_module = types.ModuleType("polaris_graph.llm.openrouter_client")
    fake_module.OpenRouterClient = fake_client_cls
    monkeypatch.setitem(
        sys.modules, "polaris_graph.llm.openrouter_client", fake_module
    )


def test_default_llm_completion_awaits_async_generate(monkeypatch):
    """The async generate() must be awaited; the return must be its .content."""
    _install_fake_openrouter(
        monkeypatch,
        '{"value": "clinical_efficacy", "confidence": 0.9}',
    )
    result = clinical_classifier._default_llm_completion("test prompt")
    assert isinstance(result, str), (
        f"expected str, got {type(result).__name__} — async/sync collision regressed"
    )
    assert "coroutine" not in result.lower(), (
        f"expected real content, got coroutine repr: {result!r}"
    )
    assert "clinical_efficacy" in result


def test_default_llm_completion_inside_running_loop_raises(monkeypatch):
    """If called from within an async context, must raise rather than silently fail."""
    _install_fake_openrouter(monkeypatch, '{"value": "clinical_efficacy"}')

    async def call_inside_loop():
        return clinical_classifier._default_llm_completion("test prompt")

    with pytest.raises(RuntimeError, match="async context"):
        asyncio.run(call_inside_loop())


def test_llm_fallback_classify_returns_efficacy_when_llm_works(monkeypatch):
    """End-to-end: with a fake OpenRouter, llm_fallback_classify resolves clinical_efficacy."""
    _install_fake_openrouter(
        monkeypatch,
        '{"value": "clinical_efficacy", "confidence": 0.85}',
    )
    result = clinical_classifier.llm_fallback_classify(
        "Is high-dose aspirin effective for migraine in adults?"
    )
    assert result.value == "clinical_efficacy"
    assert result.confidence == pytest.approx(0.85)
    assert result.provenance == "llm_fallback"


def test_llm_fallback_returns_uncertain_when_client_construction_fails(
    monkeypatch,
):
    """Keyless / network error → graceful 'uncertain' (the documented degradation)."""

    fake_module = types.ModuleType("polaris_graph.llm.openrouter_client")

    class _BrokenClient:
        def __init__(self, **kwargs):
            raise RuntimeError("OPENROUTER_API_KEY missing")

    fake_module.OpenRouterClient = _BrokenClient
    monkeypatch.setitem(
        sys.modules, "polaris_graph.llm.openrouter_client", fake_module
    )

    result = clinical_classifier.llm_fallback_classify(
        "Some clinical-ish question"
    )
    assert result.value == "uncertain"
    assert result.confidence == 0.0
    assert result.provenance == "llm_fallback"


def test_default_llm_completion_passes_kwargs_to_generate(monkeypatch):
    """temperature=0.0 and max_tokens=200 must propagate to generate()."""
    captured: dict = {}

    async def capture_generate(self, **kwargs):
        captured.update(kwargs)
        return _FakeLLMResponse('{"value": "out_of_scope", "confidence": 0.7}')

    fake_cls = type(
        "OpenRouterClient",
        (),
        {
            "__init__": lambda self, **kwargs: None,
            "generate": capture_generate,
        },
    )
    fake_module = types.ModuleType("polaris_graph.llm.openrouter_client")
    fake_module.OpenRouterClient = fake_cls
    monkeypatch.setitem(
        sys.modules, "polaris_graph.llm.openrouter_client", fake_module
    )

    clinical_classifier._default_llm_completion("test")
    assert captured.get("temperature") == 0.0
    assert captured.get("max_tokens") == 200
    assert captured.get("prompt") == "test"
