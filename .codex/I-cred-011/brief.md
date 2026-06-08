# I-cred-011 (#1160) — Phase 11: calibration metrics (pure offline scoring core) — BRIEF for Codex

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd on remaining-non-P0/P1; no iter 6.
- Surface any held-back P1 NOW. Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Reviewing a DESIGN BRIEF (acceptance-criteria correctness), not a diff. The module + 9 offline tests are
already written (smoke-as-evidence below); judge the contract + the metric correctness.

## 0. HARD CONSTRAINTS

- **Cash-free, offline, pure.** This module is the SCORING CORE only — deterministic math over
  (predicted_confidence, outcome) pairs. NO network, NO LLM, NO production caller (it analyses runs
  post-hoc). It touches NO faithfulness gate. snake_case, explicit imports, LAW VI (bin count env-overridable).
- **Spend stays gated.** The adversarial vaccine benchmark, the §6b competitor head-to-head harness, and
  the paid beat-both RUN that CONSUME these metrics are the operator-budget-gated follow-up (I-cred-011b) —
  NOT in this issue. This issue ships ZERO spend.

## 1. SCOPE (confirm)

Pure calibration-metrics module `src/polaris_graph/synthesis/calibration_metrics.py`: Brier score, ECE,
MCE, and the reliability-bin breakdown. The benchmark/competitor/run harness is I-cred-011b (spend-gated).
**Q1:** confirm this split.

## 2. Contract + metric definitions

```python
@dataclass
class ReliabilityBin:  lower, upper, count, mean_predicted, mean_outcome, gap   # gap = |mean_pred - mean_out|
@dataclass
class CalibrationReport: n, brier_score, ece, mce, bins

def brier_score(pairs) -> float:           # mean((p - o)^2); 0.0 for no valid pairs
def reliability_bins(pairs, n_bins=None) -> list[ReliabilityBin]   # equal-width [0,1] bins; empty bins omitted
def calibration_report(pairs, n_bins=None) -> CalibrationReport
```

- `pairs` = iterable of `(predicted_confidence ∈ [0,1], outcome)`; the source is POLARIS's disclosed
  per-claim certainty/credibility vs the ground-truth (1 = the claim held up in the §-1.1 line-by-line
  audit, 0 = it did not).
- **Coercion:** predicted clamped to [0,1]; **outcome binarized** (≥0.5 → 1 else 0); malformed/non-numeric
  pairs DROPPED (a calibration metric over garbage is meaningless).
- **Brier** = mean squared error (lower = better calibrated + sharper).
- **Bin assignment:** `index = min(n_bins-1, int(p*n_bins))` so `p == 1.0` lands in the LAST bin.
- **ECE** = Σ over bins of `(count/n) * gap` (population-weighted mean gap).
- **MCE** = max single-bin gap.

## 3. Acceptance criteria (offline, deterministic, no network — already passing, 9 tests)

1. `brier_score([(0,0),(1,1)]) == 0.0`; `brier_score([(0,1),(1,0)]) == 1.0`; `brier_score([(0.7,1)]) == 0.09`.
2. Perfect calibration → ECE 0, MCE 0.
3. Over-confident bin: `[(0.9,0),(0.9,0)]` → brier 0.81, ECE 0.9, MCE 0.9, one bin gap 0.9.
4. Well-calibrated bin: 7×(0.7,1)+3×(0.7,0) → mean_predicted == mean_outcome == 0.7, gap 0, ECE 0.
5. `p == 1.0` lands in the last bin `[0.9, 1.0]`.
6. Malformed pairs (`("bad",1)`, `(None,0)`) dropped; `n` counts only valid pairs.
7. Empty input → n 0, all metrics 0.0, bins [].
8. `PG_CALIBRATION_BINS` env knob changes the bin count.
9. Outcome binarized: `(1.0, 0.9)` and `(0.0, 0.4)` both Brier 0.

## 4. SMOKE (evidence): 9 passed (`tests/polaris_graph/synthesis/test_calibration_metrics_phase11.py`).

## 5. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## 6. Questions

Q1 scope split (metrics now; benchmark/competitor/paid-run harness I-cred-011b)? Q2 is the outcome-binarize-at-0.5 + drop-malformed coercion the right policy, or do you want strict input validation that raises? Q3 ECE definition — population-weighted mean gap is standard; confirm vs a fixed-bin-count debiased variant.
