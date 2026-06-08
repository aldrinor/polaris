"""I-cred-011 (Phase 11) — calibration metrics. Offline, deterministic, no network."""
from __future__ import annotations

import math

from src.polaris_graph.synthesis.calibration_metrics import (
    brier_score,
    calibration_report,
    reliability_bins,
)


def test_brier_perfect_and_worst():
    assert brier_score([(0.0, 0), (1.0, 1)]) == 0.0
    assert brier_score([(0.0, 1), (1.0, 0)]) == 1.0          # worst: ((0-1)^2 + (1-0)^2)/2
    assert abs(brier_score([(0.7, 1)]) - 0.09) < 1e-9        # (0.7-1)^2


def test_perfect_calibration_zero_ece():
    rep = calibration_report([(0.0, 0), (1.0, 1)])
    assert rep.n == 2 and rep.brier_score == 0.0 and rep.ece == 0.0 and rep.mce == 0.0


def test_overconfident_bin_has_gap():
    rep = calibration_report([(0.9, 0), (0.9, 0)])           # predicted 0.9, never happened
    assert abs(rep.brier_score - 0.81) < 1e-9
    assert abs(rep.ece - 0.9) < 1e-9 and abs(rep.mce - 0.9) < 1e-9
    assert len(rep.bins) == 1 and rep.bins[0].count == 2 and abs(rep.bins[0].gap - 0.9) < 1e-9


def test_well_calibrated_bin_zero_gap():
    # 10 predictions at 0.7, 7 positives -> mean_outcome 0.7 == mean_predicted -> gap 0
    rep = calibration_report([(0.7, 1)] * 7 + [(0.7, 0)] * 3)
    assert len(rep.bins) == 1
    assert abs(rep.bins[0].mean_predicted - 0.7) < 1e-9
    assert abs(rep.bins[0].mean_outcome - 0.7) < 1e-9
    assert abs(rep.bins[0].gap) < 1e-9 and abs(rep.ece) < 1e-9


def test_p_one_lands_in_last_bin():
    bins = reliability_bins([(1.0, 1)], n_bins=10)
    assert len(bins) == 1
    assert abs(bins[0].lower - 0.9) < 1e-9 and abs(bins[0].upper - 1.0) < 1e-9


def test_malformed_pairs_dropped():
    rep = calibration_report([(0.9, 0), ("bad", 1), (None, 0), (0.9, 0)])
    assert rep.n == 2  # only the 2 valid (0.9, 0) pairs


def test_empty_safe_defaults():
    rep = calibration_report([])
    assert rep.n == 0 and rep.brier_score == 0.0 and rep.ece == 0.0 and rep.mce == 0.0 and rep.bins == []


def test_env_bin_count(monkeypatch):
    monkeypatch.setenv("PG_CALIBRATION_BINS", "2")
    bins = reliability_bins([(0.2, 0), (0.8, 1)])  # 2 bins: [0,0.5), [0.5,1.0]
    assert len(bins) == 2 and abs(bins[0].upper - 0.5) < 1e-9


def test_outcome_coerced_to_binary():
    assert brier_score([(1.0, 0.9)]) == 0.0  # outcome 0.9 -> 1, predicted 1.0
    assert brier_score([(0.0, 0.4)]) == 0.0  # outcome 0.4 -> 0, predicted 0.0


def test_non_finite_pairs_dropped():
    """Codex #1160 P1: NaN/inf in predicted or outcome must be DROPPED, never crash the binning or
    produce a NaN metric."""
    rep = calibration_report([
        (float("nan"), 1), (0.9, float("inf")), (float("-inf"), 0), (0.9, 0), (0.9, 0),
    ])
    assert rep.n == 2  # only the two valid (0.9, 0) pairs survive
    assert math.isfinite(rep.brier_score) and math.isfinite(rep.ece) and math.isfinite(rep.mce)
    assert brier_score([(float("nan"), 1)]) == 0.0  # all-NaN input -> no valid pairs -> 0.0
