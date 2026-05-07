# Codex Diff Review — I-f7-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f7-004 — F7 adversarial 0/15, 15/15, 1/15 edge variants
**Brief:** APPROVED iter 3
**Canonical-diff-sha256:** `523c873815733c0ccd0973fe57872e78ce12cabfeb9cfa2a2263904ae9d96194`
**LOC:** 178 net (under CHARTER §1 200-cap)

## Files

```
web/app/sentence_hover_test/_demo_coverage.tsx           NEW +109 (CoverageHarness with cycled GAP_REASONS)
web/app/sentence_hover_test/coverage/page.tsx            NEW +21 (Next route + clamp_non_negative_int helper)
web/tests/e2e/frame_coverage_adversarial.spec.ts         NEW +43 (3 edge tests, ratio text + count assertions)
```

## What changed

- `CoverageHarness({covered, gap_count})` builds a synthetic VerifiedReport with `total_entity_count = covered + gap_count` and `gaps` of length `gap_count` cycled through `GAP_REASONS` literal array (Codex iter-1 P2 fix — TS union, not enum).
- `coverage/page.tsx`: `clamp_non_negative_int` allows ZERO (Codex iter-1 P1 fix), clamps to [0, 100], parses search params.
- 3 Playwright tests covering 0/15, 15/15, 1/15 — each asserts ratio text (`covered/total`) per Codex iter-2 P2 + gap-count + last-index visibility.

## Verification
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Search-param clamping:** zero allowed; max 100. Defaults 14/1 mirror existing demo.
2. **GAP_REASONS array:** explicit typed `GapReason[]` literal — no enum import attempt.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 178 net. Under 200.
5. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
