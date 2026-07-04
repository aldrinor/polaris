"""I-deepfix-001 Item-12 — DNS resilience for the per-citation relevance judge (faithfulness-neutral).

HERMETIC / OFFLINE: every test replaces the judge's httpx client with a stub that returns/raises
queued side effects. NO socket is opened, NO live LLM is called, and the OpenRouter key is fixed to a
test value. ``time.sleep`` is monkeypatched to a no-op so the bounded backoff never actually sleeps.

WHAT this proves (the Item-12 fix + the fail-CLOSED asymmetry it must preserve):

  RELEVANCE judge (``generator/relevance_judge.py::_RelevanceJudge.judge``) — fail-OPEN-KEEP leg:
    (a) ONE transient DNS ``httpx.ConnectError`` (getaddrinfo "Temporary failure in name resolution")
        then a valid 200 -> the REAL verdict is returned (the blip was retried, not collapsed to the
        always-release SUPPORTED keep). RED before the fix (single attempt), GREEN after.
    (b) PERSISTENT DNS error -> after the bounded retries the SAME always-release SUPPORTED keep fires
        (§-1.3 weight-not-filter: the relevance label never drops a source; a runtime fault keeps the
        already-strict_verify-passed cite at full weight).
    (c) A NON-DNS exception (ValueError) is NOT retried -> single attempt, keep (the retry is
        DNS/connect-specific; other faults keep the byte-identical single-attempt path).
    (d) BudgetExceededError propagates on the FIRST POST and is never retried nor masked.

  ENTAILMENT judge (``llm/entailment_judge.py``) — the faithfulness NLI leg, fail-CLOSED:
    (e) PERSISTENT DNS error -> the EXACT ("ENTAILED", "judge_error: ...") sentinel is returned after
        the bounded retries (which the strict_verify consumer DROPS). This is the load-bearing
        asymmetry: the relevance label fails OPEN (keep), the faithfulness leg fails CLOSED (drop).
        This leg is UNCHANGED by the fix; the test is the regression guard on that invariant.

NON-GOAL: no faithfulness-gate relaxation. The relevance retry only recovers a real verdict on a
transient blip (which may DEMOTE weight) or is a no-op; it never admits an unverified claim.
"""

from __future__ import annotations

import json

import httpx
import pytest

from src.polaris_graph.generator import relevance_judge
from src.polaris_graph.llm import entailment_judge, openrouter_client


