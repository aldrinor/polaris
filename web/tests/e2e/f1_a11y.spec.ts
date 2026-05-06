import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * I-f1-005 — F1 axe-core WCAG-AA compliance.
 *
 * Acceptance: zero serious/critical violations across F1 surfaces NOT
 * already covered by landing_template_grid (closed palette) or
 * accessibility (dashboard / inspector). Specifically:
 *  - `/` with the command palette OPEN (Ctrl+K), backdrop + popup visible.
 *  - `/intake?template=clinical` (target of F1 active cards).
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

function critical_or_serious(v: { impact?: string | null }) {
  return v.impact === "serious" || v.impact === "critical";
}

test.describe("F1 axe-core WCAG-AA — I-f1-005", () => {
  test("/ with command palette OPEN is WCAG-AA clean", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();
    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.filter(critical_or_serious)).toEqual([]);
  });

  test("/intake?template=clinical initial render is WCAG-AA clean", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/intake?template=clinical", {
      waitUntil: "domcontentloaded",
    });
    await expect(page.getByTestId("intake-page")).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
    expect(results.violations.filter(critical_or_serious)).toEqual([]);
  });
});
