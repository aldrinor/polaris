# Codex diff review — I-ux-001c sub-PR 4 (Source Review v6 chrome)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Phase

Diff review. Brief APPROVED iter-3 (`.codex/I-ux-001c-4/codex_brief_verdict.txt`).

## Diff under review

`.codex/I-ux-001c-4/codex_diff.patch` — single-file rebuild of `web/app/source_review/page.tsx` header chrome + 1 NEW test file.

## Approved brief acceptance criteria (must verify)

1. Brand-red eyebrow "SOURCES · POLARIS CLINICAL RESEARCH" (text-primary)
2. Display H1 "Review the sources POLARIS will check." (locked copy)
3. Tightened subtitle (locked verbatim per iter-2 P2: "What POLARIS will check for this question — and the per-tier evidence bar the corpus must clear before any claim is written.")
4. Edit-question link moved into eyebrow row (right side) preserving `/intake?q=<encoded>` deep-link
5. `data-testid="source-review-page"` selector preserved
6. ALL substantive logic UNCHANGED: listTemplates, asTemplateId, TIERS, TIER_DOT, TIER_LABEL, prettyDomain, error state, loading state, retry path, no-question fallback link, Continue CTA, /plan handoff
7. NEW `web/tests/e2e/source_review_v6.spec.ts` — 2 cases with mocked `/api/v6/templates`
8. typecheck PASS, lint PASS

## Specific checks (`specific_check_responses`)

- `visual_only_rebuild`: PASS / FAIL — only header chrome lines changed; TierCards/error/loading/retry/no-question/Continue sections bit-identical to HEAD
- `brand_red_paths_preserved`: PASS / FAIL — brand-red usage in three authorized paths (eyebrow + T1 evidence semantic + text-primary affordances) all preserved
- `existing_testids_preserved`: PASS / FAIL — `source-review-page` testid + `/intake?q=` + `/plan?q=&template=` deep-links preserved
- `playwright_test_mocks_api`: PASS / FAIL — new test mocks `**/api/v6/templates` so the auth-gated fetch doesn't race with header-link assertions
- `subtitle_copy_locked`: PASS / FAIL — subtitle text matches the iter-2 P2 lock verbatim

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
  brand_red_paths_preserved: PASS | FAIL_with_detail
  existing_testids_preserved: PASS | FAIL_with_detail
  playwright_test_mocks_api: PASS | FAIL_with_detail
  subtitle_copy_locked: PASS | FAIL_with_detail
```

## Context

- Brief (APPROVE iter-3): `.codex/I-ux-001c-4/brief.md`
- Diff: `.codex/I-ux-001c-4/codex_diff.patch`
- Branch: `bot/I-ux-001c-sub-pr-4-source-review`
