# Codex diff review — I-ux-001c sub-PR 8 (Compare v6 chrome + new CI spec)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Phase

Diff review. Brief APPROVED iter-1 clean (0 P0/P1/P2, 5/5 PASS).

## Diff under review

`.codex/I-ux-001c-8/codex_diff.patch` — header chrome rebuild in `web/app/compare/page.tsx` + NEW `web/tests/e2e/compare_g1_g8.spec.ts` + web_ci.yml block enumerating the new spec.

## Approved brief acceptance criteria

1. Brand-red eyebrow "COMPARE · POLARIS CLINICAL RESEARCH" (text-primary)
2. Display H1 "Compare two runs side-by-side."
3. Tightened subtitle locked verbatim
4. compareRuns + listCompletedRuns + ReportComparison rendering UNCHANGED
5. NEW compare_g1_g8.spec.ts with G1+G2+G8+nav-parity+v6 chrome cases (5 tests)
6. web_ci.yml updated to enumerate the new spec
7. `data-testid="compare-page"` + `comparison-result` preserved
8. typecheck PASS

## Specific checks (`specific_check_responses`)

- `visual_only_rebuild`: PASS / FAIL — only header changed; compare logic preserved
- `existing_testids_preserved`: PASS / FAIL — compare-page + comparison-result preserved
- `new_spec_g1_g8_complete`: PASS / FAIL — new compare_g1_g8.spec.ts has G1, G2, G8, nav-parity, plus v6 chrome
- `ci_wired_via_yaml`: PASS / FAIL — web_ci.yml has run_e2e_compare_g1_g8 block enumerating the new spec
- `mock_targets_correct`: PASS / FAIL — page.route targets `**/api/v6/runs**`

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
  new_spec_g1_g8_complete: PASS | FAIL_with_detail
  ci_wired_via_yaml: PASS | FAIL_with_detail
  mock_targets_correct: PASS | FAIL_with_detail
```

## Context

- Brief: `.codex/I-ux-001c-8/brief.md`
- Diff: `.codex/I-ux-001c-8/codex_diff.patch`
- Branch: `bot/I-ux-001c-sub-pr-8-compare`
