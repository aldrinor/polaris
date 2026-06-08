HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings; reserve P0/P1 for real execution blockers; classify cosmetic as P2/P3. APPROVE iff zero P0 AND zero P1.

# DIFF GATE — credibility redesign build phase (umbrella I-ready-021 #1148)

Review the NEW-MODULE diff below for code correctness against its plan-phase spec
(`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md`). This is faithfulness-adjacent code.

## HARD CONSTRAINTS (operator-locked)
- **Default-OFF byte-identical:** the module must be inert unless explicitly invoked by a flag/caller; turning it OFF (or not wiring it) leaves existing behavior byte-identical. No production path is changed in this phase.
- **Faithfulness gates UNTOUCHED:** strict_verify (`provenance_generator.py`), 4-role D8, two-family segregation, corpus_approval are NOT edited or weakened. This phase is a NEW module only.
- **LAW VI:** no hardcoded thresholds/paths — config/env; snake_case; no magic numbers; no live data in unit tests (fixtures only).

## VERIFY SPECIFICALLY
1. The module implements its plan-phase spec correctly (read the named layer/phase in the plan).
2. **The phase invariant is actually enforced AND tested** (e.g. P4: a copied row joining a cluster — even higher-authority — cannot change the cluster set / canonical origin; P5: recall-first contradictions + conservative-singleton never over-merges; P3: retraction hard-penalty + config thresholds).
3. The unit tests are MEANINGFUL (not assertion-relaxed to pass) and the attached SMOKE result is green.
4. No faithfulness gate is touched; nothing in the production path changes with the module un-wired.

## SMOKE EVIDENCE (attached below the diff — the offline pytest result is the evidence, not a self-report)

## OUTPUT SCHEMA (YAML)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

