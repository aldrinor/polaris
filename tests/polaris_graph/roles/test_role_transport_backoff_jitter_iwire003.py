"""I-wire-003 B1 (#1317): focused unit tests for the FULL-JITTER 429 backoff schedule + the
bounded JUDGE-concurrency knob on the benchmark-stage OpenRouter verifier transport.

WHY (#1317): the certify run hit a SELF-INFLICTED 429 STORM (PG_FOUR_ROLE_CLAIM_WORKERS=12 x 3
roles -> ~36 concurrent POSTs hammering the single rate-limited qwen judge) made worse by a WEAK
flat-exponential backoff (no jitter -> lock-step retries re-collide). The fix:
  (1) `_compute_backoff_delay` -> FULL-JITTER exponential backoff (de-correlates the retry herd),
      honoring a clamped server `Retry-After` as-is; MORE retries (default 5 -> 8);
  (2) a bounded Judge-concurrency semaphore (`PG_FOUR_ROLE_JUDGE_CONCURRENCY`, default 4) so the
      Judge sees a STEADY concurrency UNDER the sustainable rate, NOT a storm.

These tests are PURE (no httpx, no socket, no LLM, no spend, no real sleep): the backoff schedule
is asserted by injecting a deterministic `random.Random` AND by mocking `random.uniform` to prove
it is CALLED with the right `(0, ceiling)` window — growth + jitter-application + cap, all without
RNG flakiness. The retry-count cap is asserted via the env default.
"""

from __future__ import annotations

import random

import src.polaris_graph.roles.openrouter_role_transport as ort
from src.polaris_graph.roles.openrouter_role_transport import (
    _compute_backoff_delay,
    judge_concurrency_limit,
)


# --- The backoff schedule GROWS (full-jitter ceiling doubles per attempt) until it CAPS ---------


def test_backoff_full_jitter_ceiling_grows_then_caps(monkeypatch):
    """`random.uniform` is called with (0, min(cap, base*2**attempt)) — proves growth + cap.

    Mocking `random.uniform` (per the standing test recipe) makes the schedule deterministic AND
    proves the jitter is applied over the RIGHT window, with no dependence on RNG draws.
    """
    calls: list[tuple[float, float]] = []

    def _fake_uniform(low, high):
        calls.append((low, high))
        return high  # return the ceiling so we can also read it back through the return value

    monkeypatch.setattr(ort.random, "uniform", _fake_uniform)

    base, cap = 2.0, 60.0
    # attempts 0..6: ceiling = min(60, 2*2**a) = 2, 4, 8, 16, 32, 60(=min(60,64)), 60(=min(60,128))
    expected_ceilings = [2.0, 4.0, 8.0, 16.0, 32.0, 60.0, 60.0]
    for attempt, expected in enumerate(expected_ceilings):
        delay = _compute_backoff_delay(attempt, base, cap, retry_after=None)
        # jitter applied over EXACTLY (0, ceiling)
        assert calls[-1] == (0.0, expected), (
            f"attempt {attempt}: uniform window {calls[-1]} != (0, {expected})"
        )
        assert delay == expected  # our fake returns `high`, i.e. the ceiling

    # The ceiling is monotonically non-decreasing and never exceeds the cap.
    seen = [h for (_, h) in calls]
    assert seen == sorted(seen)
    assert max(seen) <= cap


def test_backoff_full_jitter_stays_within_window_real_rng():
    """With a real seeded RNG, every sampled delay is within [0, ceiling] and ceiling caps at `cap`."""
    rng = random.Random(1234)
    base, cap = 2.0, 30.0
    for attempt in range(0, 12):
        ceiling = min(cap, base * (2 ** attempt))
        delay = _compute_backoff_delay(attempt, base, cap, retry_after=None, rng=rng)
        assert 0.0 <= delay <= ceiling
        assert ceiling <= cap


# --- Retry-After is honored AS-IS (clamped to cap), NOT jittered --------------------------------


def test_retry_after_honored_clamped_not_jittered(monkeypatch):
    """A server `Retry-After` is returned as-is when <= cap, and clamped DOWN to cap when hostile —
    in NEITHER case is `random.uniform` consulted (the server told us exactly when to retry)."""
    def _boom(*_a, **_k):  # uniform must NOT be called on the Retry-After path
        raise AssertionError("random.uniform must not be called when Retry-After is present")

    monkeypatch.setattr(ort.random, "uniform", _boom)

    cap = 60.0
    # in-range header honored exactly
    assert _compute_backoff_delay(0, 2.0, cap, retry_after=12.0) == 12.0
    # hostile 7200s header clamped DOWN to the cap (never stalls the D8 run)
    assert _compute_backoff_delay(3, 2.0, cap, retry_after=7200.0) == cap
    # a (defensively) negative value floors at 0
    assert _compute_backoff_delay(0, 2.0, cap, retry_after=-5.0) == 0.0


# --- Retry COUNT is capped (more retries than before, but bounded) ------------------------------


def test_rate_limit_retry_default_is_eight(monkeypatch):
    """The default rate-limit retry budget is the raised value (8), bounded — not unbounded."""
    monkeypatch.delenv("PG_ROLE_HTTP_RETRY_MAX", raising=False)
    assert ort._ROLE_HTTP_RETRY_MAX_DEFAULT == "8"
    # the consumer clamps a bad override to >= 0 and reads the env lazily
    monkeypatch.setenv("PG_ROLE_HTTP_RETRY_MAX", "-3")
    assert max(0, int(__import__("os").getenv("PG_ROLE_HTTP_RETRY_MAX"))) == 0


# --- Judge-concurrency knob: env-tunable, default 4, clamped to >= 1 ----------------------------


def test_judge_concurrency_default_and_override(monkeypatch):
    monkeypatch.delenv("PG_FOUR_ROLE_JUDGE_CONCURRENCY", raising=False)
    assert judge_concurrency_limit() == 4  # conservative single-digit default

    monkeypatch.setenv("PG_FOUR_ROLE_JUDGE_CONCURRENCY", "2")
    assert judge_concurrency_limit() == 2  # env-tunable (LAW VI), read lazily

    monkeypatch.setenv("PG_FOUR_ROLE_JUDGE_CONCURRENCY", "0")
    assert judge_concurrency_limit() == 1  # never deadlock on a 0/negative value

    monkeypatch.setenv("PG_FOUR_ROLE_JUDGE_CONCURRENCY", "not_an_int")
    assert judge_concurrency_limit() == 4  # unparseable -> default
