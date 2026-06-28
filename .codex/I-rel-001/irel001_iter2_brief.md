HARD ITERATION CAP: 5 per document. This is iter 2 of 5 (re-gate of a bug-fix on the APPROVED I-rel-001).
- Reserve P0/P1 for real execution risks. Verdict APPROVE iff zero P0 AND zero P1.

REVIEW MODE: STATIC only. Read the diff `.codex/I-rel-001/irel001_iter2_fix.patch` (the ONLY change since the APPROVED I-rel-001 commit 53219194). Emit the verdict schema.

# I-rel-001 iter-2 — fix UnboundLocalError that prevented the A18 reroute from firing

## What the validation run exposed
The committed I-rel-001 A18 reroute referenced `four_role_result.coverage_fraction` for the seam screen's
coverage_fraction arg. On the real fresh drb_72 run, `four_role_result` is UNBOUND at the handler (it is only
assigned inside the D8/seam block, which the D8-never-fired path — the exact case A18 fires on — skips). So the
reroute raised UnboundLocalError, was caught by the outer `except`, and FELL THROUGH to the legacy hold:
`[release-invariant] A18 unadjudicated reroute: fabrication screen could not run (UnboundLocalError ... 'four_role_result'); FAIL CLOSED`.
It failed SAFE (no un-screened release — faithfulness intact) but the intended release-with-label never fired.

## The fix (the ONLY diff)
Wrap the coverage lookup in `try: _a18_coverage = float(getattr(four_role_result,'coverage_fraction',0.0) or 0.0)
except NameError: _a18_coverage = 0.0`, and pass `coverage_fraction=_a18_coverage`. When `four_role_result` is
unbound, coverage defaults to 0.0 (honest-conservative: coverage_fraction only feeds the disclosed
release_quality_score; the fabrication SCREEN `body_withheld`, not coverage, gates ship). The reroute now executes.

## Verify
1. Does the NameError guard correctly let the reroute run with coverage=0.0 when four_role_result is unbound, AND
   still use the real coverage when it IS bound?
2. Does this change the ship/withhold decision in any way? (It must NOT — ship is still gated strictly on
   build_seam_release_outcome body_withheld==False; coverage_fraction does not affect that.)
3. Faithfulness gates untouched; release_policy.py untouched. The outer `except` still fail-closes on a genuine
   screen error.

## Validation: 59 tests pass (test_irel001_unadjudicated_release 6 + test_iarch007_regression + test_release_invariant_iarch007).

## Output schema (REQUIRED, last lines)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: []
```
