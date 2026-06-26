"""I-wire-008 (#1322) — entailment judge: no-choices / error-body-200 health hardening (offline).

Behavioral, hermetic (a fake httpx client, NO socket). Asserts the four task invariants:
  1. A no-choices / OpenRouter error-body-returned-as-200 ROTATES to the next healthy host
     IMMEDIATELY (no bare KeyError, no 4x same-provider re-POST).
  2. The error-body-200 attempt bills ~$0 — the I-bug-100 phantom 500/100 impute is NARROWED to
     the ambiguous "content present, usage missing" case, so a provider-health storm cannot inflate
     the run budget on zero real completions and trip BudgetExceededError (== abort the run).
  3. A 429 backs off + rotates (it raises at raise_for_status, before billing — never phantom-billed).
  4. On exhaustion the judge DEGRADES FAIL-CLOSED: it returns the ('ENTAILED','judge_error:...')
     sentinel (consumers DROP -> the claim stays unmerged + flagged) and RETURNS control (no hang).
"""
import json

import pytest

from src.polaris_graph.llm import entailment_judge, openrouter_client


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
    """Pops a queued response per POST and records the provider `order` sent each time."""

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
    # OpenRouter error envelope returned with HTTP 200 — no `choices`, empty usage (zero completion).
    return _FakeResp(200, {"error": {"message": "no instances available", "code": 429}, "usage": {}})


def _no_choices_200():
    return _FakeResp(200, {"choices": [], "usage": {}})


def _entailed_200(provider: str):
    return _FakeResp(
        200,
        {
            "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0},
            "provider": provider,
        },
    )


def _http_429():
    return _FakeResp(429, {})


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    entailment_judge._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "3")
    monkeypatch.setenv("PG_ENTAILMENT_RETRY_BACKOFF_S", "0")  # keep the test fast
    monkeypatch.delenv("PG_JUDGE_UNHEALTHY_PROVIDERS", raising=False)
    yield
    entailment_judge._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()


def _track_billing(monkeypatch):
    """Capture every _add_run_cost; make impute return a LARGE marker for the phantom (500,100)
    shape and 0 for zero-token usage, so any phantom bill is detectable as a non-zero total."""
    billed: list[float] = []
    monkeypatch.setattr(openrouter_client, "_add_run_cost", lambda c: billed.append(float(c)))
    monkeypatch.setattr(openrouter_client, "check_run_budget", lambda *a, **k: None)

    def _impute(model, pin, pout, rtok):
        return 9.99 if (pin, pout) == (500, 100) else 0.0

    monkeypatch.setattr(openrouter_client, "_impute_cost_from_tokens", _impute)
    return billed


def test_error_body_200_rotates_immediately_and_bills_zero(monkeypatch):
    billed = _track_billing(monkeypatch)
    judge = entailment_judge._EntailmentJudge()
    client = _RecordingClient([_error_body_200(), _entailed_200("Novita")])
    judge._client = client

    verdict, reason = judge.judge("a sentence", "a span that entails it")

    assert verdict == "ENTAILED", (verdict, reason)
    # Rotated off the unhealthy lead on the VERY NEXT attempt (no same-provider re-POST).
    assert client.sent_orders[0] == ["friendli"], client.sent_orders
    assert client.sent_orders[1] == ["novita"], client.sent_orders
    # The error-body attempt billed the real (zero) usage — the phantom 500/100 NEVER fired.
    assert sum(billed) == 0.0, billed


def test_missing_choices_list_rotates(monkeypatch):
    _track_billing(monkeypatch)
    judge = entailment_judge._EntailmentJudge()
    client = _RecordingClient([_no_choices_200(), _entailed_200("Novita")])
    judge._client = client

    verdict, _reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert client.sent_orders[0] == ["friendli"] and client.sent_orders[1] == ["novita"]


def test_429_backs_off_and_rotates(monkeypatch):
    billed = _track_billing(monkeypatch)
    judge = entailment_judge._EntailmentJudge()
    client = _RecordingClient([_http_429(), _entailed_200("Novita")])
    judge._client = client

    verdict, _reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert client.sent_orders[0] == ["friendli"], client.sent_orders
    assert client.sent_orders[1] != ["friendli"], client.sent_orders  # rotated off the 429 host
    assert sum(billed) == 0.0, billed  # a 429 raises before billing


def test_no_choices_storm_degrades_fail_closed_zero_cost(monkeypatch):
    billed = _track_billing(monkeypatch)
    judge = entailment_judge._EntailmentJudge()
    client = _RecordingClient([_error_body_200()])  # every attempt is a no-choices/error body
    judge._client = client

    verdict, reason = judge.judge("a sentence", "a span")

    # FAIL-CLOSED sentinel: ENTAILED + judge_error: prefix -> both consumers DROP (claim unmerged).
    assert verdict == "ENTAILED", verdict
    assert reason.startswith("judge_error:"), reason
    # Returned control (no hang) and advanced through DISTINCT hosts (not 4x same provider).
    assert client.sent_orders[0] == ["friendli"], client.sent_orders
    assert len({tuple(o) for o in client.sent_orders}) >= 2, client.sent_orders
    # Zero phantom billing across the whole storm.
    assert sum(billed) == 0.0, billed


def test_unhealthy_provider_is_filtered_from_rotation(monkeypatch):
    monkeypatch.setenv("PG_JUDGE_UNHEALTHY_PROVIDERS", "novita")
    _track_billing(monkeypatch)
    judge = entailment_judge._EntailmentJudge()
    client = _RecordingClient([_error_body_200(), _entailed_200("Z.AI")])
    judge._client = client

    verdict, _reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    # novita is denied -> the rotation skips it and lands on z-ai (next healthy host).
    assert client.sent_orders[0] == ["friendli"], client.sent_orders
    assert client.sent_orders[1] == ["z-ai"], client.sent_orders
