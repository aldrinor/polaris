"""I-wire-007 (#1321) — ADAPTIVE AIMD concurrency controller for the 4-role D8 verifier transport.

THE PROBLEM (I-wire-006 #1320 root cause): the 4-role D8 verify settles only a trickle of claims
because the per-role concurrency is a FIXED static cap (`PG_FOUR_ROLE_JUDGE_CONCURRENCY=4`,
`PG_FOUR_ROLE_CLAIM_WORKERS=6`). A fixed cap cannot ride the live OpenRouter ceiling: too LOW and
the run is needlessly slow; too HIGH and it triggers a 429 storm (judge / qwen) or floods the slow
minimax host (sentinel) into the trickle-200 that the per-call deadline then force-closes. The
bottleneck is provider-chain throughput, NOT the verdict logic.

THE FIX — TCP-congestion AIMD (Additive-Increase / Multiplicative-Decrease). The exact, decades-proven
algorithm a TCP sender uses to find and ride a link's capacity without a known bandwidth: probe UP
slowly (add 1 to the in-flight limit after a clean window), back DOWN hard (halve) the instant a
congestion signal (a 429 / a force-close timeout) appears. It AUTO-FINDS the ceiling and stays just
under it, adapting as the provider's capacity shifts mid-run. Bounded to [min, max] so it can never
collapse to zero or run away.

FAITHFULNESS IS FROZEN (I-faith-001 C0). This controller is the THROUGHPUT/transport layer ONLY: it
governs ONLY HOW MANY role POSTs run concurrently, never which claim passes / holds. A slow / dropped
/ timed-out claim still hits the SAME fail-closed `RoleTransportError` -> the 4-role gate HOLDS /
UNGROUNDED. `_compose_final_verdict`, the Sentinel downgrade ladder, and the entailment decision are
UNTOUCHED. Lowering the in-flight limit only DELAYS work; it never changes a verdict.

PER-ROLE, not global (I-wire-006 review): a 429 is the qwen JUDGE rate limit; a force-close is the
minimax SENTINEL slow-host timeout. A single global controller would let a sentinel force-close
spuriously throttle the judge (and vice-versa). Each role gets its OWN controller fed by its OWN
signal.

LAW VI: every knob is env-driven (named, no magic numbers), read at construction. Default ON, but a
disabled controller (or OFF via `PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY=0`) is byte-equivalent to the
prior static `threading.BoundedSemaphore` cap so the OFF path can never start worse than baseline.
"""

from __future__ import annotations

# Standard library
import os
import threading


# === LAW VI: env knob names (no magic numbers; documented defaults) ============================
_ENABLE_ENV = "PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY"
_ENABLE_DEFAULT = "1"  # default ON (concurrency-only; OFF is byte-identical to the static cap).

# Per-role knob SUFFIXES; the resolved env var is f"PG_FOUR_ROLE_ADAPTIVE_{ROLE}_{SUFFIX}".
# A role-specific override ALWAYS wins; otherwise the generic PG_FOUR_ROLE_ADAPTIVE_<SUFFIX> is read;
# otherwise the coded default below. The defaults are deliberately conservative — the MIN equals the
# proven static baseline so an adaptive run can never begin below the cap it replaces.
_MIN_SUFFIX = "MIN"
_MAX_SUFFIX = "MAX"
_STEP_SUFFIX = "STEP"
_BACKOFF_SUFFIX = "BACKOFF"
_PROBE_WINDOW_SUFFIX = "PROBE_WINDOW"

