"""I-arch-005 B14 (#1257) — side-judge empty-content guard. Offline, deterministic, no network.

Proves: (a) is_empty_content predicate; (b) a non-empty first response returns value + captures
raw IO; (c) an empty response is RETRIED; (d) persistent empty returns a JudgeUnavailable sentinel
WITHOUT raising; (e) a propagate-class exception (BudgetExceededError) re-raises unchanged; (f) a
non-propagate exception is treated as an empty attempt (never raised); (g) the env retry budget is
honored; (h) the raw-IO trace captures EVERY attempt.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.llm.openrouter_client import BudgetExceededError
from src.polaris_graph.llm.side_judge_guard import (
    JudgeUnavailable,
    SideJudgeOutcome,
    call_side_judge_with_guard,
    is_empty_content,
    side_judge_empty_retries,
)


def _resp(content):
    return {"choices": [{"message": {"content": content}}]}


_EXTRACT = lambda r: r["choices"][0]["message"]["content"]


# ── is_empty_content ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("content", [None, "", "   ", "\n\t ", 123, {"a": 1}, []])
def test_is_empty_content_true(content):
    assert is_empty_content(content) is True


@pytest.mark.parametrize("content", ['{"verdict":"NEUTRAL"}', "x", " a "])
def test_is_empty_content_false(content):
    assert is_empty_content(content) is False


# ── env retry budget (LAW VI) ──────────────────────────────────────────────────

def test_retries_env_default(monkeypatch):
    monkeypatch.delenv("PG_SIDE_JUDGE_EMPTY_RETRIES", raising=False)
    assert side_judge_empty_retries() == 2


def test_retries_env_override(monkeypatch):
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "5")
    assert side_judge_empty_retries() == 5


def test_retries_env_invalid_falls_back(monkeypatch):
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "notanint")
    assert side_judge_empty_retries() == 2
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "-3")
    assert side_judge_empty_retries() == 2


# ── happy path: non-empty first attempt ─────────────────────────────────────────

def test_non_empty_first_attempt_returns_value_and_captures_io():
    captured = []

    class _Sink:
        def record(self, **kw):
            captured.append(kw)

    out = call_side_judge_with_guard(
        lambda: _resp('{"verdict":"CONTRADICT","confidence":0.9}'),
        extract_content=_EXTRACT,
        call_type="test_judge",
        role="evaluator",
        build_request=lambda: {"model": "m"},
        io_sink=_Sink(),
        retries=2,
    )
    assert isinstance(out, SideJudgeOutcome)
    assert out.is_unavailable is False
    assert out.value == _resp('{"verdict":"CONTRADICT","confidence":0.9}')
    # exactly ONE attempt captured (no retry needed), tagged ok, with the request body
    assert len(out.trace) == 1
    assert out.trace[0].empty is False
    assert len(captured) == 1
    assert captured[0]["status"] == "ok"
    assert captured[0]["request"] == {"model": "m"}
    assert captured[0]["call_type"] == "test_judge"


# ── retry on empty content, success on a later attempt ──────────────────────────

def test_empty_then_nonempty_retries_and_succeeds():
    seq = [_resp(None), _resp(""), _resp('{"verdict":"NEUTRAL","confidence":0.5}')]
    calls = {"n": 0}

    def _call():
        i = calls["n"]
        calls["n"] += 1
        return seq[i]

    out = call_side_judge_with_guard(
        _call, extract_content=_EXTRACT, call_type="t", retries=2,
    )
    assert out.is_unavailable is False
    assert out.value == _resp('{"verdict":"NEUTRAL","confidence":0.5}')
    assert calls["n"] == 3                      # two empty + one good = three real calls
    assert len(out.trace) == 3
    assert [a.empty for a in out.trace] == [True, True, False]


# ── persistent empty → JudgeUnavailable, NEVER raises ───────────────────────────

def test_persistent_empty_returns_sentinel_never_raises():
    out = call_side_judge_with_guard(
        lambda: _resp(None), extract_content=_EXTRACT, call_type="t", retries=2,
    )
    assert out.is_unavailable is True
    assert isinstance(out.unavailable, JudgeUnavailable)
    assert out.unavailable.attempts == 3        # 1 + 2 retries
    assert out.value is None
    # the trace captured every empty attempt (the forensic confirmation of the upstream cause)
    assert len(out.trace) == 3
    assert all(a.empty for a in out.trace)


def test_whitespace_only_content_is_empty_and_retried_then_unavailable():
    out = call_side_judge_with_guard(
        lambda: _resp("   \n  "), extract_content=_EXTRACT, call_type="t", retries=1,
    )
    assert out.is_unavailable is True
    assert out.unavailable.attempts == 2


# ── propagate class re-raises; other exceptions are empty attempts ──────────────

def test_budget_error_propagates_unchanged():
    def _call():
        raise BudgetExceededError("cap breached")

    with pytest.raises(BudgetExceededError):
        call_side_judge_with_guard(
            _call, extract_content=_EXTRACT, call_type="t",
            propagate=(BudgetExceededError,), retries=2,
        )


def test_non_propagate_exception_is_an_empty_attempt_never_raised():
    def _call():
        raise RuntimeError("transport boom")

    out = call_side_judge_with_guard(
        _call, extract_content=_EXTRACT, call_type="t",
        propagate=(BudgetExceededError,), retries=1,
    )
    assert out.is_unavailable is True
    assert out.unavailable.attempts == 2
    # the raised exception was captured into the trace as an error response, not re-raised
    assert all(a.empty for a in out.trace)
    assert out.trace[0].raw_response == {"error": "transport boom"}


def test_malformed_shape_counts_as_empty():
    # extract_content raises (wrong shape) -> treated as empty, retried, then unavailable
    out = call_side_judge_with_guard(
        lambda: {"unexpected": "shape"}, extract_content=_EXTRACT, call_type="t", retries=0,
    )
    assert out.is_unavailable is True
    assert out.unavailable.attempts == 1        # retries=0 => one attempt only


# ── zero retries: one attempt only ──────────────────────────────────────────────

def test_zero_retries_single_attempt():
    out = call_side_judge_with_guard(
        lambda: _resp('{"ok":1}'), extract_content=_EXTRACT, call_type="t", retries=0,
    )
    assert out.is_unavailable is False
    assert len(out.trace) == 1
