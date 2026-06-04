# Codex diff review — I-ux-001c sub-PR 7 (/runs/[runId] v6 chrome)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Phase

Diff review. Brief APPROVED iter-1 (accept_remaining, 0 P0/P1, 6/6 PASS).

## Diff under review

`.codex/I-ux-001c-7/codex_diff.patch` — header chrome rebuild in `web/app/runs/[runId]/page.tsx` + v6 cases folded into existing `web/tests/e2e/runs_runid_g1_g8.spec.ts`.

## Approved brief acceptance criteria (must verify)

1. NEW brand-red category eyebrow "LIVE RUN · POLARIS CLINICAL RESEARCH" (text-primary, tracking-[0.14em])
2. PROMOTED "Run {runId}" eyebrow to brand-red (text-primary)
3. Display H1 (text-3xl sm:text-4xl font-bold) with dynamic question content + loading/error fallback preserved
4. `data-testid="runs-runid-page"` + sub-component testids preserved
5. Action row (Export-bundle + New-run) preserved verbatim
6. ALL SSE/cancel/bundle/RunProgress/FollowupPanel logic UNCHANGED
7. v6 cases folded into `runs_runid_g1_g8.spec.ts` (CI-run per web_ci.yml:192)
8. Mock targets BOTH `/api/v6/runs/{id}` (status fetch) AND `/api/v6/stream/{id}` (SSE) — per brief iter-1 P2 fix
9. typecheck PASS

## Specific checks (`specific_check_responses`)

- `visual_only_rebuild`: PASS / FAIL — header region only; SSE/cancel/bundle preserved verbatim
- `dynamic_h1_preserved`: PASS / FAIL — H1 content stays the dynamic question text; only typography changed
- `eyebrows_brand_red`: PASS / FAIL — both eyebrows use text-primary
- `v6_tests_ci_wired`: PASS / FAIL — v6 cases added to runs_runid_g1_g8.spec.ts (CI-run), not standalone
- `mock_targets_correct`: PASS / FAIL — mocks `/api/v6/runs/{id}` status AND `/api/v6/stream/{id}` SSE
- `existing_testids_preserved`: PASS / FAIL — runs-runid-page testid preserved; sub-components untouched

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
  dynamic_h1_preserved: PASS | FAIL_with_detail
  eyebrows_brand_red: PASS | FAIL_with_detail
  v6_tests_ci_wired: PASS | FAIL_with_detail
  mock_targets_correct: PASS | FAIL_with_detail
  existing_testids_preserved: PASS | FAIL_with_detail
```

## Context

- Brief (APPROVE iter-1): `.codex/I-ux-001c-7/brief.md`
- Diff: `.codex/I-ux-001c-7/codex_diff.patch`
- Branch: `bot/I-ux-001c-sub-pr-7-runs-runid`
