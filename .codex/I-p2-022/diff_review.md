# Codex DESIGN+DIFF review — I-p2-022 (#761): dashboard → monitoring-only

HARD ITERATION CAP: 5. iter 4 (iter-3 P1: runs-page New-run→/intake; P2: dashboard copy "completed runs"). visual-baseline P2 = stale win32 baseline deleted, regenerates; non-blocking. Canonical-diff-sha256 `9fa629fd7e17740df90206dd3b56cf22f5557336c967cc523b68ee3d59f7066e`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Context (operator-sequenced)
#754 (just merged) relocated run-start to /plan. The dashboard was the ONLY createRun caller; now /plan is. So this PR safely reframes the dashboard from run-start → MONITORING ONLY (#761 spec).

## Diff
- web/app/dashboard/page.tsx: REPLACED the 668-line run-start workflow (template picker + scope/ambiguity/createRun/uploads/disambiguation) with a monitoring view: listCompletedRuns(50) → runs list; honest verdictOf() uses pipeline_status (NOT lifecycle status — mark_aborted stores status=completed, so an abort must not show "Verified"); rows link to /runs/[id]; "Start new research" → /intake; LoadingState/ErrorState/EmptyState (#750 kit). dashboard-page testid preserved. No createRun here anymore.
- web/tests/e2e/accessibility.spec.ts: the "/dashboard after scope rejection" a11y test → retargeted to /plan?q=<out-of-scope> (scope-check moved there); removed the F-26 "Dashboard template radiogroup keyboard-operable" gate (the radiogroup lived on the old run-start; gone now — documented in a comment).

## Claude visual audit (standalone @1366+@390, sent to operator): "Runs" header + "Start new research" CTA + honest ErrorState (no backend in harness → 500 shown truthfully; renders real runs list on live VM). Monitoring-only confirmed; no run-start form.

## Review focus
1. HONESTY: verdictOf uses pipeline_status (an aborted run must NOT render "Verified")? Empty/error/loading all honest (no fake spinner/generic copy)?
2. Did removing run-start leave any dangling consumer expecting the dashboard form? (createRun now only at /plan — confirm.) e2e edits correct (no remaining /dashboard run-start refs)?
3. a11y of the list (links, focus-visible) + responsive. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
