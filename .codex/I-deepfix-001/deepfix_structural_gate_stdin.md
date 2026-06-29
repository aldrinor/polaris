HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

You are doing a STATIC code review (read-only). Do NOT run pytest / any tests / any script — the sandbox is read-only and the author already ran the offline suite (all GREEN). Read these two files in the repo (workdir C:/POLARIS):
1. `.codex/I-deepfix-001/deepfix_structural_brief.md` — the full brief (what each fix does + faithfulness/§-1.3 rationale + test evidence).
2. `.codex/I-deepfix-001/deepfix_structural_diff.patch` — the actual consolidated diff (3 source files + 3 new test files, ~867 lines).

CONTEXT: campaign I-deepfix-001 — 3 SURGICAL structural fixes to the POLARIS sovereign clinical deep-research pipeline. A real under-load smoke proved the pipeline gets STUCK in retrieval (never reaches generation) because the scope validator drops every CRAG gap-fill sub-query to zero. These fixes address that + two hardening items. The pipeline DNA (§-1.3): WEIGHT-don't-FILTER, CONSOLIDATE-don't-DROP — never add a hard DROP/CAP/THIN/TARGET; the ONLY hard gate is the faithfulness engine, which must NOT be touched.

THE 3 FIXES (verify each against the diff hunks):
- FIX-1 (KEYSTONE) `src/polaris_graph/retrieval/scope_query_validator.py`: new `PG_SCOPE_KEEP_BEST_N` (default 1). When the scope-floor would leave the kept query-set EMPTY and below-floor non-directive / non-empty candidates exist, keep the top-N by scope similarity so the retrieval round still fires (prevents empty-round → CRAG re-grades unchanged corpus → infinite non-convergence). `PG_SCOPE_KEEP_BEST_N=0` reverts to legacy drop-to-empty (byte-identical). The B3 directive screen + empty-after-tokenization guards must still gate survivors. Function signature of `validate_amplified_queries` UNCHANGED (3 other callers).
- FIX-2 `scripts/run_honest_sweep_r3.py`: new pure helper `_per_question_retrieval_deadline()` reads `PG_RETRIEVAL_QUESTION_WALL_SECONDS`; `run_one_query` anchors it ONCE after t0 and threads it into all 8 `run_live_retrieval(...)` call sites (initial / IterResearch-or-FS / CRAG loop-back / R-6 expansion / deepener / agentic / STORM / saturation-gap) so they SHARE one monotonic deadline instead of each resetting a fresh 30-min wall. Unset/garbage/non-positive → None → the proven per-invocation default (byte-identical). `run_live_retrieval` already hands off the partial corpus with disclosure on expiry.
- FIX-3 `src/polaris_graph/synthesis/consolidation_nli.py`: new `PG_CONSOLIDATION_NLI_DEVICE` knob (unset → no device kwarg, byte-identical auto-placement). A CUDA OOM during cross-encoder LOAD retries on CPU; a CUDA OOM during PREDICT rebuilds the model on CPU and re-scores the remaining chunks. `_is_cuda_oom` degrades ONLY genuine CUDA OOM; non-OOM errors still fail loud (no silent no-op).

RED-TEAM FOCUS — front-load ALL real P0/P1 now (5-cap, no drip):
1. FAITHFULNESS-NEUTRAL: does ANY fix import or alter the faithfulness engine (strict_verify / NLI entailment verifier / 4-role D8 / provenance_generator / span-grounding)? It must NOT. Flag any touch as P0.
2. §-1.3 NO-DROP: FIX-1 must only ADD on-intent queries to an otherwise-empty set (never drop a source/corroborator); FIX-3 degrade must keep MORE baskets (degrade-not-die, never fewer); FIX-2 must not cap/drop/thin breadth (only stop the clock RESET). Any DROP/CAP/THIN path = P0.
3. CORRECTNESS: FIX-1 — does keep-best-N fire ONLY on an empty kept-set, and do the directive + empty-after-tokenization guards still apply to survivors? FIX-2 — is the shared deadline correctly threaded into ALL 8 lanes, and does a lane that starts past the deadline exit gracefully (partial corpus, no crash/abort)? FIX-3 — is `_is_cuda_oom` correct (does not swallow non-OOM errors), and is the CPU re-score of remaining chunks consistent with the GPU-scored chunks (bidirectional-entailment argmax device-invariant)?
4. DEFAULT SAFETY: PG_SCOPE_KEEP_BEST_N defaults to 1 (default-ON, NOT byte-identical) — is the behavior change safe (only rescues otherwise-stranded rounds)? PG_RETRIEVAL_QUESTION_WALL_SECONDS + PG_CONSOLIDATION_NLI_DEVICE default unset (byte-identical) — confirm.
5. HYGIENE: any silent `except: pass`, magic numbers (LAW VI: env-driven), mocks in src/, broken imports, non-snake_case, dead code.

OUTPUT EXACTLY THIS SCHEMA (the LAST line must start with `verdict:`):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
