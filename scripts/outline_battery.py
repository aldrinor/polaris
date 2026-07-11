#!/usr/bin/env python3
"""The T2 edge-case battery runner (docs/agentic_outline_redesign.md PART 3).

Loads the battery cases (``tests/battery/cases/*.py``, each exporting ``BATTERY_CASES``), runs
them, ranks the failures by severity S0..S4, and writes the wheel's plain-text output:
  * outputs/battery/<run_id>/summary.json        — machine-readable per-case + per-severity totals
  * outputs/battery/<run_id>/ranked_failures.md  — S0-first human read (the wheel's routing signal)
  * outputs/battery/history.jsonl (append)       — one line per run: run_id, git sha, counts

This first wave runs the DETERMINISTIC compute/faithfulness cases in-process, sequentially (they
are sub-second and share NO writable state; the one case that needs env seats sets+restores them
under a scoped context so the parent env is never left mutated). The ProcessPool + flock live-fetch
slots the design specifies are for the future AGENT-DRIVEN live cases (H01 targeted-fetch etc.),
which are not in this wave — that is called out honestly in the summary so the operator is not
misled about coverage.

Usage:
  python scripts/outline_battery.py --all
  python scripts/outline_battery.py --only h01a_calc_render h01e_production_handoff
  python scripts/outline_battery.py --all --max-severity S1   # exit non-zero only on S0/S1
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
import json
import pkgutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tests.battery.harness import (  # noqa: E402
    Assertion, BatteryCase, CaseResult, SEVERITIES, severity_rank,
)

_OUT_ROOT = _REPO / "outputs" / "battery"
_CASES_PKG = "tests.battery.cases"


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=_REPO, text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def load_cases(only: list[str] | None) -> list[BatteryCase]:
    """Discover every ``BATTERY_CASES`` list under tests/battery/cases/."""
    import tests.battery.cases as cases_pkg  # noqa: PLC0415

    cases: list[BatteryCase] = []
    for mod_info in pkgutil.iter_modules(cases_pkg.__path__):
        if mod_info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{_CASES_PKG}.{mod_info.name}")
        for c in getattr(mod, "BATTERY_CASES", []):
            cases.append(c)
    if only:
        want = set(only)
        cases = [c for c in cases if c.id in want]
    cases.sort(key=lambda c: c.id)
    return cases


async def _run_one(case: BatteryCase) -> CaseResult:
    t0 = time.monotonic()
    result = CaseResult(case_id=case.id, domain=case.domain,
                        capability=case.capability, xfail=case.xfail, note=case.note)
    try:
        out = case.run()
        if inspect.isawaitable(out):
            out = await out
        result.assertions = list(out or [])
    except Exception as exc:  # noqa: BLE001 — a probe crash is a case failure, never a wheel crash
        import traceback
        result.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-800:]}"
    result.wall_s = time.monotonic() - t0
    return result


async def _run_all(cases: list[BatteryCase]) -> list[CaseResult]:
    # Sequential: the deterministic compute cases are sub-second and one mutates process env under
    # a scoped restore, which is only safe without concurrent readers. Live agent cases (future
    # wave) get the ProcessPool.
    results: list[CaseResult] = []
    for c in cases:
        results.append(await _run_one(c))
    return results


def _rank_failures(results: list[CaseResult]) -> list[CaseResult]:
    """Failing (non-xfail) cases, S0 first; ties by case id."""
    fails = [r for r in results if r.outcome in ("fail", "error")]
    fails.sort(key=lambda r: (severity_rank(r.worst_severity or "S4"), r.case_id))
    return fails


def _severity_tally(results: list[CaseResult]) -> dict[str, int]:
    tally = {s: 0 for s in SEVERITIES}
    for r in results:
        if r.outcome in ("fail", "error"):
            tally[r.worst_severity or "S4"] += 1
    return tally


def write_outputs(results: list[CaseResult], run_id: str) -> tuple[Path, dict]:
    run_dir = _OUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    tally = _severity_tally(results)
    outcomes = {k: sum(1 for r in results if r.outcome == k)
                for k in ("pass", "fail", "xfail", "xpass", "error")}
    summary = {
        "run_id": run_id,
        "git_sha": _git_sha(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_cases": len(results),
        "outcomes": outcomes,
        "severity_failures": tally,
        "note": (
            "Wave-1 deterministic compute/faithfulness cases (in-process). Agent-driven live-fetch "
            "cases (H01 targeted-fetch, H18 re-retrieval) are NOT yet in the battery — the "
            "ProcessPool/flock harness for them is future work."
        ),
        "cases": [r.as_dict() for r in results],
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    ranked = _rank_failures(results)
    lines = [
        f"# Battery ranked failures — run {run_id} (git {summary['git_sha']})",
        "",
        f"cases={len(results)}  pass={outcomes['pass']}  fail={outcomes['fail']}  "
        f"xfail={outcomes['xfail']}  xpass={outcomes['xpass']}  error={outcomes['error']}",
        f"severity failures: " + "  ".join(f"{s}={tally[s]}" for s in SEVERITIES),
        "",
    ]
    if not ranked:
        lines.append("No S0/S1/S2/S3 failures. (xfail cases are known capability gaps, listed below.)")
    for r in ranked:
        lines.append(f"## [{r.worst_severity}] {r.case_id}  ({r.domain} / {r.capability})")
        if r.error:
            lines.append(f"- ERROR: {r.error.splitlines()[0]}")
        for a in r.failed:
            lines.append(
                f"- FAIL [{a.severity}] {a.name}: expected={a.expected!r} actual={a.actual!r}"
                + (f"  — {a.detail}" if a.detail else "")
            )
        lines.append("")
    xfails = [r for r in results if r.outcome == "xfail"]
    if xfails:
        lines.append("## Known capability gaps (xfail — not blockers)")
        for r in xfails:
            lines.append(f"- {r.case_id} ({r.capability}): {r.note or 'pending capability'}")
        lines.append("")
    xpasses = [r for r in results if r.outcome == "xpass"]
    if xpasses:
        lines.append("## XPASS — land these into the active set:")
        for r in xpasses:
            lines.append(f"- {r.case_id} ({r.capability})")
        lines.append("")
    (run_dir / "ranked_failures.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    hist = {
        "run_id": run_id, "git_sha": summary["git_sha"],
        "at": summary["generated_at"], "outcomes": outcomes, "severity_failures": tally,
    }
    with (_OUT_ROOT / "history.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(hist) + "\n")

    return run_dir, summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="T2 outline edge-case battery")
    ap.add_argument("--all", action="store_true", help="run every discovered case")
    ap.add_argument("--only", nargs="+", default=None, help="run only these case ids")
    ap.add_argument("--max-severity", default="S1",
                    help="exit non-zero if a failure at this severity or worse occurred (default S1)")
    ap.add_argument("--run-id", default=None)
    args = ap.parse_args(argv)

    if not args.all and not args.only:
        ap.error("pass --all or --only <case_id ...>")

    cases = load_cases(args.only)
    if not cases:
        print("no cases matched", file=sys.stderr)
        return 2

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results = asyncio.run(_run_all(cases))
    run_dir, summary = write_outputs(results, run_id)

    tally = summary["severity_failures"]
    outcomes = summary["outcomes"]
    print(f"battery run {run_id} (git {summary['git_sha']}): {len(results)} cases")
    for r in sorted(results, key=lambda x: x.case_id):
        mark = {"pass": "PASS", "fail": "FAIL", "xfail": "xfail", "xpass": "XPASS",
                "error": "ERROR"}[r.outcome]
        sev = f" [{r.worst_severity}]" if r.worst_severity and r.outcome in ("fail", "error") else ""
        print(f"  {mark:5} {r.case_id}{sev}  ({r.wall_s:.2f}s)")
    print(f"outcomes: {outcomes}")
    print("severity failures: " + "  ".join(f"{s}={tally[s]}" for s in SEVERITIES))
    print(f"output: {run_dir}/ranked_failures.md")

    cutoff = severity_rank(args.max_severity)
    blocking = sum(v for s, v in tally.items() if severity_rank(s) <= cutoff)
    if blocking:
        print(f"BLOCKING: {blocking} failure(s) at {args.max_severity} or worse", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
