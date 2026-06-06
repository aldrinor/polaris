# FX-06 (#1120) diff-gate — ITER 1 of 5

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

## Scope
**FAITHFULNESS-RELEVANT** (corpus approval is the pre-generation abort gate, invariant #5) but the
change is ARTIFACT-ONLY — it must NOT alter the abort short-circuit / pre-spend gate timing. Diff:
`.codex/I-ready-017/fx06_codex_diff.patch` (vs FX-15b verified tip `3cbd84ce`). Depends on FX-15b
(#1119, DONE).

## Bug — confirmed §-1.1 on the REAL held artifacts
The corpus-approval gate scores the FINAL post-merge `dist` (`run_honest_sweep_r3.py` ~3093,
`report=dist`), but `corpus_adequacy.json` was last written PRE-merge (~2535 base / ~2698 expansion;
the deepener + agentic merges reassign `dist`/`adequacy` in memory at ~2971-2975 but never re-wrote
the JSON). Held drb_72: `corpus_approval.json.report.total_sources = 145` (T4=31.72%) vs
`corpus_adequacy.json.total_sources = 45` — the gate scored a DIFFERENT population than adequacy +
the report consumed (gate-on-the-wrong-population). Full §-1.1: `outputs/audits/I-ready-017/fx06_s11_audit.md`.

## Fix (artifact-only; abort control-flow UNCHANGED)
After `_flush_retrieval_trace()` and BEFORE the inadequate-abort, re-write `corpus_adequacy.json`
ONCE from the FINAL `adequacy` (post base + expansion + deepener + agentic) so adequacy + approval +
report describe the SAME corpus on EVERY exit path (inadequate-abort, approval-denied, success). Plus
a fail-loud invariant: `adequacy.total_sources == dist.total_sources` (both `sum(tier_counts)`) —
refuse to proceed if a future merge reassigns `dist` without recomputing `adequacy` from it. The
abort still uses the in-memory `adequacy.decision`; the pre-spend gate timing is unchanged.

## Evidence
- **§-1.1 on REAL held artifacts**: approval=145 vs adequacy=45 divergence confirmed.
- **Offline smoke — `test_fx06_approval_population_iready017.py` → 2 passed**: invariant holds
  (`compute_tier_distribution(srcs).total_sources == assess_corpus_adequacy(tier_counts=that dist,
  ...).total_sources`, 45==45); divergence detected for a pre-merge adequacy (45) vs post-merge
  approval dist (145) — the exact held bug shape.
- **Regression**: 425 passed (corpus_approval enforcement b2, adequacy gate, manifest contract,
  run-events, plan_sufficiency, etc.).

## Also checked
- adequacy.json = `asdict(adequacy)` (top-level `total_sources`); approval.report = `dist`
  (`CorpusDistributionReport.total_sources`); both = `sum(tier_counts)`.
- The single final write supersedes the earlier ~2535/2698 writes and also fixes the deepener path
  (which likewise never re-wrote adequacy.json). Earlier writes left in place (cheap).
- The inadequate-abort (~2994) and approval-denied (~3102) paths now read the final adequacy.json.

## Question for you
The invariant is a hard `raise RuntimeError` on divergence (never fires in correct operation, since
`adequacy` is always computed from `dist`). Is a hard raise the right fail-loud here, or do you
prefer a graceful `error_corpus_population_mismatch` abort-manifest (like the other abort paths) so a
single query's invariant violation can't crash a multi-query sweep? Anything else blocking APPROVE?
