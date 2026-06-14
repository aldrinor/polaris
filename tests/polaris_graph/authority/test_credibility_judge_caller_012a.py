"""I-cred-012a — spend-tracked, gate-observed credibility caller. Offline (mocked transport), no network."""
from __future__ import annotations

import httpx
import pytest

from src.polaris_graph.authority.credibility_judge import make_credibility_judge
from src.polaris_graph.authority.credibility_judge_caller import (
    credibility_judge_model,
    make_openrouter_credibility_caller,
)
from src.polaris_graph.authority.credibility_skill import score_source_credibility
from src.polaris_graph.llm import openrouter_client as _orc


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")  # glm != deepseek => family ok
    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_MODEL", "z-ai/glm-5.1")
    _orc.reset_run_cost()  # isolate per-test run cost (the budget-breach test accumulates 999.0)


def _fake_client(captured, content, usage):
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": content}}], "usage": usage}

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            captured["url"] = url
            captured["model"] = json["model"]
            captured["body"] = json
            captured["prompt"] = json["messages"][0]["content"]
            return _Resp()

    return _Client


def test_default_model_is_open_weight():
    assert credibility_judge_model() == "z-ai/glm-5.1"


def test_strict_cost_delta_and_endpoint(monkeypatch):
    captured = {}
    monkeypatch.setattr(httpx, "Client", _fake_client(
        captured, '{"reliability_score": 0.7}', {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.002}))
    before = _orc.current_run_cost()
    text = make_openrouter_credibility_caller()("hi")
    assert text == '{"reliability_score": 0.7}'
    assert captured["url"].endswith("/chat/completions") and captured["model"] == "z-ai/glm-5.1"
    assert abs(_orc.current_run_cost() - before - 0.002) < 1e-9  # STRICT delta == the call's recorded cost


def test_provider_pinned_to_mirror_chain_no_fallback_when_gate_active(monkeypatch):
    # I-arch-004 F09: the credibility side-judge must pin to the MIRROR role's resolved provider
    # (the locked GLM-5.1 chain), NOT the RETIRED "evaluator" role. The preflight role_provider_map
    # only carries generator/mirror/sentinel/judge; "evaluator" is absent. Assert the caller looks
    # up "mirror" and pins it singleton-no-fallback (allow_fallbacks=False, require_parameters=True).
    captured = {}
    monkeypatch.setattr(httpx, "Client", _fake_client(captured, "{}", {"cost": 0.001}))
    from src.polaris_graph.benchmark import pathB_capture as _pathb
    looked_up = []

    def _fake_get_role_provider(role):
        looked_up.append(role)
        return "novita" if role == "mirror" else None

    monkeypatch.setattr(_pathb, "get_role_provider", _fake_get_role_provider)
    make_openrouter_credibility_caller()("hi")
    # The resolved provider order is the MIRROR chain, pinned with no fallback.
    assert captured["body"]["provider"] == {
        "order": ["novita"], "allow_fallbacks": False, "require_parameters": True}
    # Discriminating: the caller routed via "mirror", NOT the retired "evaluator" key.
    assert "mirror" in looked_up
    assert "evaluator" not in looked_up


def test_retired_evaluator_key_does_not_pin_provider(monkeypatch):
    # I-arch-004 F09 regression guard: BEFORE the fix the caller looked up "evaluator", which the
    # locked 4-role role_provider_map never carries -> None -> NO provider pin -> free-route. Mimic
    # that map shape (only "mirror" populated) and prove the caller now PINS (does not free-route).
    captured = {}
    monkeypatch.setattr(httpx, "Client", _fake_client(captured, "{}", {"cost": 0.001}))
    from src.polaris_graph.benchmark import pathB_capture as _pathb
    role_map = {"generator": "fireworks", "mirror": "novita",
                "sentinel": "deepinfra", "judge": "together"}
    monkeypatch.setattr(_pathb, "get_role_provider", lambda role: role_map.get(role))
    make_openrouter_credibility_caller()("hi")
    # Resolved == the mirror chain (not None, not the generator's, not unpinned/free-route).
    assert captured["body"]["provider"]["order"] == ["novita"]
    assert captured["body"]["provider"]["allow_fallbacks"] is False
    assert captured["body"]["provider"]["require_parameters"] is True


