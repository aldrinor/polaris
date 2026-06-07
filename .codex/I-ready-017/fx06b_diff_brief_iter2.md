# I-ready-017 FX-06b (#1121) — DIFF gate (iter 2 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
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

## iter-1 finding addressed
**P1-1 (early-return skipped teardown) — FIXED (commit b523df4a).** The
`error_corpus_population_mismatch` branch now runs the EXACT same early-abort teardown as the
neighboring `abort_corpus_inadequate` path BEFORE `return summary`:
```python
            try:
                write_per_run_cost_ledger(run_dir, run_id)
            except Exception:
                pass
            if q.get("v6_mode") and q.get("external_run_id"):
                emit_terminal_event(
                    q.get("external_run_id"),
                    "error_corpus_population_mismatch",
                    error_msg=summary.get("error"),
                )
            set_current_run_id(None)
            set_reasoning_sink(None)
            log_f.close()
            return summary
```
This is byte-for-byte the abort_corpus_inadequate teardown (run_honest_sweep_r3.py:3377-3388),
with the named terminal-event type. So the new abort path now emits its terminal event, writes the
per-run cost ledger, and clears run-scoped state + closes the log handle, identical to the sibling
abort paths.

## On the secondary ask ("add coverage that exercises the actual run_one_query abort path")
The invariant is a DEFENSIVE guard that CANNOT fire on the real flow: `adequacy` is computed from the
same `dist` (assess_corpus_adequacy(tier_counts=dist.tier_counts)), so total + tier_counts always
match unless a future merge reassigns `dist` without recomputing adequacy. Exercising the actual
run_one_query branch therefore requires monkeypatching assess_corpus_adequacy to force a divergence —
the same reason the sibling abort_corpus_inadequate / abort_corpus_approval_denied paths are covered
at the COMPONENT level (tests/crown_jewels/test_cj_005_corpus_approval.py + test_fx06_...), not via a
full run_one_query invocation. The teardown is now identical to the behaviorally-exercised
abort_corpus_inadequate path. If you judge a forced-divergence run_one_query test mandatory rather
than disproportionate for this defensive guard, say so and I will add the monkeypatch-based test.

## What this implements (recap)
Diff: `.codex/I-ready-017/fx06b_codex_diff.patch` (base eb92c3a6^..HEAD; 5 files).
1. tier_counts equality added to the corpus-population invariant (total-only -> total OR tier_counts).
2. Named `error_corpus_population_mismatch` abort-manifest (both populations recorded) replacing the
   generic RuntimeError->error_unexpected, registered across all 4 taxonomy surfaces.
§-1.1: outputs/audits/I-ready-017/fx06b_s11_audit.md (held approval 145 vs adequacy 45 diverge on
total + every tier).

## Offline evidence
`pytest tests/polaris_graph/test_fx06_approval_population_iready017.py` -> 5 passed.
test_manifest_contract taxonomy-lockstep passes (lone failure not_applicable_planner_lane is the
pre-existing #1135 gap, unrelated). py_compile clean.

## Questions
1. Is the teardown now correct + complete (matches abort_corpus_inadequate)?
2. Is component-level coverage acceptable for this can't-fire-on-real-flow defensive guard, or do you
   require a forced-divergence run_one_query test?
3. Any remaining faithfulness / correctness gap before APPROVE?
