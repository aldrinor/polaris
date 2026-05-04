"""End-to-end demo smoke script — validates the 5-slice FastAPI stack.

Run before the Sep 6 tracer demo to confirm:
- create_app() boots without errors
- All 5 slice routes are mounted (intake, retrieval, generation,
  audit-bundle, benchmark)
- Each /health endpoint returns 200 with the expected slice id
- A canonical clinical question round-trips through process_intake and
  yields a ScopeDecision (not an IntakeError)

Does NOT call OpenRouter or Serper — uses in-process TestClient and the
503-sentinel fall-throughs when env keys are missing. Cost: $0.

Exit 0 = demo stack healthy. Exit 1 = at least one slice failing.

Usage:
    PYTHONPATH=src python scripts/demo_smoke.py [-v]
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastapi.testclient import TestClient

from polaris_graph.api.intake import process_intake
from polaris_graph.scope.scope_decision import ScopeDecision
from polaris_v6.api.app import create_app


_EXPECTED_HEALTH = {
    "/api/intake/health": "slice_001_clinical_scope_discovery",
    "/api/retrieval/health": "slice_002_clinical_retrieval",
    "/api/generation/health": "slice_003_generator_strict_verify",
    "/api/audit-bundle/health": "slice_004_audit_bundle_export",
    "/api/benchmark/health": "slice_005_beat_both_benchmark",
}


_CANONICAL_QUESTION = (
    "Is high-dose aspirin effective for migraine in adults?"
)


def _check_health(client: TestClient, path: str, expected_slice: str,
                  verbose: bool) -> bool:
    try:
        r = client.get(path)
    except Exception as e:
        print(f"  FAIL {path}: exception {e}", file=sys.stderr)
        return False
    if r.status_code != 200:
        print(f"  FAIL {path}: status {r.status_code}", file=sys.stderr)
        return False
    body: dict[str, Any] = r.json()
    if body.get("slice") != expected_slice:
        print(
            f"  FAIL {path}: slice {body.get('slice')!r} != "
            f"{expected_slice!r}",
            file=sys.stderr,
        )
        return False
    if verbose:
        print(f"  OK   {path} -> slice={body['slice']}")
    return True


def _check_intake_pipeline(verbose: bool) -> bool:
    """Run a canonical question through process_intake.

    Asserts shape only (ScopeDecision instance, latency under budget).
    Status / scope_class depend on whether OPENROUTER_API_KEY is loaded —
    without it, the LLM-fallback branch returns out_of_scope. Smoke is a
    structural check, not a content check; for content verification run
    the full demo runbook with keys set.
    """
    try:
        result = process_intake(_CANONICAL_QUESTION)
    except Exception as e:
        print(f"  FAIL process_intake: exception {e}", file=sys.stderr)
        return False
    if not isinstance(result, ScopeDecision):
        print(
            f"  FAIL process_intake: expected ScopeDecision, got {type(result).__name__}",
            file=sys.stderr,
        )
        return False
    if result.latency_ms > 10000:
        print(
            f"  FAIL process_intake: latency {result.latency_ms}ms > 10000ms",
            file=sys.stderr,
        )
        return False
    if verbose:
        print(
            f"  OK   process_intake -> status={result.status} "
            f"scope_class={result.scope_class} "
            f"latency_ms={result.latency_ms}"
        )
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="POLARIS 5-slice demo smoke")
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Print per-check status",
    )
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    print("POLARIS demo smoke — 5-slice FastAPI stack")
    print("===========================================")

    try:
        app = create_app()
    except Exception as e:
        print(f"FAIL: create_app() raised: {e}", file=sys.stderr)
        return 1

    client = TestClient(app)

    failures = 0
    print("[1/2] Health checks:")
    for path, expected in _EXPECTED_HEALTH.items():
        if not _check_health(client, path, expected, args.verbose):
            failures += 1

    print("[2/2] Pipeline checks:")
    if not _check_intake_pipeline(args.verbose):
        failures += 1

    print("===========================================")
    if failures:
        print(f"DEMO SMOKE FAILED: {failures} check(s) failed")
        return 1
    print("DEMO SMOKE PASSED: all 5 slices healthy + intake pipeline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
