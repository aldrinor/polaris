"""I-wire-005 B-B (#1319): the Phase-7 quantified-spec Writer must BOUND the reasoning pool so a
reasoning-first GLM-5.2 generator cannot burn its whole budget on reasoning and return empty
content (the residual spec_produced=False after B4 only raised max_tokens).

Root cause (post-B4): on the VM the generator is z-ai/glm-5.2, which is in
``openrouter_client._ALWAYS_REASON_MODELS``. That branch sets ``reasoning={"effort": "high"}`` when
the caller passes NO ``reasoning_max_tokens`` and places NO cap on the reasoning pool (unlike the
``_REASONING_FIRST_MODELS`` branch, which caps reasoning at 40% of max_tokens). So GLM-5.2 at
effort=high can consume the ENTIRE 32768-token budget reasoning, return empty content, and the
reasoning stream truncates before the JSON spec closes -> SpecProviderTransportError ->
spec_produced=False. Raising max_tokens alone (B4) cannot fix a model that spends 100% of its
budget reasoning. The fix passes a bounded ``reasoning_max_tokens`` so a fixed slice is reserved
for the closing-brace JSON.

This suite proves the MECHANISM with NO live calls (patches ``_read_stream``, the layer that
receives the fully-built request body) on the real ``_ALWAYS_REASON`` (GLM) path:

  (1) WITHOUT a reasoning cap, the GLM body carries ``reasoning.effort`` and NO
      ``reasoning.max_tokens`` — i.e. the uncapped pool that starves content (the bug).
  (2) WITH the bounded ``reasoning_max_tokens`` the fixed Writer now passes, the GLM body carries
      ``reasoning.max_tokens`` (content reserved) and the call returns the JSON spec in content.

Faithfulness-neutral: a ModelSpec is structured DATA validated downstream by build_quantified_spec
(exact datapoint_ref + pure-arithmetic formulas), never verified prose — so bounding reasoning here
adds ZERO faithfulness risk; it only guarantees the model reaches the content phase.

Honest scope (LAW II): these tests prove the request BODY carries ``reasoning.max_tokens=8192``
(content reserved) on the fix path and an UNCAPPED ``reasoning.effort`` on the bug path. They do
NOT prove GLM-5.2's serving provider HONORS ``reasoning.max_tokens`` (OpenRouter does not enforce it
provider-side for V4 Pro per openrouter_client L1837-1848). The in-code precedent that it DOES help
on this exact model: the abstractive writer uses the SAME model + SAME knob and lowering its
reasoning budget changed behavior (run_honest_sweep_r3.py L635-642, "default 8192 GLM burns it").
The reasoning-stream JSON recovery (L10612-10613) is the additional backstop. End-to-end proof is
the VM re-run showing spec_produced/fired=True.

SPEND-FREE / hermetic: env snapshotted/restored; no network.
"""
from __future__ import annotations

import json
import os

import pytest

from src.polaris_graph.llm.openrouter_client import (
    _ALWAYS_REASON_MODELS,
    OpenRouterClient,
)

_GLM = "z-ai/glm-5.2"


@pytest.fixture(autouse=True)
def _isolate_env():
    snap = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(snap)


def test_glm52_is_an_always_reason_model():
    """The fix targets exactly the reasoning-first generator the VM runs — confirm GLM-5.2 is the
    _ALWAYS_REASON model whose effort=high path has no reasoning cap."""
    assert _GLM in _ALWAYS_REASON_MODELS


def _capture_body_client(capture: dict):
    """A GLM client whose HTTP layer (``_read_stream``) is replaced by a capture stub returning a
    valid one-line JSON ModelSpec in content. Records the fully-built request body so the test can
    assert how the reasoning pool was shaped."""
    client = OpenRouterClient(model=_GLM)

    async def _fake_read_stream(body, timeout):  # noqa: ANN001 — test stub
        capture["body"] = body
        content = json.dumps({"model_id": "m1"})
        usage = {"finish_reason": "stop", "prompt_tokens": 5, "completion_tokens": 5}
        return content, "", usage, {}

    client._read_stream = _fake_read_stream  # type: ignore[assignment]
    return client


@pytest.mark.asyncio
async def test_glm_without_reasoning_cap_leaves_pool_uncapped_the_bug():
    """REPRO of the bug surface: a GLM generate() WITHOUT reasoning_max_tokens gets reasoning.effort
    and NO reasoning.max_tokens — the uncapped pool that can starve content to empty."""
    capture: dict = {}
    client = _capture_body_client(capture)
    await client.generate("x", max_tokens=32768, temperature=0.0)
    reasoning = capture["body"].get("reasoning", {})
    assert reasoning.get("effort") == "high"          # uncapped effort path
    assert "max_tokens" not in reasoning              # NO content reservation -> the bug


@pytest.mark.asyncio
async def test_glm_with_bounded_reasoning_reserves_content_the_fix():
    """THE FIX: passing the bounded reasoning_max_tokens the quantified-spec Writer now supplies makes
    the GLM body carry reasoning.max_tokens (content reserved), and the call returns the JSON spec in
    content (spec_produced would be True downstream)."""
    capture: dict = {}
    client = _capture_body_client(capture)
    resp = await client.generate(
        "x", max_tokens=32768, temperature=0.0, reasoning_max_tokens=8192,
    )
    reasoning = capture["body"].get("reasoning", {})
    assert reasoning.get("max_tokens") == 8192        # content is now reserved
    # overall budget still generous so content has ~24K headroom after the reasoning slice
    assert capture["body"]["max_tokens"] == 32768
    # and the JSON spec lands in content (not lost to a runaway reasoning prelude)
    assert json.loads(resp.content)["model_id"] == "m1"
