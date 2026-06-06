# FX-11 (#1116) diff-gate — ITER 2 of 5

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

## Scope reminder
Cost-accounting ONLY. NOT a faithfulness invariant (no grounding / strict_verify / 4-role-decision
change). `check_run_budget` (the spend gate, on the per-task `current_run_cost()` ContextVar) is
untouched. Diff: `.codex/I-ready-017/fx11_codex_diff.patch` (vs FX-10 tip `e63c102b`).

## Your iter-1 verdict (what this iter addresses)
- **P1 (the blocker):** "role cost-ledger cumulative under default parallel four-role workers must
  use the parent/shared inclusive run total and be non-decreasing." Root cause: cumulative was read
  from `current_run_cost()`, the per-asyncio-task ContextVar that each parallel claim worker
  RESETS — so role-row cumulatives were per-worker / non-monotonic.
- **P2a:** blank-verdict retry (`openrouter_role_transport`) added run-budget cost but wrote no
  ledger row.
- **P2b:** `loopback_client` `usage.record(api_cost=0.0)` ledgered a phantom paid-rate token
  estimate for a free call.
- **P2c:** the best-effort write-failure test did not actually force a failure (mkdir created the
  parents).

## What iter-2 changed (the fix = the issue's literal title: a SINGLE canonical accumulator)
1. **One process-global, per-session accumulator + ONE canonical writer.** `_LEDGER_CUM_LOCK` is now
   a `threading.RLock`; new `append_cost_ledger_row(...)` (openrouter_client) **bumps the
   per-session accumulator AND appends the JSONL row under the SAME lock**. So the persisted file is
   non-decreasing in **write order** (not merely assignment order) even when several
   ThreadPoolExecutor workers write concurrently. Returns the inclusive cumulative.
2. **Grounding for the P1 (please verify):** the real fan-out is `sweep_integration.py:329-332` —
   `concurrent.futures.ThreadPoolExecutor(max_workers=PG_FOUR_ROLE_CLAIM_WORKERS)` + each task
   submitted via `contextvars.copy_context().run(...)`. `copy_context()` **inherits**
   `_CURRENT_RUN_ID_CTX` (the run id) into every worker; each worker resets only its OWN
   `_RUN_COST_CTX`. Therefore all workers resolve the SAME accumulator key (the shared run id), and
   the shared accumulator gives one rising total. (If you think threads do NOT inherit the run id
   here, that is the key thing to check — the fix's correctness rests on this copy_context inherit.)
3. **All four writers route the accumulator with ONE precedence.** `UsageTracker.record` keys
   `self.session_id or _CURRENT_RUN_ID_CTX.get() or ""`; judge / role / blank-retry key
   `_CURRENT_RUN_ID_CTX.get() or "no_run_id"`; `append_cost_ledger_row`/`ledger_bump_cumulative`
   normalize `"" -> "no_run_id"`. So generate + judge + role rows of one run share ONE accumulator
   in every case (N-301: pick up the ambient run id when none was passed). `record` does its bump +
   `_append_ledger` inside the same RLock (RLock => the inner `ledger_bump_cumulative` re-acquire is
   safe). `_append_ledger` is kept only because a test monkeypatches it.
4. **role / judge / blank-retry** now call `append_cost_ledger_row` (this removed ~50 lines of
   duplicated manual mkdir+open blocks — net DRYer).
5. **P2a:** blank-verdict retry writes a `role:<role>:blank_attempt` row (distinct call_type marks
   the discarded attempt) so ledger total stays == run-budget total. Skipped only when the blank
   carried no usage (cost 0 — accumulator unchanged anyway).
6. **P2b:** `usage.record(..., free=True)` forces `call_cost = 0.0`; `loopback_client` passes
   `free=True`. The token-based imputation backstop (invariant #6) for PAID calls with no reported
   cost is untouched (default `free=False`).
7. **P2c:** the test now points the ledger path THROUGH a regular file so `.parent.mkdir` raises a
   real error; asserts the role call still returns and no partial file is created.

## Evidence
- **§-1.1 on REAL held ledger** (`outputs/audits/I-ready-017/fx11_s11_audit.md`): the held drb_72
  ledger has 26 decreasing steps + 0 role rows (of 472). The fix is proven by offline smoke + the
  new parallel repro (a fresh ledger needs a live run).
- **Offline smoke — `test_fx11_cost_ledger_iready017.py` → 6 passed**, incl. the P1 repro
  `test_bug10b_role_cumulative_monotonic_under_parallel_workers`: 6 ThreadPoolExecutor workers ×
  `copy_context()` × per-worker `reset_run_cost()`, 30 role rows → cumulative NON-DECREASING **in
  file write order**, all tagged the ONE shared run id, final == the GLOBAL total of every role cost
  (which per-worker `current_run_cost()` could not show). Plus P2a / P2b (with a paid-call control
  proving #6 still imputes) / P2c (forced write failure).
- **Regression:** `tests/roles/` (437) + `test_entailment_judge_cost` (8) +
  `test_m206_n301_cost_ledger` (10) + sota session_id/`_append_ledger` (3) + `llm/` (11) + loopback
  regression (12) all pass.

## Questions for you
1. Is the parallel-worker monotonicity now correct given the `copy_context()` inherit of the run id
   (P1 closed)? Any path where a worker would resolve a DIFFERENT accumulator key than the
   generator for the same run?
2. Holding the RLock across the file `open()/write()` serializes ledger appends. Acceptable for
   correctness (it is what guarantees file-order monotonicity), or do you see a real contention /
   deadlock risk? (`check_run_budget` is NOT under this lock.)
3. Anything blocking APPROVE?
