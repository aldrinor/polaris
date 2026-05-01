# Per-commit Codex brief — `e331b08`

**Commit:** `e331b08 PL: v6.2 F-1 root-cause — 4 destructive surfaces + new <pre> contrast fix`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (4):**
- `web/app/dashboard/page.tsx` (-1/+1)
- `web/app/inspector/[runId]/page.tsx` (-7/+7) — 2 surfaces
- `web/app/runs/[runId]/page.tsx` (-2/+2) — error banner + `<pre>` text fix
- `web/tests/e2e/accessibility.spec.ts` (+13/-1) — new run-detail test

## What this commit does

Closes audit P1.1 from `outputs/audits/continuous/4fe03f7_audit.md`. The 2C.5 a11y fix touched 2 destructive surfaces; the subagent flagged 4 more matching the same `text-destructive` + `bg-destructive/{5,10}` pattern that escapes axe coverage in golden fixtures (only renders on failure paths).

This commit refactors all 4 to the same border-only + foreground-text pattern dae2a9f/07d6c30 used:
- **`dashboard/page.tsx:418`** — submit-form error banner.
- **`inspector/[runId]/page.tsx:149`** — Two-family-invariant FAIL card variant.
- **`inspector/[runId]/page.tsx:667`** — Charts-tab error banner.
- **`runs/[runId]/page.tsx:125`** — Run-detail page error banner.

Extending the a11y suite with a `runs/[runId]` failure-path test surfaced ANOTHER violation: 5× `<pre>` blocks at `runs/[runId]/page.tsx:214` rendering SSE event JSON used `text-muted-foreground` on `bg-muted` → 4.34:1 (need 4.5:1). Fixed in same commit by promoting `<pre>` to `text-foreground` (still legible against `bg-muted`).

Verified against the rebuilt prod server (3738):
- 8/8 a11y tests pass (added 2nd error-state test for runs page).
- 9/9 inspector e2e still pass.
- **17/17 in 23.5s on chromium.**

## Acceptance criteria

1. **Same fix pattern applied uniformly.** All 4 surfaces now use `border-destructive/60` + `text-foreground font-medium` (banners) or `border-destructive/60` (cards). No remaining `text-destructive bg-destructive/10` strings in production code paths.
2. **Two-family invariant card body still readable on the failure variant.** Promoted `text-destructive text-xs` → `text-foreground text-sm font-medium` so the warning is more emphatic, not less.
3. **`<pre>` event-block fix** (the new collateral finding) doesn't break readability. `text-foreground` on `bg-muted` is high-contrast dark-on-near-white — actually MORE readable than the old muted-on-muted.
4. **New a11y test exercises the runs page error path.** Visiting `/runs/<bogus>` should show the error banner AND no axe violations. Test passes.
5. **No regression on existing tests.** All 9 inspector e2e + 8 a11y still PASS — fix didn't introduce new selectors or change observable text.

## Codex focus

- **P0:** grep for `text-destructive` in `web/app/` — ANY remaining occurrences? (One legitimate use is the contradictions tab "FAIL"/"warn" badge — verify those pass axe in golden fixtures since they DO render in tested paths.)
- **P0:** Does `bg-muted` itself fail contrast for any other text color used elsewhere (e.g., `text-muted-foreground` on bg-muted is the same 4.34:1 — anywhere this pattern appears outside the just-fixed `<pre>`?)
- **P1:** Did we lose any visual emphasis by removing the bg-destructive tint? The error banners were arguably more "alarming" with the red tint. Trade-off: a11y vs visual hierarchy. Should we add a small destructive-colored icon to compensate?
- **P2:** The `<pre>` fix is a side-effect of the test extension. Was there value in shipping a separate commit for that finding so the audit trail is cleaner? (Current commit message names it explicitly so traceability is OK.)

## Cross-review

Lands at `outputs/audits/continuous/e331b08/cross_review.md`. Counter now **3/5** in the post-4fe03f7 batch.
