HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
- Pre-verified test results inlined; please DO NOT exec pytest.

# DIFF AUDIT iter 2: PR-3 after applying ALL iter-1 findings (I-safety-002b / #925)

iter 1 was REQUEST_CHANGES with 2 P1 + 4 P2 + 2 P3. **All 8 fixed.** Cumulative diff at
`.codex/I-safety-002b/codex_diff_pr3.patch` (commits 2894f617 + f38df40d on bot/I-ux-002).
Please verify each finding closed; return the verdict YAML.

## Pre-verified test results
```
$ python -m pytest tests/dr_benchmark/ -q
collected 91 items
tests\dr_benchmark\test_claim_audit_scorer.py ............              [ 13%]
tests\dr_benchmark\test_medhallu_adapter.py ............                [ 26%]
tests\dr_benchmark\test_pathB_capture.py .............                  [ 40%]
tests\dr_benchmark\test_pathB_run_gate.py .....................         [ 63%]
tests\dr_benchmark\test_pathB_runner.py .........                       [ 73%]
tests\dr_benchmark\test_pr3_pipeline.py ........................        [100%]
============================= 91 passed in 2.09s ==============================
```
(was 84 in iter1; +7 regression tests for the iter1 findings.)

## Your iter-1 findings → how closed → regression test

1. **P1 #1 — score_run accepts single-auditor ledgers.** `score_run.score_one` now raises
   `ValueError("ledger.auditor must be 'reconciled'")` if a claude-only / codex-only
   ledger is passed. Reconciled ledgers (from `reconcile.py`) carry `auditor="reconciled"`.
   Regression: `test_p1_1_score_run_rejects_single_auditor_ledger`.

2. **P1 #2 — silent-auditor escalation crashes on UNREACHABLE present rows.** When only one
   auditor produced a row for a claim_id:
   - If the present row is `UNREACHABLE` (already worse than VERIFIED): KEEP UNREACHABLE
     and `unreachable_subtype` intact.
   - Else: escalate verdict to `UNSUPPORTED` (or worse), DROP `unreachable_subtype` to None
     (forbidden on non-UNREACHABLE per `Claim.__post_init__`).
   Plus an additional guard: if the escalated verdict would be FABRICATED/PARTIAL but the
   present row has no span_quote, we degrade to UNSUPPORTED (no span fabrication).
   Regressions: `test_p1_2_reconcile_unreachable_silent_no_subtype_leak` +
   `test_p1_2_reconcile_silent_other_verdict_drops_subtype`.

3. **P2 #1 — Coverage accepts non-bool.** `Coverage.__post_init__` now rejects non-bool
   `covered` / `citation_supported` (string `"false"` is truthy in Python — silent scoring
   bug). Regression: `test_p2_1_coverage_rejects_non_bool`.

4. **P2 #2 — identity-pins block missing pathB_gate served-identity + reachability.**
   `score_run` now reads `pathB_gate_pin.json` + `pathB_gate_result.json` and surfaces
   `pathB_gate_identity` in the scored JSON (pinned generator + evaluator slugs,
   reachability_checked, fallbacks flag, provider_order). `aggregate_systems._identity_pins_block`
   now renders a per-polaris-question table:
   "Generator (served) | Evaluator (served) | Reachability | Fallbacks | Provider order".
   Regression: extended `test_score_polaris_passes_with_gate_pass` asserts the
   surfaced `pathB_gate_identity` shape.

5. **P2 #3 — dual-pin incomplete + nondeterministic JSON.**
   - Dropped `build_timestamp_utc` from the snapshot (deterministic by content only).
   - `build_rubric_json.py` now writes BYTES (not `write_text`) so Windows doesn't
     translate LF→CRLF and break the SHA.
   - `--allow-unpinned` is REQUIRED when the markdown pin is missing; otherwise the tool
     refuses.
   - When the markdown is pinned, the rebuilt JSON SHA is also checked against an existing
     `rubric_v3_frozen.json` pin (refuse on mismatch). Re-pinned freeze_pin.txt to the
     correct deterministic SHA `2a39d9dd…`. Verified by re-running the build WITHOUT
     `--allow-unpinned` — succeeds because on-disk SHA == pin.
   Regression: `test_p2_3_build_rubric_json_deterministic_no_timestamp` (same markdown ->
   identical doc; no `build_timestamp_utc` key).

6. **P2 #4 — parser silently under-parses.** `build_rubric_json` now FAILS CLOSED if the
   parsed question set ≠ `_EXPECTED_QUESTIONS` (frozen `("Q75","Q76","Q78","Q72","Q90")`)
   OR any question's element count ≠ `_EXPECTED_ELEMENT_COUNTS`
   (`{Q75: 7, Q76: 8, Q78: 8, Q72: 8, Q90: 8}` totalling 39). Drift in the frozen markdown
   is a freeze violation — raises `ValueError` with question_id + actual vs expected.
   Regression: `test_p2_4_build_rubric_json_fails_closed_on_drift` (Q75 short by 1 →
   raises).

7. **P3 #1 — `_carry_evidence` comment vs behavior.** When BOTH auditors landed on the
   worse verdict, the reconciled note now concatenates both auditors' notes with `" || "`
   (or returns the single non-None note). Comment is now true.

8. **P3 #2 — table cells don't escape pipes/newlines.** Added `_cell()` helper to
   `aggregate_systems`; escapes `|` → `\|` and flattens `\r\n`, `\n`, `\r` → space.
   Applied to every cell that interpolates ledger-derived text (reasons, invalid str,
   identity strings, provider order). Regression:
   `test_p3_2_aggregate_escapes_pipe_in_reasons`.

## Verify (do NOT exec)
- The 8 findings are addressed in the diff.
- The 91/91 test result above includes the 7 new regression tests covering the iter1
  fixes.
- freeze_pin.txt was updated to the new deterministic SHA (visible in the diff).

## Output schema (return EXACTLY this — no exec)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
iter1_findings_closed:
  P1_score_run_requires_reconciled: true | false
  P1_silent_auditor_UNREACHABLE_no_subtype_leak: true | false
  P2_coverage_bool_validation: true | false
  P2_identity_pins_render_served_identity_and_reachability: true | false
  P2_dual_pin_deterministic_and_required: true | false
  P2_parser_fails_closed_on_drift: true | false
  P3_carry_evidence_concatenates_both_notes: true | false
  P3_aggregate_cell_escaping: true | false
convergence_call: continue | accept_remaining
remaining_blockers: []
```
