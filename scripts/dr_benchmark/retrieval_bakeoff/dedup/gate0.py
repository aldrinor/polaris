#!/usr/bin/env python3
"""I-ret-002 (#1294) dedup layer — GATE-0 validity harness (the anti-drb_72 gate).

No candidate score is trusted until BOTH canaries below are green. GATE-0 here has three teeth:

  1. SCORER-MATH CANARY (known input -> known score). A hand-built tiny pair set with known
     gold and a FAKE candidate of known behaviour must produce the precomputed precision/recall.
     Catches a broken metric (e.g. precision/recall swapped, FP miscounted).

  2. PER-CANDIDATE LIVENESS CANARY — BIDIRECTIONAL (the dedup-specific drb_72 trap). For each
     real candidate the harness asserts BOTH directions on the byte-identical controls and a
     clearly-distinct control:
       - byte-identical bodies  -> MUST merge          (else it is dead / no-op / load-failed)
       - clearly-distinct bodies-> MUST NOT merge       (else it over-merges everything)
     A stub / empty / load-fail / no-op candidate FAILS LOUD with a non-zero exit — it can
     NEVER score a believable-low number and pass. This is the most important test in the layer:
     a no-op merger scores PERFECT precision (TP/(TP+FP) with FP=0), so precision alone would
     pass it; the no-op RECALL floor + the must-merge direction kill it.

  3. KEEP-ALL PROVENANCE CANARY. Clustering a small member set must conserve every member id
     (union of clusters == input ids). A candidate that drops a source FAILS.

  4. OVER-MERGE PRECISION-FLOOR + NO-OP RECALL-FLOOR sanity. An always-merge stub must FAIL the
     precision floor; a never-merge stub must FAIL the no-op recall floor. Asserts the floors
     actually bite.

Exit code: 0 iff every enabled check passes; non-zero (fail loud) otherwise.
Candidates whose backend is unavailable (no dep / model not downloaded) are reported as
SKIPPED — honestly, never as a pass and never as a fake score.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import run_bakeoff  # noqa: E402

# ---------------------------------------------------------------------------
# Control bodies for the liveness canary. Long enough to exceed MIN_BODY_CHARS and to be
# discriminative; the DISTINCT control shares NO content with the identical one.
# ---------------------------------------------------------------------------

CONTROL_IDENTICAL = (
    "deep brain stimulation of the subthalamic nucleus significantly improved motor symptoms "
    "in patients with advanced parkinson disease over a twelve month randomized follow up "
    "compared with best medical therapy in this multicenter controlled clinical trial"
)
CONTROL_DISTINCT = (
    "magnesium and selenium trace element status was associated with cardiovascular mortality "
    "in a large prospective cohort with extended follow up across multiple european centers "
    "after adjustment for established coronary risk factors and dietary intake patterns"
)


@dataclass
class GateCheck:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class GateReport:
    all_passed: bool
    checks: List[GateCheck] = field(default_factory=list)
    skipped_candidates: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stub candidates used to prove the gate (and the floors) actually bite.
# ---------------------------------------------------------------------------

class _AlwaysMergeStub(run_bakeoff.DedupCandidate):
    name = "stub_always_merge"

    def merge(self, body_a: str, body_b: str) -> bool:
        return True


class _NeverMergeStub(run_bakeoff.DedupCandidate):
    name = "stub_never_merge"

    def merge(self, body_a: str, body_b: str) -> bool:
        return False  # the no-op merger: perfect precision (FP=0), zero recall


class _ExactOnlyStub(run_bakeoff.DedupCandidate):
    """A correct-direction reference: merges iff bodies are byte-identical after normalization."""

    name = "stub_exact_only"

    def merge(self, body_a: str, body_b: str) -> bool:
        return (body_a or "").strip() == (body_b or "").strip() and bool((body_a or "").strip())


# ---------------------------------------------------------------------------
# Canary 1: scorer math.
# ---------------------------------------------------------------------------

def check_scorer_math() -> GateCheck:
    """Known input -> known score. Build 4 gold pairs and the ExactOnly stub; the stub merges
    only the identical pairs. Compute expected precision/recall by hand and assert equality."""
    bodies = {
        "p1a": CONTROL_IDENTICAL,
        "p1b": CONTROL_IDENTICAL,  # identical -> exact stub merges (gold positive) -> TP
        "p2a": CONTROL_IDENTICAL,
        "p2b": CONTROL_IDENTICAL,  # identical, gold positive -> TP
        "p3a": CONTROL_IDENTICAL,
        "p3b": CONTROL_DISTINCT,  # distinct, gold positive(!) -> exact stub no-merge -> FN
        "n1a": CONTROL_IDENTICAL,
        "n1b": CONTROL_DISTINCT,  # distinct bodies, gold distinct -> no-merge -> TN
    }
    pairs = [
        {"a": {"member_id": "p1a"}, "b": {"member_id": "p1b"}, "label": "syndicated_copy", "label_source": "canonical_body"},
        {"a": {"member_id": "p2a"}, "b": {"member_id": "p2b"}, "label": "syndicated_copy", "label_source": "canonical_body"},
        {"a": {"member_id": "p3a"}, "b": {"member_id": "p3b"}, "label": "syndicated_copy", "label_source": "canonical_body"},
        {"a": {"member_id": "n1a"}, "b": {"member_id": "n1b"}, "label": "distinct", "label_source": "cross_topic"},
    ]
    # ExactOnly stub: merges p1 (TP), p2 (TP), NOT p3 (FN, bodies differ), NOT n1 (TN).
    # Expected: TP=2, FP=0, FN=1, TN=1 -> precision=1.0, recall=2/3.
    res = run_bakeoff.score_candidate_on_pairs(_ExactOnlyStub(), pairs, bodies)
    ok = (
        res.tp == 2
        and res.fp == 0
        and res.fn == 1
        and res.tn == 1
        and res.precision == 1.0
        and abs((res.recall or 0.0) - (2.0 / 3.0)) < 1e-9
    )
    return GateCheck(
        name="scorer_math_canary",
        passed=ok,
        detail=(
            f"tp={res.tp} fp={res.fp} fn={res.fn} tn={res.tn} "
            f"precision={res.precision} recall={res.recall} (expected tp=2,fp=0,fn=1,tn=1,"
            f"precision=1.0,recall=0.6667)"
        ),
    )


def check_wilson_math() -> GateCheck:
    """Known input -> known Wilson lower bound (sanity on the floor decision arithmetic)."""
    # 97/100 successes -> Wilson-95 one-sided lower bound is ~0.918 (well below the 0.97 point
    # estimate) — so a 97% point estimate on n=100 does NOT clear the floor. This is the whole
    # reason we use the lower bound: a thin band cannot crown a winner.
    lb = run_bakeoff.wilson_lower_bound(97, 100)
    lb_full = run_bakeoff.wilson_lower_bound(100, 100)
    ok = 0.90 < lb < 0.95 and lb_full > 0.96
    return GateCheck(
        name="wilson_math_canary",
        passed=ok,
        detail=f"wilson_lb(97/100)={lb:.4f} (expect ~0.91-0.94); wilson_lb(100/100)={lb_full:.4f}",
    )


# ---------------------------------------------------------------------------
# Canary 2: per-candidate bidirectional liveness (the no-op trap killer).
# ---------------------------------------------------------------------------

def check_candidate_liveness(candidate: run_bakeoff.DedupCandidate) -> GateCheck:
    """A live candidate MUST merge byte-identical bodies AND MUST NOT merge clearly-distinct
    bodies. A no-op / always-merge / dead candidate fails one direction."""
    try:
        merges_identical = bool(candidate.merge(CONTROL_IDENTICAL, CONTROL_IDENTICAL))
        merges_distinct = bool(candidate.merge(CONTROL_IDENTICAL, CONTROL_DISTINCT))
    except Exception as exc:  # load/runtime failure is a LIVENESS FAIL, not a skip
        return GateCheck(
            name=f"liveness::{candidate.name}",
            passed=False,
            detail=f"candidate raised on a control pair (dead): {type(exc).__name__}: {exc}",
        )
    ok = merges_identical and not merges_distinct
    reason = ""
    if not merges_identical:
        reason = "FAILED must-merge: did not merge BYTE-IDENTICAL bodies (no-op/dead candidate)"
    elif merges_distinct:
        reason = "FAILED must-not-merge: merged CLEARLY-DISTINCT bodies (over-merger)"
    return GateCheck(
        name=f"liveness::{candidate.name}",
        passed=ok,
        detail=(reason or "merged identical, rejected distinct (live, correct direction)")
        + f" [identical_merge={merges_identical} distinct_merge={merges_distinct}]",
    )


# ---------------------------------------------------------------------------
# Canary 3: KEEP-ALL provenance.
# ---------------------------------------------------------------------------

def check_provenance_conservation(candidate: run_bakeoff.DedupCandidate) -> GateCheck:
    members = [
        ("m1", CONTROL_IDENTICAL),
        ("m2", CONTROL_IDENTICAL),  # dup of m1
        ("m3", CONTROL_DISTINCT),
        ("m4", "an unrelated short but eligible body about autonomous vehicle liability law and "
               "the allocation of fault between manufacturer and human driver under negligence"),
    ]
    try:
        ok = run_bakeoff.assert_provenance_conserved(candidate, members)
        detail = "union(cluster member ids) == input ids (no source dropped)"
    except RuntimeError as exc:
        ok = False
        detail = str(exc)
    return GateCheck(name=f"provenance_keepall::{candidate.name}", passed=ok, detail=detail)


# ---------------------------------------------------------------------------
# Canary 4: floors actually bite.
# ---------------------------------------------------------------------------

def check_floors_bite() -> List[GateCheck]:
    """An always-merge stub must FAIL the precision floor; a never-merge (no-op) stub must FAIL
    the no-op recall floor (recall==0)."""
    bodies = {
        "x1": CONTROL_IDENTICAL, "x2": CONTROL_IDENTICAL,  # positive
        "y1": CONTROL_IDENTICAL, "y2": CONTROL_DISTINCT,   # distinct (negative)
    }
    pairs = [
        {"a": {"member_id": "x1"}, "b": {"member_id": "x2"}, "label": "syndicated_copy", "label_source": "canonical_body"},
        {"a": {"member_id": "y1"}, "b": {"member_id": "y2"}, "label": "distinct", "label_source": "curated_hard_negative"},
    ]
    checks: List[GateCheck] = []

    am = run_bakeoff.score_candidate_on_pairs(_AlwaysMergeStub(), pairs, bodies)
    # always-merge: TP=1 (x), FP=1 (y) -> precision=0.5 -> must NOT pass the 0.97 floor.
    checks.append(
        GateCheck(
            name="floor_bites_over_merge",
            passed=(am.passes_precision_floor is False and am.fp >= 1),
            detail=f"always-merge stub precision={am.precision} fp={am.fp} "
            f"passes_floor={am.passes_precision_floor} (must be False)",
        )
    )

    nm = run_bakeoff.score_candidate_on_pairs(_NeverMergeStub(), pairs, bodies)
    # never-merge (no-op): TP=0, FP=0 -> precision undefined(None), recall=0. The no-op recall
    # floor: recall==0 / precision is None -> must NOT pass the floor (the drb_72 trap).
    no_op_blocked = (nm.precision is None) and ((nm.recall or 0.0) == 0.0) and (
        nm.passes_precision_floor is False
    )
    checks.append(
        GateCheck(
            name="floor_bites_no_op_recall",
            passed=no_op_blocked,
            detail=f"no-op stub precision={nm.precision} recall={nm.recall} "
            f"passes_floor={nm.passes_precision_floor} (no-op must be blocked: precision None, "
            f"recall 0, passes_floor False)",
        )
    )
    return checks


# ---------------------------------------------------------------------------
# Driver.
# ---------------------------------------------------------------------------

def build_real_candidates(repo_root: str) -> List[run_bakeoff.DedupCandidate]:
    cands: List[run_bakeoff.DedupCandidate] = [
        run_bakeoff.SimHashBaselineCandidate(),
        run_bakeoff.PolarisContentDeduplicatorCandidate(repo_root),
        run_bakeoff.DatasketchMinHashCandidate(threshold=run_bakeoff.MINHASH_THRESHOLD_GRID[4]),
        run_bakeoff.SemHashModel2VecCandidate(),
    ]
    return cands


def run_gate0(
    repo_root: str,
    extra_candidates: Optional[List[run_bakeoff.DedupCandidate]] = None,
) -> GateReport:
    report = GateReport(all_passed=True)

    # Scorer-math canaries (always run; backend-independent).
    report.checks.append(check_scorer_math())
    report.checks.append(check_wilson_math())
    report.checks.extend(check_floors_bite())

    # The reference correct-direction stub must pass liveness + provenance (proves the canary
    # accepts a correct candidate, not just rejects bad ones).
    ref = _ExactOnlyStub()
    report.checks.append(check_candidate_liveness(ref))
    report.checks.append(check_provenance_conservation(ref))

    # Per-candidate liveness + provenance for every real (available) candidate.
    candidates = build_real_candidates(repo_root)
    if extra_candidates:
        candidates = candidates + list(extra_candidates)
    for cand in candidates:
        ok, reason = cand.available()
        if not ok:
            report.skipped_candidates.append(f"{cand.name}: {reason}")
            continue
        report.checks.append(check_candidate_liveness(cand))
        report.checks.append(check_provenance_conservation(cand))

    report.all_passed = all(c.passed for c in report.checks)
    return report


def print_report(report: GateReport) -> None:
    print("=== GATE-0 dedup ===")
    for c in report.checks:
        flag = "PASS" if c.passed else "FAIL"
        print(f"  [{flag}] {c.name}: {c.detail}")
    for s in report.skipped_candidates:
        print(f"  [SKIP] {s} (backend unavailable — honest skip, not a pass)")
    print(f"=== ALL_PASSED={report.all_passed} ===")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run GATE-0 for the dedup layer.")
    parser.add_argument("--repo-root", default=os.environ.get("POLARIS_REPO_ROOT", "C:/POLARIS"))
    parser.add_argument("--json", action="store_true", help="emit JSON report")
    args = parser.parse_args(argv)
    report = run_gate0(args.repo_root)
    if args.json:
        print(
            json.dumps(
                {
                    "all_passed": report.all_passed,
                    "checks": [vars(c) for c in report.checks],
                    "skipped_candidates": report.skipped_candidates,
                },
                indent=1,
            )
        )
    else:
        print_report(report)
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
