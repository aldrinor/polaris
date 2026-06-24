#!/usr/bin/env python3
"""I-ret-002 (#1294) reranker layer — GATE-0 validity harness (the anti-drb_72 gate).

Nothing in the bake-off is trusted until BOTH canaries below are green:

  A. SCORER-MATH canary (credibility-graded NDCG@K). Known ordering -> known score:
       * ideal ordering              -> NDCG == 1.0   (normalization)
       * a hand-built fractional case -> NDCG == a HAND-COMPUTED value (the real discriminator;
         a scorer that always returns 1.0 passes the ideal case but FAILS this one).
     Plus the required-source recall@K guard math (a known eviction -> known recall).

  B. PER-CANDIDATE MODEL-WIRING LIVENESS canary. Each LOADED reranker is handed one obviously
     relevant doc and one obvious-junk doc for a fixed query and MUST satisfy BOTH:
       * score(relevant) > score(junk)            (semantic direction), AND
       * score(relevant) != score(junk)           (NOT a constant — a load-fail / OOM / wrong-
                                                    template reranker that returns a constant
                                                    would pass a bare ">" if both equal; it must
                                                    FAIL LOUD, never score a believable number).
     A stub / empty / load-fail / missing-key candidate raises RerankerLivenessError (non-zero
     exit), it is NEVER scored as "this backend is just bad".

  C. LINEAGE (gate0_lineage.py idx binding). The four gold slugs bind to their canonical idx; an
     unregistered benchmark slug fails loud.

The liveness probe is intentionally LEXICALLY separable (the relevant doc shares query tokens, the
junk doc shares none) so the legitimate CPU lexical baseline (token-overlap) ALSO passes — only a
stub/constant scorer fails. ``run_liveness_canary`` is a pure function ``(rerank_fn, ...) -> None``
so the offline smoke can feed it a constant-stub and prove the gate FAILS correctly.
"""

from __future__ import annotations

import math
import os
import sys
from typing import Callable, Sequence

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.dr_benchmark.retrieval_bakeoff.reranker._lineage_seam import (  # noqa: E402
    SLUG_TO_IDX,
    GateZeroLineageError,
    assert_drb_slug_registered,
)

# A RerankFn maps (query, list[doc_text]) -> list[float] score, one per doc, HIGHER = more relevant.
RerankFn = Callable[[str, Sequence[str]], list[float]]

# Floating tolerance for the hand-computed NDCG equality (exact math, generous slack for fp).
_NDCG_TOL = 1e-9

# The four gold-bearing slugs this layer binds (brief §6). Bound to canonical idx via the seam.
GOLD_SLUGS: tuple[str, ...] = (
    "drb_72_ai_labor",
    "drb_75_metal_ions_cvd",
    "drb_76_gut_microbiota_crc",
    "drb_78_parkinsons_dbs",
)


class GateZeroScorerError(RuntimeError):
    """Scorer-math canary failed (NDCG / recall@K math is wrong) — every score is invalid."""


class RerankerLivenessError(RuntimeError):
    """A reranker candidate is non-functional (stub / constant / load-fail) — fail loud, never score."""


# ---------------------------------------------------------------------------------------------
# The credibility-graded NDCG@K scorer + the required-source recall@K guard (the scored metric).
# These are the EXACT functions run_bakeoff scores with, so the canary tests the real math.
# ---------------------------------------------------------------------------------------------
def _dcg(gains: Sequence[float], k: int) -> float:
    """Discounted cumulative gain over the first k positions. Standard DCG = sum g_i / log2(i+2)
    (i 0-indexed -> rank 1..k uses log2(2)..log2(k+1))."""
    total = 0.0
    for i, g in enumerate(gains[:k]):
        total += float(g) / math.log2(i + 2)
    return total


def graded_ndcg_at_k(ranked_gains: Sequence[float], k: int) -> float:
    """Credibility-GRADED NDCG@K: ``ranked_gains`` are the per-position gains in the ORDER the
    reranker produced (gain from the pre-registered table; off-topic == 0). Normalized by the DCG
    of the ideal ordering (gains sorted descending). Returns 0.0 when the ideal DCG is 0 (no signal),
    never raises on empty input."""
    if k <= 0:
        raise GateZeroScorerError(f"NDCG@K requires k>0, got k={k}")
    ideal = _dcg(sorted((float(g) for g in ranked_gains), reverse=True), k)
    if ideal <= 0.0:
        return 0.0
    return _dcg(ranked_gains, k) / ideal


