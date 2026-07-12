"""P0 DEADLOCK GUARD (2026-07-12) — refuse the known-deadlocking compose config at STARTUP.

FORENSIC ROOT CAUSE (this wheel's mission; speed_investigation.md FINAL SYNTHESIS): a FULL
328-basket 16-way agentic compose DEADLOCKED — 19/20 threads wedged in ``futex_wait``, 0 progress
for 8.8 min, SIGKILLed. The cause is MULTIPLICATIVE thread oversubscription: ``PG_PARALLEL_SECTIONS``
(3) x ``PG_COMPOSE_BASKET_WORKERS`` (16) x the ~2 inner ThreadPoolExecutors all contend on ONE
process-global side-judge ``BoundedSemaphore``; the binding entailment ``acquire`` has NO timeout and
``with ThreadPoolExecutor`` ``shutdown(wait=True)`` re-hangs on an already-wedged worker. The small
verdict-identity A/B PASSED but did NOT exercise the full-scale semaphore + basket-worker + off-loop
interaction, so the deadlock only appeared at 328-basket scale.

THE GUARD (LAW VI, env-driven; NEVER silently mutates config): the two config dimensions that push the
compose into the un-certified deadlock regime are

  * ``PG_COMPOSE_BASKET_WORKERS`` > 1  — intra-section basket map concurrency, and
  * ``PG_SIDE_JUDGE_MAX_CONCURRENCY`` >= 48 — the global side-judge in-flight ceiling.

Either one, at 328-basket scale, is UN-CERTIFIED: no FULL-328 verdict-identity A/B has proven it both
completes (no hang) AND stays verdict-identical. So ``assert_safe_compose_config()`` REFUSES to start a
compose in that regime by raising ``UnsafeComposeConfigError`` — UNLESS the operator sets the explicit
certification flag ``PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED=1``, which is the CONTRACT that a full-328
verdict-identity A/B has actually been run and passed. The deadlock can therefore never ship again by
accident: shipping it now requires a human to assert, via that env flag, that the A/B was done.

The CONFIRMED-SAFE config (the clean 24.2 min / 1449.7 s run used it): off-loop ON,
``PG_COMPOSE_BASKET_WORKERS``=1 (serial byte-identical MAP+REDUCE), ``PG_SIDE_JUDGE_MAX_CONCURRENCY`` in
the 4-8 band, ``PG_PARALLEL_SECTIONS``=3 — faithfulness PASS, agentic held, no hang. That config sails
through this guard untouched (workers==1, sem<48). The guard changes NOTHING about a safe run; it only
fails-fast a KNOWN-BAD one before it can wedge the box.

Stdlib-only leaf module -> zero import cost on the safe path.
"""
from __future__ import annotations

import os

# The un-certified deadlock thresholds (see module docstring for the forensic derivation).
DEADLOCK_BASKET_WORKERS_MIN = 2        # PG_COMPOSE_BASKET_WORKERS > 1 (i.e. >= 2) is un-certified.
DEADLOCK_SIDE_JUDGE_SEM_MIN = 48       # PG_SIDE_JUDGE_MAX_CONCURRENCY >= 48 is un-certified.

ENV_BASKET_WORKERS = "PG_COMPOSE_BASKET_WORKERS"
ENV_SIDE_JUDGE_SEM = "PG_SIDE_JUDGE_MAX_CONCURRENCY"
# The ONE escape hatch: an operator sets this to attest that a FULL-328 verdict-identity A/B was run
# AND passed (both no-hang AND verdict-identical). Without it the deadlock config is refused.
ENV_AB_CERTIFIED = "PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED"

_TRUE = ("1", "true", "yes", "on")


class UnsafeComposeConfigError(RuntimeError):
    """Raised at compose startup when a KNOWN-DEADLOCKING config is requested without A/B certification.

    Fail-CLOSED by design: a compose must never begin in the multiplicative-oversubscription regime
    that wedged the box, unless a human has explicitly attested (via ``PG_COMPOSE_DEADLOCK_CONFIG_
    AB_CERTIFIED=1``) that a full-328 verdict-identity A/B certified it both completes and stays
    verdict-identical."""


def _int_env(env: "dict[str, str] | os._Environ[str]", name: str, default: int) -> int:
    """Read ``name`` as an int from ``env``; on unset/blank/malformed return ``default`` (fail to the
    SAFE reading — a typo must never silently DISABLE the guard by parsing as a huge/zero value)."""
    raw = str(env.get(name, "")).strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def evaluate_compose_config(env=None) -> "tuple[bool, list[str], bool]":
    """Pure evaluation (no raise) of the compose config safety.

    Returns ``(is_safe, violations, certified)`` where ``violations`` names each un-certified
    deadlock dimension that is active. ``is_safe`` is True iff there are NO violations OR the operator
    set the A/B certification flag. Pure/side-effect-free so tests and telemetry can call it freely."""
    env = os.environ if env is None else env
    certified = str(env.get(ENV_AB_CERTIFIED, "")).strip().lower() in _TRUE
    # Basket workers default 1 (serial); side-judge sem default 4 (judge_concurrency.DEFAULT_MAX_CONCURRENCY).
    workers = _int_env(env, ENV_BASKET_WORKERS, 1)
    sem = _int_env(env, ENV_SIDE_JUDGE_SEM, 4)
    violations: list[str] = []
    if workers >= DEADLOCK_BASKET_WORKERS_MIN:
        violations.append(
            f"{ENV_BASKET_WORKERS}={workers} (>1: intra-section basket concurrency — un-certified "
            f"at 328-basket scale; DEADLOCKED 19/20 threads in futex_wait)"
        )
    if sem >= DEADLOCK_SIDE_JUDGE_SEM_MIN:
        violations.append(
            f"{ENV_SIDE_JUDGE_SEM}={sem} (>={DEADLOCK_SIDE_JUDGE_SEM_MIN}: global side-judge "
            f"in-flight ceiling — un-certified; the binding entailment acquire has NO timeout)"
        )
    is_safe = (not violations) or certified
    return is_safe, violations, certified


def assert_safe_compose_config(env=None) -> None:
    """STARTUP GUARD: refuse a known-deadlocking compose config unless A/B-certified.

    Call ONCE at the top of every compose entry point. Raises ``UnsafeComposeConfigError`` iff a
    deadlock dimension is active (``PG_COMPOSE_BASKET_WORKERS``>1 or ``PG_SIDE_JUDGE_MAX_CONCURRENCY``
    >=48) AND ``PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED`` is not set. A SAFE config (the default, and
    the confirmed 24.2 min clean run) is a no-op. When certified, it does NOT raise but the caller may
    log the attestation."""
    is_safe, violations, certified = evaluate_compose_config(env)
    if is_safe:
        return
    raise UnsafeComposeConfigError(
        "REFUSING to start compose in a KNOWN-DEADLOCKING config (this wheel's mission: the FULL "
        "328-basket 16-way compose wedged 19/20 threads in futex_wait and was SIGKILLed). "
        "Un-certified deadlock dimension(s): "
        + "; ".join(violations)
        + f". To ship this config you MUST first run a FULL-328 verdict-identity A/B proving it "
        f"BOTH completes (no hang) AND stays verdict-identical, then set {ENV_AB_CERTIFIED}=1 to "
        "attest it. The CONFIRMED-SAFE config is PG_COMPOSE_BASKET_WORKERS=1 + "
        "PG_SIDE_JUDGE_MAX_CONCURRENCY in 4-8 + PG_PARALLEL_SECTIONS=3 (off-loop ON)."
    )
