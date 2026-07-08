"""I-deepfix-001 (de-storm) — bounded, env-driven CONCURRENCY cap for the per-claim mirror-chain
side judges (``entailment_judge`` + ``credibility_judge_caller`` + ``semantic_conflict_detector``).

ROOT CAUSE this cures (forensically observed on the 2026-07-04 super-serious deepener preflight,
``/root/deepener_preflight.log``): each of the three side judges fires a BLOCKING glm-5.2 mirror-chain
POST per claim, driven from a BOUNDED-PARALLEL verify / tiering / consolidation pool. But NOTHING
capped how many of those POSTs were in flight AT ONCE. Under the verify burst ~32 entailment POSTs
hit the mirror-chain LEAD host (``friendli``) at essentially the same instant — an account-QPS 429
storm on ONE host ("429 Too Many Requests" x32). The chain alternates (``novita`` / ``z-ai``) were
DNS-degraded on the box at the time ("Temporary failure in name resolution"), so provider rotation
kept landing back on ``friendli``; the per-claim judge then burned its retry budget on ~15-50s
rate-limit backoffs and, on exhaustion, emitted the fail-CLOSED ``('ENTAILED','judge_error: ...')``
sentinel. Consumers DROP that sentinel, so the entailment-requiring layers (the abstract / the
full-verify pass) collapsed to empty while the per-section body — verified earlier in smaller,
time-spread bursts — kept its claims.

The CURE (transport-only, faithfulness-NEUTRAL): cap the number of side-judge provider POSTs that are
IN FLIGHT at once with a process-global bounded semaphore, SHARED across all three judges so the cap
is on TOTAL glm-5.2 mirror QPS (they all hit the SAME ``[friendli, novita, z-ai, phala]`` chain).
Fewer simultaneous POSTs per host -> fewer 429s -> fewer retry-exhaustion fail-closed drops -> MORE
claims verified with the SAME verdicts (a §-1.3 STRENGTHENING — it never relaxes faithfulness). This
composes with the existing ``judge_burst_spread`` round-robin START-host spread: with ``N`` in flight
spread over 4 hosts each host sees ~``N/4`` normally, and ``N`` is the worst-case ceiling if the
alternates are unreachable and every call rotates back to the lead.

It changes ONLY *when* a POST is admitted — never the model, prompt, temperature, ``max_tokens``,
reasoning effort, JSON verdict parsing, provider rotation, or the fail-closed sentinel. A timed-out /
errored member still fails CLOSED exactly as before; this helper can neither manufacture nor flip a
verdict.

LAW VI — env-driven (single knob, ``PG_SIDE_JUDGE_MAX_CONCURRENCY``):
  * unset                       -> ``DEFAULT_MAX_CONCURRENCY`` (the de-storm is ON by default).
  * ``N`` (>= 1)                -> at most ``N`` side-judge POSTs in flight at once.
  * ``0``                       -> UNBOUNDED escape hatch: ``acquire_judge_slot()`` is a no-op
                                   context manager, byte-identical to the pre-fix behavior.
  * negative / malformed        -> ``DEFAULT_MAX_CONCURRENCY`` (a typo must not silently disable the
                                   storm protection — the safe direction).

The bound is resolved at each ``acquire`` (so a test / bakeoff can re-point the env within one
process) and the process-global semaphore is (re)built lazily whenever the resolved bound changes,
guarded by a lock. Stdlib-only leaf module -> zero off-mode import cost.
"""
from __future__ import annotations

import contextlib
import os
import threading

ENV_SIDE_JUDGE_MAX_CONCURRENCY = "PG_SIDE_JUDGE_MAX_CONCURRENCY"

# 4 mirror-chain hosts ([friendli, novita, z-ai, phala]); with burst-spread this is ~1 POST/host
# normally and a worst-case ceiling of 4 on the lead if the alternates are unreachable — comfortably
# below the ~32-simultaneous burst that 429-stormed friendli. Operators can raise this via the env if
# the provider capacity allows (the memory standard is "<= 4 agents in flight").
DEFAULT_MAX_CONCURRENCY = 4

_LOCK = threading.Lock()
_SEMAPHORE: threading.BoundedSemaphore | None = None
_SEMAPHORE_BOUND: int | None = None

# I-deepfix-001 (box2 credibility-pass SPEED fix): a PROCESS-GLOBAL, thread-safe PHASE OVERRIDE. When
# set (> 0) it REPLACES the env-resolved cap for the DURATION of a wrapped phase — used to raise the
# side-judge concurrency ONLY while the advisory credibility pass runs (both its legs: the credibility
# scorer AND the basket-member entailment verify go through ``acquire_judge_slot``), leaving the
# composition-time entailment cap at its protected env value. Default None => no override => the env
# path below is byte-identical. Set/cleared by ``credibility_pass_concurrency`` around the pass; on the
# one-query-per-VM model no two passes overlap in a process.
_OVERRIDE_LOCK = threading.Lock()
_CONCURRENCY_OVERRIDE: int | None = None


class JudgeSlotTimeout(RuntimeError):
    """Raised by ``acquire_judge_slot(timeout=…)`` when a slot is not admitted within the deadline.

    A wedged slot-holder (e.g. the documented GIL/fut.result stall) can no longer freeze the run: an
    ADVISORY caller (the credibility judge) catches this and degrades THAT row to a disclosed
    ``judge_error`` priors fallback. Binding callers that pass no timeout are unaffected (default
    ``None`` == the pre-fix unbounded acquire)."""


