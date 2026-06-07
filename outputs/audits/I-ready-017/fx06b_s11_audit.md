# §-1.1 audit — FX-06b (#1121): corpus-population invariant (tier_counts + named status)

**Standard:** §-1.1 on the REAL held drb_72 artifacts
(`outputs/audits/I-ready-017/run_artifacts/`: `corpus_approval.json` vs `corpus_adequacy.json`).
FX-06b is two non-required P2 follow-ups of FX-06 (#1120): (1) strengthen the corpus-population
invariant to also compare `tier_counts` (not just `total_sources`); (2) emit a NAMED
`error_corpus_population_mismatch` abort-manifest instead of a generic `RuntimeError ->
error_unexpected`. Faithfulness-adjacent (corpus approval = invariant #5).

## The held divergence (claim-by-claim)

CLAIM: the corpus-approval gate scored a DIFFERENT population than the corpus_adequacy artifact +
the report consumed (the FX-06 bug).

EVIDENCE (held artifacts):
- `corpus_approval.json`: total_sources = **145**, tier_counts = `{T1:54, T2:3, T4:46, T5:2, T6:9, T7:12, UNKNOWN:19}`.
- `corpus_adequacy.json`: total_sources = **45**, tier_counts = `{T1:6, T2:3, T4:23, T5:2, T6:7, UNKNOWN:4}`.

VERDICT: **CONFIRMED divergence on BOTH axes.** total_sources differs (145 vs 45) AND the tier
composition differs on every tier (T1 54 vs 6, T4 46 vs 23, T7 12 vs 0, UNKNOWN 19 vs 4). The FX-06
total-only invariant already catches THIS held case (145 != 45). FX-06b adds the `tier_counts`
dimension, which closes the residual gap: a FUTURE divergence where the two populations happen to
have the SAME total but a different tier mix (e.g. a T1 swapped for a T4) would pass the total-only
check yet still mean the gate scored a population the report does not consume. The held bug did not
exhibit that exact shape (its totals already differ), so the strengthening is ADDITIVE defensive
coverage, not a fix for a currently-firing case.

## The fix (verified)
1. The invariant condition is now
   `adequacy.total_sources != dist.total_sources OR dict(adequacy.tier_counts) != dict(dist.tier_counts)`.
   Component test `test_fx06b_tier_counts_divergence_caught_at_equal_total` builds an adequacy whose
   tier_counts differs from a dist's at an EQUAL total (45 == 45, one T1 -> T4) and asserts the
   strengthened condition fires where the total-only check would not.
   `test_fx06b_no_false_positive_when_populations_match` confirms no false abort when adequacy is
   written from the same dist (total AND tier_counts identical).
2. On a mismatch the run emits `summary.status = "error_corpus_population_mismatch"` + a named
   abort-manifest (with both populations' total + tier_counts recorded) + a pipeline-verdict
   report.md, then returns — instead of raising a generic RuntimeError that the outer handler
   converts to `error_unexpected`. The status is registered across all four taxonomy surfaces
   (UNIFIED_STATUS_VALUES, _SUMMARY_TO_UNIFIED, v6 PipelineStatus, regression_lab
   KNOWN_STATUS_VALUES); `test_fx06b_named_status_registered_in_all_taxonomies` +
   test_manifest_contract lock-step assert it.

## Faithfulness
The corpus-population invariant is a pre-generator abort (invariant #5 territory): the change
STRENGTHENS it (catches a divergence class the total-only check missed) and makes the refusal
self-documenting. It can only refuse MORE precisely, never approve a divergent population. No
strict_verify / provenance / 4-role / two-family change. Defensive guard — should never fire in
normal operation (all merge paths recompute adequacy from the same dist).

## Offline evidence
`pytest tests/polaris_graph/test_fx06_approval_population_iready017.py` -> 5 passed (2 existing +
3 new). `test_manifest_contract.py` taxonomy-lockstep tests pass (the new status present + mirrored
across UNIFIED/KNOWN/expected; the lone failure `not_applicable_planner_lane` is the pre-existing
#1135 gap, confirmed unrelated by stash-and-rerun). py_compile clean across all 3 touched source files.
