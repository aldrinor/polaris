# Per-commit Codex brief — `2057fac`

**Commit:** `2057fac PL: v6.2 Phase 2C.2 visual regression baselines — 4/4 stable on chromium`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (6):**
- `web/tests/e2e/visual.spec.ts` (new, 4 tests)
- `web/tests/e2e/visual.spec.ts-snapshots/dashboard-initial-chromium-win32.png`
- `web/tests/e2e/visual.spec.ts-snapshots/inspector-executive-summary-chromium-win32.png`
- `web/tests/e2e/visual.spec.ts-snapshots/inspector-verified-sentences-chromium-win32.png`
- `web/tests/e2e/visual.spec.ts-snapshots/inspector-error-state-chromium-win32.png`
- `docs/todo_list.md` (mark 2C.2 done)

## What this commit does

Phase 2C.2 — establishes baseline screenshots for 4 high-traffic surfaces using Playwright's built-in `toHaveScreenshot`. Each baseline:

- Captures `fullPage: true` (covers below-the-fold layout regressions).
- `animations: "disabled"` to freeze tw-animate-css transitions.
- `maxDiffPixelRatio: 0.02` — generous 2% threshold absorbs font-hinting drift across CI hardware without missing genuine layout breakage (button vanishing, card shifting, color regression, content collapse).
- Masks the runId text in headers so per-run identifiers don't blow the diff.

Re-baseline command (when intentional UI changes land):
```
SCREENSHOT_BASE_URL=http://127.0.0.1:3738 \
  npx playwright test --project=chromium tests/e2e/visual.spec.ts \
  --update-snapshots
```

Verified: 4/4 baselines generated cleanly, then re-run without `--update-snapshots` shows 4/4 PASS in 5.4s (proves stability — same render, same diff = OK).

## Acceptance criteria

1. **Baselines exist on disk + are committed.** Git shows 4 PNG files under `web/tests/e2e/visual.spec.ts-snapshots/`. Without these, the suite can't gate against regressions on subsequent runs.
2. **Re-baseline path documented.** Spec file header has the exact command for regenerating after legitimate UI changes; otherwise developers will be tempted to `--update-snapshots` blindly on every diff.
3. **Threshold is justified, not magic.** 2% pixel diff = ~25k pixels at 1440x900 fullpage; large enough to absorb anti-aliasing drift, small enough to catch e.g. a 100x100 button moving ≥50px.
4. **Dynamic regions masked.** RunId text masking means re-running against `golden_clinical_001` always produces the same baseline-relevant diff. Verify no other dynamic regions sneak in (timestamps, "queued at" lines, vega tooltips).
5. **No baseline drift between consecutive runs of the SAME state.** Running twice in a row must succeed; demonstrated above (5.4s clean re-run).

## Codex focus

- **P0:** The 2% threshold + fullPage means a small change to one component (e.g., adding a 30px tall banner) could pass under threshold despite shifting everything below by 30px. Should we capture per-card screenshots instead of fullPage to catch this?
- **P0:** Cross-OS baselines: the snapshot filenames are `*-chromium-win32.png`. On Linux CI these become `*-chromium-linux.png` and would need separate baselines. Are we OK with Windows-only baselines for now, or should we generate Linux ones via Docker before CI lands?
- **P1:** No baseline yet for Charts tab (Vega-Lite SVG renders nondeterministically across font versions). Defer to Codex review whether to add with a higher threshold or skip permanently.
- **P2:** Should we also baseline dark-mode renders? The frontend has next-themes but the e2e config locks `colorScheme: "light"`.

## Cross-review

Lands at `outputs/audits/continuous/2057fac/cross_review.md`. Counter now **3/5** toward C-trigger.
