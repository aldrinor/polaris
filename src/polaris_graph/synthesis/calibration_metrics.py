"""I-cred-011 (Phase 11) — calibration metrics (Brier / ECE / MCE / reliability bins) — pure offline.

A standalone, deterministic analysis utility for the credibility-weighted sourcing redesign: given
(predicted_confidence, outcome) pairs — e.g. the per-claim ``certainty``/``credibility_weight`` POLARIS
disclosed vs the ground-truth (1 = the claim held up in the §-1.1 line-by-line audit, 0 = it did not) —
compute how well-calibrated those confidences are:

  * ``brier_score``  = mean squared error between predicted probability and outcome (lower = better).
  * ``ece``          = Expected Calibration Error: bin by predicted probability, average the per-bin
                       |mean_predicted − mean_outcome| gaps weighted by bin population.
  * ``mce``          = Max Calibration Error: the worst single-bin gap.
  * ``reliability_bins`` = the per-bin breakdown (the reliability-diagram data).

This is PURE offline math — NO network, NO LLM, NO production caller (it analyses runs post-hoc, so it
needs no default-OFF flag for byte-identity). It does NOT touch any faithfulness gate. The adversarial
vaccine benchmark + the §6b competitor head-to-head + the paid beat-both RUN that CONSUME these metrics
are the spend-bearing follow-up (operator-budget-gated); this module is the cash-free scoring core.
LAW VI: the bin count is env-overridable; snake_case; explicit imports.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

_ENV_BINS = "PG_CALIBRATION_BINS"
_DEFAULT_BINS = 10


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def _coerce_pairs(pairs) -> list[tuple]:
    """Keep only FINITE numeric (predicted, outcome) pairs; clamp predicted to [0,1] and binarize the
    outcome at 0.5. Non-numeric / NaN / inf / malformed pairs are DROPPED (a calibration metric over
    garbage is meaningless, and NaN must never reach the binning or the Brier sum — Codex #1160 P1)."""
    out: list[tuple] = []
    for pair in (pairs or []):
        try:
            predicted, outcome = pair
            predicted_f = float(predicted)
            outcome_f = float(outcome)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(predicted_f) and math.isfinite(outcome_f)):
            continue
        out.append((_clamp01(predicted_f), 1.0 if outcome_f >= 0.5 else 0.0))
    return out


@dataclass
class ReliabilityBin:
    """One [lower, upper) bucket of a reliability diagram.

    Records how many predictions fell in the bucket and their mean predicted
    probability vs mean observed outcome; ``gap`` is the absolute difference
    between the two.
    """

    lower: float
    upper: float
    count: int
    mean_predicted: float
    mean_outcome: float
    gap: float            # |mean_predicted - mean_outcome|


@dataclass
class CalibrationReport:
    """Aggregate calibration metrics over ``n`` prediction/outcome pairs.

    Bundles the Brier score, expected and maximum calibration error (ECE/MCE),
    and the per-bucket ``ReliabilityBin`` list backing the reliability diagram.
    """

    n: int
    brier_score: float
    ece: float
    mce: float
    bins: list


def brier_score(pairs) -> float:
    """Mean squared error between predicted probability and 0/1 outcome (0.0 for no valid pairs)."""
    valid = _coerce_pairs(pairs)
    if not valid:
        return 0.0
    return sum((p - o) ** 2 for p, o in valid) / len(valid)


def reliability_bins(pairs, n_bins: int | None = None) -> list[ReliabilityBin]:
    """Equal-width [0,1] reliability bins (the reliability-diagram data). Empty bins are omitted."""
    if n_bins is None:
        n_bins = _int_env(_ENV_BINS, _DEFAULT_BINS)
    n_bins = max(1, n_bins)
    valid = _coerce_pairs(pairs)
    buckets: list[list[tuple]] = [[] for _ in range(n_bins)]
    for p, o in valid:
        # p == 1.0 lands in the LAST bin (upper-inclusive at the top edge).
        index = min(n_bins - 1, int(p * n_bins))
        buckets[index].append((p, o))
    out: list[ReliabilityBin] = []
    for i, bucket in enumerate(buckets):
        if not bucket:
            continue
        count = len(bucket)
        mean_predicted = sum(p for p, _ in bucket) / count
        mean_outcome = sum(o for _, o in bucket) / count
        out.append(ReliabilityBin(
            lower=i / n_bins,
            upper=(i + 1) / n_bins,
            count=count,
            mean_predicted=mean_predicted,
            mean_outcome=mean_outcome,
            gap=abs(mean_predicted - mean_outcome),
        ))
    return out


def calibration_report(pairs, n_bins: int | None = None) -> CalibrationReport:
    """Full calibration report: n, Brier, ECE (population-weighted mean gap), MCE (max gap), and bins."""
    valid = _coerce_pairs(pairs)
    n = len(valid)
    bins = reliability_bins(valid, n_bins)
    ece = sum((b.count / n) * b.gap for b in bins) if n else 0.0
    mce = max((b.gap for b in bins), default=0.0)
    return CalibrationReport(
        n=n,
        brier_score=brier_score(valid),
        ece=ece,
        mce=mce,
        bins=bins,
    )
