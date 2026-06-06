"""I-ready-019 (#1102) — a STRUCTURAL discovery 404 must FAIL LOUD, not silent template fallback.

The drb_72 collapse: a 100%-dead discovery LLM (404 'No endpoints found') was swallowed by
STORM persona-gen + the agentic searcher into template fallbacks, so the run completed GREEN on
dead discovery (LAW II silent-downgrade). The fix raises a typed `NoEndpointError` at the source
(openrouter_client) and the discovery callers re-raise it instead of falling back.

These tests pin the caller contract WITHOUT a network call: a `NoEndpointError` from
`generate_structured` PROPAGATES (run fails loud); a generic transient error STILL falls back.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.polaris_graph.llm.openrouter_client import NoEndpointError
from src.polaris_graph.agents.storm_interviews import _discover_perspectives


class _FakeClient:
    def __init__(self, exc: Exception) -> None:
        self.generate_structured = AsyncMock(side_effect=exc)


def test_no_endpoint_error_is_runtime_error() -> None:
    assert issubclass(NoEndpointError, RuntimeError)


@pytest.mark.asyncio
async def test_storm_persona_gen_reraises_structural_404() -> None:
    """A structural 404 must propagate — NOT be swallowed into template personas."""
    client = _FakeClient(NoEndpointError("OpenRouter 404 'No endpoints found' for deepseek/deepseek-v4-pro"))
    with pytest.raises(NoEndpointError):
        await _discover_perspectives(client, "q", "ctx", 3)


@pytest.mark.asyncio
async def test_storm_persona_gen_still_falls_back_on_generic_error() -> None:
    """A generic/transient error STILL falls back to template personas (unchanged behavior)."""
    client = _FakeClient(RuntimeError("transient provider blip"))
    out = await _discover_perspectives(client, "q", "ctx", 3)
    assert isinstance(out, list) and len(out) >= 1  # fallback personas, not a raise
