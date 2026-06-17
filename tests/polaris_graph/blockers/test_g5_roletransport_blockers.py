"""#1226 (I-pipe-001) — 4-role D8 medium-blank stall + no watchdog (G5 role-transport blocker).

THE BUG: a reasoning verifier (e.g. GLM-5.1 Mirror under xhigh) can burn its whole token budget on
reasoning and emit EMPTY content. Combined with the per-POST 900s timeout, the COMPOSED retry loop
(effort-ladder / provider-failover x transport-retries x rate-limit-backoff) can stall for HOURS per
claim, so the D8 4-role gate never finishes and the whole sweep hangs.

THE FIX (RELIABILITY, kill-switch default-ON; `PG_ROLE_BLANK_WATCHDOG=0` reverts to byte-identical
control flow), all in `openrouter_role_transport.py`:
  (1) PG_ROLE_BLANK_MAX_RETRIES (default 3): a HARD ceiling on blank-content RETRIES, implemented by
      TRUNCATING the per-call effort/provider ladder to `1 + max_retries` attempts. At the default
      (1+3=4) this is the IDENTITY for every role's default ladder (Judge 3, Mirror/routed-Sentinel
      4, classifier 1, decomposition 3 — all <= 4), so it only bites a custom over-cap ladder.
  (2) PG_ROLE_CALL_TIMEOUT_S (default 3600s): a COOPERATIVE monotonic-clock wall-clock watchdog over
      the WHOLE `complete()` retry loop. Aborts a wedged call LOUDLY (re-raises the existing
      BlankVerdictError if blanking, else RoleTransportError) instead of hanging the gate.

FAITHFULNESS: this is a RELIABILITY/INFRA fix only. It NEVER touches strict_verify, the NLI judge,
the 4-role audit, or any provenance check. On exhaustion it re-raises the EXISTING fail-loud typed
errors -> release stays HELD; no fake/empty verdict is ever synthesized (asserted below).

SPEND-FREE: every test injects `httpx.Client(transport=httpx.MockTransport(...))` — NO socket / NO
real LLM / NO spend. The watchdog-firing test monkeypatches `time.monotonic` (NO real sleeps).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from src.polaris_graph.roles import openrouter_role_transport as ort
from src.polaris_graph.roles import provider_routing
from src.polaris_graph.roles.openai_compatible_transport import (
    BlankVerdictError,
    RoleTransportError,
)
from src.polaris_graph.roles.openrouter_role_transport import OpenRouterRoleTransport
from src.polaris_graph.roles.role_transport import RoleRequest

_MIRROR_SLUG = "z-ai/glm-5.1"
_SENTINEL_SLUG = "minimax/minimax-m2"
_JUDGE_SLUG = "qwen/qwen3.6-35b-a3b"

# DETERMINISTIC routing fixture (the SAME one test_provider_routing.py uses) so the Mirror's
# provider-failover attempt count is `1 + PG_PROVIDER_BLANK_RETRIES` regardless of ambient
# config/settings/openrouter_provider_routing.yaml (which is live-data-dependent). The Mirror is a
# PROVIDER-FAILOVER role: it gets >1 blank attempt ONLY when `role_provider_routing("mirror")` is
# non-None, so the Mirror-count tests below MUST pin routing on (Judge/Sentinel-effort-ladder tests
# do NOT depend on routing — their count is `len(_VERIFIER_EFFORT_LADDER)`).
_ROUTING_FIXTURE = str(
    Path(__file__).resolve().parents[2] / "fixtures" / "openrouter_provider_routing_fixture.yaml"
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Default OpenRouter key + a clean #1226 / lineup env so each test controls the knobs it sets.

    Pins provider routing ON against the DETERMINISTIC fixture (so the Mirror failover path is
    deterministic, not ambient-config-dependent) and resets the routing cache. Clearing the #1226
    knobs means tests that don't set them exercise the DEFAULT-ON behavior (watchdog ON, cap 3,
    timeout 3600s) — the shipping default the separate test phase runs.
    """
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key")
    # Deterministic provider routing (mirror failover -> 1 + PG_PROVIDER_BLANK_RETRIES attempts).
    monkeypatch.setenv("PG_OPENROUTER_PROVIDER_ROUTING", "1")
    monkeypatch.setenv("PG_PROVIDER_ROUTING_CONFIG", _ROUTING_FIXTURE)
    provider_routing.reset_cache()
    for var in (
        "PG_ROLE_BLANK_WATCHDOG",
        "PG_ROLE_BLANK_MAX_RETRIES",
        "PG_ROLE_CALL_TIMEOUT_S",
        "PG_PROVIDER_BLANK_RETRIES",
        "PG_FOUR_ROLE_EFFORT_LADDER",
        "PG_FOUR_ROLE_REASONING_EFFORT",
        "PG_SENTINEL_REASONING",
        "PG_MIRROR_MODEL",
        "PG_SENTINEL_MODEL",
        "PG_JUDGE_MODEL",
        "PG_FOUR_ROLE_TRANSPORT",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    provider_routing.reset_cache()


def _make_transport(handler) -> OpenRouterRoleTransport:
    return OpenRouterRoleTransport(httpx.Client(transport=httpx.MockTransport(handler)))


def _sequenced_handler(responses, *, served_model, provider="DeepInfra"):
    """MockTransport handler returning `responses[i]` for the i-th POST (clamped to the last),
    recording every request body so per-attempt config / attempt-count can be asserted."""
    seen: dict = {"bodies": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["bodies"].append(json.loads(request.content.decode("utf-8")))
        message = responses[min(len(seen["bodies"]) - 1, len(responses) - 1)]
        payload = {
            "model": served_model,
            "provider": provider,
            "choices": [{"message": {"role": "assistant", **message}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 5},
        }
        return httpx.Response(200, json=payload)

    return handler, seen


# ======================================================================= pure helpers (isolated)
def test_watchdog_expired_pure_predicate():
    # strictly-exceeds semantics: equal-to-budget is NOT expired; over-budget IS.
    assert ort._watchdog_expired(100.0, 30.0, 130.0) is False  # exactly at budget
    assert ort._watchdog_expired(100.0, 30.0, 130.001) is True  # just over
    assert ort._watchdog_expired(100.0, 30.0, 100.0) is False  # no time elapsed
    assert ort._watchdog_expired(100.0, 30.0, 1000.0) is True  # far over


def test_role_blank_watchdog_enabled_defaults_on_and_killswitch(monkeypatch):
    # default (unset) -> ON; the documented kill-switch tokens -> OFF; anything else -> ON.
    monkeypatch.delenv("PG_ROLE_BLANK_WATCHDOG", raising=False)
    assert ort.role_blank_watchdog_enabled() is True
    for off in ("0", "false", "False", "no", "off", " 0 "):
        monkeypatch.setenv("PG_ROLE_BLANK_WATCHDOG", off)
        assert ort.role_blank_watchdog_enabled() is False, off
    for on in ("1", "true", "yes", "anything"):
        monkeypatch.setenv("PG_ROLE_BLANK_WATCHDOG", on)
        assert ort.role_blank_watchdog_enabled() is True, on


def test_role_blank_max_retries_default_and_clamp(monkeypatch):
    monkeypatch.delenv("PG_ROLE_BLANK_MAX_RETRIES", raising=False)
    assert ort.role_blank_max_retries() == 3  # default
    monkeypatch.setenv("PG_ROLE_BLANK_MAX_RETRIES", "7")
    assert ort.role_blank_max_retries() == 7
    monkeypatch.setenv("PG_ROLE_BLANK_MAX_RETRIES", "-5")  # negative clamps to 0
    assert ort.role_blank_max_retries() == 0


def test_role_call_timeout_seconds_default_and_clamp(monkeypatch):
    monkeypatch.delenv("PG_ROLE_CALL_TIMEOUT_S", raising=False)
    assert ort.role_call_timeout_seconds() == 3600.0  # generous default
    monkeypatch.setenv("PG_ROLE_CALL_TIMEOUT_S", "120.5")
    assert ort.role_call_timeout_seconds() == 120.5
    monkeypatch.setenv("PG_ROLE_CALL_TIMEOUT_S", "0")  # non-positive -> default (never abort-all)
    assert ort.role_call_timeout_seconds() == 3600.0
    monkeypatch.setenv("PG_ROLE_CALL_TIMEOUT_S", "not-a-number")  # unparseable -> default
    assert ort.role_call_timeout_seconds() == 3600.0


# =================================================== bounded retries succeed (blanks then content)
def test_blanks_then_content_recovers_within_bound():
    """A stubbed transport returning blanks N(<cap) times then content -> bounded retries SUCCEED
    (returns the real verdict, never a fake one). The Judge is the effort-ladder role: blank at
    xhigh -> recover at the 'low' rung."""
    blank = {"content": "", "reasoning": "looped without converging"}
    good = {"content": "VERIFIED"}
    handler, seen = _sequenced_handler([blank, good], served_model=_JUDGE_SLUG)
    resp = _make_transport(handler).complete(
        RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
    )
    assert resp.raw_text == "VERIFIED"
    assert len(seen["bodies"]) == 2, "one blank then content = exactly 2 attempts"


# ====================================================== all-blank -> loud raise (never fake verdict)
def test_all_blank_raises_loud_never_fake_verdict_judge():
    """Every attempt blanks -> the EXISTING fail-loud BlankVerdictError propagates after the ladder.
    No RoleResponse is ever synthesized (release HELD; fail-closed)."""
    blank = {"content": "", "reasoning": "never converges"}
    handler, seen = _sequenced_handler([blank], served_model=_JUDGE_SLUG)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    # default ladder (xhigh, low, off) = 3 attempts <= default cap 4 -> UNCHANGED by truncation.
    assert len(seen["bodies"]) == 3
    # BlankVerdictError is a RoleTransportError subclass -> downstream `except RoleTransportError`
    # still catches it (fail-closed propagation unchanged).
    assert issubclass(BlankVerdictError, RoleTransportError)


# ============================================= flag-OFF == current behavior (counts + types identical)
def test_flag_off_is_identical_judge_all_blank(monkeypatch):
    """PG_ROLE_BLANK_WATCHDOG=0 -> ladder NOT truncated, watchdog NOT checked. Even with a tiny cap
    AND a tiny timeout set, OFF must reproduce the pre-#1226 attempt count (Judge ladder = 3)."""
    monkeypatch.setenv("PG_ROLE_BLANK_WATCHDOG", "0")
    monkeypatch.setenv("PG_ROLE_BLANK_MAX_RETRIES", "0")  # would truncate to 1 attempt IF on
    monkeypatch.setenv("PG_ROLE_CALL_TIMEOUT_S", "0.000001")  # would abort instantly IF on
    blank = {"content": "", "reasoning": "never converges"}
    handler, seen = _sequenced_handler([blank], served_model=_JUDGE_SLUG)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    assert len(seen["bodies"]) == 3, "OFF: full ladder runs, neither cap nor watchdog bites"


def test_flag_off_mirror_provider_failover_count_unchanged(monkeypatch):
    """OFF: the Mirror provider-failover path keeps its (1 + PG_PROVIDER_BLANK_RETRIES) attempts
    even with a tiny cap set — proves the kill-switch fully reverts."""
    monkeypatch.setenv("PG_ROLE_BLANK_WATCHDOG", "0")
    monkeypatch.setenv("PG_ROLE_BLANK_MAX_RETRIES", "0")
    monkeypatch.setenv("PG_PROVIDER_BLANK_RETRIES", "3")  # -> 4 Mirror attempts
    blank = {"content": ""}
    handler, seen = _sequenced_handler([blank], served_model=_MIRROR_SLUG)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="mirror", model_slug=_MIRROR_SLUG, prompt="decide", params={})
        )
    assert len(seen["bodies"]) == 4, "OFF: Mirror keeps 1 + PG_PROVIDER_BLANK_RETRIES = 4 attempts"


def test_flag_on_default_is_identity_mirror(monkeypatch):
    """Flag ON at the DEFAULT cap (3 -> 4 attempts) must NOT change the Mirror's existing all-blank
    count (1 + PG_PROVIDER_BLANK_RETRIES = 4). Default-ON identity guard (the separate test phase
    runs this default; truncating [:4] of a 4-length ladder is the identity)."""
    monkeypatch.delenv("PG_ROLE_BLANK_WATCHDOG", raising=False)  # default ON
    monkeypatch.delenv("PG_ROLE_BLANK_MAX_RETRIES", raising=False)  # default 3 -> cap 4
    monkeypatch.setenv("PG_PROVIDER_BLANK_RETRIES", "3")  # -> 4 Mirror attempts
    blank = {"content": ""}
    handler, seen = _sequenced_handler([blank], served_model=_MIRROR_SLUG)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="mirror", model_slug=_MIRROR_SLUG, prompt="decide", params={})
        )
    assert len(seen["bodies"]) == 4, "default-ON cap 4 == existing Mirror max -> identity"