def required_recall_at_k(ranked_required_flags: Sequence[bool], total_required: int, k: int) -> float:
    """Fraction of REQUIRED (sole-supporter) sources that survive in the top-K. This is the
    non-regression guard: a reranker that evicts a required source below K starves the basket. A
    pure re-ORDER count-cut is fine; a SEMANTIC drop is forbidden upstream (the harness never drops).
    total_required==0 -> recall is 1.0 (vacuously satisfied)."""
    if total_required <= 0:
        return 1.0
    if k <= 0:
        raise GateZeroScorerError(f"recall@K requires k>0, got k={k}")
    survived = sum(1 for flag in ranked_required_flags[:k] if flag)
    return survived / float(total_required)


# ---------------------------------------------------------------------------------------------
# Canary A — scorer math.
# ---------------------------------------------------------------------------------------------
def run_scorer_math_canary() -> None:
    """Fail loud unless the NDCG + recall math matches HAND-COMPUTED known values.

    Ideal case: gains [3,2,1] already sorted -> NDCG@3 == 1.0.
    Fractional case (the real discriminator): a SWAP of the top two of [3,2,1,0] to [2,3,1,0].
      DCG@4(actual) = 2/log2(2) + 3/log2(3) + 1/log2(4) + 0
                    = 2/1 + 3/1.5849625007 + 1/2 + 0 = 2 + 1.8927892607 + 0.5 = 4.3927892607
      IDCG@4        = 3/1 + 2/1.5849625007 + 1/2 + 0 = 3 + 1.2618595071 + 0.5 = 4.7618595071
      NDCG@4        = 4.3927892607 / 4.7618595071 = 0.9224945117  (hand-computed below)
    """
    # ---- ideal ordering -> 1.0 (normalization check) ----
    ideal = graded_ndcg_at_k([3, 2, 1], k=3)
    if abs(ideal - 1.0) > _NDCG_TOL:
        raise GateZeroScorerError(f"NDCG ideal-ordering canary: expected 1.0, got {ideal!r}")

    # ---- a scorer that always returns 1.0 must NOT pass; the fractional case discriminates ----
    log2_3 = math.log2(3)
    dcg_actual = 2.0 / 1.0 + 3.0 / log2_3 + 1.0 / 2.0 + 0.0
    idcg = 3.0 / 1.0 + 2.0 / log2_3 + 1.0 / 2.0 + 0.0
    expected_frac = dcg_actual / idcg
    got_frac = graded_ndcg_at_k([2, 3, 1, 0], k=4)
    if abs(got_frac - expected_frac) > _NDCG_TOL:
        raise GateZeroScorerError(
            f"NDCG fractional canary: expected {expected_frac!r}, got {got_frac!r} "
            f"(a constant-1.0 scorer is caught here)"
        )

    # ---- worst ordering (reverse) is strictly < the ideal (and < the fractional swap) ----
    worst = graded_ndcg_at_k([0, 1, 2, 3], k=4)
    if not (worst < got_frac < 1.0 + _NDCG_TOL):
        raise GateZeroScorerError(
            f"NDCG monotonicity canary: expected worst({worst!r}) < swap({got_frac!r}) < 1.0"
        )

    # ---- zero-signal pool -> 0.0, never a divide-by-zero ----
    zero_signal = graded_ndcg_at_k([0, 0, 0], k=3)
    if abs(zero_signal - 0.0) > _NDCG_TOL:
        raise GateZeroScorerError(f"NDCG zero-signal canary: expected 0.0, got {zero_signal!r}")

    # ---- required-source recall@K guard math ----
    # 4 required sources; ranking keeps 3 of them in top-3, evicts 1 below -> recall == 3/4.
    r_kept = required_recall_at_k([True, True, False, True, False], total_required=4, k=3)
    if abs(r_kept - (2.0 / 4.0)) > _NDCG_TOL:
        # top-3 flags == [True, True, False] -> 2 survived of 4 required.
        raise GateZeroScorerError(f"recall@K canary: expected {2/4!r}, got {r_kept!r}")
    r_all = required_recall_at_k([True, True, True, True], total_required=4, k=4)
    if abs(r_all - 1.0) > _NDCG_TOL:
        raise GateZeroScorerError(f"recall@K all-kept canary: expected 1.0, got {r_all!r}")
    r_none_required = required_recall_at_k([False, False], total_required=0, k=2)
    if abs(r_none_required - 1.0) > _NDCG_TOL:
        raise GateZeroScorerError(f"recall@K vacuous canary: expected 1.0, got {r_none_required!r}")


