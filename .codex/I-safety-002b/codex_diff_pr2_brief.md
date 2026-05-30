HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# DIFF AUDIT iter 2: PR-2 after applying ALL iter-1 findings (I-safety-002b / #925)

iter-1 verdict was REQUEST_CHANGES with 2 P1 + 2 P2 + 1 P3. **All fixed.** Verify, then APPROVE.
Cumulative diff at `.codex/I-safety-002b/codex_diff_pr2.patch` (b8cb9d53 + 0bc2c805 on bot/I-ux-002).

## Your iter-1 findings, how addressed, where to verify
1. **P1 — generator pinned from wrong env var.** `pathB_runner._role_pins` now reads
   `PG_GENERATOR_MODEL` first (the documented honest_sweep override), then
   `OPENROUTER_DEFAULT_MODEL`, then the static default. Regression test
   `test_pin_reads_pg_generator_model_first` proves PG_GENERATOR_MODEL wins over
   OPENROUTER_DEFAULT_MODEL=wrong/wrong-slug.
2. **P1 — system_fingerprint hard-required as surrogate.** Surrogate is now
   `("provider_name", "model")` only. system_fingerprint is still captured by
   build_response_metadata when present (and recorded under `served_identity_by_role`),
   but it is NOT required for a call to pass. Regression test
   `test_gate_passes_without_system_fingerprint` proves a response with only
   provider+model passes.
3. **P2 — PG_PATHB_GATE_SALT plaintext in pin file.** Added `PG_PATHB_GATE_SALT` to
   `_SECRET_EXPLICIT` in `pathB_run_gate.py` so `is_secret_var` returns True →
   `build_effective_config` records `{secret: True, present, length, salted_hmac}`, never
   the value. Regression test `test_salt_is_redacted_in_pin` asserts the plaintext salt
   is absent from `pathB_gate_pin.json` while `PG_PATHB_GATE_SALT` still appears as a
   secret-presence entry.
4. **P2 #2 — assert_post_run runs after manifest/judge artifacts written.** Structural:
   `run_one_query` writes per-run artifacts during the run (manifest, judge,
   evaluator_rule_checks), and the gate's post-run assert happens after run_one_query
   returns. I made this machine-readable: on either preflight FAIL or post-run-assert
   FAIL, `gate_around_question` writes a `pathB_gate_INVALID` sentinel file in run_dir.
   Downstream PR-3 scoring will check for this sentinel and skip the run_dir's artifacts.
   The gate is now the source of truth for run validity, even though artifacts already
   exist on disk. Regression test `test_post_run_fail_writes_invalid_sentinel`.
5. **P3 — preflight FAIL leaves no result file.** `gate_around_question` now catches
   GateError from `preflight()`, writes
   `pathB_gate_result.json = {verdict: FAIL, stage: preflight, reason}` + the
   `pathB_gate_INVALID` sentinel, then re-raises. Regression test
   `test_preflight_fail_writes_result_and_sentinel`.

## Verification (already done)
- `pytest tests/dr_benchmark/` = **67/67 passed** (was 62; +5 regression tests for the
  iter-1 fixes).
- The existing tests (`test_pathB_run_gate.py` 21 tests) still pin system_fingerprint as
  a surrogate in their fake pins — those test the gate primitives directly and remain
  valid; the runner's choice not to require system_fingerprint is a runner policy, not a
  gate-primitive change.

## What to verify this round
- Each iter-1 finding is closed in the cumulative diff.
- The pin file's salt is genuinely redacted (the regression test asserts it; you can
  re-derive the assertion by reading `pathB_run_gate._SECRET_EXPLICIT`).
- No new bug introduced by the `try/except GateError` around preflight (the
  `gate_around_question` body raises GateError, the outer test re-raises after writing
  artifacts).
- No regression in role-tag wrapping, retrieval hooks, or exception propagation (P3 P3,
  retrieval_hooks_complete, exception_propagation_correct were "true" in iter-1; verify
  they're still true).

## Output schema (return EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
iter1_findings_closed:
  P1_generator_env_var: true | false
  P1_surrogate_no_sysfp: true | false
  P2_salt_redacted: true | false
  P2_invalid_sentinel_for_downstream_skip: true | false
  P3_preflight_fail_writes_result: true | false
role_tag_chokepoints_correct: true | false
per_question_lifecycle_correct: true | false
retrieval_hooks_complete: true | false
exception_propagation_correct: true | false
convergence_call: continue | accept_remaining
remaining_blockers: []
```
Loose verdict prose without this schema will be rejected and resubmitted.
