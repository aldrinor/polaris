import { expect, test } from "@playwright/test";

/**
 * Phase 2C.2 — visual regression baselines.
 *
 * Captures one screenshot per major user-facing surface and compares against
 * the committed baseline on every CI run. Diff threshold and mask coverage
 * are conservative (≤2% pixel diff, dynamic regions masked) to avoid flake
 * from font hinting, antialiasing, or run-id strings.
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

test.describe("Visual baselines — Inspector golden_clinical_001", () => {
  test("Executive summary tab (default)", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    // Mask the run-id string in the header (varies per run).
    await expect(page).toHaveScreenshot("inspector-executive-summary.png", {
      ...SCREENSHOT_OPTIONS,
      mask: [page.locator("text=/Run golden_clinical/")],
    });
  });

  test("Verified sentences tab", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();
    await expect(page).toHaveScreenshot("inspector-verified-sentences.png", {
      ...SCREENSHOT_OPTIONS,
      mask: [page.locator("text=/Run golden_clinical/")],
    });
  });
});

test.describe("Visual baselines — Inspector error state", () => {
  test("/inspector/<bad-runid> error banner", async ({ page }) => {
    await page.goto("/inspector/does_not_exist_runid_404", {
      waitUntil: "networkidle",
    });
    await expect(page.getByText(/POLARIS backend returned 404/i)).toBeVisible();
    await expect(page).toHaveScreenshot("inspector-error-state.png", {
      ...SCREENSHOT_OPTIONS,
      mask: [page.locator("text=/Run does_not_exist/")],
    });
  });
});
