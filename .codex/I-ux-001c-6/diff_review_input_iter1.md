# Codex diff review — I-ux-001c sub-PR 6 (Dashboard v6 chrome)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Phase

Diff review. Brief APPROVED iter-5 (5-cap converged, 0 P0/P1/P2, 5/5 PASS).

## Diff under review

`.codex/I-ux-001c-6/codex_diff.patch` — header chrome rebuild in `web/app/dashboard/page.tsx` + v6 cases folded into existing `web/tests/e2e/dashboard_g1_g8.spec.ts`.

## Approved brief acceptance criteria (must verify)

1. Brand-red eyebrow "RUNS · POLARIS CLINICAL RESEARCH" (text-primary)
2. Display H1 "Your recent runs." (locked copy)
3. Honest subtitle "Open one to replay the proof, claim by claim — every brief carries its own audit bundle." ('audit bundle' not 'signed bundle' per iter-4 honest fix)
4. Start-new-research CTA preserved in same row position (right side) with `data-testid="dashboard-start-run"`
5. `data-testid="dashboard-page"`, `runs-list`, `run-row-*` testids preserved
6. listCompletedRuns + LoadingState + ErrorState + EmptyState + run-row rendering + verdict pills + inspector deep-links UNCHANGED
7. v6 cases folded into `dashboard_g1_g8.spec.ts` (CI-run per web_ci.yml:185)
8. typecheck PASS, lint PASS

## Specific checks (`specific_check_responses`)

- `visual_only_rebuild`: PASS / FAIL — only header region changed; runs-list/states preserved verbatim
- `existing_testids_preserved`: PASS / FAIL — dashboard-page, dashboard-start-run, runs-list, run-row-* preserved
- `start_run_cta_preserved`: PASS / FAIL — link still href="/intake" with same testid
- `subtitle_honest`: PASS / FAIL — "audit bundle" (not "signed bundle"); matches honest sovereignty constraint
- `v6_tests_ci_wired`: PASS / FAIL — v6 cases added to dashboard_g1_g8.spec.ts (the CI-run file per web_ci.yml:185), not a standalone dead file
- `playwright_mock_correct`: PASS / FAIL — mock targets `**/api/v6/runs**` matching the real listCompletedRuns URL pattern

## Output schema (BIND)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  visual_only_rebuild: PASS | FAIL_with_detail
  existing_testids_preserved: PASS | FAIL_with_detail
  start_run_cta_preserved: PASS | FAIL_with_detail
  subtitle_honest: PASS | FAIL_with_detail
  v6_tests_ci_wired: PASS | FAIL_with_detail
  playwright_mock_correct: PASS | FAIL_with_detail
```

## Context

- Brief (APPROVE iter-5): `.codex/I-ux-001c-6/brief.md`
- Diff: `.codex/I-ux-001c-6/codex_diff.patch`
- Branch: `bot/I-ux-001c-sub-pr-6-dashboard`
- Follow-up filed: #892 (other v6 specs are also CI-dead; fold or update web_ci.yml)