# Coded per-role defaults. MIN == the historical static cap for that role (judge 4, sentinel was
# unbounded -> a conservative 4 floor when adaptive is ON), MAX rides the ceiling, STEP=1 (additive
# +1 per clean window), BACKOFF=0.5 (halve on a congestion signal), PROBE_WINDOW=8 (clean successes
# before one additive step — long enough that a single lucky call does not ramp into a storm).
_ROLE_DEFAULTS: dict[str, dict[str, str]] = {
    "judge": {
        _MIN_SUFFIX: "4",      # == PG_FOUR_ROLE_JUDGE_CONCURRENCY historical default.
        _MAX_SUFFIX: "16",
        _STEP_SUFFIX: "1",
        _BACKOFF_SUFFIX: "0.5",
        _PROBE_WINDOW_SUFFIX: "8",
    },
    "sentinel": {
        _MIN_SUFFIX: "4",      # sentinel was unbounded; a small adaptive floor rides up from here.
        _MAX_SUFFIX: "12",
        _STEP_SUFFIX: "1",
        _BACKOFF_SUFFIX: "0.5",
        _PROBE_WINDOW_SUFFIX: "8",
    },
}


def adaptive_concurrency_enabled() -> bool:
    """Whether the AIMD controller governs per-role concurrency (default ON).

    OFF (`0`/`false`/`no`/`off`) reverts every role to its prior STATIC `BoundedSemaphore` cap —
    byte-equivalent to pre-#1321. Read at controller-construction time.
    """
    return os.getenv(_ENABLE_ENV, _ENABLE_DEFAULT).strip().lower() not in ("0", "false", "no", "off")


def _resolve_int(role: str, suffix: str) -> int:
    """Resolve a per-role integer knob: role-specific env > generic env > coded default. Min 1."""
    role_env = f"PG_FOUR_ROLE_ADAPTIVE_{role.upper()}_{suffix}"
    generic_env = f"PG_FOUR_ROLE_ADAPTIVE_{suffix}"
    default = _ROLE_DEFAULTS.get(role, {}).get(suffix, "1")
    raw = os.getenv(role_env) or os.getenv(generic_env) or default
    try:
        return max(1, int(raw))
    except (TypeError, ValueError):
        return max(1, int(default))


def _resolve_float(role: str, suffix: str) -> float:
    """Resolve a per-role float knob (the BACKOFF multiplier): role-specific > generic > default."""
    role_env = f"PG_FOUR_ROLE_ADAPTIVE_{role.upper()}_{suffix}"
    generic_env = f"PG_FOUR_ROLE_ADAPTIVE_{suffix}"
    default = _ROLE_DEFAULTS.get(role, {}).get(suffix, "0.5")
    raw = os.getenv(role_env) or os.getenv(generic_env) or default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = float(default)
    # Clamp into (0, 1): a multiplicative DECREASE must shrink (>=1 would never back off) and stay
    # above 0 (0 would collapse the window to the floor in one hit, defeating the gentle AIMD ride).
    if not (0.0 < value < 1.0):
        value = float(default)
    return value


