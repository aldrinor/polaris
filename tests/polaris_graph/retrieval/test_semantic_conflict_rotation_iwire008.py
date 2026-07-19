"""I-wire-008 (#1322) — NLI semantic-conflict side-judge: provider rotation (offline, no socket).

This side-judge previously had NO rotation: it pinned ONE mirror host (allow_fallbacks:False) and
the B14 empty-content guard re-POSTed the SAME host on every no-choices attempt — the real
"4x same-provider retry" the issue names (a flaky novita lead -> 3 same-host attempts ->
conflict_unscored). These hermetic tests assert:
  * ON: a no-choices on the lead ADVANCES to the next healthy host and the retry returns the REAL
    verdict (faithfulness-neutral: same model, healthier host).
  * Persistent no-choices ON: tries DISTINCT hosts then degrades FAIL-CLOSED to the
    conflict_unscored label (disclosed gap — never a fabricated conflict, never a dropped one) and
    RETURNS control. The error-body attempts bill ~$0 (phantom impute narrowed).
  * OFF (default): single-host pin, no rotation (byte-identical).
"""
import json

import pytest

from src.polaris_graph.benchmark import benchmark_run_capture
from src.polaris_graph.llm import openrouter_client
from src.polaris_graph.retrieval import semantic_conflict_detector as scd


class _FakeResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=None)

    def json(self):
        return self._payload


class _RecordingClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.sent_orders: list[list] = []
        self._i = 0

    def post(self, endpoint, headers=None, json=None):  # noqa: A002 — httpx kwarg name
        prov = (json or {}).get("provider") or {}
        self.sent_orders.append(list(prov.get("order") or []))
        resp = self._responses[min(self._i, len(self._responses) - 1)]
        self._i += 1
        return resp

    def close(self):
        pass


def _error_body_200():
    return _FakeResp(200, {"error": {"message": "no instances", "code": 429}, "usage": {}})


def _contradict_200():
    return _FakeResp(
        200,
        {
            "choices": [{"message": {"content": json.dumps({"verdict": "CONTRADICT", "confidence": 0.9})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0},
        },
    )


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    scd._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    monkeypatch.setenv("PG_SIDE_JUDGE_EMPTY_RETRIES", "2")  # 3 attempts
    monkeypatch.delenv("PG_JUDGE_UNHEALTHY_PROVIDERS", raising=False)
    # Make impute return a LARGE marker for the phantom (400,60) shape, 0 otherwise.
    monkeypatch.setattr(openrouter_client, "check_run_budget", lambda *a, **k: None)
    monkeypatch.setattr(
        openrouter_client, "_impute_cost_from_tokens",
        lambda model, pin, pout, rtok: 9.99 if (pin, pout) == (400, 60) else 0.0,
    )
    yield
    scd._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()


def _judge_with_client(responses):
    judge = scd._SemanticContradictionJudge(strict_fail_closed=False)
    judge._client = _RecordingClient(responses)
    return judge, judge._client


def test_rotation_on_advances_off_no_choices_to_real_verdict(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    judge, client = _judge_with_client([_error_body_200(), _contradict_200()])

    label, confidence = judge.judge("improved overall survival", "no overall survival benefit")

    assert label == "contradict", (label, confidence)
    assert client.sent_orders[0] == ["friendli"], client.sent_orders
    assert client.sent_orders[1] == ["novita"], client.sent_orders  # rotated off the no-choices lead


def test_rotation_on_persistent_no_choices_fails_closed_unscored(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    billed: list[float] = []
    monkeypatch.setattr(openrouter_client, "_add_run_cost", lambda c: billed.append(float(c)))
    judge, client = _judge_with_client([_error_body_200()])  # every attempt no-choices

    label, confidence = judge.judge("claim a", "claim b")

    # FAIL-CLOSED disclosed gap: not a fabricated conflict, not a dropped real one.
    assert label == scd.CONFLICT_UNSCORED_LABEL, (label, confidence)
    # Tried DISTINCT hosts (not 3x the same), and returned control (no hang).
    assert client.sent_orders[0] == ["friendli"], client.sent_orders
    assert len({tuple(o) for o in client.sent_orders}) >= 2, client.sent_orders
    # The no-choices attempts billed the real (zero) usage — phantom 400/60 never fired.
    assert sum(billed) == 0.0, billed


def test_rotation_off_is_single_host_pin(monkeypatch):
    monkeypatch.delenv("PG_JUDGE_PROVIDER_ROTATE", raising=False)
    token = pathB_capture.set_role_providers({"mirror": "friendli"})
    try:
        judge, client = _judge_with_client([_error_body_200(), _contradict_200()])
        judge.judge("claim a", "claim b")
        # No rotation: every attempt pinned the SAME single host (byte-identical to pre-fix).
        assert client.sent_orders, "no POST made"
        assert all(o == ["friendli"] for o in client.sent_orders), client.sent_orders
    finally:
        pathB_capture.reset_role_providers(token)
