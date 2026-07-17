# Codex diff review — I-ux-001c sub-PR 5 (Plan Review v6 chrome)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Phase

Diff review. Brief APPROVED iter-1 clean (0 P0/P1/P2, all 5 specific checks PASS).

## Diff under review

`.codex/I-ux-001c-5/codex_diff.patch` — single-file header chrome rebuild of `web/app/plan/page.tsx` + 1 NEW test file.

## Approved brief acceptance criteria (must verify)

1. Brand-red eyebrow "PLAN · POLARIS CLINICAL RESEARCH" (text-primary)
2. Display H1 "Confirm the plan before the run." (locked copy)
3. Tightened subtitle locked verbatim: "Re-checked end-to-end — POLARIS will only start the run when the question, scope, and template are all clear."
4. Edit-question link moved into eyebrow row (right side) preserving `/intake` deep-link
5. `data-testid="plan-page"` selector preserved
6. ALL substantive logic UNCHANGED: runIntake, runDisambiguation, createRun, ConcurrentRunError handling, vetted-question card, plan steps, Start-run button, error/concurrent/blocked states
7. NEW `web/tests/e2e/plan_v6.spec.ts` — 2 cases with mocked `/api/v6/intake`
8. typecheck PASS, lint PASS

## Specific checks (`specific_check_responses`)

- `visual_only_rebuild`: PASS / FAIL — only header chrome lines changed; remainder bit-identical to HEAD
- `existing_testids_preserved`: PASS / FAIL — plan-page, plan-blocked, plan-concurrent, plan-start-run preserved
- `playwright_test_mocks_api`: PASS / FAIL — new test mocks `**/api/v6/intake` so the auth-gated re-check doesn't race
- `subtitle_copy_locked`: PASS / FAIL — subtitle text matches the brief lock verbatim
- `back_link_preserved`: PASS / FAIL — Edit-question link still `href="/intake"`

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
  playwright_test_mocks_api: PASS | FAIL_with_detail
  subtitle_copy_locked: PASS | FAIL_with_detail
  back_link_preserved: PASS | FAIL_with_detail
```

## Context

- Brief (APPROVE iter-1): `.codex/I-ux-001c-5/brief.md`
- Diff: `.codex/I-ux-001c-5/codex_diff.patch`
- Branch: `bot/I-ux-001c-sub-pr-5-plan-review`
