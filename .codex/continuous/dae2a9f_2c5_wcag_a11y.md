# Per-commit Codex brief — `dae2a9f`

**Commit:** `dae2a9f PL: v6.2 Phase 2C.5 WCAG-AA audit + scope-card color-contrast fix`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (5):**
- `web/tests/e2e/accessibility.spec.ts` (new, 6 tests, ~95 lines)
- `web/app/dashboard/page.tsx` (a11y fix on scope-rejected card)
- `web/package.json` (+@axe-core/playwright ^4.11.3)
- `web/package-lock.json` (lockfile churn)
- `docs/todo_list.md` (mark 2C.5 done)

## What this commit does

Adds the WCAG-AA accessibility audit (Phase 2C.5) using `@axe-core/playwright` v4.11.3. The new test suite hits 6 distinct user-visible states across 3 routes — dashboard initial, dashboard after scope-rejection, Inspector Executive summary, Inspector Verified, Inspector Charts (with Vega SVG rendered), Inspector Contradictions — and runs axe with the WCAG 2A + 2AA + 2.1AA + 2.2AA + best-practice rule sets.

The first run surfaced **a real serious-severity color-contrast violation** on the dashboard scope-rejected card:
- `.text-destructive` body text on `bg-destructive/5` background → 4.36:1 (need 4.5:1).
- `.text-muted-foreground` CardDescription on the same background → 4.33:1.

Root cause: tinted-red background under near-black/red text drops below the AA contrast floor at 12px font size. **Fix**: dropped the tinted background entirely (kept `border-destructive/60` for the visual semantic), and bumped the body lines to `text-foreground text-sm font-medium` so they pass AA at the current size.

After the fix:
- 6/6 a11y tests pass on chromium (10.9s).
- 9/9 inspector e2e still pass (no regression on scope-rejection text-find).

## Acceptance criteria

1. **Real violation, real fix.** Codex MUST verify the fix isn't just suppressing the rule (no `axe-builder.disableRules(['color-contrast'])`); we changed actual classnames so the rule passes legitimately.
2. **WCAG tag breadth.** The audit covers wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, and best-practice — not the loose `wcag2a` alone.
3. **Loud failure.** When axe finds violations, the helper throws an `Error` with the rule id, severity, affected node selectors, AND axe's own `failureSummary` so the next engineer sees the fix path immediately. No silent `expect.toEqual` that hides the diagnostic.
4. **No regression on existing e2e.** The Dashboard scope-rejection test still finds the `Rejected` text + `clinical_treatment_recommendation` reason; only the visual styling changed.
5. **No mocking.** Tests run against the live Next.js production build at `/dashboard` and `/inspector/{runId}`; no Playwright route interception.

## Codex focus

- **P0:** Are there other surfaces using the same `bg-destructive/5` + `text-destructive` pattern that ALSO fail but weren't covered by the 6-test suite? (`runs/[runId]/page.tsx:125`, `inspector/[runId]/page.tsx:121,144,157,310,662` all reference it.)
- **P0:** The Charts tab a11y test uses `golden_climate_005`. Does Vega-Lite's auto-generated SVG include accessible roles (`role="img"`, `aria-label`)? axe sometimes misses chart accessibility because the SVG content is dynamic — should we add a stricter assertion?
- **P1:** Does the WCAG-AA gate need to also run on `webkit` and `firefox`? Color-contrast computation is engine-agnostic but focus-visible rules can differ.
- **P2:** Should the helper accept an `allowlist` of rule ids per page so we can document known-acceptable exceptions (e.g., `region` rule for embedded charts)?

## Cross-review

Lands at `outputs/audits/continuous/dae2a9f/cross_review.md`.
