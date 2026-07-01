HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate — beat-both Wave A, ITER 2 (re-gate after your iter-1 REQUEST_CHANGES)

You reviewed Wave A at iter 1 and returned REQUEST_CHANGES with 1 novel P0, 1 continuing P0, 1 P1, 2 P2. This iter reviews the FIX for those findings. The primary review target is the delta patch `.codex/I-deepfix-001/wave_a_gatefix_delta.patch` (547 lines, `scripts/dr_benchmark/run_gate_b.py` +132 and a new offline test `tests/polaris_graph/test_deepfix_wave_a_gate_fixes.py`). Read the touched files in the repo (root `C:/POLARIS`, read-only) for context. The full original Wave A diff is unchanged from iter 1 except for this delta.

## Your iter-1 findings and how each is addressed — VERIFY each resolution

**(1) novel_p0 — WS-1 judge idempotency cache is process-wide, never reset, `reset_judge_verdict_cache` has no production caller → a stale/poisoned VERIFIED can leak across documents.**
FIX 1: `reset_judge_verdict_cache()` is now imported and CALLED at the top of `run_gate_b_query` (right after `enable_four_role_mode()`, run_gate_b.py ~line 3473). `run_gate_b_query` processes exactly one report; `main()` runs each benchmark query through it in the SAME process. Resetting at that per-document boundary means within-one-report byte-twins still share a verdict, but no verdict crosses a document boundary. Rides the existing default-ON `PG_JUDGE_VERDICT_IDEMPOTENCY` — OFF ⇒ cache never populated AND reset not called ⇒ byte-identical. `judge_adapter.py` itself is NOT edited; verdict decision logic (`parse_judge_verdict` / `_compose_final_verdict`) untouched.
- **VERIFY:** is the reset at the correct boundary (per report/document, not per-claim which would defeat within-report dedup, and not never)? Can any path still let a stale/poisoned verdict from document N reach document N+1? Does a cache MISS still fall through to a real judge call (never a default-VERIFIED)? Is there any OTHER process-wide judge state with the same cross-document leak that Wave A missed?

**(2) continuing_p0 — "ALL-GLM lock still violated: judge defaults to moonshotai/kimi-k2.6."**
This finding rested on an ALL-GLM premise that the OPERATOR HAS SINCE CORRECTED. The operator directive (2026-06-30, `feedback_judge_model_provider_availability_render_blocker`): the D8 terminal judge MUST be `moonshotai/kimi-k2.6`, chosen for its high OpenRouter provider count (21 providers) which prevents the 429 trickle that caused the D8 false-negatives in the drb_72 re-smoke. So the kimi default at `openrouter_role_transport.py:211` is CORRECT and was deliberately LEFT in place; `PG_BENCHMARK_JUDGE_MODEL` is NOT forced to GLM. The precise posture (see `.codex/I-deepfix-001/BEATBOTH_PLAN_CORRECTIONS.md` OPERATOR DECISION block) is **all-GLM everywhere EXCEPT the D8 terminal judge**:
  - Generator + mirror + side-checkers (entailment / semantic_conflict / credibility / span-quality) + external evaluator `PG_EVALUATOR_MODEL` = GLM-5.2 (the all-GLM / sovereignty-dropped campaign).
  - D8 TERMINAL faithfulness judge = kimi-k2.6, a DISTINCT family → every VERIFIED/UNSUPPORTED verdict is decided by a model that did not write the text (the meaningful two-family self-bias safeguard). `assert_four_role_families_distinct()` passes: `{generator: z-ai, mirror: z-ai, sentinel: minimax, judge: moonshotai}`.
  - `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY` stays **1** (NOT 0). It governs only the disclosed all-GLM SIDE surface (GLM generator vs GLM external-evaluator/side-checkers). Setting 0 would ABORT the run at `check_family_segregation`. It does NOT touch the D8 terminal judge (kimi, cross-family).
- **VERIFY:** confirm this is faithfulness-SAFE and honest, NOT a relaxation. Specifically: (a) does the D8 terminal verdict (the gate that decides VERIFIED/UNSUPPORTED) genuinely run on kimi, cross-family from the GLM generator? (b) does `PERMIT=1` weaken ONLY the disclosed all-GLM side surface (external evaluator + side-checkers), and NOT the terminal judge? (c) is the two-family self-bias protection therefore intact at the surface that matters for faithfulness? If you believe the all-GLM side-checkers create a real self-bias faithfulness risk despite the cross-family terminal judge, say so and rate it — but note the side-check→GLM mapping is operator-locked (§9.1.8) and is DISCLOSED, not silent.

**(3) p1 — WS-2 `assert_cross_source_synthesis_fired` defined but never called in the post-run path.**
FIX 3: an M6 firing canary is now wired into `main()`'s per-query loop. Key subtlety the implementer found: the M6 producer logs its markers via its MODULE logger to STDOUT, NOT to `run_dir/run_log.txt` (run_honest_sweep_r3.py:7442-7444 tees `_log` to the file; module `logger.info` only reaches stdout) — so reading run_log.txt would be a FALSE GREEN. So a new `_CrossSourceMarkerCaptureHandler` captures that one module logger's records in-process for the query, and `_run_m6_firing_canary(...)` feeds the captured text to the UNCHANGED `assert_cross_source_synthesis_fired`. It mirrors the existing breadth-canary pattern: self-skips on non-released/smoke, self-skips when `PG_CROSS_SOURCE_SYNTHESIS` is off (inside the assert), sets `overall_rc=1` on a genuine silent no-op. Sweep record gains `m6_cross_source_canary`; `ok` now also requires it not FAILED. Kill-switch: new default-ON `PG_M6_FIRING_CANARY`; OFF ⇒ no handler, no canary ⇒ byte-identical.
- **VERIFY:** does the canary actually FAIL the run (overall_rc=1) when M6 is ON but produced zero cross-source units, and PASS when it fired? Is the module-logger capture the right source (not a false-green from an empty file)? Is it observability-only — does it assert anything about a VERDICT (it must not)? Does the `finally` detach the handler so it can't leak across queries?

**(4) p2 (WS-5 caveat wording; trailing whitespace).** WS-5 wording left as-is (advisory-only, non-blocker per your own rating). Trailing whitespace: `git diff --check` on the Wave A + delta hunks now reports NONE.

## Non-negotiables to re-confirm
- **Frozen engine untouched:** `git diff --name-only` over the engine (`strict_verify` / `provenance` / `nli_verifier` / `role_pipeline` / `judge_adapter` / `judge_contract` / `span_grounding` / `four_role` / `mirror_adapter` / `sentinel_adapter`) must be EMPTY. `judge_adapter.py` is USED (existing `reset_judge_verdict_cache`) but not edited. Confirm.
- **§-1.3 (WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP):** none of the 3 fixes drops/caps/floors a source. Confirm.
- Offline test `tests/polaris_graph/test_deepfix_wave_a_gate_fixes.py` = 36/36 pass (independently re-run: PASS).

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
frozen_engine_untouched: true | false
p0_1_cache_leak_resolved: true | false          # FIX 1 — cross-document leak closed, no UNSUPPORTED→VERIFIED path
p0_2_judge_posture_ok: true | false             # kimi D8 terminal + PERMIT=1 side surface is faithfulness-safe & honest
p1_m6_canary_wired_and_fails_on_noop: true | false   # FIX 3 — canary genuinely fails a silent no-op
ws1_cache_or_retry_can_flip_unsupported_to_verified: true | false   # must be false
s13_violations: [...]
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
