# Codex Brief Review — I-p2c-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-p2c-005 — Mobile end-to-end. Scope: mobile viewport full flow. Acceptance: Playwright mobile. LOC estimate 130.
- **Substrate today:** existing `p2c_001_chain.spec.ts` walks F1→F5 on default viewport. No mobile-viewport chain spec.
- **Honest framing per CLAUDE.md §9.4:** ship a Playwright spec that runs the F1→F5 chain on mobile viewport (375×667, iPhone-13 user agent). Asserts each page renders + the mobile-specific `evidence-tooltip-touch-active` (per existing I-f6-003 mobile-tap-to-show) renders on the F5 fixture page. NOT a test for backend pipeline; same scope as I-p2c-001.

## Plan

### `web/tests/e2e/p2c_005_mobile.spec.ts` (NEW)

1. `test.use({ viewport: { width: 375, height: 667 }, hasTouch: true, isMobile: true })` so all tests in the file render mobile-style.
2. F1: `/intake` — assert `intake-form` and `intake-question-input`.
3. F2: `/disambiguation_modal_preview` — assert `disambiguation-cluster-0`.
4. F3: `/upload` — assert `upload-dropzone`.
5. F4: `/sse` — assert `sse-harness`.
6. F5: `/sentence_hover_test/evidence_tooltip` — assert `evidence-tooltip-trigger`, then perform `tap()` on trigger, assert `evidence-tooltip-popup` becomes visible (mobile tap fallback per I-f6-003).
7. Single test asserts all 5 step-counters complete.

## Risks for Codex Red-Team

1. **Mobile tap behavior:** `page.touchscreen.tap(x, y)` or `locator.tap()` triggers actual touch events on `hasTouch: true` context.
2. **Existing testid contracts:** same as p2c_001_chain — verified at write-time.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** estimated ~70 LOC. Comfortable.

## Acceptance criteria

1. New `web/tests/e2e/p2c_005_mobile.spec.ts` runs F1→F5 page-render chain on mobile viewport (375×667, hasTouch).
2. F5 step explicitly tests mobile tap-to-show via `tap()`.
3. Spec docstring notes mobile-viewport scope.
4. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-4.
**Completeness check:** list files actually read.

## Output schema

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