class AdaptiveConcurrencyController:
    """A thread-safe DYNAMIC-limit concurrency gate driven by TCP-congestion AIMD.

    Unlike `threading.BoundedSemaphore` (which CANNOT change size mid-run — the documented reason the
    static judge/sentinel semaphores only ever loosen), this gate's limit both GROWS and SHRINKS at
    runtime under a single `threading.Condition`:

      * `acquire()` blocks while `in_flight >= limit`, then increments `in_flight`.
      * `release()` decrements `in_flight` and notifies one waiter.
      * `on_success()` / `on_throttle()` / `on_timeout()` mutate `limit` per the AIMD rules and
        notify waiters when the limit grows (so a blocked acquirer can proceed immediately).

    The AIMD math (`on_*`) is PURE w.r.t. the lock-protected `_limit` / `_clean_streak` state and is
    unit-tested directly (no threads, no network): additive +`step` after `probe_window` clean
    successes, multiplicative *`backoff` on a throttle/timeout, clamped to `[min_limit, max_limit]`.

    FAITHFULNESS-NEUTRAL: governs ONLY concurrency. A throttled limit delays work; it never changes a
    verdict. The role transport's existing fail-closed `RoleTransportError` path is untouched.
    """

    def __init__(
        self,
        *,
        min_limit: int,
        max_limit: int,
        step: int = 1,
        backoff: float = 0.5,
        probe_window: int = 8,
        start_limit: int | None = None,
    ) -> None:
        min_limit = max(1, int(min_limit))
        max_limit = max(min_limit, int(max_limit))
        self._min_limit = min_limit
        self._max_limit = max_limit
        self._step = max(1, int(step))
        # backoff clamped into (0,1): a decrease must shrink and never reach 0.
        self._backoff = backoff if 0.0 < backoff < 1.0 else 0.5
        self._probe_window = max(1, int(probe_window))
        # Start at the FLOOR (TCP slow-start analogue): probe UP from the known-safe min, never
        # begin at the max and provoke an immediate storm.
        start = self._min_limit if start_limit is None else int(start_limit)
        self._limit = min(self._max_limit, max(self._min_limit, start))
        self._in_flight = 0
        self._clean_streak = 0
        self._cond = threading.Condition()

    # --- the gate ---------------------------------------------------------------------------------
    def acquire(self) -> None:
        """Block until an in-flight slot is free under the CURRENT (possibly shrunk) limit, then take it."""
        with self._cond:
            while self._in_flight >= self._limit:
                self._cond.wait()
            self._in_flight += 1

    def release(self) -> None:
        """Free this caller's in-flight slot and wake one waiter."""
        with self._cond:
            if self._in_flight > 0:
                self._in_flight -= 1
            self._cond.notify()

    # --- AIMD signals (pure math under the lock; unit-tested directly) ----------------------------
    def on_success(self) -> None:
        """Additive-increase: after `probe_window` consecutive clean successes, raise the limit by
        `step` (clamped to `max_limit`) and wake waiters so the new headroom is used immediately."""
        with self._cond:
            self._clean_streak += 1
            if self._clean_streak >= self._probe_window and self._limit < self._max_limit:
                self._limit = min(self._max_limit, self._limit + self._step)
                self._clean_streak = 0
                self._cond.notify_all()

    def on_throttle(self) -> None:
        """Multiplicative-decrease on a 429/503 (rate-limit) signal: halve the limit (clamped to
        `min_limit`) and reset the clean streak. The shrink takes effect on the NEXT acquire (an
        in-flight overage drains naturally as slots release — never an over-release of the gate)."""
        self._multiplicative_decrease()

    def on_timeout(self) -> None:
        """Multiplicative-decrease on a force-close / total-deadline timeout (a congestion signal for
        the slow-host sentinel leg) — identical AIMD back-off to `on_throttle`."""
        self._multiplicative_decrease()

    def _multiplicative_decrease(self) -> None:
        with self._cond:
            self._limit = max(self._min_limit, int(self._limit * self._backoff))
            self._clean_streak = 0
            # No notify: the limit only SHRANK, so no blocked acquirer can newly proceed.

    # --- introspection (telemetry / tests; never gates) -------------------------------------------
    @property
    def limit(self) -> int:
        with self._cond:
            return self._limit

    @property
    def in_flight(self) -> int:
        with self._cond:
            return self._in_flight

    @property
    def bounds(self) -> tuple[int, int]:
        return (self._min_limit, self._max_limit)


def build_role_controller(role: str) -> AdaptiveConcurrencyController:
    """Construct the AIMD controller for `role` from its env-resolved knobs (LAW VI).

    The MIN floor equals the role's proven static cap, so an adaptive run can never start below the
    baseline it replaces. Read at construction; the transport builds one controller per role lazily.
    """
    min_limit = _resolve_int(role, _MIN_SUFFIX)
    max_limit = _resolve_int(role, _MAX_SUFFIX)
    step = _resolve_int(role, _STEP_SUFFIX)
    backoff = _resolve_float(role, _BACKOFF_SUFFIX)
    probe_window = _resolve_int(role, _PROBE_WINDOW_SUFFIX)
    return AdaptiveConcurrencyController(
        min_limit=min_limit,
        max_limit=max_limit,
        step=step,
        backoff=backoff,
        probe_window=probe_window,
    )
