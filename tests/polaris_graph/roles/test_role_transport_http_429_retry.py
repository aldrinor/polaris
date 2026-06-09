"""Tests for the I-beatboth-429 (#1173) HTTP rate-limit backoff-retry on the benchmark-stage
OpenRouter verifier RoleTransport.

WHY (#1173): the 4-role seam makes one judge call per claim (~178 for drb_72) — a burst that
trips OpenRouter's rate limit on the qwen judge. Before this fix the per-call retry loop retried
ONLY `httpx.TransportError` (connection-level), and ANY non-200 status (incl 429) raised
`RoleTransportError` immediately -> release HELD on a TRANSIENT 429. That systematically held
beat-both-worthy reports (drb_72 + drb_75, 2/2).

CONTRACT (RESILIENCE ONLY, FAIL-CLOSED — never weakens the gate):
  (a) a 429-then-200 sequence SUCCEEDS — the role POST is retried after a bounded backoff and the
      second (200) response's verdict is returned (assert the underlying POST ran >= 2x);
  (b) an ALWAYS-429 sequence STILL raises `RoleTransportError` after the bounded retries are
      exhausted (fail-closed — the existing non-200 raise fires -> release HELD, never a fake
      verdict, never a silent fallback);
  (c) the `Retry-After` integer-seconds header is honored as the backoff delay when present;
  (d) the rate-limit retry budget (PG_ROLE_HTTP_RETRY_MAX) is SEPARATE from the transport-fault
      budget (PG_ROLE_TRANSPORT_RETRIES) — a 429 is not a connection reset.

SPEND-FREE / NO NETWORK: every test injects an `httpx.Client(transport=httpx.MockTransport(...))`
(same pattern as tests/roles/test_openrouter_role_transport_meta007.py), so there is NO socket /
NO real LLM / NO spend in any path pytest exercises. `time.sleep` is monkeypatched to a no-op so
the bounded backoff never actually blocks the test run.
"""

from __future__ import annotations

import httpx
import pytest

import src.polaris_graph.roles.openrouter_role_transport as ort
from src.polaris_graph.roles.openrouter_role_transport import (
    OpenRouterRoleTransport,
    _parse_retry_after_seconds,
)
from src.polaris_graph.roles.openai_compatible_transport import RoleTransportError
from src.polaris_graph.roles.role_transport import RoleRequest

# Benchmark-stage Judge slug (the effort-ladder reasoning role that takes the per-claim burst).
_JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"

_GOOD_PAYLOAD = {
    "model": _JUDGE_SLUG,
    "provider": "DeepInfra",
    "choices": [{"message": {"role": "assistant", "content": "VERIFIED"}}],
    "usage": {"prompt_tokens": 11, "completion_tokens": 5},
}


@pytest.fixture(autouse=True)
def _transport_env(monkeypatch):
    """Provide the OpenRouter key (LAW VI) and pin SMALL, deterministic rate-limit knobs so the
    bounded-retry assertions are exact. Also no-op `time.sleep` so the backoff never blocks."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    # SMALL retry budget so the always-429 case raises quickly and the POST-count math is clean.
    monkeypatch.setenv("PG_ROLE_HTTP_RETRY_MAX", "2")
    monkeypatch.setenv("PG_ROLE_HTTP_RETRY_STATUS", "429,503")
    # Tiny backoff (defense-in-depth; sleep is also no-op'd below).
    monkeypatch.setenv("PG_ROLE_HTTP_BACKOFF_BASE_SECONDS", "0.01")
    monkeypatch.setenv("PG_ROLE_HTTP_BACKOFF_CAP_SECONDS", "0.05")
    # The Judge is the effort-ladder role; keep its blank-retry behavior out of these tests by
    # only ever returning NON-blank content. No reasoning-effort override needed.
    monkeypatch.delenv("PG_JUDGE_MODEL", raising=False)
    monkeypatch.delenv("PG_FOUR_ROLE_REASONING_EFFORT", raising=False)
    # NO real sleeping — record the delays so the backoff path can be asserted.
    slept: list[float] = []
    monkeypatch.setattr(ort.time, "sleep", lambda s: slept.append(s))
    return slept


def _make_transport(handler) -> OpenRouterRoleTransport:
    """Build the OpenRouter transport with an INJECTED MockTransport client (no network)."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterRoleTransport(client)


def _sequenced_handler(statuses):
    """A MockTransport handler returning a canned response per call from `statuses`.

    Each entry is either an int status (429/503 -> empty-body rate-limited; 200 -> the good
    verdict payload) or a `(status, headers)` tuple. After the list is exhausted the LAST entry
    repeats (so an always-429 list of length 1 stays 429 forever). Records every call.
    """
    seen = {"n": 0, "statuses": []}

    def handler(request: httpx.Request) -> httpx.Response:
        idx = min(seen["n"], len(statuses) - 1)
        entry = statuses[idx]
        seen["n"] += 1
        if isinstance(entry, tuple):
            status, hdrs = entry
        else:
            status, hdrs = entry, {}
        seen["statuses"].append(status)
        if status == 200:
            return httpx.Response(200, json=_GOOD_PAYLOAD)
        # A rate-limited / unavailable response is NEVER JSON-parsed (we retry before the parse),
        # so an empty body is realistic and safe.
        return httpx.Response(status, headers=hdrs, json={})

    return handler, seen


