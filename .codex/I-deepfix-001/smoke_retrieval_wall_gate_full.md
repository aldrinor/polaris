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

=== THE DIFF UNDER REVIEW ===
```diff
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index 519d48e9..8fbed8e6 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -2233,14 +2233,26 @@ _SMOKE_SCALE_OVERRIDES: dict[str, str] = {
     "PG_PREFLIGHT_MIN_BREADTH": "10",        # was 100
     # I-cred-008b basket-coverage gate scales with breadth; keep the super-heavy preflight's own
     # gates ON (faithfulness/behavioral) — only the BREADTH-count floor is lowered for the smoke.
-    # timeout hierarchy — coherent per-call < generator < section < seam < run-wall, scaled so a HANG
-    # is caught in ~40 min. A tiny smoke section finishes in minutes, well under these, so none
-    # truncates a HEALTHY section (the arch-005 trap).
+    # timeout hierarchy — coherent retrieval-wall < run-wall (with back-half headroom) AND
+    # per-call < generator < section < seam < run-wall, scaled so a HANG is caught in ~60 min.
+    # A tiny smoke section finishes in minutes, well under these, so none truncates a HEALTHY
+    # section (the arch-005 trap).
+    # I-deepfix-001 (#1344) SMOKE-HANDOFF FIX: the full slate pins PG_RETRIEVAL_QUESTION_WALL_SECONDS
+    # =5400 via FLOOR semantics; on the smoke that EXCEEDS the smoke run-wall (was 2400), so the
+    # per-question retrieval deadline could NEVER hand off the partial corpus -> retrieval ran
+    # UNBOUNDED and the smoke never reached generation/render (the back-half plumbing stayed
+    # unexercised). The benchmark preflight SKIPS the retrieval<run coherence check on smoke_scale
+    # (run_gate_b.py:2616 `and not smoke_scale`), so nothing caught the incoherent hierarchy. Pin a
+    # smoke retrieval wall STRICTLY BELOW the smoke run-wall with ample back-half room: 1200 retrieval
+    # + up to 2400 back-half <= 3600 run-wall (seam backstop 1800 < 2400 -> a healthy back half is
+    # never guillotined). Smoke-only; the PAID slate (5400 < 10800) is UNTOUCHED. Faithfulness-neutral:
+    # a disclosed retrieval_wall_hit hands off the partial corpus and drops no source (§-1.3).
+    "PG_RETRIEVAL_QUESTION_WALL_SECONDS": "1200", # per-question retrieval handoff (20 min) — < run-wall
     "PG_VERIFIER_LLM_TIMEOUT_SECONDS": "300",    # per verifier LLM call (5 min)
     "PG_GENERATOR_LLM_TIMEOUT_SECONDS": "600",   # per generator call (10 min) — synced to live module below
     "PG_SECTION_WALLCLOCK_SECONDS": "900",       # per section (15 min)
     "PG_FOUR_ROLE_SEAM_TIMEOUT_SECONDS": "1800", # 4-role D8 seam (30 min)
-    "PG_RUN_WALL_CLOCK_SEC": "2400",             # OUTER backstop (40 min)
+    "PG_RUN_WALL_CLOCK_SEC": "3600",             # OUTER backstop (60 min) — retrieval 1200 + back-half 2400
     # modest cost cap for a smoke (synced to the live module below)
     "PG_MAX_COST_PER_RUN": "10",
     # CORRECTNESS (not scale-down): the GLM-5.1 Mirror blanks at xhigh effort and STALLS the 4-role
```
