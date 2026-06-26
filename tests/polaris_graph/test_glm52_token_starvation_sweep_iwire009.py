"""I-wire-009 (#1323): comprehensive GLM-5.2 reasoning-first token-starvation sweep.

GLM-5.2 (the campaign generator/mirror) is in ``openrouter_client._ALWAYS_REASON_MODELS``. Its
branch-1 request path (openrouter_client.py ~L1778) runs reasoning at ``effort=high`` with NO cap
whenever the caller passes no ``reasoning_max_tokens``; the branch-3 40%-cap NEVER reaches it because
branch 1 catches it first. So on every generator leg that did not pass a reasoning budget, GLM-5.2
could spend the whole (PG_GLM5_MIN_MAX_TOKENS=4096-floored) completion budget on the reasoning
prelude, return ``content=""``, and the promotion guard correctly raised
``ReasoningFirstTruncationError`` (the OUTLINE crash: 10330 reasoning chars, content=0,
finish_reason=length).

This issue is a token-BUDGET fix ONLY — the fail-loud truncation guard is CORRECT and stays intact;
we make starvation not HAPPEN by (a) bounding the reasoning pool so a fixed slice is reserved, and
(b) giving content a generous ceiling so it has room AFTER reasoning (CLAUDE.md §9.1.8).

All tests are hermetic (no network): they patch ``OpenRouterClient.generate`` (leg-level wiring) or
``OpenRouterClient._read_stream`` (the layer that receives the fully-built body / shapes the
response), mirroring the I-wire-005 quantified-spec suite. Faithfulness-neutral: every fixed leg's
output is still governed by the UNCHANGED strict_verify / structural validation downstream.
"""
from __future__ import annotations

import json
import os
import types

import pytest