# ============================================== blank-bound TRUNCATION bites only when over the cap
def test_blank_max_retries_truncates_over_cap_ladder(monkeypatch):
    """Make the cap the BINDING constraint: a high PG_PROVIDER_BLANK_RETRIES (would be 11 attempts)
    truncated by a low PG_ROLE_BLANK_MAX_RETRIES=2 -> exactly 1 + 2 = 3 attempts, then the EXISTING
    fail-loud BlankVerdictError. Proves the hard ceiling actually bounds an over-cap ladder."""
    monkeypatch.setenv("PG_ROLE_BLANK_WATCHDOG", "1")
    monkeypatch.setenv("PG_PROVIDER_BLANK_RETRIES", "10")  # would be 11 Mirror attempts
    monkeypatch.setenv("PG_ROLE_BLANK_MAX_RETRIES", "2")  # cap -> 1 + 2 = 3 attempts
    blank = {"content": ""}
    handler, seen = _sequenced_handler([blank], served_model=_MIRROR_SLUG)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="mirror", model_slug=_MIRROR_SLUG, prompt="decide", params={})
        )
    assert len(seen["bodies"]) == 3, "cap truncates 11 -> 3 attempts (1 + PG_ROLE_BLANK_MAX_RETRIES)"


# ====================================================== wall-clock watchdog fires loudly (no sleeps)
def test_watchdog_aborts_loud_when_wallclock_exceeded(monkeypatch):
    """A wedged-in-retries call: monkeypatch `time.monotonic` so the SECOND check sees the budget
    blown -> the watchdog re-raises the last BlankVerdictError BEFORE entering another POST. No real
    sleep; never a fake verdict. The first attempt blanks (so `last_blank` is set), then the watchdog
    trips at the top of attempt 2."""
    monkeypatch.setenv("PG_ROLE_BLANK_WATCHDOG", "1")
    monkeypatch.setenv("PG_ROLE_CALL_TIMEOUT_S", "100")
    # I-arch-007 (#1264): the POST now runs on a worker thread (the HARD per-POST total-deadline),
    # so the watchdog (main thread) and httpx's elapsed-timer (worker thread) would RACE on a shared
    # fixed-tick iterator and scramble the sequence. Gate the fake clock on POST COUNT instead —
    # thread-safe + deterministic regardless of read count/order: 0 before the first POST records a
    # blank, past-budget (5000s) after. SAME intent (the watchdog passes attempt-1's check, the POST
    # blanks -> last_blank set, then attempt-2's check trips and re-raises the blank before any 2nd POST).
    blank = {"content": "", "reasoning": "looping"}
    handler, seen = _sequenced_handler([blank], served_model=_JUDGE_SLUG)

    def _fake_monotonic():
        return 0.0 if len(seen["bodies"]) < 1 else 5_000.0

    monkeypatch.setattr(ort.time, "monotonic", _fake_monotonic)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    # exactly ONE POST happened: attempt 1 blanked, then the watchdog aborted BEFORE attempt 2's POST.
    assert len(seen["bodies"]) == 1, "watchdog aborts the composed loop before the next POST"


def test_watchdog_off_does_not_abort_even_when_expired(monkeypatch):
    """OFF: even with a 0-ish timeout AND a clock that has 'elapsed', the watchdog never fires, so
    the full ladder runs to its natural fail-loud end (identity guard for the watchdog half)."""
    monkeypatch.setenv("PG_ROLE_BLANK_WATCHDOG", "0")
    monkeypatch.setenv("PG_ROLE_CALL_TIMEOUT_S", "0.0001")
    monkeypatch.setattr(ort.time, "monotonic", lambda: 9_999_999.0)
    blank = {"content": "", "reasoning": "looping"}
    handler, seen = _sequenced_handler([blank], served_model=_JUDGE_SLUG)
    with pytest.raises(BlankVerdictError):
        _make_transport(handler).complete(
            RoleRequest(role="judge", model_slug=_JUDGE_SLUG, prompt="decide")
        )
    assert len(seen["bodies"]) == 3, "OFF: watchdog never aborts; full 3-rung ladder runs"
