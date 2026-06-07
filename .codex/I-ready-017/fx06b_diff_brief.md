# I-ready-017 FX-06b (#1121) — DIFF gate (iter 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## What this implements (#1121 — the two non-required P2 follow-ups of FX-06 #1120)
Diff: `.codex/I-ready-017/fx06b_codex_diff.patch` (base eb92c3a6^..HEAD; 5 files). Non-rerun-gating.

1. **tier_counts equality.** The FX-06 corpus-population invariant compared only `total_sources`, so
   a same-SIZE tier mismatch would pass. Strengthened to
   `adequacy.total_sources != dist.total_sources OR dict(adequacy.tier_counts) != dict(dist.tier_counts)`.
2. **Named abort status.** The invariant raised a generic `RuntimeError` -> outer handler ->
   `error_unexpected`. Now (inside run_one_query, mirroring the abort_corpus_inadequate inline
   pattern) it emits `summary.status = "error_corpus_population_mismatch"` + a named abort-manifest
   (recording BOTH populations' total + tier_counts) + a pipeline-verdict report.md + returns.
   Registered across all 4 taxonomy surfaces: scripts/run_honest_sweep_r3.UNIFIED_STATUS_VALUES +
   _SUMMARY_TO_UNIFIED (self-map), src/polaris_v6/schemas/run_status.PipelineStatus,
   src/polaris_graph/audit_ir/regression_lab._STATUS_TIERS (tier 3) -> KNOWN_STATUS_VALUES; and the
   test_manifest_contract expected set (lock-step).

## §-1.1 on the REAL held drb_72 artifact (outputs/audits/I-ready-017/fx06b_s11_audit.md)
corpus_approval.json (total 145, tier_counts {T1:54,T2:3,T4:46,T5:2,T6:9,T7:12,UNKNOWN:19}) vs
corpus_adequacy.json (total 45, {T1:6,T2:3,T4:23,T5:2,T6:7,UNKNOWN:4}) diverge on BOTH total AND
every tier. The total-only check already catches THIS held case; the tier_counts strengthening is
additive coverage for the equal-total tier-skew class the held bug did not exhibit.

## Offline evidence
`pytest tests/polaris_graph/test_fx06_approval_population_iready017.py` -> 5 passed (2 existing +
3 new: tier-skew caught at equal total / no-false-positive when matched / named status registered in
UNIFIED + _SUMMARY_TO_UNIFIED + KNOWN_STATUS_VALUES + PipelineStatus). test_manifest_contract
taxonomy-lockstep tests pass (the lone failure `not_applicable_planner_lane` is the pre-existing
#1135 gap — confirmed unrelated by stash-and-rerun on a prior leg). py_compile clean on all 3 source files.

## Faithfulness
Strengthens a pre-generator corpus-population refusal (invariant #5 territory): refuses more
precisely (catches a divergence class the total-only check missed), self-documents the refusal; never
approves a divergent population. No strict_verify / provenance / 4-role / two-family change.
Defensive guard — should never fire (all merge paths recompute adequacy from the same dist).

## Questions
1. Is the strengthened condition + the named inline abort-emit (status + manifest + report.md +
   return) correct and consistent with the abort_corpus_inadequate pattern in the same function?
2. Is the 4-surface status registration complete + consistent (no taxonomy drift)?
3. Any faithfulness / correctness gap before APPROVE?
