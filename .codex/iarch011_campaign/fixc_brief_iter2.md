HARD ITERATION CAP: 3 per document. This is iter 2 of 3.
- Front-load ALL real findings. Same quality bar regardless of iteration.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; classify the rest P3/P2/cosmetic.
- If iter 3 returns REQUEST_CHANGES, Claude force-APPROVEs on remaining non-P0/P1 findings.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: judge against 2025-2026 frontier practice; no grandfathering. The faithfulness engine
(strict_verify / NLI entailment / span-grounding) is NEVER relaxed — flag any change that would.

# Codex diff review — I-arch-011 FIX-C (PG_PARALLEL_VERIFY) — iter 2 (your iter-1 P1 + P2 addressed)

Review the patch FILE (static only, do NOT run pytest):

    .codex/iarch011_campaign/fixc_diff.patch   (2 files; workdir C:/POLARIS read-only)

## WHAT CHANGED SINCE YOUR ITER-1 REVIEW
Your iter-1 verdict was REQUEST_CHANGES: ONE P1 (parallel-verify cost not reconciled to the parent budget
gate) + two P2. BOTH the P1 and the actionable P2 are now fixed. The diff is now 2 files (was 1).

**P1 ADDRESSED (cost reconciliation) — `provenance_generator.py` parallel-verify branch (~2789-2818):**
You were CORRECT — verified against source: `_RUN_COST_CTX` is a ContextVar (openrouter_client.py:99);
`_add_run_cost` does `_RUN_COST_CTX.set(...)` (:303); each worker runs in `_parent_ctx.copy().run(...)`, so
the judge's `_add_run_cost`/`check_run_budget` mutate the COPY and are lost to the parent → the parallel
verify spend bypassed PG_MAX_COST_PER_RUN. FIX = the EXACT pattern the codebase already documents for the
credibility offload (`ledger_cumulative` docstring, openrouter_client.py:345-351): the cost LEDGER is a
process-global lock-protected per-session accumulator (`append_cost_ledger_row` bumps it from any thread,
NOT a contextvar), so we snapshot `ledger_cumulative(run_id)` BEFORE the pool, run the pool, then
`_add_run_cost(after - before)` + `check_run_budget(0)` on the PARENT context. The gate is now inclusive of
the parallel judge spend; a cap breach raises BudgetExceededError (same terminal behavior as the serial
per-call check). Cost-accounting only — verdicts unchanged.

**P2-1 ADDRESSED (force-exact) — `run_gate_b.py`:** added `"PG_PARALLEL_VERIFY"` to
`_BENCHMARK_FORCE_EXACT_FLAGS` so the slate value 16 is forced EXACTLY (a stray env value can neither exceed
the 16-worker cap nor silently revert to serial=1).

**P2-2 (telemetry shared-dict increments) — ACCEPTED, not changed:** it is PRE-EXISTING in the fix#19
parallel path (not introduced by this diff), you confirmed it does NOT change kept/dropped verdicts, and the
GIL makes the int increments effectively atomic. Captured as a cosmetic follow-up, not fixed in this diff.

## BEHAVIORAL PROOF (unchanged, banked)
`scripts/iarch011_parallel_verify_gate.py` (real glm-5.1 judge + PG_PARALLEL_VERIFY=16 on the banked drb_78
corpus): the enrichment verify COMPLETES in 17.4 min (was ~173 min serial) and keeps 1746 cited / 657
distinct sources on the REAL enforce path. Real-judge keep-rate 39/40=97%.

## YOUR JOB
A. Confirm the P1 is RESOLVED: the reconciliation correctly makes the parent run-budget gate inclusive of
   the parallel verify spend (snapshot delta of the process-global ledger accumulator, re-added to the
   parent `_RUN_COST_CTX`, budget re-checked). Confirm the `_cost_delta > 0` guard and the run_id source
   (parent `_CURRENT_RUN_ID_CTX`) are correct, and that this matches the credibility_pass offload pattern.
B. Confirm NO new P0/P1 introduced (e.g. a double-count: does any OTHER site already reconcile the same
   delta? the serial path does NOT use this block, so no double count there).
C. 3-PRONG unchanged: FIX-C is a concurrency knob + cost-accounting correctness; no faithfulness relaxation,
   no grandfather, no cap/floor/throttle on breadth. The parallel path is verdict-identical to serial
   (contextvars copied, `map` order-preserving, fail-loud).

## OUTPUT SCHEMA (return EXACTLY this; last `verdict:` line is parsed)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
