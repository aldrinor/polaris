V30 sweep integration audit — pass 2.

**Skip git status.** Three files only.

## Context

Pass-1 verdict: CONDITIONAL-blockers. Commit `d816d4c` addresses:

- Blocker: phase-1 synth now cross-checks each entity against
  `legacy_report_text` + `legacy_bibliography` via
  `_entity_cited_in_legacy()`. Non-gap + NOT cited →
  FAIL_UNBOUND_CITATION (engineer-owned). Non-gap + no cross-
  check → PASS with explicit "phase1_synth_retrieval_only"
  warning. Gap → FAIL_MIN_FIELDS unchanged.
- Medium 1 (non-hermetic gating): runner's PG_V30_ENABLED check
  now happens BEFORE the import. Disabled runs touch no V30
  code.
- Medium 2 (report.md append boundary): factored into
  `append_disclosure_to_report(path, text) -> bool`. Returns
  False when path missing; never creates a file.
- Medium 3 (runner hook untested): factored
  `merge_v30_into_manifest(manifest, v30_result)` and added
  6 TestRunnerHookMergeHelper tests.
- Nit 1 (no_contract): new `skipped_reason` field on
  V30SweepResult; runner surfaces as
  manifest["v30_skipped_reason"].
- Nit 2 (stale comment): cleaned up.

Regression: 313/313 scoped V30 pass.

## What to verify

Files (commit `d816d4c`):

1. `src/polaris_graph/v30_sweep_integration.py` — new helpers
   `_entity_cited_in_legacy`, `merge_v30_into_manifest`,
   `append_disclosure_to_report`; new `skipped_reason` field.
2. `scripts/run_honest_sweep_r3.py` — hermetic gating; uses
   the factored helpers.
3. `tests/polaris_graph/test_v30_sweep_integration.py` —
   17 tests (was 9; +8).

Check each of the six:

1. **Blocker**: phase-1 synth correctly cross-checks against
   legacy output.
   - Fully cited → PASS
   - Partially cited → cited=PASS, uncited=FAIL_UNBOUND_CITATION
   - No cross-check → PASS + warning
   - Gap → FAIL_MIN_FIELDS
   Verify `_entity_cited_in_legacy()` covers DOI/PMID/
   url_pattern in bibliography PLUS DOI/anchor/label_name/
   url_pattern as report substring.
2. **Medium 1**: the runner's V30 block is fully gated. An
   import-time failure of v30_sweep_integration can't stamp
   manifest["v30_error"] when PG_V30_ENABLED=0.
3. **Medium 2**: append_disclosure_to_report returns False for
   missing report; never creates a file.
4. **Medium 3**: merge_v30_into_manifest matches the runner's
   expectations. TestRunnerHookMergeHelper covers the four
   code paths (disabled/coverage/skipped_reason/error+warnings)
   + report.md append boundary.
5. **Nit 1**: compile_frame returning None → skipped_reason=
   "no_contract_for_slug". FrameCompilerError →
   "compile_frame_error".
6. **Nit 2**: completions comment accurate.

**Second-round adversarial attempts** (xhigh budget):
- Any remaining path where V30 can mutate manifest when
  disabled?
- Any legacy-output cross-check that false-passes (e.g. a
  DOI substring that accidentally matches unrelated content)?
- Any edge case where phase-1 synth emits a verdict that
  contradicts M-60 routing (e.g. FAIL_UNBOUND_CITATION gets
  routed to curator)?

## Output

Write to
`outputs/codex_findings/v30_sweep_integration_audit/pass2_findings.md`.

Format:
```markdown
# Codex V30 sweep integration audit — pass 2

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Blocker resolution
<verified / still open>

## Medium 1/2/3 resolutions
<verified>

## Nit 1/2 resolutions
<verified>

## Adversarial attempts
<list each>

## Residual concerns
<anything>

## Next
On APPROVED / CONDITIONAL-no-blockers: sweep integration is
ready for live-run exercise.
```

Keep under 100 lines.