# ---------------------------------------------------------------------------------------------
# Canary B — per-candidate model-wiring liveness (the highest-priority anti-drb_72 check).
# ---------------------------------------------------------------------------------------------
# A LEXICALLY-separable probe: the relevant doc shares query tokens; the junk doc shares NONE. This
# makes the legitimate CPU lexical baseline pass while a stub/constant scorer fails.
LIVENESS_QUERY = "deep brain stimulation for parkinson disease motor symptoms"
LIVENESS_RELEVANT_DOC = (
    "Deep brain stimulation of the subthalamic nucleus improved motor symptoms in patients with "
    "advanced parkinson disease, reducing bradykinesia and tremor in a randomized trial."
)
LIVENESS_JUNK_DOC = (
    "The quarterly municipal recycling schedule lists curbside pickup dates for compost bins and "
    "reminds residents to flatten cardboard boxes before collection."
)


def run_liveness_canary(rerank_fn: RerankFn, *, candidate_name: str) -> None:
    """Fail loud unless ``rerank_fn`` ranks the obviously-relevant doc STRICTLY above the obvious
    junk doc AND the two scores DIFFER. This is a PURE function of the passed callable, so the
    offline smoke can feed it a constant-stub and assert it raises.

    Raises RerankerLivenessError (non-zero exit at the caller) on ANY of: wrong length, NaN/inf,
    constant scores, or relevant<=junk. Never returns a believable low number for a broken model.
    """
    docs = [LIVENESS_RELEVANT_DOC, LIVENESS_JUNK_DOC]
    try:
        scores = rerank_fn(LIVENESS_QUERY, docs)
    except Exception as exc:  # a load-fail / OOM / missing-key surfaces here -> fail loud
        raise RerankerLivenessError(
            f"candidate {candidate_name!r} FAILED to score the liveness probe (load/runtime error): "
            f"{exc!r}. Excluded as non-functional; never scored."
        ) from exc

    if not isinstance(scores, (list, tuple)) or len(scores) != 2:
        raise RerankerLivenessError(
            f"candidate {candidate_name!r} returned {scores!r} (expected 2 numeric scores) — "
            f"stub/empty output, excluded as non-functional."
        )
    try:
        s_rel = float(scores[0])
        s_junk = float(scores[1])
    except (TypeError, ValueError) as exc:
        raise RerankerLivenessError(
            f"candidate {candidate_name!r} returned non-numeric scores {scores!r}: {exc!r}"
        ) from exc

    if not (math.isfinite(s_rel) and math.isfinite(s_junk)):
        raise RerankerLivenessError(
            f"candidate {candidate_name!r} returned non-finite scores rel={s_rel!r} junk={s_junk!r}"
        )
    if s_rel == s_junk:
        raise RerankerLivenessError(
            f"candidate {candidate_name!r} returned a CONSTANT score ({s_rel!r}) for relevant AND "
            f"junk — a load-fail / wrong-template / OOM-fallback model. FAIL LOUD (drb_72 class), "
            f"never accept a believable-looking NDCG from a constant scorer."
        )
    if not (s_rel > s_junk):
        raise RerankerLivenessError(
            f"candidate {candidate_name!r} ranked the JUNK doc >= the relevant doc "
            f"(rel={s_rel!r} <= junk={s_junk!r}) — non-functional / rank-inverted, excluded."
        )


# ---------------------------------------------------------------------------------------------
# Canary C — lineage.
# ---------------------------------------------------------------------------------------------
def run_lineage_canary(slugs: Sequence[str] = GOLD_SLUGS) -> None:
    """Fail loud unless every gold slug is a registered benchmark slug bound to a canonical idx."""
    for slug in slugs:
        assert_drb_slug_registered(slug)  # fail loud on an unregistered drb_* slug
        if slug not in SLUG_TO_IDX:
            raise GateZeroLineageError(
                f"GATE0 reranker: gold slug {slug!r} not bound to a canonical idx in SLUG_TO_IDX."
            )


def run_scorer_and_lineage_gate(slugs: Sequence[str] = GOLD_SLUGS) -> None:
    """The offline-safe portion of GATE-0 (no model loads): scorer math + lineage. The per-candidate
    liveness canary is run separately by run_bakeoff against each LOADED model."""
    run_lineage_canary(slugs)
    run_scorer_math_canary()


def main() -> int:
    try:
        run_scorer_and_lineage_gate()
    except (GateZeroScorerError, GateZeroLineageError) as exc:
        print(f"GATE-0 (scorer+lineage) FAILED: {exc}", file=sys.stderr)
        return 2
    print("GATE-0 scorer-math + lineage canaries GREEN (per-candidate liveness runs in run_bakeoff).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
