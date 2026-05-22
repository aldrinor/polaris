import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * I-f1-005 — F1 axe-core WCAG-AA compliance.
 *
 * Acceptance: zero serious/critical violations across the home + intake.
 * (I-p2-013 #752 folded the closed-home axe check here after the
 * template-grid spec was removed when the home became a one-CTA hero.)
 * Specifically:
 *  - `/` closed (the one-CTA hero home).
 *  - `/` with the command palette OPEN (Ctrl+K), backdrop + popup visible.
 *  - `/intake?template=clinical`.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

function critical_or_serious(v: { impact?: string | null }) {
  return v.impact === "serious" || v.impact === "critical";
}

test.describe("F1 axe-core WCAG-AA — I-f1-005", () => {
  test("/ closed (one-CTA hero) is WCAG-AA clean", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("home-hero-search")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(WCAG_TAGS)
      .analyze();
    expect(results.violations.filter(critical_or_serious)).toEqual([]);
  });

  test("/ with command palette OPEN is WCAG-AA clean", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();
    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();

    const results = await new AxeBuilder({ page })
      .withTags(WCAG_TAGS)
      .analyze();
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

    const results = await new AxeBuilder({ page })
      .withTags(WCAG_TAGS)
      .analyze();
    expect(results.violations.filter(critical_or_serious)).toEqual([]);
  });
});
