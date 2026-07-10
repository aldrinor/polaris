"""S0 INTAKE adversarial stress runner (offline, deterministic).

Runs the Fable adversarial S0-INTAKE battery
(``tests/polaris_graph/test_s0_intake_adversarial_battery.py``) in-process, then
classifies EVERY case into one of six outcomes and writes a forensic report the
blind operator can read by ear:

    passed        a regression-floor assert held               (OK)
    xfailed       a documented gap failed as designed           (OK)
    xpassed       a non-strict xfail unexpectedly passed         (BREAK)
    xpass_strict  a strict xfail unexpectedly passed             (BREAK)
    failed        a regression-floor assert broke               (BREAK)
    error         a setup/teardown/collection error             (BREAK)

The battery mixes two case kinds by design (see the battery docstring):
regression-floor plain asserts that must PASS, and ``xfail(strict=True)``
gap-exposing cases that must XFAIL today. So the CLEAN state is: only
``passed`` + ``xfailed`` present, every break bucket empty.

This runner is SELF-ROOTING: it puts its own repo root (the parent of
``scripts/``) at ``sys.path[0]`` so ``import src.polaris_graph`` always resolves
the co-located intake-core source, regardless of ``PYTHONPATH`` or the current
working directory. That matters because the S0 RunConfig API differs across
branches — the battery must run against the source that ships next to it.

Fully offline: the battery passes ``llm_fn=None`` and an explicit ``env`` to
every case, loads the knob registry from the repo yaml, and never touches the
network or a GPU.

Usage:
    python scripts/intake_stress.py --out <dir>

Exit code 0 iff CLEAN (zero breaks); 1 otherwise.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import platform
import sys
from pathlib import Path

# ── self-root: import the source that ships beside this script ────────────────
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest  # noqa: E402  (imported after sys.path is fixed)

_DEFAULT_TEST_REL = "tests/polaris_graph/test_s0_intake_adversarial_battery.py"

# Outcome buckets that count as a break (a real regression / undocumented change).
_BREAK_CATEGORIES = frozenset({"failed", "error", "xpass_strict", "xpassed", "skipped", "unknown"})
# Outcome buckets that are the healthy designed state.
_OK_CATEGORIES = frozenset({"passed", "xfailed"})


class _ResultCollector:
    """Pytest plugin: records every phase report so we can classify per case."""

    def __init__(self) -> None:
        self.cases: dict[str, dict] = {}

    def pytest_runtest_logreport(self, report) -> None:  # noqa: ANN001 (pytest api)
        case = self.cases.setdefault(report.nodeid, {"nodeid": report.nodeid, "phases": {}})
        case["phases"][report.when] = {
            "outcome": report.outcome,
            "has_wasxfail": hasattr(report, "wasxfail"),
            "wasxfail": getattr(report, "wasxfail", None),
            "longrepr": report.longreprtext if report.longrepr is not None else "",
            "capstdout": getattr(report, "capstdout", "") or "",
        }


def _classify(case: dict) -> str:
    """Map one case's phase reports to a single outcome category."""
    phases = case["phases"]
    setup = phases.get("setup", {})
    call = phases.get("call", {})
    teardown = phases.get("teardown", {})

    if setup.get("outcome") == "failed" or teardown.get("outcome") == "failed":
        return "error"
    if not call:
        # No call phase ran: a plain skip at setup (no xfail wasfail attached).
        if setup.get("outcome") == "skipped":
            return "skipped"
        return "unknown"

    outcome = call.get("outcome")
    if call.get("has_wasxfail"):
        # xfail machinery attached a reason: skipped==xfailed, passed==(non-strict) xpassed.
        if outcome == "skipped":
            return "xfailed"
        if outcome == "passed":
            return "xpassed"
    if outcome == "passed":
        return "passed"
    if outcome == "failed":
        # A strict xpass is reported as failed with this marker in the longrepr.
        if "[XPASS(strict)]" in (call.get("longrepr") or ""):
            return "xpass_strict"
        return "failed"
    if outcome == "skipped":
        return "skipped"
    return "unknown"


def _reason_for(category: str) -> tuple[str, str]:
    """Return (expected, got) plain-English strings for a break category."""
    table = {
        "failed": ("assert holds (regression-floor)", "assertion broke"),
        "error": ("case runs clean", "setup/teardown/collection error"),
        "xpass_strict": ("stays XFAIL (documented gap)", "gap silently fixed -> strict XPASS; remove the xfail marker"),
        "xpassed": ("stays XFAIL (documented gap)", "unexpectedly passed (non-strict XPASS)"),
        "skipped": ("case runs", "unexpectedly skipped"),
        "unknown": ("known outcome", "unclassifiable phase reports"),
    }
    return table.get(category, ("known outcome", category))


