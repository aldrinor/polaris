import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * I-f1-005 — F1 axe-core WCAG-AA compliance.
 *
 * Acceptance: zero serious/critical violations across the home + intake.
 * (I-ux-001c sub-PR 2 #882 retargeted the home selectors: the previous one-CTA
 * hero with a search bar was replaced by the v6 marketing-auth hero whose
 * single primary CTA is `home-primary-cta` — the proof-as-CTA card is the
 * hero climax. command_palette focus-restore target `header-sign-in-link`
 * is preserved via HomePaletteShell.)
 * Specifically:
 *  - `/` closed (the v6 marketing-auth hero).
 *  - `/` with the command palette OPEN (Ctrl+K), backdrop + popup visible.
 *  - `/intake?template=clinical`.
 */

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

function critical_or_serious(v: { impact?: string | null }) {
  return v.impact === "serious" || v.impact === "critical";
}

test.describe("F1 axe-core WCAG-AA — I-f1-005", () => {
  test("/ closed (v6 marketing-auth hero) is WCAG-AA clean", async ({
    page,
  }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("home-h1")).toBeVisible();
    await expect(page.getByTestId("home-primary-cta")).toBeVisible();
    await expect(page.getByTestId("proof-as-cta")).toBeVisible();

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
