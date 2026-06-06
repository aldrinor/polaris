# FX-06 §-1.1 audit — corpus-approval scores SAME population as adequacy + report (#1120)

**Standard:** §-1.1 on the REAL held drb_72 `run_artifacts/corpus_approval.json` vs
`corpus_adequacy.json` (both are run-time OUTPUT, so the divergence is confirmed on the real
artifacts; the fix is an artifact-write re-ordering proven by component smoke + verified by a fresh
run at RERUN).

## The bug, on the real artifacts (line-by-line)
- `corpus_approval.json` → `report.total_sources = 145`, `report.tier_fractions.T4 = 0.3172`.
- `corpus_adequacy.json` → `total_sources = 45`, `tier_counts = {T1:6,T2:3,T4:23,T5:2,T6:7,UNKNOWN:4}`
  (sum = 45).
- **DIVERGE: 145 ≠ 45.** The corpus-approval gate scored a 145-source set (the post-agentic dist,
  padded with the ~100 nav/conference junk URLs FX-15b now removes) while corpus_adequacy.json — and
  the report's Methods "Actual distribution" — described the 45-source evidence-backed set. A
  quality gate scoring a WIDER pre-filter pool than the dataset downstream consumes is the
  gate-on-the-wrong-population anti-pattern (lethal in clinical: the gate's tier mix is not the
  delivered tier mix).

Root cause (verified in `run_honest_sweep_r3.py`): `corpus_adequacy.json` is written PRE-merge
(~2535 base / ~2698 expansion); the deepener + agentic merges reassign `dist`/`adequacy` in memory
(~2971-2975) but NEVER re-wrote the JSON; the approval decision (`report=dist`, ~3093) scores the
final post-merge `dist`.

## The fix (artifact-only; abort control-flow UNCHANGED)
After `_flush_retrieval_trace()` and BEFORE the inadequate-abort, re-write `corpus_adequacy.json`
ONCE from the FINAL `adequacy` (post base + expansion + deepener + agentic), so adequacy + approval
+ report all describe the SAME delivered corpus on every exit path. Plus a fail-loud invariant:
`adequacy.total_sources == dist.total_sources` (both are `sum(tier_counts)`) — refuses to proceed if
a future merge reassigns `dist` without recomputing `adequacy` from it. The abort decision still
uses the in-memory `adequacy.decision`, so the pre-spend gate timing is unchanged (invariant #5
preserved: still aborts BEFORE any generator token).

## Offline smoke (proves the invariant the fix relies on)
`pytest tests/polaris_graph/test_fx06_approval_population_iready017.py` → 2 passed:
- **invariant holds**: `compute_tier_distribution(srcs).total_sources == assess_corpus_adequacy(
  tier_counts=that dist, ...).total_sources` (45 == 45) — so writing adequacy from the final dist
  makes the two artifacts agree.
- **divergence detected**: a PRE-merge adequacy (45) vs the POST-merge approval dist (145) are
  unequal — the exact held bug shape (45, 145) the fail-loud invariant catches.
- Regression: 425 passed across corpus_approval enforcement (b2), adequacy gate, manifest contract,
  run-events, etc.

## Faithfulness check
Cost/telemetry-correctness of the GATE population. The re-write is artifact-only; the approval abort
short-circuit (no generator tokens on an unapproved corpus, invariant #5) is untouched. The fail-loud
invariant is fail-CLOSED (refuses to proceed on divergence) per LAW II. No grounding / strict_verify
/ 4-role change. The DELIVERED tier mix the gate now scores == the mix the report consumes.
