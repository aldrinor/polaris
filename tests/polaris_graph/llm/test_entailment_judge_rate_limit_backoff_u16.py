"""U16 (I-deepfix-001) — entailment-judge rate-limit / connectivity backoff (offline, hermetic).

RED->GREEN. The per-claim entailment judge (strict_verify check-(f) side-judge) previously treated a
real HTTP 429/503, a DNS "name resolution" ConnectError, and a 200-wrapped 429 error-envelope with the
SAME tiny fixed backoff (0.5s) and the SAME small general retry budget (2) as a bad-verdict. Under a
transient account-QPS 429 storm or a DNS blip the ~3 attempts exhausted in ~1s and the claim
fail-closed DROPPED -> over ~178 claims/report the storm self-sustained, the seam tore, and
drb_75 checkpoint-resume never converged. This suite proves the fix:

  * a real 429 with a `Retry-After` header waits the SERVER-instructed delay (not 0.5s);
  * a DNS ConnectError + a 200-wrapped 429 recover a REAL verdict via the LARGER rate-limit retry
    budget with a floored/backed-off cadence, instead of over-dropping to the judge_error sentinel;
  * a NON-rate-limit fault keeps the byte-identical fixed-backoff + small-budget path (invariance);
  * the judge MODEL stays two-family-valid + open and the family-segregation guard is INTACT.

HERMETIC: a stub `httpx.Client` (the `judge._build_client` injection contract) — NO socket, NO live
LLM, NO real sleep (an autouse spy records the intended durations). Faithfulness is NEVER relaxed: the
fail-closed ('ENTAILED','judge_error:...') sentinel + verdict logic are byte-unchanged; the fix only
recovers a transient transport fault that would otherwise over-drop a salvageable verdict.
"""

from __future__ import annotations

import json
import threading

import httpx
import pytest

from src.polaris_graph.llm import entailment_judge, openrouter_client


# --------------------------------------------------------------------------------------------- env


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-hermetic")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_ENTAILMENT_MODEL", "z-ai/glm-5.2")
    # The pre-fix trap: a SMALL general budget (the value that over-dropped a 429/DNS storm)...
    monkeypatch.setenv("PG_ENTAILMENT_RETRIES", "2")
    # ...and the U16 fix: a LARGER, bounded rate-limit budget + a real floored backoff.
    monkeypatch.setenv("PG_ENTAILMENT_RATE_LIMIT_RETRIES", "5")
    monkeypatch.setenv("PG_ENTAILMENT_RATE_LIMIT_FLOOR_S", "15")
    monkeypatch.setenv("PG_ENTAILMENT_RATE_LIMIT_CAP_S", "60")
    # The pre-fix fixed backoff — contrasts against the 20s Retry-After the fix must honor.
    monkeypatch.setenv("PG_ENTAILMENT_RETRY_BACKOFF_S", "0.5")
    # Rotation OFF -> hermetic single-host pin; the stub ignores provider anyway. (iwire008 covers the
    # rotation-ON path; U16 PRESERVES rotation, it does not depend on it.)
    monkeypatch.delenv("PG_JUDGE_PROVIDER_ROTATE", raising=False)
    for k in ("OPENROUTER_BASE_URL", "PG_ENTAILMENT_TRANSPORT_POISON_MARKERS",
              "PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY"):
        monkeypatch.delenv(k, raising=False)
    entailment_judge._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()
    yield
    entailment_judge._JUDGE_SINGLETON = None
    openrouter_client.reset_run_cost()


@pytest.fixture(autouse=True)
def sleeps(monkeypatch):
    """Record every intended backoff duration WITHOUT actually sleeping (fast + deterministic)."""
    recorded: list[float] = []
    monkeypatch.setattr(entailment_judge.time, "sleep", lambda s=0.0: recorded.append(float(s)))
    return recorded


# --------------------------------------------------------------------------------- stub transport


_JUDGE_REQUEST = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


