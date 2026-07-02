"""I-deepfix-001 (KEYSTONE de-storm) — round-robin BURST-SPREAD start index for the per-claim
mirror-chain judge callers (``entailment_judge`` + ``credibility_judge_caller``).

ROOT CAUSE this cures: both judges pin ONE mirror-chain host (``order=[chain[0]]``,
``allow_fallbacks=False``). Under the credibility pass's 20-way concurrency the old cursor-0 start
POSTed EVERY in-flight member to the SAME chain-lead host simultaneously -> an account-QPS 429 storm
on ONE host -> the pass blows its wall -> ``credibility_analysis=None`` (empty conclusion + W5
tiering starvation). This helper spreads the START host round-robin across the chain so
~``inflight / len(chain)`` members land on each host; a faulted call still walks the FULL ring
(wraparound) from wherever it started, so it can reach every healthy host before failing closed.

TRANSPORT-ONLY, faithfulness-NEUTRAL. This picks WHICH healthy host answers; it NEVER changes the
glm-5.2 model, the prompt, temperature 0.0, max_tokens/reasoning effort, the JSON verdict parsing, or
the fail-closed sentinel. A timed-out / errored member still fails CLOSED (UNSUPPORTED) — it is
NEVER fake-stamped SUPPORTS. Same glm-5.2 model on every chain host (operator pre-approved judge-host
non-sovereignty 2026-06-13), so the verdict the answering host returns is the real verdict.

LAW VI — env-gated, DEFAULT-ON, byte-identical OFF:
  * ``PG_JUDGE_BURST_SPREAD`` unset / ``1`` / ``true`` / ``on`` / ``spread`` -> "spread" (DEFAULT).
  * ``PG_JUDGE_BURST_SPREAD=0`` / ``false`` / ``no`` / ``off`` -> "off": cursor 0 + no-wrap ring stop
    == the pre-fix single-lead pin (byte-identical to the I-arch-011 rotation semantics).
  * ``PG_JUDGE_BURST_SPREAD=lb`` -> "lb": the documented D8-Judge cure — drop the single-host
    ``order`` and let OpenRouter LOAD-BALANCE the burst across all glm-5.2 endpoints. Opt-in fallback
    if round-robin start proves insufficient on the real snapshot; NOT the default.
"""
from __future__ import annotations

import itertools
import os
import threading

ENV_JUDGE_BURST_SPREAD = "PG_JUDGE_BURST_SPREAD"

# Process-global round-robin counter shared by BOTH judge callers so the two bursts spread over the
# SAME chain in a coordinated way. Guarded by a lock so concurrent verify-workers draw DISTINCT
# consecutive integers (no lost increment -> a balanced spread). RISK-4 (benign): a multi-query
# process shares this counter — it still spreads; under one-query-per-VM it is moot.
_BURST_START = itertools.count()
_BURST_LOCK = threading.Lock()


def burst_spread_mode() -> str:
    """Resolve the burst-spread mode from ``PG_JUDGE_BURST_SPREAD``.

    Returns one of ``"spread"`` (DEFAULT — round-robin start index), ``"off"`` (byte-identical
    single-lead pin), or ``"lb"`` (load-balance alternative). An unrecognized value defaults to
    ``"spread"`` (the de-storm stays ACTIVE — the safe direction)."""
    raw = os.environ.get(ENV_JUDGE_BURST_SPREAD, "").strip().lower()
    if raw in ("0", "false", "no", "off"):
        return "off"
    if raw == "lb":
        return "lb"
    return "spread"


def next_burst_start_index(chain_len: int) -> int:
    """Return the next round-robin START index in ``[0, chain_len)``.

    Thread-safe: a lock guards the shared counter so concurrent verify-workers get DISTINCT
    consecutive integers, giving a balanced spread across the chain hosts. ``chain_len <= 1`` returns
    ``0`` (a single/empty chain has nothing to spread across)."""
    if chain_len <= 1:
        return 0
    with _BURST_LOCK:
        return next(_BURST_START) % chain_len


def _reset_burst_start(start: int = 0) -> None:
    """TEST-ONLY: reset the process-global round-robin counter to a known state so a test can assert a
    deterministic START host. Not called on any production path."""
    global _BURST_START  # noqa: PLW0603 — deliberate test hook for the shared counter
    with _BURST_LOCK:
        _BURST_START = itertools.count(start)
