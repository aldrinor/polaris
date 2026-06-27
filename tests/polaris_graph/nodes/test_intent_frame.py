"""Offline $0 unit test for the W1 intent-frame wiring (I-wire-001).

Proves the three required behaviours WITHOUT any LLM, network, GPU, or paid
call — the GLM-5.2 policy is a pure-Python stub. Cost: $0.

  enabled + valid  -> typed frame + the exact firing canary, llm called once.
  enabled + empty  -> IntentFrameError (blank reply AND parses-to-zero-questions).
  disabled         -> no-op (None), llm NEVER called (byte-identical legacy, $0).
"""
from __future__ import annotations

import json
import logging

import pytest

from src.polaris_graph.nodes import intent_frame as ifr

_CANARY_TOKEN = "[intent_frame] #scope IntentFrame fired:"


def _counting_llm(reply: str):
    """A stub GLM-5.2 policy that returns ``reply`` and counts its calls."""
    state = {"calls": 0}

    def llm(prompt: str) -> str:
        state["calls"] += 1
        return reply

    return llm, state


def test_flag_default_off_and_on():
    """Default (unset) => OFF; recognised truthy values => ON."""
    import os

    os.environ.pop(ifr._ENV_FLAG, None)
    assert ifr.intent_frame_enabled() is False
    for truthy in ("1", "true", "TRUE", "yes", "on"):
        os.environ[ifr._ENV_FLAG] = truthy
        try:
            assert ifr.intent_frame_enabled() is True, truthy
        finally:
            os.environ.pop(ifr._ENV_FLAG, None)
    # an unrecognised value stays OFF (fail-safe legacy)
    os.environ[ifr._ENV_FLAG] = "maybe"
    try:
        assert ifr.intent_frame_enabled() is False
    finally:
        os.environ.pop(ifr._ENV_FLAG, None)


def test_enabled_valid_emits_frame_and_canary(monkeypatch, caplog):
    """enabled + valid JSON reply -> typed frame, single llm call, exact canary."""
    monkeypatch.setenv(ifr._ENV_FLAG, "1")
    reply = json.dumps(
        {
            "questions": [
                "What is the magnitude of weight reduction vs placebo?",
                "What is the common adverse-event profile?",
            ],
            "domain": "Clinical",
            "clarification_needed": ["Which population — adults only?"],
        }
    )
    llm, state = _counting_llm(reply)

    with caplog.at_level(logging.INFO, logger="src.polaris_graph.nodes.intent_frame"):
        frame = ifr.run_intent_frame("semaglutide efficacy and safety", llm)

    assert isinstance(frame, ifr.IntentFrame)
    assert frame.questions == [
        "What is the magnitude of weight reduction vs placebo?",
        "What is the common adverse-event profile?",
    ]
    assert frame.domain == "clinical"  # normalized lowercase
    assert frame.clarification_needed == ["Which population — adults only?"]
    # single GLM-5.2 call (proves "single-call" decomposition, no retry storm)
    assert state["calls"] == 1
    # the EXACT firing canary surfaced, with real runtime counts
    assert _CANARY_TOKEN in caplog.text
    assert "questions=2 domain=clinical clarify=1" in caplog.text


def test_enabled_tolerates_fences_and_key_aliases(monkeypatch):
    """A fenced reply using the gold-fixture aliases still parses (parser-only)."""
    monkeypatch.setenv(ifr._ENV_FLAG, "1")
    reply = (
        "Here is the frame:\n```json\n"
        + json.dumps(
            {
                "sub_questions": ["How has US CPI moved over 24 months?"],
                "domain": "economics",
                "ambiguities_to_clarify": [],
            }
        )
        + "\n```\n"
    )
    llm, state = _counting_llm(reply)
    frame = ifr.run_intent_frame("inflation drivers", llm)
    assert frame is not None
    assert frame.questions == ["How has US CPI moved over 24 months?"]
    assert frame.domain == "economics"
    assert frame.clarification_needed == []
    assert state["calls"] == 1


def test_enabled_empty_reply_raises(monkeypatch):
    """enabled + blank llm reply -> IntentFrameError (silent no-op aborts)."""
    monkeypatch.setenv(ifr._ENV_FLAG, "1")
    llm, state = _counting_llm("   ")
    with pytest.raises(ifr.IntentFrameError):
        ifr.run_intent_frame("some prompt", llm)
    assert state["calls"] == 1


def test_enabled_zero_questions_raises(monkeypatch):
    """enabled + valid JSON but ZERO questions -> IntentFrameError (fail-closed)."""
    monkeypatch.setenv(ifr._ENV_FLAG, "1")
    reply = json.dumps({"questions": [], "domain": "general", "clarification_needed": []})
    llm, state = _counting_llm(reply)
    with pytest.raises(ifr.IntentFrameError):
        ifr.run_intent_frame("some prompt", llm)
    assert state["calls"] == 1


def test_enabled_unparseable_json_raises(monkeypatch):
    """enabled + non-JSON reply -> IntentFrameError (no silent swallow)."""
    monkeypatch.setenv(ifr._ENV_FLAG, "1")
    llm, _ = _counting_llm("I cannot help with that.")
    with pytest.raises(ifr.IntentFrameError):
        ifr.run_intent_frame("some prompt", llm)


def test_disabled_is_noop_and_never_calls_llm(monkeypatch, caplog):
    """disabled (default) -> None, llm NEVER called, no canary (byte-identical, $0)."""
    monkeypatch.delenv(ifr._ENV_FLAG, raising=False)
    llm, state = _counting_llm(json.dumps({"questions": ["x"], "domain": "general"}))
    with caplog.at_level(logging.INFO, logger="src.polaris_graph.nodes.intent_frame"):
        result = ifr.run_intent_frame("some prompt", llm)
    assert result is None
    assert state["calls"] == 0  # no spend, no GLM call
    assert _CANARY_TOKEN not in caplog.text


if __name__ == "__main__":
    import sys

    sys.exit(pytest.main([__file__, "-q"]))
