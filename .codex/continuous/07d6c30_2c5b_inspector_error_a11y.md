# Per-commit Codex brief — `07d6c30`

**Commit:** `07d6c30 PL: v6.2 Phase 2C.5 follow-up — Inspector error-state a11y fix`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (2):**
- `web/app/inspector/[runId]/page.tsx` (+11/-3): error-banner restructure
- `web/tests/e2e/accessibility.spec.ts` (+15/-0): new error-state describe block

## What this commit does

Acts on the dae2a9f brief P0 finding. Extending the WCAG-AA test suite to cover Inspector error states (visit `/inspector/<bad-runid>`) surfaced **2 more real WCAG violations** that the original 6-test suite missed:

1. `color-contrast` [serious] — `text-destructive` (#e7000b) on `bg-destructive/10` (#fde6e7) → 4.0:1 ratio (need 4.5:1).
2. `page-has-heading-one` [moderate] — when bundle fetch fails, `bundle.question` (the only h1 on the page) never renders, leaving the page with no level-1 heading.

**Fix**: replaced the bare `<p role="alert">` error banner with a proper `<section role="alert" aria-labelledby="inspector-error-heading">` wrapper. The section contains an `<h1 id="inspector-error-heading">Bundle load failed</h1>` (satisfies `page-has-heading-one` AND gives screen readers the alert context) plus a high-contrast border-only message paragraph using `text-foreground font-medium` (passes contrast).

After the fix:
- 7/7 a11y tests pass on chromium (11.9s) — including the new `Inspector destructive error banner (invalid runId)` test.
- 9/9 inspector e2e still pass — no regression on the success-path Inspector tabs.

## Acceptance criteria

1. **Real bug caught + fixed.** The new test ACTUALLY triggers the error path by navigating to `/inspector/does_not_exist_runid_404`, not by mocking the fetch error. Confirms the prod build serves the error banner correctly.
2. **Heading hierarchy is semantically correct.** The error h1 ("Bundle load failed") doesn't conflict with the success-path h1 ("{bundle.question}") because they render in mutually exclusive branches.
3. **No suppressed rules.** Codex MUST verify we didn't add a `disableRules(['color-contrast'])` or page-level allow-listing. The fix changed the actual classnames + DOM structure.
4. **Existing dashboard test still passes.** The dashboard scope-rejection test (which uses similar destructive styling) is unaffected — it was already fixed in dae2a9f.
5. **Same error message text preserved.** The user-visible string is still `{error}` from the catch block, so existing test assertions like `getByText(/POLARIS backend returned 404/i)` keep working.

## Codex focus

- **P0:** `runs/[runId]/page.tsx:125` and `inspector/[runId]/page.tsx:662` use the same `text-destructive border-destructive/50 bg-destructive/10` pattern. The new test only covers the inspector top-level error banner; should we extend coverage to the runs page error and the per-section regen-failure banner inside Sentences tab?
- **P0:** Did changing the error wrapper from `<p>` to `<section>` break any consumer that depended on the old DOM (e.g., a CSS selector somewhere)? grep for `[role="alert"]` confirms no other code targets it.
- **P1:** Should we add a "Return to dashboard" link inside the error section so users have an obvious recovery path? Currently they can use the breadcrumb but the action isn't called out.
- **P2:** The error h1 says "Bundle load failed" — could be more descriptive (e.g., "Run {runId} could not be loaded") for clearer page titles in browser tabs/screen readers.

## Cross-review

Lands at `outputs/audits/continuous/07d6c30/cross_review.md`. Counter now at **2/5** toward next adversarial-reviewer subagent trigger.
