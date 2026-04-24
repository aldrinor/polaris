V30 Phase-2 fix plan — Codex pass-4 review.

## Context

Pass-3 verdict: CONDITIONAL (5/7 checks pass; 2 blockers remain):
- M-63 fix #3 "generalize OR alias" still reopened → committed
  to GENERALIZE only.
- `coverage_semantics` inconsistent (long-form strings in M-64)
  → canonicalized to `phase1_retrieval_coverage` /
  `phase2_report_coverage`.

Both fixed in the latest plan revision. Remaining references to
`phase1_retrieval_coverage_only` are the Phase-1 warning NAME
(historical fact, not an enum value).

## What to verify

Read `outputs/audits/v30_phase2/fix_plan_phase2.md`:

1. M-63 fix #3 (around line 98-115): commits to GENERALIZE
   regex, explicitly says "NO alias layer. This is the one
   committed path."
2. M-64 fix #4 (around line 287-306): uses canonical enum
   values `phase2_report_coverage` (not the long form).
   Historical references to `phase1_retrieval_coverage_only`
   as the WARNING NAME being replaced are fine.
3. Acceptance lines 308-314: use `phase2_report_coverage`.

## Output

Write to
`outputs/codex_findings/v30_phase2_plan_review_pass1/pass4_findings.md`.

```
Verdict: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL | REJECT
Finding 4 (pass-3): <closed / still open>
Finding 7 (pass-3): <closed / still open>
Implementation greenlight: yes/no
```

Keep under 40 lines. If APPROVED or CONDITIONAL-no-blockers,
Claude auto-runs M-63 immediately.
