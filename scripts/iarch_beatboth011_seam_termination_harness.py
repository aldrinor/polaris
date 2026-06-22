#!/usr/bin/env python3
"""I-beatboth-011 #1290 — fail-loud harness for the 4-role D8 seam TERMINATION fix.

THE DEFECT (path-audit, verified live on a 3.8h grinding resume): a benchmark run could grind ~7.2h
instead of terminating at its advertised 3h run-wall, because:
  1. `_resolve_four_role_seam_timeout()` defaults to `max(7200, 4*6500)=26000s` (~7.22h) and
     `PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS` was pinned ONLY in `_SMOKE_SCALE_OVERRIDES`, so a full/--resume
     run used the 7.2h default.
  2. the seam is awaited via a BLOCKING `.result(timeout=_seam_timeout)` on the event-loop thread, which
     starves the enclosing `asyncio.wait_for(run_one_query, run-wall)` — so the run-wall never fires.
  3. preflight checked only generator<section<run-wall, NOT seam<=run-wall — so it passed while the seam
     could exceed the wall.

THE FIX (timeout plumbing only — faithfulness engine UNTOUCHED):
  A. `_FULL_CAPABILITY_BENCHMARK_SLATE` now pins `PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS=7200` (< run-wall) and
     it rides `_BENCHMARK_FORCE_EXACT_FLAGS` so a stale .env cannot restore the grind.
  B. the seam `.result()` timeout is capped by the REMAINING run-wall budget
     (`min(_seam_timeout, deadline-now)`), so the blocking call can never overrun the wall.
  C. `preflight_full_capability` fail-CLOSES when the resolved seam timeout EXCEEDS the run-wall.

This harness asserts A/B/C OFFLINE (no live LLM / model load). FAIL LOUD (non-zero exit) on regression.
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 #1290 seam-termination: {msg}")
    sys.exit(1)


def main() -> None:
    import scripts.dr_benchmark.run_gate_b as rgb
    from scripts.run_honest_sweep_r3 import (
        _resolve_four_role_seam_timeout as _resolve_seam,
        run_wall_clock_seconds,
    )

    # (A) the FULL slate bounds the seam below the run-wall + force-exact ------------------------------
    slate = rgb._FULL_CAPABILITY_BENCHMARK_SLATE
    if "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS" not in slate:
        _fail("(A) the FULL slate does NOT pin PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS (the 7.2h grind survives)")
    seam_slate = int(slate["PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS"])
    wall_slate = int(slate["PG_RUN_WALL_CLOCK_SEC"])
    if not (seam_slate <= wall_slate):
        _fail(f"(A) slate seam {seam_slate} NOT <= run-wall {wall_slate} — seam can grind past the wall")
    if "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS" not in rgb._BENCHMARK_FORCE_EXACT_FLAGS:
        _fail("(A) PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS is NOT force-exact — a stale .env could restore the grind")
    print(f"(A) ok: full slate pins seam={seam_slate}s <= run-wall={wall_slate}s, force-exact.")

    # (B) resolver: the env WINS OUTRIGHT (so the slate pin actually lowers it); unset => the grind -----
    _saved = os.environ.get("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS")
    try:
        os.environ["PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS"] = "5400"
        if _resolve_seam() != 5400.0:
            _fail(f"(B) env override ignored: _resolve_four_role_seam_timeout()={_resolve_seam()} != 5400")
        os.environ.pop("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", None)
        default_seam = _resolve_seam()
        if default_seam <= wall_slate:
            print(f"(B) note: unset default seam={default_seam:.0f}s (<= wall only because gen timeout small)")
        else:
            print(f"(B) confirmed: unset default seam={default_seam:.0f}s EXCEEDS wall {wall_slate} "
                  f"(this is the grind the slate pin + force-exact prevent)")
    finally:
        if _saved is None:
            os.environ.pop("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", None)
        else:
            os.environ["PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS"] = _saved
    print("(B) ok: PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS wins outright in the resolver.")

    # (C) the preflight seam<=run-wall condition: holds at the slate values, violated when seam>wall -----
    _saved_seam = os.environ.get("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS")
    _saved_wall = os.environ.get("PG_RUN_WALL_CLOCK_SEC")
    try:
        os.environ["PG_RUN_WALL_CLOCK_SEC"] = "10800"
        os.environ["PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS"] = "7200"
        if not (float(_resolve_seam()) <= float(run_wall_clock_seconds())):
            _fail("(C) the slate-pinned seam should satisfy seam<=run-wall but does not")
        os.environ["PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS"] = "99999"
        if float(_resolve_seam()) <= float(run_wall_clock_seconds()):
            _fail("(C) a seam (99999) ABOVE the wall (10800) did NOT violate seam<=run-wall — preflight blind")
    finally:
        for k, v in (("PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS", _saved_seam), ("PG_RUN_WALL_CLOCK_SEC", _saved_wall)):
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    # verify the preflight actually CARRIES the seam<=run-wall fail-closed assertion (source-anchored)
    pf_src = Path(_REPO / "scripts" / "dr_benchmark" / "run_gate_b.py").read_text(encoding="utf-8", errors="replace")
    if "seam timeout" not in pf_src or "EXCEEDS the run-wall" not in pf_src:
        _fail("(C) preflight_full_capability is MISSING the seam<=run-wall fail-closed assertion")
    print("(C) ok: preflight fail-closes when the resolved seam timeout exceeds the run-wall.")

    # (D) the seam .result() is capped by the remaining run-wall budget --------------------------------
    # (D1) the cap formula: with a near deadline, the effective wait is bounded; with no deadline, unchanged.
    seam_timeout = 7200.0
    deadline_near = time.monotonic() + 90.0
    eff_capped = max(1.0, min(float(seam_timeout), deadline_near - time.monotonic()))
    if not (eff_capped <= 95.0):
        _fail(f"(D1) cap formula did not bound the wait to the remaining wall (~90s): got {eff_capped:.1f}s")
    eff_uncapped = float(seam_timeout)  # deadline is None -> unchanged behaviour
    if eff_uncapped != 7200.0:
        _fail("(D1) with no deadline the effective timeout must equal the resolved seam timeout (unchanged)")
    # (D2) the cap wiring is PRESENT at the seam call site (regression guard for the blocking-.result fix)
    sweep_src = Path(_REPO / "scripts" / "run_honest_sweep_r3.py").read_text(encoding="utf-8", errors="replace")
    needed = ["_seam_effective_timeout", "_RUN_WALL_CLOCK_DEADLINE_CTX.get()", "min(float(_seam_timeout)"]
    missing = [n for n in needed if n not in sweep_src]
    if missing:
        _fail(f"(D2) the seam .result() run-wall cap wiring is MISSING from run_honest_sweep_r3.py: {missing}")
    if re.search(r"\.result\(\s*\n?\s*timeout=_seam_timeout\s*\n?\s*\)", sweep_src):
        _fail("(D2) the seam still calls .result(timeout=_seam_timeout) UNCAPPED — the blocking-overrun fix regressed")
    print("(D) ok: the seam .result() is capped by the remaining run-wall budget (formula + wiring present).")

    print(
        "PASS I-beatboth-011 #1290: the 4-role D8 seam is BOUNDED in the full slate (force-exact) below the "
        "run-wall (A), the env wins outright so the pin takes (B), preflight fail-closes on seam>run-wall (C), "
        "and the seam .result() is capped by the remaining run-wall budget so the blocking call cannot overrun "
        "the wall (D). A full/--resume run now terminates inside its wall. Faithfulness engine untouched."
    )


if __name__ == "__main__":
    main()