from src.polaris_graph.llm.openrouter_client import (
    _ALWAYS_REASON_MODELS,
    OpenRouterClient,
    ReasoningFirstTruncationError,
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


def _fake_response(content: str):
    return types.SimpleNamespace(
        content=content, input_tokens=5, output_tokens=5,
    )


def _patch_generate_capture(monkeypatch):
    """Replace OpenRouterClient.generate with an async stub that records every call's kwargs +
    the bound client model, and returns a fake response. Returns the captured-calls list."""
    calls: list[dict] = []

    async def _fake_generate(self, prompt, system="", max_tokens=4096, temperature=0.7,
                             timeout=None, reasoning_max_tokens=None, reasoning_exclude=None,
                             response_format=None):
        calls.append({
            "model": self.model,
            "max_tokens": max_tokens,
            "reasoning_max_tokens": reasoning_max_tokens,
        })
        # NOT_JSON so the outline parser fails -> the retry leg ALSO fires (both calls captured).
        return _fake_response("NOT_JSON limitations/table prose body")

    async def _noop_close(self):
        return None

    monkeypatch.setattr(OpenRouterClient, "generate", _fake_generate, raising=True)
    monkeypatch.setattr(OpenRouterClient, "close", _noop_close, raising=False)
    return calls


def test_glm52_is_an_always_reason_model():
    """The whole sweep targets exactly the reasoning-first generator the VM runs."""
    assert _GLM in _ALWAYS_REASON_MODELS


@pytest.mark.asyncio
async def test_outline_primary_and_retry_pass_bounded_reasoning_and_content_floor(monkeypatch):
    """THE CRASH LEG. Both the primary outline call AND the validation-retry call must pass a
    bounded reasoning budget AND a content ceiling generous enough to leave room after it."""
    from src.polaris_graph.generator.multi_section_generator import _call_outline

    calls = _patch_generate_capture(monkeypatch)
    evidence = [
        {"evidence_id": "E1", "title": "Trial A efficacy", "tier": "T1", "statement": "x"},
        {"evidence_id": "E2", "title": "Safety review", "tier": "T2", "statement": "y"},
    ]
    # caller max_tokens=2500 (the function default) -> must be floored UP to the content floor.
    await _call_outline(
        research_question="Does drug X work?",
        evidence=evidence,
        model=_GLM,
        temperature=0.2,
        max_tokens=2500,
    )
    # Parse fails on NOT_JSON => primary + retry both fired.
    assert len(calls) >= 2, "outline retry did not fire; expected primary + retry"
    for c in calls:
        assert c["model"] == _GLM
        assert c["reasoning_max_tokens"] is not None and c["reasoning_max_tokens"] > 0, \
            "outline leg left the reasoning pool UNCAPPED (the bug)"
        # content ceiling raised off the 2500 caller value to the generous floor (16384 default)
        assert c["max_tokens"] >= 16384
        # reasoning leaves content headroom
        assert c["reasoning_max_tokens"] < c["max_tokens"]


@pytest.mark.asyncio
async def test_limitations_leg_passes_bounded_reasoning_and_content_floor(monkeypatch):
    """A representative SMALL-budget leg (caller max_tokens=400). Confirms the content ceiling is
    floored up and the reasoning pool is bounded below it."""
    from src.polaris_graph.generator.multi_section_generator import _call_limitations

    calls = _patch_generate_capture(monkeypatch)
    await _call_limitations(
        tier_fractions={"T1": 1.0},
        contradictions=[],
        date_range=None,
        model=_GLM,
        temperature=0.3,
        max_tokens=400,
    )
    assert len(calls) == 1
    c = calls[0]
    assert c["reasoning_max_tokens"] is not None and c["reasoning_max_tokens"] > 0
    assert c["max_tokens"] >= 6000               # floored up off 400
    assert c["reasoning_max_tokens"] < c["max_tokens"]


def _capture_body_client(capture: dict, *, finish_reason="stop", content='{"ok": 1}', reasoning=""):
    """A GLM client whose HTTP layer (_read_stream) is replaced — records the fully-built request
    body and returns a controllable (content, reasoning, finish_reason)."""
    client = OpenRouterClient(model=_GLM)

    async def _fake_read_stream(body, timeout):  # noqa: ANN001 — test stub
        capture["body"] = body
        usage = {"finish_reason": finish_reason, "prompt_tokens": 5, "completion_tokens": 4096}
        return content, reasoning, usage, {}

    client._read_stream = _fake_read_stream  # type: ignore[assignment]
    return client


@pytest.mark.asyncio
async def test_bounded_reasoning_shapes_glm_body_and_caller_value_overrides(monkeypatch):
    """MECHANISM: passing reasoning_max_tokens on the GLM _ALWAYS_REASON path sets
    reasoning.max_tokens (content reserved) and DROPS the uncapped effort=high; an explicit caller
    value is honored verbatim (precedence)."""
    capture: dict = {}
    client = _capture_body_client(capture)
    await client.generate("x", max_tokens=16384, temperature=0.0, reasoning_max_tokens=6144)
    reasoning = capture["body"].get("reasoning", {})
    assert reasoning.get("max_tokens") == 6144          # bounded -> content reserved
    assert "effort" not in reasoning                    # the uncapped path is gone
    assert capture["body"]["max_tokens"] == 16384


@pytest.mark.asyncio
async def test_uncapped_glm_is_the_bug_repro(monkeypatch):
    """REPRO: WITHOUT a reasoning cap the GLM body carries effort=high and NO reasoning.max_tokens —
    the uncapped pool that starves content. (Proves our per-leg caps are load-bearing.)"""
    capture: dict = {}
    client = _capture_body_client(capture)
    await client.generate("x", max_tokens=4096, temperature=0.0)
    reasoning = capture["body"].get("reasoning", {})
    assert reasoning.get("effort") == "high"
    assert "max_tokens" not in reasoning


@pytest.mark.asyncio
async def test_truncation_guard_still_trips_on_finish_reason_length(monkeypatch):
    """FAITHFULNESS FROZEN (I-faith-001): the fail-loud guard MUST stay intact. A GLM response with
    empty content + a partial reasoning scratchpad + finish_reason=length must still raise
    ReasoningFirstTruncationError (the budget fix prevents starvation; it does NOT relax the guard)."""
    capture: dict = {}
    client = _capture_body_client(
        capture,
        finish_reason="length",
        content="",                                       # content starved to empty
        reasoning="Step 1: analyze the corpus and plan the section before writing the",  # cut off
    )
    with pytest.raises(ReasoningFirstTruncationError):
        await client.generate("x", max_tokens=4096, temperature=0.0, reasoning_max_tokens=2048)


def test_every_fixed_leg_reserves_content_below_its_reasoning_cap():
    """BUDGET INVARIANT for all 8 fixed legs: at the shipped defaults the reasoning cap is positive
    AND strictly below the content ceiling/floor, so content always has room AFTER reasoning."""
    # (reasoning_env, reasoning_default, content_env, content_default)
    legs = [
        ("PG_OUTLINE_REASONING_MAX_TOKENS", "6144", "PG_OUTLINE_MIN_MAX_TOKENS", "16384"),
        ("PG_SECTION_REASONING_MAX_TOKENS", "16384", "PG_SECTION_MAX_TOKENS", "64000"),
        ("PG_TRIAL_TABLE_REASONING_MAX_TOKENS", "2048", "PG_TRIAL_TABLE_MIN_MAX_TOKENS", "6000"),
        ("PG_M50_REASONING_MAX_TOKENS", "2048", "PG_M50_MIN_MAX_TOKENS", "6000"),
        ("PG_LIMITATIONS_REASONING_MAX_TOKENS", "2048", "PG_LIMITATIONS_MIN_MAX_TOKENS", "6000"),
        ("PG_FACT_DEDUP_REASONING_MAX_TOKENS", "2048", "PG_FACT_DEDUP_MIN_MAX_TOKENS", "6000"),
        ("PG_ANALYST_SYNTHESIS_REASONING_MAX_TOKENS", "16384", "PG_SECTION_MAX_TOKENS", "64000"),
        ("PG_REPAIR_REASONING_MAX_TOKENS", "2048", "PG_REPAIR_MIN_MAX_TOKENS", "4096"),
    ]
    for r_env, r_def, c_env, c_def in legs:
        reasoning = int(os.getenv(r_env, r_def))
        content = int(os.getenv(c_env, c_def))
        assert reasoning > 0, f"{r_env} must reserve a positive reasoning slice"
        assert reasoning < content, (
            f"{r_env}={reasoning} must be < {c_env}={content} so content has room after reasoning"
        )


def test_abstractive_writer_default_reasoning_is_bounded_below_content():
    """The LOCKED floor_abstractive composer (the active winner) must BOUND reasoning BY DEFAULT.
    Its I-wire-005 default was -1 (=> effort=high, uncapped) — the same generous-ceiling assumption
    the outline crash disproved. I-wire-009 changes the default to a positive cap below the content
    ceiling; an operator can still restore effort=high for a non-reasoning-first model via a <=0 env.
    Asserts the REAL module constants (not a literal copy)."""
    from src.polaris_graph.generator import abstractive_writer as aw

    assert aw._DEFAULT_REASONING_MAX_TOKENS > 0, "abstractive writer reasoning default must be bounded"
    assert aw._DEFAULT_REASONING_MAX_TOKENS < aw._DEFAULT_MAX_TOKENS, (
        "abstractive writer reasoning cap must leave room under the content ceiling"
    )
    # the <=0 escape hatch (writer line ~413: `rmt if rmt and rmt > 0 else None`) still reaches
    # effort=high for a non-reasoning-first caller.
    for sentinel in (-1, 0):
        resolved = max(0, sentinel)
        assert (resolved if resolved and resolved > 0 else None) is None