# ----------------------------------------------------------------------------------------------
# (a) 429 -> 200 : the role POST is retried after backoff and SUCCEEDS (retry worked).
# ----------------------------------------------------------------------------------------------
def test_http_429_then_200_recovers(_transport_env):
    slept = _transport_env
    handler, seen = _sequenced_handler([429, 200])
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED", "the 200 verdict after the 429 retry must be returned"
    assert seen["n"] >= 2, "the 429 must have been retried (POST issued >= 2x)"
    assert seen["statuses"][:2] == [429, 200]
    assert len(slept) == 1, "exactly one backoff sleep before the successful retry"
    assert slept[0] > 0.0, "the backoff delay must be a positive sleep"


def test_http_503_then_200_recovers(_transport_env):
    # 503 (transient unavailable) is in the default retryable set alongside 429.
    handler, seen = _sequenced_handler([503, 200])
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert seen["n"] >= 2, "the 503 must have been retried"


# ----------------------------------------------------------------------------------------------
# (b) always-429 : FAIL-CLOSED — RoleTransportError is raised after the bounded retries (HELD).
# ----------------------------------------------------------------------------------------------
def test_http_429_always_fails_closed_after_bounded_retries(_transport_env):
    handler, seen = _sequenced_handler([429])  # length-1 -> repeats 429 forever
    with pytest.raises(RoleTransportError, match="HTTP 429"):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    # PG_ROLE_HTTP_RETRY_MAX=2 -> 1 original POST + 2 bounded retries = 3 POSTs, then HELD.
    assert seen["n"] == 3, "a persistent 429 must raise after exactly RETRY_MAX bounded retries"


def test_http_503_always_fails_closed(_transport_env):
    handler, seen = _sequenced_handler([503])
    with pytest.raises(RoleTransportError, match="HTTP 503"):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    assert seen["n"] == 3, "a persistent 503 fails closed after the bounded retries"


# ----------------------------------------------------------------------------------------------
# (c) a NON-retryable non-200 status is NOT retried — it fails loud IMMEDIATELY (fail-closed,
#     no resilience widening to non-rate-limit errors).
# ----------------------------------------------------------------------------------------------
def test_non_retryable_status_raises_immediately(_transport_env):
    # 400 is NOT in the retryable set -> the existing non-200 raise fires on the first response.
    handler, seen = _sequenced_handler([400, 200])
    with pytest.raises(RoleTransportError, match="HTTP 400"):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    assert seen["n"] == 1, "a non-retryable status must NOT be retried"


# ----------------------------------------------------------------------------------------------
# (d) the `Retry-After` integer-seconds header is honored as the backoff delay — but CLAMPED to
#     PG_ROLE_HTTP_BACKOFF_CAP_SECONDS (Codex iter-1 P1: a hostile/misconfigured header must never
#     make the judge sleep past the cap, which would itself stall the 4-role run).
# ----------------------------------------------------------------------------------------------
def test_retry_after_header_is_honored_within_cap(_transport_env, monkeypatch):
    # Raise the cap above the header value so the 7s Retry-After is honored verbatim — proves the
    # header IS read and preferred over the exponential default.
    monkeypatch.setenv("PG_ROLE_HTTP_BACKOFF_CAP_SECONDS", "30")
    slept = _transport_env
    handler, _seen = _sequenced_handler([(429, {"Retry-After": "7"}), 200])
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert slept == [7.0], "an integer Retry-After within the cap must override the exponential backoff"


def test_retry_after_is_clamped_to_cap(_transport_env):
    # Codex iter-1 P1: a huge server Retry-After must NOT make the judge sleep past backoff_cap
    # (the fixture pins cap=0.05). The header is still honored as the SIGNAL, just clamped.
    slept = _transport_env
    handler, _seen = _sequenced_handler([(429, {"Retry-After": "7200"}), 200])
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert slept == [0.05], "a Retry-After above the cap must clamp to PG_ROLE_HTTP_BACKOFF_CAP_SECONDS"


def test_retry_after_parse_helper():
    # Integer seconds -> float; absent / empty / non-numeric / HTTP-date / negative -> None
    # (the caller then falls back to the capped exponential backoff).
    assert _parse_retry_after_seconds("0") == 0.0
    assert _parse_retry_after_seconds("30") == 30.0
    assert _parse_retry_after_seconds("  5 ") == 5.0
    assert _parse_retry_after_seconds(None) is None
    assert _parse_retry_after_seconds("") is None
    assert _parse_retry_after_seconds("not-a-number") is None
    assert _parse_retry_after_seconds("Wed, 21 Oct 2025 07:28:00 GMT") is None
    assert _parse_retry_after_seconds("-3") is None


# ----------------------------------------------------------------------------------------------
# the rate-limit retry budget is SEPARATE from the transport-fault retry budget.
# ----------------------------------------------------------------------------------------------
def test_rate_limit_budget_separate_from_transport_budget(_transport_env, monkeypatch):
    # PG_ROLE_TRANSPORT_RETRIES=0 (zero transport-fault retries) must NOT shrink the rate-limit
    # budget — a 429 still gets PG_ROLE_HTTP_RETRY_MAX (=2) retries.
    monkeypatch.setenv("PG_ROLE_TRANSPORT_RETRIES", "0")
    handler, seen = _sequenced_handler([429, 429, 200])
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert seen["n"] == 3, "two 429s retried under the SEPARATE rate-limit budget, then 200"
