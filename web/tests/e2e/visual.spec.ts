import { expect, test } from "@playwright/test";

/**
 * Phase 2C.2 — visual regression baselines.
 *
 * Captures one screenshot per major user-facing surface and compares against
 * the committed baseline on every CI run. Diff threshold and mask coverage
 * are conservative (≤2% pixel diff, dynamic regions masked) to avoid flake
 * from font hinting, antialiasing, or run-id strings.
 *
 * The 2 legacy `/inspector/golden_*` visual describes were deleted at
 * I-cd-013b (#669) after I-cd-013a (#609) rebuilt the Inspector route
 * to consume signed-bundle fixtures. The new Inspector visual baselines
 * live alongside `tests/e2e/inspector_route.spec.ts`.
 *
 * To re-baseline after intentional UI changes:
 *   SCREENSHOT_BASE_URL=http://127.0.0.1:3738 \
 *     npx playwright test --project=chromium tests/e2e/visual.spec.ts \
 *     --update-snapshots
 */

const SCREENSHOT_OPTIONS = {
  fullPage: true,
  animations: "disabled" as const,
  // 2% allows minor font-hinting drift across CI environments while still
  // catching real regressions like a button vanishing or layout collapsing.
  maxDiffPixelRatio: 0.02,
};

test.describe("Visual baselines — research dashboard", () => {
  test("/dashboard initial render", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await expect(page).toHaveScreenshot(
      "dashboard-initial.png",
      SCREENSHOT_OPTIONS,
    );
  });
});
