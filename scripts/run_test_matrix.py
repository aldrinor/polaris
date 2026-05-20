#!/usr/bin/env python3
"""I-cd-034 (#634) — Phase 5b test-matrix runner.

Iterates the 24-row test matrix (`docs/carney_handover/test_matrix.md`)
against the live deployed POLARIS product (`polaris-orchestrator` OVH
VM by default). Emits a structured YAML result file:

    outputs/audits/I-cd-034/matrix_results_<utc_iso>.yaml

Each row records:
- row_id (R01-R24)
- journey_stage (J1-J11) where applicable
- status: pass | fail | skip | needs_operator_action
- evidence: link to the artifact (run_id, screenshot, log, etc.)
- notes: human-readable observation

The runner is intentionally SUPERVISED — it does NOT auto-merge anything
or report "matrix green" unilaterally. The operator reviews the YAML at
the end and signs off via the I-cd-034-followup Issue.

OpenRouter spend ROW SUBSET (LLM-bound):
- R03 (artifact-contract schema) — needs a real /runs/<id>/bundle.tar.gz
- R05 (per-claim provenance) — needs a real verified report
- R07 (scope intake) — needs scope-gate LLM call
- R09 (ambiguity detection) — needs ambiguity-gate LLM call
- R11 (generation BEAT-BOTH) — needs full pipeline-A run

These 5 rows estimate ~$30-50 OpenRouter spend per full matrix pass.

Usage:
    export POLARIS_MATRIX_BASE_URL="http://51.79.90.35:3000"
    export OPENROUTER_API_KEY="sk-or-..."
    export POLARIS_MATRIX_AUTH_USER="carney_office"
    export POLARIS_MATRIX_AUTH_PASS="..."
    python scripts/run_test_matrix.py --rows R01-R24 --journey J1-J11

Exit codes:
    0   all selected rows pass (or skip with documented reason)
    10  one or more rows fail (matrix is RED)
    11  configuration error (missing env)
    12  network unreachable / target down
    99  uncaught exception
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Test-row catalog (24 rows per docs/carney_handover/test_matrix.md).
# Each row carries: id, name, llm_bound (does this row need real LLM spend),
# journey_stages it touches, and a default skip_reason if llm_bound and the
# operator has not flagged --include-llm.
_MATRIX_ROWS: list[dict[str, Any]] = [
    {"id": "R01", "name": "Sign-in (static_accounts auth)", "llm_bound": False, "stages": ["J1"]},
    {"id": "R02", "name": "App-shell + nav presence (G1-G8)", "llm_bound": False, "stages": ["J1", "J2", "J3", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R03", "name": "Artifact-contract schema (BundleManifest v1.0)", "llm_bound": True, "stages": ["J7", "J8"]},
    {"id": "R04", "name": "Run lifecycle (queued→in_progress→completed)", "llm_bound": True, "stages": ["J6", "J7"]},
    {"id": "R05", "name": "Per-claim provenance + source span", "llm_bound": True, "stages": ["J8"]},
    {"id": "R06", "name": "Family segregation (two-family)", "llm_bound": False, "stages": ["J7", "J8"]},
    {"id": "R07", "name": "Scope intake gate", "llm_bound": True, "stages": ["J3"]},
    {"id": "R08", "name": "Refusal-bait detection", "llm_bound": True, "stages": ["J3"]},
    {"id": "R09", "name": "Ambiguity detection + disambiguation modal", "llm_bound": True, "stages": ["J3"]},
    {"id": "R10", "name": "Retrieval + corpus adequacy", "llm_bound": True, "stages": ["J4"]},
    {"id": "R11", "name": "Generation BEAT-BOTH (vs ChatGPT/Gemini)", "llm_bound": True, "stages": ["J5", "J11"]},
    {"id": "R12", "name": "Live SSE stream (run events)", "llm_bound": True, "stages": ["J6"]},
    {"id": "R13", "name": "Bundle export + signature verify", "llm_bound": False, "stages": ["J7"]},
    {"id": "R14", "name": "Inspector — claim → source navigation", "llm_bound": False, "stages": ["J8"]},
    {"id": "R15", "name": "Inspector offline (tar.gz drop)", "llm_bound": False, "stages": ["J8"]},
    {"id": "R16", "name": "Document upload + grounding", "llm_bound": False, "stages": ["J9"]},
    {"id": "R17", "name": "Dashboard run creation", "llm_bound": True, "stages": ["J10"]},
    {"id": "R18", "name": "Evidence Contract editor", "llm_bound": False, "stages": ["J11"]},
    {"id": "R19", "name": "Workspace memory (save/forget)", "llm_bound": False, "stages": ["J11"]},
    {"id": "R20", "name": "Pin replay timeseries", "llm_bound": False, "stages": ["J11"]},
    {"id": "R21", "name": "Cancel + cooperative-abort", "llm_bound": True, "stages": ["J6"]},
    {"id": "R22", "name": "Codex code review (process gate)", "llm_bound": False, "stages": []},
    {"id": "R23", "name": "WCAG-AA accessibility sweep", "llm_bound": False, "stages": ["J1", "J2", "J3", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R24", "name": "Fixture governance (schema-freeze)", "llm_bound": False, "stages": []},
]


@dataclass
class RowResult:
    row_id: str
    name: str
    status: str  # pass | fail | skip | needs_operator_action
    evidence: str = ""
    notes: str = ""
    duration_ms: int = 0
    journey_stages: list[str] = field(default_factory=list)


def _env_or_die(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        print(f"ERROR: missing required env var {name}", file=sys.stderr)
        sys.exit(11)
    return val


def _check_reachable(base_url: str) -> bool:
    """Probe /health on the target. Returns True if reachable."""
    try:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(f"{base_url}/health", method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _run_row(row: dict[str, Any], include_llm: bool, base_url: str) -> RowResult:
    """Stub runner — every row currently returns `needs_operator_action`.
    The operator wires concrete row implementations as they execute the
    matrix supervised. The skeleton ensures every row is enumerated and
    the YAML output is well-formed.
    """
    start = time.monotonic()
    if row["llm_bound"] and not include_llm:
        return RowResult(
            row_id=row["id"],
            name=row["name"],
            status="skip",
            notes="LLM-bound; --include-llm not set (OpenRouter spend deferred)",
            journey_stages=row["stages"],
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    return RowResult(
        row_id=row["id"],
        name=row["name"],
        status="needs_operator_action",
        evidence=f"see docs/carney_handover/test_matrix.md#{row['id']}",
        notes=(
            "Row runner is a skeleton; operator executes against "
            f"{base_url} and records pass/fail + evidence link here."
        ),
        journey_stages=row["stages"],
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def _emit_results(results: list[RowResult], out_path: Path) -> None:
    """Emit a structured YAML-shaped JSON (no PyYAML dep) for portability."""
    payload = {
        "run_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "matrix_total": len(_MATRIX_ROWS),
        "rows_executed": len(results),
        "status_counts": {
            s: sum(1 for r in results if r.status == s)
            for s in ("pass", "fail", "skip", "needs_operator_action")
        },
        "rows": [asdict(r) for r in results],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 5b test-matrix runner.")
    parser.add_argument(
        "--rows",
        default="R01-R24",
        help="Row range or comma-separated ids (default: R01-R24).",
    )
    parser.add_argument(
        "--journey",
        default="J1-J11",
        help="Journey stage range or comma-separated (default: J1-J11).",
    )
    parser.add_argument(
        "--include-llm",
        action="store_true",
        help="Execute LLM-bound rows (incurs OpenRouter spend). Default: skip.",
    )
    args = parser.parse_args()

    base_url = _env_or_die("POLARIS_MATRIX_BASE_URL")
    if args.include_llm:
        _env_or_die("OPENROUTER_API_KEY")
    _env_or_die("POLARIS_MATRIX_AUTH_USER")
    _env_or_die("POLARIS_MATRIX_AUTH_PASS")

    if not _check_reachable(base_url):
        print(f"ERROR: {base_url}/health unreachable", file=sys.stderr)
        return 12

    # Parse row selection.
    if "-" in args.rows and "," not in args.rows:
        start_s, end_s = args.rows.split("-")
        start_n = int(start_s.lstrip("R"))
        end_n = int(end_s.lstrip("R"))
        selected_ids = {f"R{n:02d}" for n in range(start_n, end_n + 1)}
    else:
        selected_ids = set(args.rows.split(","))

    results: list[RowResult] = []
    for row in _MATRIX_ROWS:
        if row["id"] not in selected_ids:
            continue
        result = _run_row(row, args.include_llm, base_url)
        results.append(result)
        print(
            f"[{result.row_id}] {result.status:>22}  {result.name}  "
            f"({result.duration_ms}ms)"
        )

    utc = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = Path(__file__).resolve().parent.parent / "outputs" / "audits" / "I-cd-034" / f"matrix_results_{utc}.yaml.json"
    _emit_results(results, out_path)
    print(f"\nResults written to: {out_path}")

    fail_count = sum(1 for r in results if r.status == "fail")
    if fail_count > 0:
        print(f"\n{fail_count} rows FAILED — matrix is RED.")
        return 10
    print("\nNo failures (skips + needs_operator_action are not RED).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
