#!/usr/bin/env python3
"""I-cd-034 (#634) — Phase 5b test-matrix runner.

Iterates the 24-row test matrix (`docs/carney_handover/test_matrix.md`)
against the live deployed POLARIS product (`polaris-orchestrator` OVH
VM by default). Emits a structured YAML result file:

    outputs/audits/I-cd-034/matrix_results_<utc_iso>.json
    (JSON content; .json extension. The "structured YAML" framing in
    parent #516 maps to "structured machine-readable" — we ship JSON
    for stdlib portability.)

Each row records:
- row_id (R01-R24)
- journey_stage (J1-J11) where applicable
- status: pass | fail | skip | needs_operator_action
- evidence: link to the artifact (run_id, screenshot, log, etc.)
- notes: human-readable observation

The runner is intentionally SUPERVISED — it does NOT auto-merge anything
or report "matrix green" unilaterally. The operator reviews the YAML at
the end and signs off via the I-cd-034-followup Issue.

OpenRouter spend ROW SUBSET (LLM-bound test types per doc):
- R03 (Artifact contract / schema versioning) — needs a real /runs/<id>/bundle
- R05 (E2E happy path) — drives a real run through pipeline-A
- R06 (E2E adversarial) — adversarial inputs against the LLM gates
- R19 (LLM quality gates) — intrinsic LLM-bound
- R21 (Anti-sycophancy) — intrinsic LLM-bound

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
# Codex iter-2 P1-003 fix: row catalog now matches the 24 TEST TYPES
# enumerated in docs/carney_handover/test_matrix.md (NOT product workflow
# checks). Each test-type's `stages` is the subset of J1-J11 where the
# doc says it applies.
#
# llm_bound rows are those whose execution against the live deployed
# product requires real OpenRouter spend (LLM-quality gates + the
# generation/scope/ambiguity surfaces that drive LLM calls per row's
# applicable journey stages):
#   R03  Artifact contract / schema versioning (touches J7/J8 — uses bundle)
#   R05  E2E happy path (uses J5 generation)
#   R06  E2E adversarial (uses J5 generation + J3 scope)
#   R19  LLM quality gates (intrinsic LLM-bound)
#   R21  Anti-sycophancy (intrinsic LLM-bound)
_MATRIX_ROWS: list[dict[str, Any]] = [
    {"id": "R01", "name": "Unit tests", "llm_bound": False, "stages": ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R02", "name": "Integration tests", "llm_bound": False, "stages": ["J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R03", "name": "Artifact contract / schema versioning", "llm_bound": True, "stages": ["J7", "J8"]},
    {"id": "R04", "name": "Visual regression", "llm_bound": False, "stages": ["J1", "J2", "J3", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R05", "name": "E2E happy path", "llm_bound": True, "stages": ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R06", "name": "E2E adversarial", "llm_bound": True, "stages": ["J3", "J4", "J5", "J6", "J8"]},
    {"id": "R07", "name": "Cross-browser", "llm_bound": False, "stages": ["J1", "J2", "J3", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R08", "name": "Accessibility (WCAG-AA)", "llm_bound": False, "stages": ["J1", "J2", "J3", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R09", "name": "Multi-tab safety", "llm_bound": False, "stages": ["J3", "J6", "J7", "J10"]},
    {"id": "R10", "name": "Network resilience", "llm_bound": False, "stages": ["J4", "J5", "J6", "J7"]},
    {"id": "R11", "name": "Streaming SSE ordering / backpressure", "llm_bound": False, "stages": ["J6"]},
    {"id": "R12", "name": "Cancellation / resume", "llm_bound": False, "stages": ["J6"]},
    {"id": "R13", "name": "Performance", "llm_bound": False, "stages": ["J2", "J3", "J6", "J7", "J8"]},
    {"id": "R14", "name": "Security", "llm_bound": False, "stages": ["J1", "J3", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R15", "name": "Tenant isolation + data deletion", "llm_bound": False, "stages": ["J1", "J9", "J11"]},
    {"id": "R16", "name": "Privacy / log redaction", "llm_bound": False, "stages": ["J4", "J5", "J6", "J7", "J9"]},
    {"id": "R17", "name": "Sovereignty (data-classification routing)", "llm_bound": False, "stages": ["J4", "J5", "J9"]},
    {"id": "R18", "name": "Migration tests", "llm_bound": False, "stages": []},
    {"id": "R19", "name": "LLM quality gates", "llm_bound": True, "stages": ["J5", "J11"]},
    {"id": "R20", "name": "Semantic chart correctness", "llm_bound": False, "stages": ["J11"]},
    {"id": "R21", "name": "Anti-sycophancy", "llm_bound": True, "stages": ["J3", "J5"]},
    {"id": "R22", "name": "Codex code review (process gate)", "llm_bound": False, "stages": []},
    {"id": "R23", "name": "Layer-3 walkthrough", "llm_bound": False, "stages": ["J1", "J2", "J3", "J5", "J6", "J7", "J8", "J9", "J10", "J11"]},
    {"id": "R24", "name": "Fixture governance + flake budget", "llm_bound": False, "stages": []},
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

    # Codex iter-2 P2-004 fix: unknown row IDs are a configuration error,
    # NOT a successful no-op. Fail with exit 11 (config error).
    all_known_ids = {row["id"] for row in _MATRIX_ROWS}
    unknown_ids = selected_ids - all_known_ids
    if unknown_ids:
        print(
            f"ERROR: unknown row id(s): {sorted(unknown_ids)}. "
            f"Valid: R01-R24.",
            file=sys.stderr,
        )
        return 11

    # Codex iter-1 P2-001 fix: parse + apply --journey selection.
    if "-" in args.journey and "," not in args.journey:
        j_start, j_end = args.journey.split("-")
        j_start_n = int(j_start.lstrip("J"))
        j_end_n = int(j_end.lstrip("J"))
        selected_stages = {f"J{n}" for n in range(j_start_n, j_end_n + 1)}
    else:
        selected_stages = set(args.journey.split(","))

    # Codex iter-2 P2-004 fix: unknown journey IDs also fail loud.
    all_known_stages = {f"J{n}" for n in range(1, 12)}
    unknown_stages = selected_stages - all_known_stages
    if unknown_stages:
        print(
            f"ERROR: unknown journey id(s): {sorted(unknown_stages)}. "
            f"Valid: J1-J11.",
            file=sys.stderr,
        )
        return 11

    results: list[RowResult] = []
    for row in _MATRIX_ROWS:
        if row["id"] not in selected_ids:
            continue
        # Skip rows whose declared stages do not intersect the selected
        # journey window. Rows with empty stages (R22 process gate,
        # R24 fixture governance) always run because they are not
        # journey-bound.
        if row["stages"] and not (set(row["stages"]) & selected_stages):
            continue
        result = _run_row(row, args.include_llm, base_url)
        results.append(result)
        print(
            f"[{result.row_id}] {result.status:>22}  {result.name}  "
            f"({result.duration_ms}ms)"
        )

    utc = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Codex iter-1 P2-002 fix: align extension with docstring (.json
    # since the content is JSON, not strict YAML; the file name is
    # explicit so reviewers know what to open with).
    out_path = Path(__file__).resolve().parent.parent / "outputs" / "audits" / "I-cd-034" / f"matrix_results_{utc}.json"
    _emit_results(results, out_path)
    print(f"\nResults written to: {out_path}")

    fail_count = sum(1 for r in results if r.status == "fail")
    if fail_count > 0:
        print(f"\n{fail_count} rows FAILED — matrix is RED.")
        return 10
    print("\nNo failures (skips + needs_operator_action are not RED).")
    return 0


if __name__ == "__main__":
    # Codex iter-1 P2-002 fix: docstring promised exit 99 on uncaught
    # exceptions; this wrapper actually delivers it.
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException as exc:  # noqa: BLE001 — diagnostic top-level
        print(f"UNCAUGHT: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(99)
