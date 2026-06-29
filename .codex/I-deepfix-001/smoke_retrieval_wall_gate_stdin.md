HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings now. Same quality bar regardless of iteration.
- Reserve P0/P1 for real execution risks; classify non-blockers as P2/P3.
Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

STATIC review (read-only), FOCUSED + FAST. Do NOT run pytest. Do NOT re-audit the whole pipeline.

CONTEXT: POLARIS deep-research benchmark harness `scripts/dr_benchmark/run_gate_b.py`. `--smoke-scale` runs apply `_SMOKE_SCALE_OVERRIDES` (a dict force-set into os.environ AFTER the full-capability slate's FLOOR loop, at run_gate_b.py:2291-2293) to shrink a smoke to a fast plumbing run. The full (paid) slate sets `PG_RETRIEVAL_QUESTION_WALL_SECONDS=5400` and `PG_RUN_WALL_CLOCK_SEC=10800` and is UNCHANGED by this diff.

THE BUG THIS FIXES (confirmed from a real killed smoke): on the smoke path the slate's FLOOR semantics pinned `PG_RETRIEVAL_QUESTION_WALL_SECONDS=5400` (90 min) while the smoke override set `PG_RUN_WALL_CLOCK_SEC=2400` (40 min). Since retrieval-wall (5400) > run-wall (2400), the per-question retrieval deadline (anchored in run_honest_sweep_r3.py:7956, honored by the search lanes + live_retriever) could NEVER hand off the partial corpus before the run-wall — so retrieval ran unbounded and the smoke never reached generation/render. The benchmark preflight at run_gate_b.py:2615-2623 SKIPS the `retrieval_wall < run_wall` coherence check on smoke_scale (`and not smoke_scale`), so nothing caught it.

THE FIX (this diff, in `_SMOKE_SCALE_OVERRIDES` only): add `PG_RETRIEVAL_QUESTION_WALL_SECONDS=1200` (smoke retrieval handoff at 20 min) and raise the smoke `PG_RUN_WALL_CLOCK_SEC` from 2400 to 3600 (60 min), so the smoke timeout hierarchy is coherent: retrieval 1200 < run-wall 3600, with a 2400s back-half budget that exceeds the 1800s 4-role seam backstop.

YOUR TASK — verify ONLY these properties of the diff:
1. CORRECTNESS: on a smoke run, after `_SMOKE_SCALE_OVERRIDES` is force-applied (line 2293 direct os.environ assignment, AFTER the slate FLOOR loop), `PG_RETRIEVAL_QUESTION_WALL_SECONDS` resolves to 1200 (not 5400) and `PG_RUN_WALL_CLOCK_SEC` to 3600. Confirm the smoke override genuinely wins over the slate FLOOR for these two keys (i.e. these keys are applied via the 2291-2293 smoke loop, not re-raised afterward).
2. COHERENCE: 1200 < 3600, and back-half budget (3600-1200=2400) >= the smoke 4-role seam backstop (PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS=1800) and section wall (900). No inner smoke backstop now exceeds the smoke run-wall.
3. PAID PATH UNTOUCHED: the full slate values (PG_RETRIEVAL_QUESTION_WALL_SECONDS=5400, PG_RUN_WALL_CLOCK_SEC=10800) and the non-smoke preflight coherence check (2615-2623) are unchanged; a non-smoke run is byte-identical.
4. FAITHFULNESS-NEUTRAL: the change only moves wall/handoff timing; it drops no source and touches no faithfulness gate (a retrieval_wall_hit hands off the partial corpus with disclosure, §-1.3).
5. NO NEW BUG: e.g. does raising the smoke run-wall to 3600 contradict any other smoke assumption (the smoke comment claims "~15-20 min"; the hang-catch window widens to ~60 min — flag if any code asserts the smoke run-wall==2400). Is 1200 strictly above the smoke per-section (900) so a healthy retrieval phase is not itself starved? (Retrieval wall bounds the whole retrieval phase, section wall bounds one generation section — independent axes; just sanity-check.)

If correct with no NEW P0/P1, APPROVE. If you spot a real NEW P0/P1, REQUEST_CHANGES with exact file:line.

OUTPUT EXACTLY THIS SCHEMA (LAST line starts with `verdict:`):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
