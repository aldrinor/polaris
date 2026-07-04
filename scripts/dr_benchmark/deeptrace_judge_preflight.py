#!/usr/bin/env python3
"""I-deepfix-001 fix I5 — DeepTRACE benchmark-judge provider/headroom preflight (the measurement gate).

WHY THIS EXISTS (the measurement precondition, closes the Codex iter-2 novel P1)
-------------------------------------------------------------------------------
The DeepTRACE 8-metric scorer (``scripts/dr_benchmark/deeptrace_scorer.py``) needs a binary
Factual-Support Matrix ``S[i][j] = "does listed source j support statement i?"``. That per-(statement,
source) decision is made by a BENCHMARK-SCORER judge locked SEPARATELY from the runtime faithfulness
judge in ``config/benchmark/deeptrace_judge_lock.yaml``. A drb_72-class report makes ~178 statement-
support calls under concurrency, so the locked judge MUST have real OpenRouter provider redundancy — a
low-provider model 429s and the support matrix comes back PARTIAL, which silently produces a WRONG
DeepTRACE number. And a number scored under an UNSIGNED lock is not an operator-authorized measurement.

THIS PREFLIGHT FAILS LOUD (refuses to let any DeepTRACE number be claimed) when ANY of:
  1. the lock is UNSIGNED (``signature.signed`` is not true) — the lock is inert until the operator signs.
  2. the locked benchmark judge has FEWER operational OpenRouter providers than
     ``provider_headroom.min_operational_provider_count`` — the support matrix would return partial.
  3. provider headroom could NOT be measured (no ``OPENROUTER_API_KEY`` / network error) — never a
     silent pass; an unmeasured headroom is a blocker, not an OK.
  4. the comparability policy is missing or not one of the recognized honest paths — a number produced
     under an undeclared comparability policy is not comparable and must not be claimed.

DNA: this is a MEASUREMENT gate + measurement-judge lock, not a pipeline knob. It has NO cap / target /
thinner on the pipeline; it only decides whether a DeepTRACE NUMBER is claimable. Fail-loud, never a
silent fallback (LAW II). Every threshold comes from the operator-signed lock (LAW VI).

BUILD-ONLY / OFFLINE-TESTABLE
-----------------------------
``evaluate_preflight(lock, operational_provider_count)`` is a PURE function over a lock dict + an integer
count (offline, $0, no network) — that is what the unit test exercises RED->GREEN. Only ``--check`` touches
the network (a single GET to OpenRouter ``/models/{slug}/endpoints`` to count operational providers, using
the SAME operational definition as ``scripts/diagnostics/rank_openrouter_providers.py``: ``status == 0``
AND ``uptime_last_30m >= PG_PROVIDER_UPTIME_FLOOR``).

Usage
-----
    # offline: evaluate the lock with a known provider count (e.g. from a prior --check)
    python scripts/dr_benchmark/deeptrace_judge_preflight.py --provider-count 21

    # live: count operational providers for the locked judge, then evaluate (exit 0 clean, 4 == blocked)
    python scripts/dr_benchmark/deeptrace_judge_preflight.py --check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

# The default DeepTRACE benchmark-judge lock path (LAW VI: overridable via --lock).
DEFAULT_LOCK_PATH = "config/benchmark/deeptrace_judge_lock.yaml"

# Operational-endpoint definition, IDENTICAL to scripts/diagnostics/rank_openrouter_providers.py so the
# headroom count matches the routing layer's notion of "healthy". LAW VI: env-overridable floor.
_UPTIME_FLOOR = float(os.getenv("PG_PROVIDER_UPTIME_FLOOR", "98.0"))

# The honest comparability policies the lock may declare (arXiv 2509.04499 measurement discipline).
_VALID_COMPARABILITY_POLICIES = {"paper_judge", "self_rescore"}


@dataclass
class PreflightResult:
    """The outcome of the DeepTRACE benchmark-judge preflight. ``claimable`` is True IFF a DeepTRACE
    number may be claimed (lock signed, provider headroom met + measured, comparability declared)."""

    claimable: bool
    blockers: list[str] = field(default_factory=list)
    signed: bool = False
    model_slug: Optional[str] = None
    min_provider_floor: Optional[int] = None
    operational_provider_count: Optional[int] = None
    comparability_policy: Optional[str] = None


def load_lock(path: str = DEFAULT_LOCK_PATH) -> dict:
    """Load the benchmark-judge lock YAML. Raises FileNotFoundError (fail-loud) if it is missing — a
    DeepTRACE number cannot be claimed without the operator-signed lock present."""
    import yaml  # local import: keep the module import lightweight for the pure path

    with open(path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping, got {type(data).__name__}")
    return data


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def evaluate_preflight(
    lock: Mapping[str, Any],
    operational_provider_count: Optional[int],
) -> PreflightResult:
    """PURE preflight (offline, $0). Decide whether a DeepTRACE number is claimable for the given lock +
    measured operational provider count. ``operational_provider_count is None`` means "could not measure"
    and is itself a blocker (never a silent pass).

    Blockers (fail-loud, LAW II):
      * lock unsigned;
      * comparability policy missing / unrecognized;
      * provider headroom unmeasured (count is None);
      * operational provider count below the lock's ``min_operational_provider_count`` floor.
    """
    blockers: list[str] = []

    signature = lock.get("signature") or {}
    signed = _as_bool(signature.get("signed", False))
    if not signed:
        blockers.append(
            "benchmark-judge lock is UNSIGNED (signature.signed is not true) — the lock is INERT until "
            "an operator signs it; NO DeepTRACE number is claimable. Sign "
            f"{DEFAULT_LOCK_PATH} (signature.signed:true + operator + signed_commit)."
        )

    benchmark_judge = lock.get("benchmark_judge") or {}
    model_slug = benchmark_judge.get("model_slug")
    if not model_slug:
        blockers.append("benchmark_judge.model_slug is empty — the benchmark judge is not declared.")

    comparability = lock.get("comparability") or {}
    policy = comparability.get("policy")
    if policy not in _VALID_COMPARABILITY_POLICIES:
        blockers.append(
            f"comparability.policy={policy!r} is not one of {sorted(_VALID_COMPARABILITY_POLICIES)} — a "
            "DeepTRACE number produced under an undeclared comparability policy is not comparable and "
            "must not be claimed (never mix self_rescore POLARIS numbers with paper-published numbers)."
        )

    headroom = lock.get("provider_headroom") or {}
    try:
        min_floor = int(headroom.get("min_operational_provider_count"))
    except (TypeError, ValueError):
        min_floor = None
    if min_floor is None:
        blockers.append(
            "provider_headroom.min_operational_provider_count is missing/invalid — the headroom floor "
            "is undefined, so headroom cannot be enforced."
        )

    if operational_provider_count is None:
        blockers.append(
            "provider headroom could NOT be measured (no OPENROUTER_API_KEY or a network error on the "
            "/models/{slug}/endpoints probe) — an UNMEASURED headroom is a blocker, never a silent pass. "
            "Run --check with OPENROUTER_API_KEY set."
        )
    elif min_floor is not None and operational_provider_count < min_floor:
        blockers.append(
            f"benchmark judge {model_slug!r} has {operational_provider_count} operational OpenRouter "
            f"provider(s) < the lock floor of {min_floor} — the ~"
            f"{headroom.get('expected_statement_support_calls_per_report', '?')} statement-support "
            "calls/report would 429 and the Factual-Support Matrix would return PARTIAL -> a wrong "
            "DeepTRACE number. Raise headroom (a higher-provider judge) or lower the operator-signed "
            "floor before claiming a number."
        )

    return PreflightResult(
        claimable=not blockers,
        blockers=blockers,
        signed=signed,
        model_slug=model_slug,
        min_provider_floor=min_floor,
        operational_provider_count=operational_provider_count,
        comparability_policy=policy,
    )


def count_operational_providers(model_slug: str, timeout: float = 30.0) -> Optional[int]:
    """Count OpenRouter endpoints for ``model_slug`` that are OPERATIONAL (status == 0 AND
    uptime_last_30m >= PG_PROVIDER_UPTIME_FLOOR). Returns None on any network/auth failure (the caller
    treats None as a fail-loud blocker — never a silent 0-or-pass). Network; only called by --check."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    url = f"https://openrouter.ai/api/v1/models/{model_slug}/endpoints"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read())
    except Exception:  # noqa: BLE001 — any probe failure => unmeasured (None), a fail-loud blocker upstream
        return None
    endpoints = (payload.get("data") or {}).get("endpoints") or []
    operational = 0
    for ep in endpoints:
        up = ep.get("uptime_last_30m")
        if ep.get("status") == 0 and (up is None or up >= _UPTIME_FLOOR):
            operational += 1
    return operational