def _extract_evidence(collector: _ResultCollector) -> str:
    """Pull the machine-written evidence trail printed by test_zz_dump_evidence_trail."""
    for nodeid, case in collector.cases.items():
        if nodeid.rsplit("::", 1)[-1].startswith("test_zz_dump_evidence_trail"):
            return case["phases"].get("call", {}).get("capstdout", "")
    return ""


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(description="S0 INTAKE adversarial stress runner (offline).")
    parser.add_argument("--out", required=True, help="Output directory for the forensic report.")
    parser.add_argument(
        "--test-path",
        default=str(_REPO_ROOT / _DEFAULT_TEST_REL),
        help="Path to the adversarial battery (default: co-located battery).",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    test_path = Path(args.test_path)
    if not test_path.exists():
        print(f"FATAL: battery not found at {test_path}", flush=True)
        return 2

    collector = _ResultCollector()
    pytest_argv = [str(test_path), "-q", "-p", "no:cacheprovider", "-o", "addopts="]
    exit_status = int(pytest.main(pytest_argv, plugins=[collector]))

    # ── classify every collected case ────────────────────────────────────────
    cases: list[dict] = []
    for nodeid in sorted(collector.cases):
        case = collector.cases[nodeid]
        category = _classify(case)
        rec = {"nodeid": nodeid, "category": category}
        if category in _BREAK_CATEGORIES:
            rec["longrepr"] = case["phases"].get("call", {}).get("longrepr", "") \
                or case["phases"].get("setup", {}).get("longrepr", "")
        cases.append(rec)

    counts: dict[str, int] = {}
    for rec in cases:
        counts[rec["category"]] = counts.get(rec["category"], 0) + 1

    breaks = []
    for rec in cases:
        if rec["category"] in _BREAK_CATEGORIES:
            expected, got = _reason_for(rec["category"])
            longrepr = (rec.get("longrepr") or "").strip()
            quoted = longrepr.splitlines()[-1].strip() if longrepr else ""
            breaks.append({
                "case": rec["nodeid"],
                "category": rec["category"],
                "expected": expected,
                "got": got,
                "quoted_evidence": quoted[:500],
            })

    total_cases = len(cases)
    clean = (not breaks) and (exit_status == 0) and total_cases > 0
    evidence_trail = _extract_evidence(collector)

    report = {
        "schema": "intake_stress-1",
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "python": platform.python_version(),
        "pytest": pytest.__version__,
        "repo_root": str(_REPO_ROOT),
        "test_path": str(test_path),
        "pytest_exit_status": exit_status,
        "total_cases": total_cases,
        "counts": counts,
        "clean": clean,
        "cases": cases,
        "breaks": breaks,
    }

    (out_dir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out_dir / "summary.txt").open("w", encoding="utf-8") as fh:
        for rec in cases:
            fh.write(f"{rec['category'].upper():12} {rec['nodeid']}\n")
    (out_dir / "evidence_trail.txt").write_text(evidence_trail, encoding="utf-8")

    # ── stdout: per-case lines first, then evidence, then breaks + verdict LAST ──
    # (the verdict + breaks land in the final lines so `... | tail -N` keeps them).
    print("===== S0 INTAKE ADVERSARIAL STRESS — PER-CASE OUTCOMES =====", flush=True)
    for rec in cases:
        marker = "OK  " if rec["category"] in _OK_CATEGORIES else "BREAK"
        print(f"{marker} {rec['category'].upper():12} {rec['nodeid']}", flush=True)

    if evidence_trail.strip():
        print("\n===== MACHINE-WRITTEN EVIDENCE TRAIL =====", flush=True)
        for line in evidence_trail.strip().splitlines():
            print(line, flush=True)

    print("\n===== BREAKS =====", flush=True)
    if not breaks:
        print("none - every case landed in its designed bucket (passed | xfailed).", flush=True)
    else:
        for b in breaks:
            print(f"BREAK [{b['category']}] {b['case']}", flush=True)
            print(f"      expected: {b['expected']}", flush=True)
            print(f"      got:      {b['got']}", flush=True)
            if b["quoted_evidence"]:
                print(f"      quote:    {b['quoted_evidence']}", flush=True)

    print("\n===== RESULT =====", flush=True)
    ordered = ["passed", "xfailed", "failed", "error", "xpass_strict", "xpassed", "skipped", "unknown"]
    count_str = " ".join(f"{k}={counts.get(k, 0)}" for k in ordered if counts.get(k, 0))
    print(f"total_cases={total_cases}  {count_str}", flush=True)
    print(f"pytest_exit_status={exit_status}", flush=True)
    print(f"report_json={out_dir / 'report.json'}", flush=True)
    print(f"CLEAN={'true' if clean else 'false'}", flush=True)

    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
