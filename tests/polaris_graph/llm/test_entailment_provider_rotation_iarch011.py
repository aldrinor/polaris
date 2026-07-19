"""I-arch-011 — entailment-judge provider-ROTATION on a blank-200 (behavioral, hermetic, no socket).

Root cause (measured on box4 2026-06-19): the mirror role pins ONE host (z-ai) with
allow_fallbacks:False; z-ai has intermittent empty-body-200 windows under load. OpenRouter does NOT
auto-advance off a blank (it is an HTTP 200), so every retry re-hit the SAME blanking host and the
judge_error sentinel DROPPED the sentence in enforce mode -> a FAITHFUL-but-NARROW breadth collapse.

These tests inject a fake httpx client (NO socket) that BLANKS on the first POST and returns a real
ENTAILED verdict on the second, and assert:
  * OFF (default): the provider block stays the single-host pin and NEVER rotates (byte-identical).
  * ON: a blank advances the pinned provider to the NEXT mirror host (z-ai -> baidu) and the retry
    returns the REAL verdict from that healthy host. Faithfulness-neutral-to-improving: a real verdict
    replaces a blank-induced drop; the gate logic / fail-closed sentinel are untouched.
"""
import json

import pytest

from src.polaris_graph.benchmark import benchmark_run_capture
from src.polaris_graph.llm import entailment_judge


@pytest.fixture(autouse=True)
def _burst_spread_off(monkeypatch):
    """I-deepfix-001: these I-arch-011 tests assert the single-lead ROTATION-WALK (start friendli ->
    next host). The new default-ON round-robin burst-spread START host is validated separately in
    test_judge_burst_spread_ideepfix001.py; pin it OFF here so the deterministic friendli-lead the
    assertions below depend on is byte-identical to the pre-fix behavior."""
    monkeypatch.setenv("PG_JUDGE_BURST_SPREAD", "0")


class _FakeResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}", request=None, response=None
            )

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


def _blank_200():
    # empty content body + a served-provider envelope = the z-ai intermittent-window signature.
    return _FakeResp(200, {"choices": [{"message": {"content": ""}}], "usage": {}, "provider": "Z.AI"})


def _entailed_200(provider: str):
    return _FakeResp(
        200,
        {
            "choices": [{"message": {"content": json.dumps({"verdict": "ENTAILED", "reason": "ok"})}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0},
            "provider": provider,
        },
    )


@pytest.fixture
def _mirror_pinned(monkeypatch):
    """Make get_role_provider('mirror') resolve to z-ai (as a live preflight would) + ensure routing on."""
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    token = pathB_capture.set_role_providers({"mirror": "z-ai"})
    try:
        yield
    finally:
        pathB_capture.reset_role_providers(token)


def _fresh_judge():
    # Construct a judge directly (not the process singleton) so the injected client is isolated.
    return entailment_judge._EntailmentJudge()


def test_rotation_off_is_single_host_pin(_mirror_pinned, monkeypatch):
    """OFF (default): a blank retries the SAME host; the provider order is the single-host pin on EVERY
    attempt — byte-identical to the pre-I-arch-011 behavior (no rotation)."""
    monkeypatch.delenv("PG_JUDGE_PROVIDER_ROTATE", raising=False)
    judge = _fresh_judge()
    client = _RecordingClient([_blank_200(), _entailed_200("Z.AI")])
    judge._client = client

    verdict, _reason = judge.judge("a sentence", "a span that entails it")

    # Every POST pinned the single lead host — rotation never fired.
    assert client.sent_orders, "no POST was made"
    assert all(order == ["z-ai"] for order in client.sent_orders), client.sent_orders


def test_rotation_on_advances_off_blank_to_real_verdict(_mirror_pinned, monkeypatch):
    """ON: a blank on z-ai advances to baidu, and the retry returns the REAL verdict from baidu.
    This is the faithfulness-IMPROVING effect: a real ENTAILED replaces a z-ai-blank-induced DROP."""
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    judge = _fresh_judge()
    client = _RecordingClient([_blank_200(), _entailed_200("Novita")])
    judge._client = client

    verdict, reason = judge.judge("a sentence", "a span that entails it")

    assert verdict == "ENTAILED", (verdict, reason)
    assert len(client.sent_orders) >= 2, client.sent_orders
    # First attempt hit the chain LEAD; the blank rotated the SECOND attempt to the next mirror host.
    # I-wire-008 config-drift sync: the glm-5.2 mirror chain (I-beatboth-008) leads friendli->novita.
    assert client.sent_orders[0] == ["friendli"], client.sent_orders
    assert client.sent_orders[1] == ["novita"], client.sent_orders


def test_rotation_on_fires_without_pathb_role_map(monkeypatch):
    """Codex diff-gate P1: rotation must NOT depend on the pathB `_gate_provider` contextvar. With NO
    role map set (get_role_provider('mirror') == None) — the exact run_gate_b verify-worker case Codex
    flagged — rotation must STILL derive the chain from the routing YAML, pin the lead, and advance off a
    blank. This is the behavioral proof the fix can never silently NO-OP on the production path."""
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    # Deliberately do NOT call set_role_providers -> get_role_provider('mirror') is None.
    assert pathB_capture.get_role_provider("mirror") is None
    judge = _fresh_judge()
    client = _RecordingClient([_blank_200(), _entailed_200("Novita")])
    judge._client = client

    verdict, _reason = judge.judge("a sentence", "a span that entails it")

    assert verdict == "ENTAILED", verdict
    assert len(client.sent_orders) >= 2, client.sent_orders
    assert client.sent_orders[0] == ["friendli"], client.sent_orders  # chain LEAD from YAML, not _gate_provider
    assert client.sent_orders[1] == ["novita"], client.sent_orders   # rotated off the blank


def test_rotation_on_real_verdict_first_call_does_not_rotate(_mirror_pinned, monkeypatch):
    """ON but the lead host answers cleanly on attempt 0 -> exactly ONE POST, no rotation (the healthy
    common case stays a single fast call)."""
    monkeypatch.setenv("PG_JUDGE_PROVIDER_ROTATE", "1")
    judge = _fresh_judge()
    client = _RecordingClient([_entailed_200("Z.AI")])
    judge._client = client

    verdict, _reason = judge.judge("a sentence", "a span that entails it")

    assert verdict == "ENTAILED"
    assert client.sent_orders == [["friendli"]], client.sent_orders  # I-wire-008 drift sync: glm-5.2 lead
