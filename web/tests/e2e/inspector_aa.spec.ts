// I-ux-001c (#878) sub-PR 1: axe-core WCAG 2.2 AA scan for the Inspector route.
//
// Target: zero violations on /inspector/v1-canonical-success at desktop and
// mobile viewports. The Inspector hero is the CENTERPIECE — accessibility
// gate is a hard prerequisite for the demo.
//
// Runner: invoked by Playwright (uses @axe-core/playwright, already installed
// at web/node_modules/@axe-core/playwright/). This file follows the same
// pattern as web/tests/a11y/* existing scans.
//
// Run locally:
//   cd web && npx next start -p 3738 &
//   cd web && SCREENSHOT_BASE_URL=http://127.0.0.1:3738 \
//     npx playwright test tests/a11y/inspector_aa.test.mjs
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const INSPECTOR_PATH = "/inspector/v1-canonical-success";

test.describe("I-ux-001c · Inspector axe a11y (WCAG 2.2 AA)", () => {
  test("desktop: zero AA violations on idle state", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(INSPECTOR_PATH);
    await page.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();

    if (results.violations.length > 0) {
      console.error(
        "axe violations:",
        JSON.stringify(results.violations, null, 2),
      );
    }
    expect(results.violations).toEqual([]);
  });

  test("desktop: zero AA violations with proof panel open", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto(INSPECTOR_PATH);
    const firstClaim = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]')
      .first();
    await firstClaim.click();
    await expect(page.getByTestId("proof-panel")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();

    if (results.violations.length > 0) {
      console.error(
        "axe violations (proof open):",
        JSON.stringify(results.violations, null, 2),
      );
    }
    expect(results.violations).toEqual([]);
  });

  test("mobile: zero AA violations with sheet open", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(INSPECTOR_PATH);
    const firstClaim = page
      .getByTestId("claims-list")
      .locator('[data-testid^="claim-"]')
      .first();
    await firstClaim.click();
    await expect(page.getByTestId("proof-replay-sheet")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();

    if (results.violations.length > 0) {
      console.error(
        "axe violations (mobile sheet open):",
        JSON.stringify(results.violations, null, 2),
      );
    }
    expect(results.violations).toEqual([]);
  });
});
