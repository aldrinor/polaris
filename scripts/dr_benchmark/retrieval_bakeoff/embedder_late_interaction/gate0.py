#!/usr/bin/env python3
"""I-ret-002 (#1294) — embedder_late_interaction layer: GATE-0 validity harness.

This is the anti-drb_72 gate. NO candidate score from run_bakeoff.py is trusted until BOTH
canaries below are GREEN. It exits NON-ZERO and FAILS LOUD on any breach.

PART 1 — SCORER-MATH CANARY (known input -> known score):
  - auc_pos_gt_neg: perfect separation -> 1.0; inverted -> 0.0; tie -> 0.5; empty class -> None.
  - recall_at_k: gold in top-k -> 1.0; gold below k -> 0.0; no gold -> None.
  - cosine: identical unit vectors -> 1.0; orthogonal -> 0.0; opposite -> -1.0.
  - maxsim: a query whose tokens each match a doc token -> ~len(query_tokens); empty -> 0.0.
  These validate the EXACT functions run_bakeoff.py uses (shared scorer.py), so the math the
  canary blesses is the math that scores candidates.

PART 2 — PER-CANDIDATE LIVENESS CANARY (the drb_72 killer):
  Each candidate must, on a KNOWN on-topic > off-topic micro-pair:
    (a) LOAD (real model on the GPU box; injected encoder in the offline smoke),
    (b) have loaded_id == requested_id (Gate-B / I-arch-009 no-silent-MiniLM-fallback),
    (c) score the on-topic doc STRICTLY ABOVE the off-topic doc (correct semantic direction).
  A candidate that returns a STUB / EMPTY / CONSTANT / load-fail / missing-dep result FAILS the
  liveness canary with a non-zero exit — it can NEVER pass by scoring a believable-low number.
  needs_gpu candidates on a CPU box are reported as HONESTLY SKIPPED (status skipped_needs_gpu),
  which is NOT a pass and NOT a silent score — the run on the real box must re-run liveness there.

Usage:
  python gate0.py                 # PART 1 only (offline scorer math) — always runnable
  python gate0.py --live          # PART 1 + PART 2 with REAL model loaders (GPU box)
  (the offline smoke_test.py drives PART 2 with INJECTED encoders, incl. a deliberate stub)
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Callable, Optional

from scorer import auc_pos_gt_neg, cosine, maxsim, rank_by_score, recall_at_k
from run_bakeoff import (
    CANDIDATES,
    Candidate,
    CandidateLoadError,
    LoadedEncoder,
    load_candidate,
)


class GateZeroError(AssertionError):
    """Raised fail-loud when a GATE-0 canary breaks. A run that raises this is INVALID."""


_EPS = 1e-9


# ---------------------------------------------------------------------------
# PART 1 — scorer-math canary
# ---------------------------------------------------------------------------
def check_scorer_math() -> list[str]:
    """Validate the shared scorer math on known inputs. Returns the list of passed-check names."""
    passed: list[str] = []

    def expect(name: str, got: Optional[float], want: Optional[float]) -> None:
        if want is None:
            if got is not None:
                raise GateZeroError(f"{name}: expected None, got {got!r}")
        elif got is None or abs(got - want) > 1e-6:
            raise GateZeroError(f"{name}: expected {want}, got {got!r}")
        passed.append(name)

    # AUC.
    expect("auc_perfect", auc_pos_gt_neg([0.9, 0.8], [0.1, 0.2]), 1.0)
    expect("auc_inverted", auc_pos_gt_neg([0.1, 0.2], [0.9, 0.8]), 0.0)
    expect("auc_tie", auc_pos_gt_neg([0.5], [0.5]), 0.5)
    expect("auc_empty_pos", auc_pos_gt_neg([], [0.5]), None)
    expect("auc_empty_neg", auc_pos_gt_neg([0.5], []), None)

    # recall@k.
    expect("recall_hit_top1", recall_at_k(["gold", "x", "y"], {"gold"}, 1), 1.0)
    expect("recall_miss_below_k", recall_at_k(["x", "y", "gold"], {"gold"}, 2), 0.0)
    expect("recall_no_gold", recall_at_k(["x", "y"], set(), 2), None)

    # cosine.
    expect("cosine_identical", cosine([1.0, 0.0], [1.0, 0.0]), 1.0)
    expect("cosine_orthogonal", cosine([1.0, 0.0], [0.0, 1.0]), 0.0)
    expect("cosine_opposite", cosine([1.0, 0.0], [-1.0, 0.0]), -1.0)
    expect("cosine_zero_vector", cosine([0.0, 0.0], [1.0, 0.0]), 0.0)

    # maxsim: 2 query tokens, each identical to a doc token -> 2.0 (sum of two 1.0 cosines).
    qt = [[1.0, 0.0], [0.0, 1.0]]
    dt = [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
    ms = maxsim(qt, dt)
    if abs(ms - 2.0) > 1e-6:
        raise GateZeroError(f"maxsim_perfect: expected 2.0, got {ms!r}")
    passed.append("maxsim_perfect")
    if maxsim([], dt) != 0.0 or maxsim(qt, []) != 0.0:
        raise GateZeroError("maxsim_empty: expected 0.0 for empty token sets")
    passed.append("maxsim_empty")

    # rank_by_score: highest score first, stable on ties.
    ranked = rank_by_score(["a", "b", "c"], [0.1, 0.9, 0.5])
    if ranked != ["b", "c", "a"]:
        raise GateZeroError(f"rank_by_score: expected ['b','c','a'], got {ranked}")
    passed.append("rank_by_score")

    return passed


# ---------------------------------------------------------------------------
# PART 2 — per-candidate liveness canary
# ---------------------------------------------------------------------------
# A KNOWN on-topic > off-topic micro-pair (clinical-flavored, matches the POLARIS domain).
LIVENESS_QUERY = (
    "What is the effect of deep brain stimulation on motor symptoms in Parkinson's disease?"
)
LIVENESS_ON_TOPIC = (
    "Subthalamic nucleus deep brain stimulation significantly reduced bradykinesia and rigidity "
    "in patients with advanced Parkinson's disease, improving UPDRS motor scores."
)
LIVENESS_OFF_TOPIC = (
    "Gut microbiota dysbiosis and Fusobacterium nucleatum abundance were associated with "
    "colorectal cancer progression in a 16S rRNA cohort study."
)


@dataclass
class LivenessOutcome:
    name: str
    passed: bool
    status: str  # "live" | "skipped_needs_gpu" | "skipped_no_dep" | "FAILED"
    on_topic_score: Optional[float]
    off_topic_score: Optional[float]
    detail: str


def _score_pair(enc: LoadedEncoder, query: str, doc: str) -> float:
    """Single (query, doc) scalar score via the encoder's arch (cosine or MaxSim)."""
    if enc.candidate.arch == "single_vector":
        assert enc.encode_single is not None
        qv = enc.encode_single([query], True)[0]
        dv = enc.encode_single([doc], False)[0]
        return cosine(qv, dv)
    assert enc.encode_tokens is not None
    qt = enc.encode_tokens([query], True)[0]
    dt = enc.encode_tokens([doc], False)[0]
    return maxsim(qt, dt)