def _print_result(result: PreflightResult) -> None:
    print("[deeptrace-judge-preflight] benchmark judge:", result.model_slug)
    print(f"[deeptrace-judge-preflight] lock signed: {result.signed}")
    print(
        "[deeptrace-judge-preflight] operational providers:",
        result.operational_provider_count,
        f"(floor {result.min_provider_floor})",
    )
    print("[deeptrace-judge-preflight] comparability policy:", result.comparability_policy)
    if result.claimable:
        print("[deeptrace-judge-preflight] OK — a DeepTRACE number is claimable under this lock.")
    else:
        print("[deeptrace-judge-preflight] BLOCKED — a DeepTRACE number is NOT claimable:")
        for b in result.blockers:
            print(f"  - {b}")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="DeepTRACE benchmark-judge provider/headroom preflight (I5 measurement gate)."
    )
    ap.add_argument("--lock", default=DEFAULT_LOCK_PATH, help="path to the benchmark-judge lock YAML")
    ap.add_argument(
        "--check",
        action="store_true",
        help="LIVE: count operational OpenRouter providers for the locked judge, then evaluate",
    )
    ap.add_argument(
        "--provider-count",
        type=int,
        default=None,
        help="offline: evaluate against a KNOWN operational-provider count (skips the network probe)",
    )
    args = ap.parse_args(argv)

    try:
        lock = load_lock(args.lock)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[deeptrace-judge-preflight] BLOCKED — cannot load lock: {exc}", file=sys.stderr)
        return 4

    count: Optional[int] = args.provider_count
    if args.check:
        model_slug = (lock.get("benchmark_judge") or {}).get("model_slug") or ""
        count = count_operational_providers(model_slug) if model_slug else None

    result = evaluate_preflight(lock, count)
    _print_result(result)
    return 0 if result.claimable else 4


if __name__ == "__main__":
    sys.exit(main())
