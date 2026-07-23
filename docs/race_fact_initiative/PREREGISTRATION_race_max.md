# Pre-registration — RACE max-arm measurement (written BEFORE draw 1 completes)

Timestamp basis: written 2026-07-23, ~11:45Z, before any draw score is known.
Decision partner: Fable (consulted 2026-07-23). Operator asleep; consult-Fable-for-decisions standing order.

## What is being measured
- Config "max" = 8 retained champion levers (PG_SECTION_STRUCTURE, PG_SYNTHESIS_TABLE_CONSTRUCT,
  PG_SUMMARY_TABLE_COMPOSE, PG_PROMPT_SCOPE_WEIGHTING, PG_NARRATIVE_ATTRIBUTION,
  PG_FACET_EVIDENCE_PACKS, PG_BASKET_SYNTHESIS, PG_COVERAGE_OBLIGATIONS)
  + Batch 3 (PG_CONTRADICTION_MINING, PG_RELATION_EVIDENCE_PACKS).
- Generator: Kimi-K3. Task: DRB task-72 (AI & labor-market literature review). Corpus: cp4_corpus_s3gear_329.
- n = 3 independent generator draws, each scored once by the real RACE judge (gpt-5.5). Report mean + spread.
- Per-draw timeout 5400s (90 min). Harness: scripts/run_race_max_focus.sh (ARMS=max).

## Reference points (established, not re-measured tonight)
- Our champion: 0.5084.  Pre-gen redesign draw: 0.5062.
- Field top on our tested board: ADORE 0.5265, Tavily 0.5244.

## SCOPE CAVEAT (critical for honesty — Fable Q4.1)
This measurement is TASK-72 ONLY. ADORE's 0.5265 is self-reported bench-wide in the Atlassian paper
(per tonight's research; ADORE is not on the live leaderboard). Comparing a task-72 mean to a bench-wide
number is apples-to-oranges. Therefore:
  - Any "beats ADORE / beats the field" claim MUST be scoped: "on task-72, vs ADORE's reported score."
  - The defensible headline claim is vs our own champion 0.5084 (same task, same harness lineage).

## PRE-REGISTERED WIN CRITERIA (locked before seeing draw 1)
1. CHAMPION-BEAT (defensible, primary): max mean > 0.5084 AND (mean − 0.5084) ≥ ~0.014 (clears the
   baseline_triple noise floor) AND spread ≤ ~0.010. Below that = FLAT (no real gain) — report honestly.
2. FIELD-WIN (task-72 scoped, secondary): max mean ≥ 0.5265 AND (mean − 0.5265) ≥ spread AND spread ≤ ~0.007.
   A mean of 0.528 with spread 0.02 is NOT a win.
3. No draw dropping: n=3 means all 3 count. A rerun is allowed ONLY for infrastructure failure
   (K3 outage mid-draw), logged as such — never "best 3 of 4."
4. Judge identity: confirm/log the actual RACE judge model ID from the score output.

## Drift control (Fable Q1)
Re-score the stored champion report outputs/champ_clean_1/report.md with tonight's judge, in parallel.
- Expect ~0.508. If tonight's judge gives it that, drift is ruled out and the 0.5084 comparison holds.
- If it gives materially different (e.g. 0.48 / 0.53), note a calibration footnote on the whole night.

## DRIFT CHECK RESULT (2026-07-23 ~11:47Z) — DRIFT DETECTED
Re-scored stored champion-recipe report outputs/champ_clean_1/report.md on tonight's judge:
  Overall 0.4718 (Comp 0.4842 / Insight 0.4728 / IF 0.4652 / Read 0.4541). Expected ~0.508.
Gap = -0.036. TWO confounds, so this is NOT a clean baseline:
  (a) possible judge drift (tonight's judge harsher than the one behind historical 0.5084), AND
  (b) champ_clean_1 is dated Jul-21 and PREDATES the 8-lever "full" set (built Jul-22) — it is an
      OLDER champion-recipe report, not the current config.
CONSEQUENCE: historical numbers (0.5084, ADORE 0.5265, Tavily 0.5244) are NOT comparable to tonight's
scores. The ONLY defensible comparison is WITHIN tonight's judge. => must generate fresh same-judge
baselines tonight (full = 8 champion levers; baseline = all off). "Beat ADORE/field" is effectively
NOT defensibly claimable tonight (cross-judge + task-72-vs-benchwide). Honest deliverable = within-judge
delta: does max (champ levers + Batch3) beat full (champ levers) and baseline, same judge, tonight?

REVISED WIN CRITERION (within tonight's judge):
  - Batch-3 real gain: max mean − full mean ≥ ~0.014 AND spreads ≤ ~0.010.
  - Full-stack gain: max mean − baseline mean ≥ ~0.014.
  - Report all three arm means + spreads honestly; no cross-judge "beat everyone" claim.

## Branch on result
- FLAT (~0.508 ± noise): STOP. Honest morning summary: "does not beat the field; here is the real number."
- HIGH (>0.52): THEN run a fresh same-harness baseline arm before making any claim (a surprising win
  needs its own drift-controlled baseline, not just the historical reference).