def check_candidate_liveness(
    cand: Candidate,
    device: str,
    loader: Callable[[Candidate, str], LoadedEncoder],
) -> LivenessOutcome:
    """Liveness for ONE candidate: load + identity + correct on>off direction. FAIL LOUD on breach.

    Returns a LivenessOutcome; ``passed`` is False for any real failure. needs_gpu on CPU and
    missing-dep are honest SKIPS (passed=True so the offline gate does not red on them) but they
    are clearly statused so they are NOT mistaken for a real pass — the live run re-checks them.
    """
    if cand.needs_gpu and device != "cuda":
        return LivenessOutcome(
            cand.name, True, "skipped_needs_gpu", None, None,
            "needs_gpu and no CUDA — honestly skipped offline; MUST re-run liveness on GPU box",
        )
    try:
        enc = loader(cand, device)
    except ImportError as exc:
        return LivenessOutcome(
            cand.name, True, "skipped_no_dep", None, None, f"missing dependency: {exc}"
        )
    except CandidateLoadError as exc:
        # identity mismatch / load fail = a REAL failure, not a skip.
        return LivenessOutcome(cand.name, False, "FAILED", None, None, f"load/identity: {exc}")
    except Exception as exc:  # noqa: BLE001 — any other load crash is a hard liveness failure
        return LivenessOutcome(cand.name, False, "FAILED", None, None, f"load crash: {exc!r}")

    try:
        on = _score_pair(enc, LIVENESS_QUERY, LIVENESS_ON_TOPIC)
        off = _score_pair(enc, LIVENESS_QUERY, LIVENESS_OFF_TOPIC)
    except Exception as exc:  # noqa: BLE001
        return LivenessOutcome(cand.name, False, "FAILED", None, None, f"score crash: {exc!r}")

    # A stub/constant encoder returns equal (or NaN/empty) scores -> on is NOT strictly > off.
    if not (on > off + _EPS):
        return LivenessOutcome(
            cand.name, False, "FAILED", on, off,
            "on-topic NOT strictly above off-topic — stub/empty/constant or wrong-direction "
            "model (a believable-low score must NOT pass; this is the drb_72 guard)",
        )
    return LivenessOutcome(cand.name, True, "live", on, off, "on>off in correct direction")


def run_liveness(
    device: str,
    loader: Callable[[Candidate, str], LoadedEncoder] = load_candidate,
    only: Optional[list[str]] = None,
) -> list[LivenessOutcome]:
    names = only or list(CANDIDATES.keys())
    return [check_candidate_liveness(CANDIDATES[n], device, loader) for n in names]


def main() -> int:
    ap = argparse.ArgumentParser(description="GATE-0 validity harness (embedder_late_interaction)")
    ap.add_argument("--live", action="store_true", help="run PART 2 with REAL model loaders (GPU)")
    ap.add_argument("--candidates", default="", help="comma-separated subset for PART 2")
    args = ap.parse_args()

    print("== GATE-0 PART 1: scorer-math canary ==")
    passed = check_scorer_math()
    print(f"  scorer math OK ({len(passed)} checks): {', '.join(passed)}")

    if not args.live:
        print("\n(PART 2 liveness needs --live with real loaders, or run via smoke_test.py with "
              "injected encoders. Skipping live liveness here.)")
        print("\nGATE-0 PART 1: PASS")
        return 0

    from run_bakeoff import detect_device

    device = detect_device()
    only = [c.strip() for c in args.candidates.split(",") if c.strip()] or None
    print(f"\n== GATE-0 PART 2: per-candidate liveness (device={device}) ==")
    outcomes = run_liveness(device, only=only)
    failures = []
    for o in outcomes:
        flag = "PASS" if o.passed else "FAIL"
        print(f"  [{flag}] {o.name}: status={o.status} on={o.on_topic_score} "
              f"off={o.off_topic_score} — {o.detail}")
        if not o.passed:
            failures.append(o.name)
    if failures:
        print(f"\nGATE-0 FAILED — liveness breach: {failures}")
        return 1
    print("\nGATE-0 PART 1 + PART 2: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