def _ok_payload(verdict: str = "ENTAILED", reason: str = "ok") -> dict:
    return {
        "choices": [{"message": {"content": json.dumps({"verdict": verdict, "reason": reason})}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }


def _resp(status: int, payload: dict | None = None, headers: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload if payload is not None else {},
        headers=headers or {},
        request=_JUDGE_REQUEST,
    )


class _StubClient:
    """Returns/raises a SEQUENCE of side effects per `.post()` (the last one repeats). Mirrors the
    real `is_closed` BOOL so the production self-heal guard never spuriously rebuilds this stub."""

    def __init__(self, side_effects):
        self._fx = list(side_effects)
        self.n = 0
        self.is_closed = False

    def post(self, *args, **kwargs):
        i = self.n
        self.n += 1
        fx = self._fx[min(i, len(self._fx) - 1)]
        if isinstance(fx, BaseException):
            raise fx
        return fx

    def close(self):
        self.is_closed = True


def _make_judge(monkeypatch, side_effects):
    """A real `_EntailmentJudge` whose per-thread client is the stub (bypasses __init__/network)."""
    judge = entailment_judge._EntailmentJudge.__new__(entailment_judge._EntailmentJudge)
    judge._model = "z-ai/glm-5.2"
    judge._endpoint = "https://openrouter.ai/api/v1/chat/completions"
    judge._api_key = "test-key-hermetic"
    judge._tls = threading.local()
    stub = _StubClient(side_effects)
    monkeypatch.setattr(judge, "_build_client", lambda: stub)
    return judge, stub


# ======================================================== RED->GREEN: a 429 with Retry-After honored


def test_real_429_honors_retry_after_not_fixed_backoff(monkeypatch, sleeps):
    """A real HTTP 429 carrying `Retry-After: 20` -> the judge waits the SERVER-instructed 20s
    (clamped to the 60s cap), NOT the 0.5s fixed backoff, then recovers the real verdict.

    RED (pre-fix): a 429 hits the generic branch and sleeps the fixed 0.5s -> recorded == [0.5, 0.5].
    GREEN (post-fix): recorded == [20.0, 20.0]. Verdict is ENTAILED in both — the discriminator is the
    HONORED Retry-After delay (a single-provider 429 no longer burns the retry budget in ~1s)."""
    judge, _ = _make_judge(
        monkeypatch,
        [
            _resp(429, headers={"Retry-After": "20"}),
            _resp(429, headers={"Retry-After": "20"}),
            _resp(200, _ok_payload("ENTAILED", "supported")),
        ],
    )
    verdict, reason = judge.judge("a sentence", "a span that entails it")
    assert verdict == "ENTAILED", (verdict, reason)
    assert not reason.startswith("judge_error:")
    assert sleeps == [20.0, 20.0], (
        f"Retry-After: 20 must be honored verbatim; got {sleeps} (pre-fix would be the 0.5s fixed backoff)"
    )


# =============================================== RED->GREEN: a DNS blip uses the larger recovery budget


def test_dns_connect_error_uses_larger_budget_and_recovers(monkeypatch, sleeps):
    """A DNS 'name resolution' ConnectError on attempts 1-4 then success on attempt 5 -> the judge
    recovers a REAL verdict using the larger rate-limit retry budget (5), with a floored backoff.

    RED (pre-fix): only the general budget (2) applies -> the 4-failure storm exhausts and the claim
    DROPS to the ('ENTAILED','judge_error:...') sentinel (the seam-tear / over-drop).
    GREEN (post-fix): recovers -> verdict ENTAILED, reason not judge_error; >2 floored backoffs used."""
    dns_err = httpx.ConnectError("[Errno -3] Temporary failure in name resolution")
    judge, _ = _make_judge(
        monkeypatch,
        [dns_err, dns_err, dns_err, dns_err, _resp(200, _ok_payload("ENTAILED", "supported"))],
    )
    verdict, reason = judge.judge("a sentence", "a span that entails it")
    assert verdict == "ENTAILED", (verdict, reason)
    assert not reason.startswith("judge_error:"), (
        "PRE-FIX: the DNS storm over-dropped to the judge_error sentinel (only 2 general retries); "
        "POST-FIX the larger rate-limit budget recovers the real verdict."
    )
    assert len(sleeps) >= 3, f"the larger rate-limit budget must retry past the general 2; got {sleeps}"
    assert all(s >= 15.0 for s in sleeps), f"each rate-limit backoff must respect the 15s floor; got {sleeps}"
    assert all(s <= 60.0 for s in sleeps), f"each rate-limit backoff must respect the 60s cap; got {sleeps}"


# ===================================== RED->GREEN: a 200-wrapped 429 error-envelope is a rate-limit fault


def test_200_wrapped_429_classified_as_rate_limit_and_recovers(monkeypatch, sleeps):
    """An OpenRouter error envelope returned as HTTP 200 with code 429 (`{"error":{"code":429}}`) is
    classified as a rate-limit fault (reason `rate_limit_200`) and recovers via the larger budget.

    RED (pre-fix): classified as the generic `error_body_200` -> general budget (2) -> the 4-failure
    storm over-drops to the judge_error sentinel.
    GREEN (post-fix): recovers -> verdict ENTAILED, reason not judge_error."""
    err_200 = _resp(200, {"error": {"message": "rate-limited", "code": 429}, "usage": {}})
    judge, _ = _make_judge(
        monkeypatch,
        [err_200, err_200, err_200, err_200, _resp(200, _ok_payload("ENTAILED", "supported"))],
    )
    verdict, reason = judge.judge("a sentence", "a span that entails it")
    assert verdict == "ENTAILED", (verdict, reason)
    assert not reason.startswith("judge_error:"), (
        "PRE-FIX: a 200-wrapped 429 storm was over-dropped on the general budget; POST-FIX the "
        "rate_limit_200 classification recovers on the larger rate-limit budget."
    )
    assert len(sleeps) >= 3 and all(15.0 <= s <= 60.0 for s in sleeps), sleeps


def test_no_choices_reason_classifies_rate_limit_code():
    """Unit-level proof of the reclassification: a 429/503/502/504-coded 200-wrapped error envelope
    yields `rate_limit_200`; a non-rate-limit error code keeps the byte-identical `error_body_200`."""
    assert entailment_judge._no_choices_reason({"error": {"code": 429}}) == "rate_limit_200"
    assert entailment_judge._no_choices_reason({"error": {"code": 503}}) == "rate_limit_200"
    assert entailment_judge._no_choices_reason({"error": {"code": 500}}) == "error_body_200"
    assert entailment_judge._no_choices_reason({"error": {"message": "x"}}) == "error_body_200"
    # A well-formed empty/missing choices body is NOT an error envelope (unchanged classification).
    assert entailment_judge._no_choices_reason({"choices": []}) == "no_choices"


# =========================================================== INVARIANCE: off-path is byte-identical


def test_non_rate_limit_fault_keeps_fixed_backoff_and_small_budget(monkeypatch, sleeps):
    """A NON-rate-limit transport fault (RemoteProtocolError) is unchanged: it retries on the small
    general budget (2) with the fixed 0.5s backoff, then fails CLOSED to the exact sentinel. Proves the
    U16 change is scoped strictly to rate-limit/connectivity faults (off-path byte-identical)."""
    judge, _ = _make_judge(monkeypatch, [httpx.RemoteProtocolError("persistent mid-stream disconnect")])
    verdict, reason = judge.judge("a sentence", "a span")
    assert verdict == "ENTAILED"
    assert reason == "judge_error: RemoteProtocolError"
    assert sleeps == [0.5, 0.5], f"a non-rate-limit fault must keep the fixed 0.5s backoff; got {sleeps}"


def test_rate_limit_classifier_unit():
    """The predicate: a 429/503 HTTPStatusError + a DNS ConnectError are rate-limit/connectivity; a
    parse / closed-client / bad-verdict fault is NOT (keeps its existing fixed-backoff path)."""
    resp429 = _resp(429)
    assert entailment_judge._is_rate_limit_or_connectivity_fault(
        httpx.HTTPStatusError("429", request=_JUDGE_REQUEST, response=resp429)
    ) is True
    assert entailment_judge._is_rate_limit_or_connectivity_fault(
        httpx.ConnectError("[Errno -3] Temporary failure in name resolution")
    ) is True
    # NOT rate-limit -> keeps the byte-identical fixed-backoff + rotation/rebuild path.
    assert entailment_judge._is_rate_limit_or_connectivity_fault(
        RuntimeError("Cannot send a request, as the client has been closed.")
    ) is False
    assert entailment_judge._is_rate_limit_or_connectivity_fault(json.JSONDecodeError("x", "y", 0)) is False
    assert entailment_judge._is_rate_limit_reason("rate_limit_200") is True
    assert entailment_judge._is_rate_limit_reason("bad_verdict='MAYBE'") is False


# ================================================= FAITHFULNESS GUARD: model two-family-valid + open


def test_default_judge_model_is_two_family_valid_and_open_and_guard_intact(monkeypatch):
    """The judge MODEL is UNCHANGED by U16 (transport-only fix): the default entailment model stays
    the open-weight, sovereign `z-ai/glm-5.2`, it is two-family-valid vs the deepseek generator, AND
    the family-segregation guard still RAISES on a same-family judge (I did not weaken it)."""
    from src.polaris_graph.llm.openrouter_client import check_family_segregation

    monkeypatch.delenv("PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY", raising=False)
    model = entailment_judge._DEFAULT_ENTAILMENT_MODEL
    assert model == "z-ai/glm-5.2"
    # Open-weight / sovereign: not a closed US-vendor slug.
    assert not any(
        model.startswith(p) for p in ("openai/", "anthropic/", "google/gemini", "x-ai/grok")
    )
    # Two-family-VALID: the default judge is a DIFFERENT training lineage from the deepseek generator.
    gen_fam, eval_fam = check_family_segregation(
        generator_model="deepseek/deepseek-v4-pro", evaluator_model=model
    )
    assert gen_fam != eval_fam
    # Guard INTACT: a SAME-family judge STILL raises (the two-family invariant is not weakened).
    with pytest.raises(RuntimeError):
        check_family_segregation(
            generator_model="deepseek/deepseek-v4-pro", evaluator_model="deepseek/deepseek-r1"
        )
