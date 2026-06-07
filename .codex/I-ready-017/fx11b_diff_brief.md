# I-ready-017 FX-11b (#1117) — DIFF gate (iter 1 of 5)

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

## What this implements (#1117 — the 3 cost-accounting P2 follow-ups of FX-11 #1116)
Diff: `.codex/I-ready-017/fx11b_codex_diff.patch` (base HEAD~1..HEAD; 4 files). Cost-accounting
ONLY — no faithfulness / strict_verify / provenance / 4-role path. Non-rerun-gating.

1. **NLI-conflict judge ledger row** (`semantic_conflict_detector.py` `_SemanticContradictionJudge.judge`).
   After `_orc._add_run_cost(actual_cost)` + `check_run_budget`, now also calls
   `_orc.append_cost_ledger_row(session_id=_orc.current_run_id() or "", call_type="nli_conflict_judge",
   cost_usd=actual_cost, input_tokens=..., output_tokens=...)`. The budget was already fed by
   `_add_run_cost` (the `_RUN_COST_CTX` accumulator); `append_cost_ledger_row` bumps the SEPARATE
   ledger accumulator + writes the row, so NO budget double-count. Best-effort (try/except — ledger
   I/O never aborts detection). Held ledger had 0 `nli_conflict_judge` rows (the writer didn't exist).
2. **free-call summary** (`openrouter_client.py` `UsageTracker`). Added
   `total_free_input/output_tokens`; `record(free=True)` accumulates them; `total_cost_usd` imputes
   over PAID tokens only (`total_* - total_free_*`). Free tokens stay in `total_input/output_tokens`
   for token REPORTING; the `total_api_reported_cost` branch is unchanged (still wins).
3. **pipeline-B run-id** (`graph.py` `build_and_run`). `set_current_run_id(vector_id)` on entering the
   client block (so judge/role writers, which key on the ambient run id, share the generator's
   accumulator key) + `set_current_run_id(None)` after the run. Pipeline A already sets this.

## §-1.1 (outputs/audits/I-ready-017/fx11b_s11_audit.md)
Held `cost_ledger.jsonl`: 472 rows, `{generate:31, entailment_judge:441}`, ZERO `nli_conflict_judge`
(item-1 symptom confirmed structurally). Items 2+3 grounded by mechanism + tests.

## Offline evidence
`pytest tests/polaris_graph/test_fx11b_cost_ledger_iready017.py` -> 5 passed (NLI row written w/
correct call_type/session_id/cost; ledger-failure non-fatal; free tokens excluded from imputed cost;
all-free imputes 0; api-cost still wins). Regression: fx11_cost_ledger + m206_n301_cost_ledger +
entailment_judge_cost + semantic_conflict_detector -> 40 passed (no regression). py_compile clean.

## Notes for review
- Item 3: free-token exclusion only changes the IMPUTED fallback. Confirm it cannot under-report a
  genuinely-paid call (free=False calls never touch total_free_*; the api-cost branch is untouched).
- Item 1: confirm append_cost_ledger_row (ledger accumulator) + _add_run_cost (_RUN_COST_CTX) are
  genuinely separate accumulators so the NLI budget is not double-counted.
- Item 2: graph.py is pipeline-B (legacy/UI), not the benchmark/rerun path; the reset is best-effort
  (an exception leaves the ambient id for the next build_and_run to overwrite — benign per-request).

## Questions
1. Is the NLI ledger-row addition correct (no budget double-count; right key/call_type)?
2. Is the free-token exclusion correct + non-regressing for paid calls?
3. Is the pipeline-B set/reset acceptable, or do you require a try/finally reset?
4. Any cost-accounting / correctness gap before APPROVE?
