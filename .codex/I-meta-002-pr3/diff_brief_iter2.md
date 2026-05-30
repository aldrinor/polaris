# Codex DIFF-gate — I-meta-002 sub-PR-3 — iter 2 of 5

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Reserve P0/P1 for real execution/safety risks; classify minor issues P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

## What changed since your iter-1 diff review
Your iter-1 verdict was REQUEST_CHANGES, zero P0, two P1 (both empirically reproduced):

> P1-a (release_policy.py:274): release_allowed ignores needs_rewrite, so a first-pass material
> UNSUPPORTED/UNREACHABLE or PARTIAL S0/S1 can return release_allowed=True before the required
> rewrite/refuse-in-place attempt.
> P1-b (release_policy.py:204): residual below-coverage hold requires a CURRENT
> UNSUPPORTED/UNREACHABLE row; after rewrite_already_attempted=True, dropping/refusing that row
> can leave fixed-ledger coverage below threshold but still release with no gap or held reason.

**Fixes applied:**
- **P1-a:** added held reason `d8_pending_rewrite`. After all gates, `if needs_rewrite:
  held_reasons.append(_REASON_PENDING_REWRITE)`. So any pass with pending rewrites is NOT
  releasable (`release_allowed = not held_reasons`). A first-pass material UNSUPPORTED now holds.
- **P1-b:** the coverage floor is now UNCONDITIONAL on the ledger — `if
  coverage_ledger.fraction() < coverage_threshold: hold + coverage_shortfall gap`. The previous
  `residual_below_coverage` (row-presence) precondition is REMOVED. Dropping/refusing the row no
  longer dodges the gate (the fixed denominator means a missing claim lowers the fraction). This
  also closes the corner where a required element simply had no claim at all. Per-row residual
  gaps are still emitted post-attempt for transparency (separate from the gate).

This is a deliberate, strictly-safer strengthening of brief item 3: the coverage floor holds on
the ledger regardless of whether a residual row is present. New stable codes: `d8_pending_rewrite`
(held reason), `coverage_shortfall` (gap kind).

**Your exact iter-1 reproductions are now regression tests and pass:**
- `test_first_pass_pending_rewrite_blocks_release_codex_p1a` — first-pass UNSUPPORTED -> release_allowed=False, d8_pending_rewrite.
- `test_dropped_residual_below_coverage_still_holds_codex_p1b` — rewrite_already_attempted=True, residual row DROPPED, ledger 0.25 < 0.70 -> release_allowed=False, d8_unsupported_residual_below_coverage + coverage_shortfall gap.

## Smoke (serialized, §8.4)
- `pytest tests/roles tests/architecture tests/dr_benchmark -q` -> 223 passed, 0 failed.
- `verify_lock --consistency` -> exit 0.
- Frozen `claim_audit_scorer.py` untouched (zero diff); `polaris_pipeline_canonical.md` not drifted.

## Review ask
Re-probe `apply_d8_release_policy`: can ANY pass return release_allowed=True while (a) a material
claim is still pending its first rewrite, or (b) fixed-ledger coverage < threshold, or (c) a
FABRICATED was ever seen, or (d) an S0 must-cover category lacks a VERIFIED claim? APPROVE iff
none of these can release and there is no new perverse drop/refuse incentive.

## DIFF (full sub-PR-3 diff, both fixes included)