============ THE DIFF + SMOKE EVIDENCE ============
## PHASE: P11 calibration metrics (#1160) — DIFF gate ITER 2. Iter-1 REQUEST_CHANGES (1 P1) addressed: _coerce_pairs now DROPS non-finite values — math.isfinite(predicted) AND math.isfinite(outcome) required, so NaN/inf in either field is dropped (never reaches int(p*n_bins) binning, never produces a NaN Brier, never silently coerces a NaN outcome to 0). Regression test_non_finite_pairs_dropped (nan/inf/-inf predicted+outcome all dropped; metrics finite; all-NaN -> 0.0). SMOKE: 10 passed.
```diff
diff --git a/src/polaris_graph/synthesis/calibration_metrics.py b/src/polaris_graph/synthesis/calibration_metrics.py
new file mode 100644
index 00000000..ba6c601b
--- /dev/null
+++ b/src/polaris_graph/synthesis/calibration_metrics.py
@@ -0,0 +1,129 @@
+"""I-cred-011 (Phase 11) — calibration metrics (Brier / ECE / MCE / reliability bins) — pure offline.
+
+A standalone, deterministic analysis utility for the credibility-weighted sourcing redesign: given
+(predicted_confidence, outcome) pairs — e.g. the per-claim ``certainty``/``credibility_weight`` POLARIS
+disclosed vs the ground-truth (1 = the claim held up in the §-1.1 line-by-line audit, 0 = it did not) —
+compute how well-calibrated those confidences are:
+
+  * ``brier_score``  = mean squared error between predicted probability and outcome (lower = better).
+  * ``ece``          = Expected Calibration Error: bin by predicted probability, average the per-bin
+                       |mean_predicted − mean_outcome| gaps weighted by bin population.
+  * ``mce``          = Max Calibration Error: the worst single-bin gap.
+  * ``reliability_bins`` = the per-bin breakdown (the reliability-diagram data).
+
+This is PURE offline math — NO network, NO LLM, NO production caller (it analyses runs post-hoc, so it
+needs no default-OFF flag for byte-identity). It does NOT touch any faithfulness gate. The adversarial
+vaccine benchmark + the §6b competitor head-to-head + the paid beat-both RUN that CONSUME these metrics
+are the spend-bearing follow-up (operator-budget-gated); this module is the cash-free scoring core.
+LAW VI: the bin count is env-overridable; snake_case; explicit imports.
+"""
+from __future__ import annotations
+
+import math
+import os
+from dataclasses import dataclass
+
+_ENV_BINS = "PG_CALIBRATION_BINS"
+_DEFAULT_BINS = 10
+
+
+def _int_env(name: str, default: int) -> int:
+    try:
+        value = int(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+    return value if value > 0 else default
+
+
+def _clamp01(value: float) -> float:
+    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value
+
+
+def _coerce_pairs(pairs) -> list[tuple]:
+    """Keep only FINITE numeric (predicted, outcome) pairs; clamp predicted to [0,1] and binarize the
+    outcome at 0.5. Non-numeric / NaN / inf / malformed pairs are DROPPED (a calibration metric over
+    garbage is meaningless, and NaN must never reach the binning or the Brier sum — Codex #1160 P1)."""
+    out: list[tuple] = []
+    for pair in (pairs or []):
+        try:
+            predicted, outcome = pair
+            predicted_f = float(predicted)
+            outcome_f = float(outcome)
+        except (TypeError, ValueError):
+            continue
+        if not (math.isfinite(predicted_f) and math.isfinite(outcome_f)):
+            continue
+        out.append((_clamp01(predicted_f), 1.0 if outcome_f >= 0.5 else 0.0))
+    return out
+
+
+@dataclass
+class ReliabilityBin:
+    lower: float
+    upper: float
+    count: int
+    mean_predicted: float
+    mean_outcome: float
+    gap: float            # |mean_predicted - mean_outcome|
+
+
+@dataclass
+class CalibrationReport:
+    n: int
+    brier_score: float
+    ece: float
+    mce: float
+    bins: list
+
+
+def brier_score(pairs) -> float:
+    """Mean squared error between predicted probability and 0/1 outcome (0.0 for no valid pairs)."""
+    valid = _coerce_pairs(pairs)
+    if not valid:
+        return 0.0
+    return sum((p - o) ** 2 for p, o in valid) / len(valid)
+
+
+def reliability_bins(pairs, n_bins: int | None = None) -> list[ReliabilityBin]:
+    """Equal-width [0,1] reliability bins (the reliability-diagram data). Empty bins are omitted."""
+    if n_bins is None:
+        n_bins = _int_env(_ENV_BINS, _DEFAULT_BINS)
+    n_bins = max(1, n_bins)
+    valid = _coerce_pairs(pairs)
+    buckets: list[list[tuple]] = [[] for _ in range(n_bins)]
+    for p, o in valid:
+        # p == 1.0 lands in the LAST bin (upper-inclusive at the top edge).
+        index = min(n_bins - 1, int(p * n_bins))
+        buckets[index].append((p, o))
+    out: list[ReliabilityBin] = []
+    for i, bucket in enumerate(buckets):
+        if not bucket:
+            continue
+        count = len(bucket)
+        mean_predicted = sum(p for p, _ in bucket) / count
+        mean_outcome = sum(o for _, o in bucket) / count
+        out.append(ReliabilityBin(
+            lower=i / n_bins,
+            upper=(i + 1) / n_bins,
+            count=count,
+            mean_predicted=mean_predicted,
+            mean_outcome=mean_outcome,
+            gap=abs(mean_predicted - mean_outcome),
+        ))
+    return out
+
+
+def calibration_report(pairs, n_bins: int | None = None) -> CalibrationReport:
+    """Full calibration report: n, Brier, ECE (population-weighted mean gap), MCE (max gap), and bins."""
+    valid = _coerce_pairs(pairs)
+    n = len(valid)
+    bins = reliability_bins(valid, n_bins)
+    ece = sum((b.count / n) * b.gap for b in bins) if n else 0.0
+    mce = max((b.gap for b in bins), default=0.0)
+    return CalibrationReport(
+        n=n,
+        brier_score=brier_score(valid),
+        ece=ece,
+        mce=mce,
+        bins=bins,
+    )
diff --git a/tests/polaris_graph/synthesis/test_calibration_metrics_phase11.py b/tests/polaris_graph/synthesis/test_calibration_metrics_phase11.py
new file mode 100644
index 00000000..253ccace
--- /dev/null
+++ b/tests/polaris_graph/synthesis/test_calibration_metrics_phase11.py
@@ -0,0 +1,75 @@
+"""I-cred-011 (Phase 11) — calibration metrics. Offline, deterministic, no network."""
+from __future__ import annotations
+
+import math
+
+from src.polaris_graph.synthesis.calibration_metrics import (
+    brier_score,
+    calibration_report,
+    reliability_bins,
+)
+
+
+def test_brier_perfect_and_worst():
+    assert brier_score([(0.0, 0), (1.0, 1)]) == 0.0
+    assert brier_score([(0.0, 1), (1.0, 0)]) == 1.0          # worst: ((0-1)^2 + (1-0)^2)/2
+    assert abs(brier_score([(0.7, 1)]) - 0.09) < 1e-9        # (0.7-1)^2
+
+
+def test_perfect_calibration_zero_ece():
+    rep = calibration_report([(0.0, 0), (1.0, 1)])
+    assert rep.n == 2 and rep.brier_score == 0.0 and rep.ece == 0.0 and rep.mce == 0.0
+
+
+def test_overconfident_bin_has_gap():
+    rep = calibration_report([(0.9, 0), (0.9, 0)])           # predicted 0.9, never happened
+    assert abs(rep.brier_score - 0.81) < 1e-9
+    assert abs(rep.ece - 0.9) < 1e-9 and abs(rep.mce - 0.9) < 1e-9
+    assert len(rep.bins) == 1 and rep.bins[0].count == 2 and abs(rep.bins[0].gap - 0.9) < 1e-9
+
+
+def test_well_calibrated_bin_zero_gap():
+    # 10 predictions at 0.7, 7 positives -> mean_outcome 0.7 == mean_predicted -> gap 0
+    rep = calibration_report([(0.7, 1)] * 7 + [(0.7, 0)] * 3)
+    assert len(rep.bins) == 1
+    assert abs(rep.bins[0].mean_predicted - 0.7) < 1e-9
+    assert abs(rep.bins[0].mean_outcome - 0.7) < 1e-9
+    assert abs(rep.bins[0].gap) < 1e-9 and abs(rep.ece) < 1e-9
+
+
+def test_p_one_lands_in_last_bin():
+    bins = reliability_bins([(1.0, 1)], n_bins=10)
+    assert len(bins) == 1
+    assert abs(bins[0].lower - 0.9) < 1e-9 and abs(bins[0].upper - 1.0) < 1e-9
+
+
+def test_malformed_pairs_dropped():
+    rep = calibration_report([(0.9, 0), ("bad", 1), (None, 0), (0.9, 0)])
+    assert rep.n == 2  # only the 2 valid (0.9, 0) pairs
+
+
+def test_empty_safe_defaults():
+    rep = calibration_report([])
+    assert rep.n == 0 and rep.brier_score == 0.0 and rep.ece == 0.0 and rep.mce == 0.0 and rep.bins == []
+
+
+def test_env_bin_count(monkeypatch):
+    monkeypatch.setenv("PG_CALIBRATION_BINS", "2")
+    bins = reliability_bins([(0.2, 0), (0.8, 1)])  # 2 bins: [0,0.5), [0.5,1.0]
+    assert len(bins) == 2 and abs(bins[0].upper - 0.5) < 1e-9
+
+
+def test_outcome_coerced_to_binary():
+    assert brier_score([(1.0, 0.9)]) == 0.0  # outcome 0.9 -> 1, predicted 1.0
+    assert brier_score([(0.0, 0.4)]) == 0.0  # outcome 0.4 -> 0, predicted 0.0
+
+
+def test_non_finite_pairs_dropped():
+    """Codex #1160 P1: NaN/inf in predicted or outcome must be DROPPED, never crash the binning or
+    produce a NaN metric."""
+    rep = calibration_report([
+        (float("nan"), 1), (0.9, float("inf")), (float("-inf"), 0), (0.9, 0), (0.9, 0),
+    ])
+    assert rep.n == 2  # only the two valid (0.9, 0) pairs survive
+    assert math.isfinite(rep.brier_score) and math.isfinite(rep.ece) and math.isfinite(rep.mce)
+    assert brier_score([(float("nan"), 1)]) == 0.0  # all-NaN input -> no valid pairs -> 0.0
```
