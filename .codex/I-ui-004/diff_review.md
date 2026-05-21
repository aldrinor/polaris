# Codex DIFF review — I-ui-004 (#543) run-compare view

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings. P0/P1 for real execution risks only. APPROVE iff zero P0/P1. Final line MERGE AUTHORIZED if mergeable. web/ only.

Canonical-diff-sha256: `350b5f29ec4e05104d162afd793869b7351245830a9ff74eb9ccde06c94be52f`. 4 files, 319+.

## EMPIRICAL: typecheck clean, lint 0 errors, npm build SUCCEEDS (/compare prerendered). e2e pending #720.

## Implements the brief you APPROVE'd (iter 1). Diff: .codex/I-ui-004/codex_diff.patch.
- web/lib/api.ts — ReportComparison type + listCompletedRuns(limit) (GET /runs?status=completed) + compareRuns(l,r) (GET /runs/{l}/compare/{r}); both authFetch + asJsonOrThrow.
- web/app/compare/page.tsx (NEW) — two run-pickers from listCompletedRuns; Compare disabled unless two distinct; renders ReportComparison (%shared, flags, evidence/frame columns, contradictions); error 400/404/422; empty-list → /intake.
- nav: "Compare" added to both PRIMARY_NAVs (app_shell.tsx + home_keyboard_shell.tsx) after Benchmark.

## Review focus
1. Clients: authFetch + asJsonOrThrow correct; listCompletedRuns shape RunStatusResponse[] (matches #705 endpoint)?
2. distinct-guard (UI disable) + backend 400 fallback + error mapping (400/404/422) correct?
3. shared_evidence_pct (0..1) → Math.round(*100)%.
4. Nav parity (both files) — G1 "identical nav across routes"; home_g1_g8 8-label loop still passes with the 9th link?
5. Defensive rendering of arrays/counts.
6. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: [...]
```
