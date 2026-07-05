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


def resolve_max_concurrency() -> int:
    """Resolve the configured in-flight side-judge cap from ``PG_SIDE_JUDGE_MAX_CONCURRENCY``.

    Returns the cap ``N >= 1`` when bounded, or ``0`` for UNBOUNDED (the explicit ``"0"`` escape
    hatch). Unset -> ``DEFAULT_MAX_CONCURRENCY``. A negative or malformed value -> ``DEFAULT_MAX_
    CONCURRENCY`` (a typo must not silently disable the de-storm). Never raises (a transport-config
    read must not break the judge)."""
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
def acquire_judge_slot():
    """Admit at most ``resolve_max_concurrency()`` side-judge provider POSTs concurrently.

    Wrap the blocking provider POST in ``with acquire_judge_slot():``. When the cap is ``0``
    (unbounded escape hatch) this is a no-op — byte-identical to the pre-fix path. Otherwise it
    acquires one slot of the shared process-global bounded semaphore for the duration of the POST and
    releases it on EVERY exit path (success, timeout, or exception), so a hung/timed-out call frees
    its slot when its total-deadline force-closes it. TRANSPORT-ONLY: it never touches the verdict."""
    bound = resolve_max_concurrency()
    if bound <= 0:
        yield
        return
    sem = _get_semaphore(bound)
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
