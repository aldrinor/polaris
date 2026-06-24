"""I-ret-002 (#1294) layer 2 (fetch_crawl) — GATE-0 validity harness (the anti-drb_72 gate).

NO candidate score in this layer is trusted until BOTH canaries below are green:

A) SCORER-MATH CANARY (two-extreme, known input -> known score)
   * A "good" engine body == the gold reference body must score: recovery verdict == gold
     RECOVERED, reference_recall ~= 1.0, recovery_correct == True.
   * A "junk" engine body (a CAPTCHA / Cloudflare shell, an empty string) must score: verdict
     WALLED / FETCH_FAIL (NOT RECOVERED), reference_recall ~= 0.0, recovery_correct == False vs a
     RECOVERED gold row. If the scorer cannot separate these two extremes, the scorer math is
     broken and EVERY downstream number is meaningless -> FAIL LOUD (non-zero exit).

B) PER-ENGINE LIVENESS CANARY (the drb_72 anti-pattern — the HIGHEST-priority check)
   A candidate that returns a stub / empty / load-fail / MISSING-KEY result must FAIL LOUD here,
   never silently score a believable-low number. Concretely:
     * zyte:       assert ZYTE_API_KEY is present AND a PG_ZYTE* knob is configured AND a known
                   fetchable URL returns a real (non-shell, non-empty) body. A keyless Zyte FAILS
                   LOUD (it is NOT allowed to "score low" — a keyless engine that scores 0.1 looks
                   like a bad engine when it is actually a dead one).
     * firecrawl:  assert FIRECRAWL_API_KEY present + a known URL returns a real body, else FAIL LOUD.
     * crawl4ai / playwright: assert the package imports AND a Chromium runtime is present AND a
                   known URL returns a real body, else FAIL LOUD.
   A "stub candidate" (an engine adapter that returns "" / a shell for everything) must be CAUGHT —
   that is the explicit liveness contract the smoke test exercises offline.

MODES:
  * ``--scorer-only``  : run only the scorer-math canary (offline, no engines). Always available.
  * default (live)     : scorer canary + per-engine liveness on the REAL engines (needs keys/VM).
The offline smoke test calls ``run_scorer_canary`` and ``assert_engine_live`` with MOCKED engines.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, Callable

from _polaris_root import ensure_on_syspath

ensure_on_syspath()

from build_fixture import (  # noqa: E402
    FETCH_FAIL,
    RECOVERED,
    WALLED,
    classify_recovery,
)
from run_bakeoff import (  # noqa: E402
    STATUS_NO_KEY,
    STATUS_SCORED,
    EngineSpec,
    engine_availability,
    engine_specs,
    reference_recall,
    score_url,
)


class GateZeroError(RuntimeError):
    """Raised FAIL-LOUD when a GATE-0 canary fails. A run that raises this is INVALID."""


# A known-fetchable canary URL for the liveness probe (a stable, robots-friendly endpoint that a
# healthy fetch engine returns a real body for). LAW VI env-overridable.
_ENV_LIVENESS_URL = "PG_FETCH_LIVENESS_URL"
_DEFAULT_LIVENESS_URL = "https://example.com/"

# Minimum reference-recall the scorer canary's GOOD case must reach (it is the gold body itself, so
# this is ~1.0; we assert well above the junk case). The JUNK case must be at/below the junk ceiling.
_GOOD_RECALL_MIN = 0.95
_JUNK_RECALL_MAX = 0.05

# A representative real CAPTCHA/Cloudflare shell body (the exact run-#7 anchor vocabulary) — must
# classify as WALLED and recall ~0 of a real gold body. Kept verbatim-ish so it exercises the SAME
# shell_detector path production uses.
_JUNK_SHELL_BODY = (
    "Just a moment... This page is displayed while the website verifies you are not a bot. "
    "Please complete the captcha challenge. Checking your browser before accessing. "
    "Cloudflare Ray ID. Performance & Security by Cloudflare."
)

# A representative real main-content gold body (substantive clinical prose) for the GOOD case.
_GOOD_GOLD_BODY = (
    "Deep brain stimulation of the subthalamic nucleus significantly reduced motor symptoms in "
    "patients with advanced Parkinson disease compared with best medical therapy. In this "
    "randomized trial, the stimulation group showed a mean improvement of 41 percent on the "
    "unified Parkinson disease rating scale at six months, with reductions in dyskinesia and "
    "levodopa-equivalent daily dose. Adverse events included transient confusion and dysarthria."
)


# ── A) Scorer-math canary ────────────────────────────────────────────────────────────────

@dataclass
class CanaryResult:
    name: str
    passed: bool
    detail: dict[str, Any]


def _gold_tokens(body: str) -> set[str]:
    from build_fixture import content_tokens

    return set(content_tokens(body))


def run_scorer_canary() -> list[CanaryResult]:
    """Two-extreme scorer-math canary. Returns the per-case results; raises if any FAILS LOUD."""
    results: list[CanaryResult] = []
    gold_tokens = _gold_tokens(_GOOD_GOLD_BODY)

    # CASE 1: good body == gold on a TRUSTWORTHY (gold RECOVERED) row -> RECOVERED, recall ~1.0,
    # recovered True. This is a true main-content recovery.
    good = score_url(_GOOD_GOLD_BODY, RECOVERED, gold_tokens, reference_trustworthy=True)
    good_ok = (
        good["effective_recovery_class"] == RECOVERED
        and good["reference_recall"] >= _GOOD_RECALL_MIN
        and good["recovered"] is True
    )
    results.append(CanaryResult("scorer_good_body_recovered", good_ok, good))
    if not good_ok:
        raise GateZeroError(
            f"GATE-0 scorer canary FAILED (good case): a body identical to the gold reference on a "
            f"trustworthy row must score RECOVERED with recall>={_GOOD_RECALL_MIN} and recovered==True. "
            f"Got {good}. The scorer math is broken — every downstream number is meaningless."
        )

    # CASE 2: junk shell body -> WALLED (a shell, NOT RECOVERED), recall ~0, recovered False. A
    # fetch-shell must NEVER count as a recovery (the drb_72 self-citation hole).
    junk = score_url(_JUNK_SHELL_BODY, RECOVERED, gold_tokens, reference_trustworthy=True)
    junk_ok = (
        junk["effective_recovery_class"] != RECOVERED
        and junk["reference_recall"] <= _JUNK_RECALL_MAX
        and junk["recovered"] is False
    )
    results.append(CanaryResult("scorer_junk_shell_not_recovered", junk_ok, junk))
    if not junk_ok:
        raise GateZeroError(
            f"GATE-0 scorer canary FAILED (junk case): a CAPTCHA/Cloudflare shell must NOT score "
            f"RECOVERED and must recall<={_JUNK_RECALL_MAX} of the gold body. Got {junk}. The "
            f"scorer would reward a fetch-shell as a recovery — the drb_72 self-citation hole."
        )

    # CASE 3: empty body -> FETCH_FAIL, recall 0, recovered False.
    empty = score_url("", RECOVERED, gold_tokens, reference_trustworthy=True)
    empty_ok = (
        empty["effective_recovery_class"] == FETCH_FAIL
        and empty["reference_recall"] == 0.0
        and empty["recovered"] is False
    )
    results.append(CanaryResult("scorer_empty_body_fetch_fail", empty_ok, empty))
    if not empty_ok:
        raise GateZeroError(
            f"GATE-0 scorer canary FAILED (empty case): an empty body must score FETCH_FAIL with "
            f"recall 0.0 and recovered False. Got {empty}."
        )

    # CASE 5 (the §-1.3 anti-inversion canary): an engine that BEATS a wall — returns a full real
    # article on a row the INCUMBENT walled (gold WALLED, NO trustworthy reference) — must be a WIN
    # (recovered True AND wall_broken True), NEVER scored wrong. This is the crown-jewel discriminator
    # (Zyte beating a paywall) and the exact inversion this metric was rebuilt to kill.
    wall_break = score_url(_GOOD_GOLD_BODY, WALLED, _gold_tokens(_JUNK_SHELL_BODY),
                           reference_trustworthy=False)
    wall_break_ok = (
        wall_break["effective_recovery_class"] == RECOVERED
        and wall_break["recovered"] is True
        and wall_break["wall_broken"] is True
        and wall_break["reference_meaningful"] is False
    )
    results.append(CanaryResult("scorer_wall_break_is_a_win_not_wrong", wall_break_ok, wall_break))
    if not wall_break_ok:
        raise GateZeroError(
            "GATE-0 scorer canary FAILED (wall-break case): an engine that recovers a full article "
            "on an incumbent-WALLED row (no trustworthy reference) MUST be a WIN (recovered + "
            f"wall_broken True), never scored wrong against the shell gold. Got {wall_break}. "
            "Scoring this as wrong is the §-1.3 inversion that punishes a valid better source."
        )

    # CASE 4: classify_recovery direction sanity (the rubric the fixture trusts).
    direction_ok = (
        classify_recovery(_GOOD_GOLD_BODY) == RECOVERED
        and classify_recovery(_JUNK_SHELL_BODY) == WALLED
        and classify_recovery("") == FETCH_FAIL
    )
    results.append(CanaryResult("rubric_direction", direction_ok, {
        "good": classify_recovery(_GOOD_GOLD_BODY),
        "junk": classify_recovery(_JUNK_SHELL_BODY),
        "empty": classify_recovery(""),
    }))
    if not direction_ok:
        raise GateZeroError(
            "GATE-0 scorer canary FAILED (rubric direction): classify_recovery must map a real body "
            "-> RECOVERED, a CAPTCHA shell -> WALLED, an empty body -> FETCH_FAIL."
        )
    return results


# ── B) Per-engine liveness canary (the highest-priority drb_72 anti-pattern check) ──────

def _zyte_knobs_present() -> bool:
    """True iff at least one PG_ZYTE* knob is configured (the brief's explicit Zyte liveness clause).

    Zyte being keyless OR un-configured is a dead engine, not a low-quality one — the run is invalid
    until configured. We require the API key (asserted separately) AND a PG_ZYTE* knob so a half-wired
    Zyte (key but no enablement flag) is also caught.
    """
    return any(k.upper().startswith("PG_ZYTE") for k in os.environ)


def assert_engine_live(
    spec: EngineSpec,
    fetch_override: Callable[[str], str] | None = None,
    liveness_url: str | None = None,
) -> CanaryResult:
    """Per-engine liveness: a stub/empty/keyless/load-fail engine FAILS LOUD (never scores low).

    ``fetch_override`` lets the smoke test inject a mocked engine (a real one OR a deliberately
    dead stub) with NO network. For the real VM run, ``fetch_override`` is None and the engine's
    production adapter is used.

    Contract:
      * A no_key engine (e.g. keyless zyte) -> raise GateZeroError (NOT a low score).
      * zyte additionally requires a PG_ZYTE* knob configured.
      * A load_fail / needs_browser engine -> raise GateZeroError.
      * A SCORED engine whose canary fetch returns an empty / shell body -> raise GateZeroError
        (the engine is wired but DEAD — exactly the silent no-op the gate exists to catch).
      * Only a SCORED engine that returns a real, non-shell, content-bearing body PASSES.
    """
    url = liveness_url or os.environ.get(_ENV_LIVENESS_URL, _DEFAULT_LIVENESS_URL)

    # Availability first (keys / package / browser) — unless the smoke injects a fetch (then the
    # smoke is asserting the fetch-result contract, having simulated availability).
    if fetch_override is None:
        status = engine_availability(spec)
        if spec.name == "zyte" and status == STATUS_SCORED and not _zyte_knobs_present():
            raise GateZeroError(
                "GATE-0 liveness FAILED (zyte): ZYTE_API_KEY is set but NO PG_ZYTE* knob is "
                "configured — Zyte is half-wired (a silent no-op without the enablement flag). "
                "Configure PG_ZYTE* on the VM. A keyless/half-wired Zyte must FAIL LOUD, never "
                "score low (the drb_72 anti-pattern)."
            )
        if status != STATUS_SCORED:
            raise GateZeroError(
                f"GATE-0 liveness FAILED ({spec.name}): availability={status} — a "
                f"{status} engine must FAIL LOUD, never be scored as a believable-low candidate. "
                f"{_status_remedy(spec, status)}"
            )
        fetch = _live_adapter(spec.name)
    else:
        fetch = fetch_override

    try:
        body = fetch(url)
    except Exception as exc:  # noqa: BLE001 — a probe exception is a DEAD engine, fail loud.
        raise GateZeroError(
            f"GATE-0 liveness FAILED ({spec.name}): the canary fetch of {url} raised "
            f"{type(exc).__name__}: {exc} — engine is wired but dead."
        ) from exc

    cls = classify_recovery(body)
    recall_proxy = reference_recall(body, _gold_tokens(body))  # self-recall is 1.0 for non-empty
    if not (body or "").strip():
        raise GateZeroError(
            f"GATE-0 liveness FAILED ({spec.name}): the canary fetch of {url} returned an EMPTY "
            f"body. A stub/dead engine must fail loud here, never score a believable-low number."
        )
    if cls in (WALLED, FETCH_FAIL):
        raise GateZeroError(
            f"GATE-0 liveness FAILED ({spec.name}): the canary fetch of {url} returned a "
            f"{cls} body (a shell / dead fetch), not real content. Engine is not live."
        )
    return CanaryResult(
        f"liveness_{spec.name}", True,
        {"url": url, "recovery_class": cls, "self_recall": round(recall_proxy, 3),
         "body_len": len((body or '').strip())},
    )


def _status_remedy(spec: EngineSpec, status: str) -> str:
    if status == STATUS_NO_KEY:
        return f"Set {spec.needs_key_env} on the VM."
    return {
        "load_fail": f"Install {spec.pip_id}.",
        "needs_browser": "Run `playwright install chromium`.",
    }.get(status, "")


def _live_adapter(name: str) -> Callable[[str], str]:
    from run_bakeoff import _FETCH_ADAPTERS

    return _FETCH_ADAPTERS[name]


# ── Driver ───────────────────────────────────────────────────────────────────────────────

def run_gate0(scorer_only: bool = False, engines_to_probe: list[str] | None = None) -> int:
    """Run GATE-0. Returns 0 iff all canaries pass; raises GateZeroError (caught -> exit 2) on fail."""
    print("[gate0] A) scorer-math canary ...")
    for r in run_scorer_canary():
        print(f"  [{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}")
    if scorer_only:
        print("[gate0] scorer-only mode: skipping live per-engine liveness (run on the VM with keys).")
        return 0

    print("[gate0] B) per-engine liveness canary (FAIL LOUD on stub/keyless/dead) ...")
    specs = engine_specs()
    if engines_to_probe:
        specs = [s for s in specs if s.name in set(engines_to_probe)]
    for spec in specs:
        r = assert_engine_live(spec)
        print(f"  [PASS] {r.name}: {r.detail}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fetch_crawl GATE-0 validity harness.")
    parser.add_argument("--scorer-only", action="store_true",
                        help="run only the offline scorer-math canary (no engines)")
    parser.add_argument("--engine", action="append", default=None,
                        help="probe only these engines for liveness (repeatable)")
    args = parser.parse_args(argv)
    try:
        return run_gate0(scorer_only=args.scorer_only, engines_to_probe=args.engine)
    except GateZeroError as exc:
        print(f"[gate0] FAIL LOUD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
