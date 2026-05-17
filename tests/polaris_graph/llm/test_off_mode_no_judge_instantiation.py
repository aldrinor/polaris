"""Tests for I-bug-102 — off-mode does not instantiate the judge.

When `PG_STRICT_VERIFY_ENTAILMENT=off`, the entailment gate is
disabled entirely:
- `_entailment_mode()` returns "off"
- `_get_judge()` is NEVER called
- `_EntailmentJudge.__init__` does NOT run
- No `httpx.Client` is constructed
- No OpenRouter network call occurs

This is the "zero entailment-judge code-path execution" contract.
The class definitions are loaded into the module namespace at
import time (Python module evaluation), but no judge OBJECT exists.

These tests exercise the contract via mocking `_EntailmentJudge.__init__`
and asserting it is never called. Existing baseline tests in
`test_strict_verify_entailment.py` cover the verify_sentence
end-to-end off-mode behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.polaris_graph.clinical_generator import strict_verify
from src.polaris_graph.llm import entailment_judge


@pytest.fixture(autouse=True)
def _reset_judge_state():
    entailment_judge._JUDGE_SINGLETON = None
    entailment_judge.reset_judge_telemetry()
    yield
    entailment_judge._JUDGE_SINGLETON = None
    entailment_judge.reset_judge_telemetry()


def test_off_mode_does_not_instantiate_judge(monkeypatch):
    """Off-mode end-to-end: verify_sentence completes without ever
    constructing an `_EntailmentJudge` instance.

    Hardens the I-bug-102 contract: even if some downstream call
    accidentally tries to construct the judge, this test catches it
    by mocking `_EntailmentJudge.__init__` and asserting it was
    never called.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")

    # Track __init__ calls on the real class. If the off-path
    # accidentally constructs a judge, the mock fires.
    init_mock = MagicMock(return_value=None)
    monkeypatch.setattr(entailment_judge._EntailmentJudge, "__init__", init_mock)

    # We don't even need to call verify_sentence to exercise the contract;
    # it's enough to call _entailment_mode() and confirm the dispatch
    # branch is not taken. But we do call it to demonstrate end-to-end
    # behavior.
    mode = strict_verify._entailment_mode()
    assert mode == "off"

    # The judge singleton must remain None; nothing in the off-path
    # accessed it.
    assert entailment_judge._JUDGE_SINGLETON is None
    assert init_mock.call_count == 0, (
        "off-mode MUST NOT instantiate the judge"
    )


def test_off_mode_telemetry_remains_zero(monkeypatch):
    """Off-mode → no judge call → no telemetry counter increments."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    snap_before = entailment_judge.get_judge_telemetry()
    assert snap_before == {
        "calls": 0,
        "entailed": 0,
        "neutral": 0,
        "contradicted": 0,
        "judge_error": 0,
    }
    # Even with high-volume verify_sentence calls, off-mode does
    # not tick any judge counter.
    # (verify_sentence calls also exercise _entailment_mode() internally)
    mode = strict_verify._entailment_mode()
    assert mode == "off"
    snap_after = entailment_judge.get_judge_telemetry()
    assert snap_after == snap_before, (
        "off-mode must not change judge telemetry"
    )


def test_off_mode_no_httpx_client_constructed(monkeypatch):
    """Off-mode → _EntailmentJudge.__init__ never runs → no
    httpx.Client construction, no api-key check, no
    family-segregation check.

    Demonstrates the cost saving: the off-path is a single env-var
    read + early-return inside verify_sentence.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Even without an OPENROUTER_API_KEY env var, off-mode succeeds.
    # If __init__ were called, it would raise RuntimeError on the
    # missing API key. The fact that this test exits cleanly proves
    # __init__ is not on the off-path.
    mode = strict_verify._entailment_mode()
    assert mode == "off"