def test_budget_breach_propagates_through_caller_and_judge(monkeypatch):
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    monkeypatch.setattr(httpx, "Client", _fake_client({}, "{}", {"cost": 999.0}))

    def _boom(*a, **k):
        raise BudgetExceededError("cap breached")

    monkeypatch.setattr(_orc, "check_run_budget", _boom)
    caller = make_openrouter_credibility_caller()
    with pytest.raises(BudgetExceededError):
        caller("hi")
    # P1-2: the breach must NOT be masked as judge_error — it propagates through make_credibility_judge.
    judge = make_credibility_judge(caller)
    with pytest.raises(BudgetExceededError):
        judge("q", {"title": "t"})


def test_missing_api_key_fails_loud(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        make_openrouter_credibility_caller()


def test_family_segregation_is_checked_at_construction(monkeypatch):
    # P1-1: the caller MUST run the two-family check on the credibility model (so a misconfig that puts it
    # in the generator's family fails loudly). Verify the check is wired (not its internal behavior).
    called = {}
    monkeypatch.setattr(_orc, "check_family_segregation", lambda **kw: called.update(kw))
    make_openrouter_credibility_caller(model="z-ai/glm-5.1")
    assert called.get("evaluator_model") == "z-ai/glm-5.1"


def test_pathb_capture_raw_io_and_ledger_recorded(monkeypatch):
    # P2: the caller must FEED the gate surface — Path-B capture, raw-IO sink, and the cost ledger.
    captured = {}
    monkeypatch.setattr(httpx, "Client", _fake_client(
        captured, "{}", {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.001}))
    from src.polaris_graph.benchmark import pathB_capture as _pathb
    seen = {}
    monkeypatch.setattr(_pathb, "is_active", lambda: True)
    monkeypatch.setattr(_pathb, "capture_llm_call", lambda **kw: seen.__setitem__("capture", kw))
    monkeypatch.setattr(_orc, "append_cost_ledger_row", lambda **kw: seen.__setitem__("ledger", kw))

    class _Sink:
        def record(self, **kw):
            seen["raw_io"] = kw

    monkeypatch.setattr(_orc, "current_raw_io_sink", lambda: _Sink())
    make_openrouter_credibility_caller()("hi")
    assert seen["capture"]["role"] == "evaluator"
    assert seen["ledger"]["call_type"] == "credibility_judge" and seen["ledger"]["cost_usd"] == 0.001
    assert seen["raw_io"]["call_type"] == "credibility_judge" and seen["raw_io"]["role"] == "evaluator"


def test_raw_io_labels_malformed_envelope_as_judge_error(monkeypatch):
    # I-cred-012a iter-4 P2: a served-but-malformed (no choices) response must be raw-IO-labeled
    # "judge_error", not transport-"ok" (it becomes a judge_error when the content extract fails).
    class _NoChoicesResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"usage": {"cost": 0.001}}  # well-formed HTTP 200 but NO choices envelope

    class _NoChoicesClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return _NoChoicesResp()

    monkeypatch.setattr(httpx, "Client", _NoChoicesClient)
    seen = {}

    class _Sink:
        def record(self, **kw):
            seen["status"] = kw.get("status")

    monkeypatch.setattr(_orc, "current_raw_io_sink", lambda: _Sink())
    caller = make_openrouter_credibility_caller()
    # I-arch-002 (#1251): a no-choices envelope now returns EMPTY content after bounded retries (rather than
    # raising in the caller); the judge wrapper maps empty -> {} -> per-row judge_error (fail-loud upstream).
    # The raw-IO sink still labels the malformed envelope status="judge_error".
    result = caller("hi")
    assert (result or "").strip() == ""
    assert seen["status"] == "judge_error"


def test_caller_to_judge_to_p2_end_to_end(monkeypatch):
    captured = {}
    monkeypatch.setattr(httpx, "Client", _fake_client(
        captured, '{"reliability_score": 0.65, "relevance_score": 1.0}',
        {"prompt_tokens": 8, "completion_tokens": 4, "cost": 0.001}))
    judge = make_credibility_judge(make_openrouter_credibility_caller())
    rows = [{"evidence_id": "e1", "authority_score": 0.6, "authority_confidence": "HIGH",
             "signal_scores": {"scholarly": 0.9}, "title": "T", "source_url": "http://x"}]
    out = score_source_credibility("does X work?", rows, judge=judge)[0]
    assert out.judge_error is False and out.reliability_score == 0.65
    assert "does X work?" in captured["prompt"] and "authority_score" in captured["prompt"]