def resolve_max_concurrency() -> int:
    """Resolve the configured in-flight side-judge cap.

    Precedence: an active ``credibility_pass_concurrency`` PHASE OVERRIDE (> 0) wins; otherwise the
    env ``PG_SIDE_JUDGE_MAX_CONCURRENCY``. Returns the cap ``N >= 1`` when bounded, or ``0`` for
    UNBOUNDED (the explicit ``"0"`` escape hatch). Unset -> ``DEFAULT_MAX_CONCURRENCY``. A negative or
    malformed value -> ``DEFAULT_MAX_CONCURRENCY`` (a typo must not silently disable the de-storm).
    Never raises (a transport-config read must not break the judge)."""
    with _OVERRIDE_LOCK:
        override = _CONCURRENCY_OVERRIDE
    if override is not None and override > 0:
        return override
    raw = os.environ.get(ENV_SIDE_JUDGE_MAX_CONCURRENCY, "").strip()
    if raw == "":
        return DEFAULT_MAX_CONCURRENCY
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_MAX_CONCURRENCY
    if n == 0:
        return 0  # explicit unbounded escape hatch (byte-identical to the pre-fix behavior)
    if n < 0:
        return DEFAULT_MAX_CONCURRENCY
    return n


@contextlib.contextmanager
def credibility_pass_concurrency(bound: int | None):
    """Temporarily REPLACE the side-judge concurrency cap for the wrapped block (the credibility pass).

    ``bound`` <= 0 / None => no override (byte-identical: the env cap governs). ``bound`` >= 1 raises
    the effective cap to exactly ``bound`` for the DURATION of the block — every ``acquire_judge_slot``
    call on any thread reads it via ``resolve_max_concurrency``. Restores the prior value on EVERY exit
    (success or exception). Faithfulness-neutral: it changes only HOW MANY advisory/entailment POSTs are
    admitted at once during this ONE phase; it never touches the model, prompt, verdict, or gate. Leaves
    the composition-time side-judge cap (the env value) untouched, so the storm protection there holds.
    The (re)built semaphore is swapped atomically per ``_get_semaphore``; in-flight holders release the
    object they acquired, so a mid-flight bound change never corrupts a live acquire."""
    global _CONCURRENCY_OVERRIDE
    try:
        n = int(bound) if bound is not None else 0
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        yield
        return
    with _OVERRIDE_LOCK:
        prev = _CONCURRENCY_OVERRIDE
        _CONCURRENCY_OVERRIDE = n
    try:
        yield
    finally:
        with _OVERRIDE_LOCK:
            _CONCURRENCY_OVERRIDE = prev


def _get_semaphore(bound: int) -> threading.BoundedSemaphore:
    """Return the process-global ``BoundedSemaphore`` for ``bound`` (>= 1), rebuilding it iff the
    resolved bound changed since the last call. In production the bound is constant so the semaphore
    is built exactly once; a test that re-points the env gets a fresh semaphore. In-flight holders
    release the object they acquired, so a rebuild never corrupts a live acquire."""
    global _SEMAPHORE, _SEMAPHORE_BOUND
    with _LOCK:
        if _SEMAPHORE is None or _SEMAPHORE_BOUND != bound:
            _SEMAPHORE = threading.BoundedSemaphore(bound)
            _SEMAPHORE_BOUND = bound
        return _SEMAPHORE


@contextlib.contextmanager
def acquire_judge_slot(timeout: float | None = None):
    """Admit at most ``resolve_max_concurrency()`` side-judge provider POSTs concurrently.

    Wrap the blocking provider POST in ``with acquire_judge_slot():``. When the cap is ``0``
    (unbounded escape hatch) this is a no-op — byte-identical to the pre-fix path. Otherwise it
    acquires one slot of the shared process-global bounded semaphore for the duration of the POST and
    releases it on EVERY exit path (success, timeout, or exception), so a hung/timed-out call frees
    its slot when its total-deadline force-closes it. TRANSPORT-ONLY: it never touches the verdict.

    ``timeout`` (I-deepfix-001 box2 fix): when a positive deadline is supplied and no slot is admitted
    within it, raise ``JudgeSlotTimeout`` BEFORE the POST (nothing acquired => nothing released). This
    is the graceful-degrade path for the ADVISORY credibility judge: a wedged slot-holder can no longer
    strangle the run — the timed-out row falls back to a disclosed ``judge_error`` prior. ``None`` (the
    default, used by every binding caller) keeps the pre-fix UNBOUNDED acquire, byte-identical."""
    bound = resolve_max_concurrency()
    if bound <= 0:
        yield
        return
    sem = _get_semaphore(bound)
    if timeout is not None and timeout > 0:
        if not sem.acquire(timeout=timeout):
            raise JudgeSlotTimeout(
                f"side-judge slot not admitted within {timeout:g}s (cap={bound}) — degrading this "
                "advisory judge call to a disclosed judge_error prior so a wedged slot-holder can "
                "never freeze the run (transport-only; no verdict/gate touched)"
            )
    else:
        sem.acquire()
    try:
        yield
    finally:
        sem.release()


def _reset_for_test() -> None:
    """TEST-ONLY: drop the process-global semaphore so the next ``acquire`` rebuilds it from the
    current env. Not called on any production path."""
    global _SEMAPHORE, _SEMAPHORE_BOUND
    with _LOCK:
        _SEMAPHORE = None
        _SEMAPHORE_BOUND = None