# --------------------------------------------------------------------------------------------- env


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch):
    """Fix the OpenRouter key, ride the documented single-family override (so construction does not
    trip check_family_segregation), and zero every backoff so the bounded retries never sleep."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    monkeypatch.setenv("PG_RELEVANCE_ALLOW_SAME_FAMILY", "1")
    # Zero the relevance-judge DNS backoff so the retries do not actually sleep in the suite.
    monkeypatch.setenv("PG_RELEVANCE_DNS_RETRY_BACKOFF_S", "0")
    monkeypatch.setenv("PG_RELEVANCE_DNS_RETRY_BACKOFF_CAP_S", "0")
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    # Belt-and-braces: no real sleep anywhere in either judge module.
    monkeypatch.setattr(relevance_judge.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(entailment_judge.time, "sleep", lambda *_a, **_k: None)
    yield


@pytest.fixture(autouse=True)
def _reset_run_cost():
    openrouter_client.reset_run_cost()
    yield
    openrouter_client.reset_run_cost()


@pytest.fixture(autouse=True)
def _reset_relevance_singleton():
    relevance_judge.reset_judge_singleton()
    yield
    relevance_judge.reset_judge_singleton()


# ------------------------------------------------------------------------------------------ stubs


class _FakeJudgeClient:
    """A stub httpx.Client: returns/raises the queued side effects, one per ``.post()`` call. The last
    side effect is repeated for any calls beyond the queue (so a persistent-fault list of length 1
    faults on every attempt)."""

    def __init__(self, side_effects):
        self._side_effects = side_effects
        self.n = 0

    def post(self, *args, **kwargs):
        i = self.n
        self.n += 1
        effect = self._side_effects[min(i, len(self._side_effects) - 1)]
        if isinstance(effect, Exception):
            raise effect
        return effect


_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _dns_error() -> httpx.ConnectError:
    """The Item-12 fault: a getaddrinfo name-resolution failure surfaces as httpx.ConnectError."""
    return httpx.ConnectError("[Errno -3] Temporary failure in name resolution (getaddrinfo)")


def _relevance_http_response(label: str, reason: str = "", cost: float | None = None) -> httpx.Response:
    payload: dict = {
        "choices": [{"message": {"content": json.dumps({"label": label, "reason": reason})}}],
    }
    if cost is not None:
        payload["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "cost": cost}
    return httpx.Response(200, json=payload, request=_REQUEST)


def _make_relevance_judge(side_effects) -> relevance_judge._RelevanceJudge:
    judge = relevance_judge._RelevanceJudge()
    judge._client = _FakeJudgeClient(side_effects)
    return judge


# ============================================================ RELEVANCE JUDGE — fail-OPEN-KEEP leg


def test_relevance_dns_error_then_success_returns_real_verdict():
    """(a) ONE getaddrinfo ConnectError then a valid 200 -> the REAL verdict (INSUFFICIENT) is
    returned, not the always-release SUPPORTED keep. RED before the fix (single attempt would drop to
    SUPPORTED without ever making the second, successful call), GREEN after."""
    judge = _make_relevance_judge(
        [_dns_error(), _relevance_http_response("INSUFFICIENT", "right entity, wrong relation")]
    )
    label, reason = judge.judge("claim text", "cited span text")
    assert label == relevance_judge.LABEL_INSUFFICIENT
    assert not reason.startswith("judge_error:")
    assert judge._client.n == 2  # one failed DNS attempt + one success


def test_relevance_persistent_dns_fails_open_keep():
    """(b) PERSISTENT getaddrinfo error -> after the bounded retries the always-release SUPPORTED keep
    fires (§-1.3: never drop a source on a transport fault). Asserts the retries were exhausted."""
    import os

    os.environ["PG_RELEVANCE_DNS_RETRY_ATTEMPTS"] = "2"
    try:
        judge = _make_relevance_judge([_dns_error()])
        label, reason = judge.judge("claim text", "cited span text")
        assert label == relevance_judge.LABEL_SUPPORTED  # fail-open KEEP preserved
        assert reason.startswith("judge_error:")
        assert judge._client.n == 3  # 1 + PG_RELEVANCE_DNS_RETRY_ATTEMPTS
    finally:
        os.environ.pop("PG_RELEVANCE_DNS_RETRY_ATTEMPTS", None)


def test_relevance_non_dns_exception_not_retried():
    """(c) A NON-DNS exception (ValueError) is NOT a DNS/connect fault -> single attempt, always-release
    keep. Proves the retry is DNS/connect-specific, not a blanket retry-everything."""
    judge = _make_relevance_judge([ValueError("malformed body — not a connectivity fault")])
    label, reason = judge.judge("claim text", "cited span text")
    assert label == relevance_judge.LABEL_SUPPORTED
    assert reason.startswith("judge_error:")
    assert judge._client.n == 1  # NOT retried


def test_relevance_budget_exceeded_propagates_not_retried(monkeypatch):
    """(d) A per-run budget breach on the judge spend propagates on the FIRST POST — never retried,
    never masked as a transient judge error."""
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.0001)
    # A valid 200 whose cost (0.001) breaches the 0.0001 cap on the first attempt.
    judge = _make_relevance_judge([_relevance_http_response("SUPPORTED", "ok", cost=0.001)])
    with pytest.raises(openrouter_client.BudgetExceededError):
        judge.judge("claim text", "cited span text")
    assert judge._client.n == 1  # the breach aborts before any retry


# ============================================================ ENTAILMENT JUDGE — faithfulness fail-CLOSED


@pytest.fixture(autouse=True)
def _reset_entailment_singleton():
    entailment_judge._JUDGE_SINGLETON = None
    yield
    entailment_judge._JUDGE_SINGLETON = None


def _make_entailment_judge(side_effects) -> entailment_judge._EntailmentJudge:
    judge = entailment_judge._EntailmentJudge()
    judge._client = _FakeJudgeClient(side_effects)
    return judge


def test_entailment_persistent_dns_fails_closed_sentinel(monkeypatch):
    """(e) PERSISTENT getaddrinfo error on the NLI faithfulness leg -> the EXACT
    ("ENTAILED", "judge_error: ...") fail-CLOSED sentinel is returned after the bounded retries. The
    consumer (strict_verify enforce) DROPS this sentinel, so the faithfulness leg fails CLOSED — the
    opposite of the relevance leg's fail-OPEN keep. This leg is UNCHANGED by the Item-12 fix; this is
    the regression guard on the asymmetry the fix must preserve."""
    # Two-family models (§9.1.1) so _EntailmentJudge construction passes check_family_segregation.
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "google/gemma-4-31b-it")
    # Keep both retry budgets small so the test is fast + deterministic; a getaddrinfo ConnectError is
    # classified as a connectivity fault, so it takes the rate-limit budget.
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "1")
    monkeypatch.setenv("PG_ENTAILMENT_RATE_LIMIT_RETRIES", "1")
    monkeypatch.setenv("PG_ENTAILMENT_RATE_LIMIT_FLOOR_S", "0")
    monkeypatch.setenv("PG_ENTAILMENT_RATE_LIMIT_CAP_S", "0")
    monkeypatch.setenv("PG_ENTAILMENT_RETRY_BACKOFF_S", "0")

    judge = _make_entailment_judge([_dns_error()])
    verdict, reason = judge.judge("a sentence", "a span")

    # The load-bearing fail-CLOSED sentinel: ENTAILED verdict + judge_error: prefix (do NOT flip).
    assert verdict == "ENTAILED"
    assert reason.startswith("judge_error:")
    # It RETRIED the DNS blip (more than one attempt) rather than collapsing on the first hit.
    assert judge._client.n >= 2
