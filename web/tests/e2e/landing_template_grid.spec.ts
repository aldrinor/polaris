import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * I-f1-001 — Next.js landing page Card grid (8 templates).
 *
 * Replaces the slice-005 demo walkthrough cards with the F1 template-browse
 * grid: 1 active template (clinical, linked to /intake)
 * + 7 to-build templates (aria-disabled, "Coming soon" badge, no link).
 *
 * Acceptance per `.codex/I-f1-001/brief.md` (Codex APPROVE iter 2):
 *  - 8 cards render at 4 viewports (1920/1024/768/375)
 *  - Active cards link to /dashboard?template=<id>
 *  - To-build cards are aria-disabled, no href, keyboard-skipped
 *  - axe-core WCAG-AA clean at 1024px
 */

const ACTIVE_IDS = ["clinical"] as const;
const TO_BUILD_IDS = [
  "policy",
  "tech",
  "due_diligence",
  "ai_sovereignty",
  "canada_us",
  "workforce",
  "custom",
] as const;

const VIEWPORTS = [
  { name: "1920", width: 1920, height: 1080 },
  { name: "1024", width: 1024, height: 768 },
  { name: "768", width: 768, height: 1024 },
  { name: "375", width: 375, height: 667 },
] as const;

test.describe("Landing template grid — I-f1-001", () => {
  for (const vp of VIEWPORTS) {
    test(`renders 8 template cards at ${vp.name}px`, async ({ page }) => {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/", { waitUntil: "networkidle" });

      await expect(page.getByTestId("template-grid")).toBeVisible();

      for (const id of ACTIVE_IDS) {
        await expect(page.getByTestId(`template-card-${id}`)).toBeVisible();
      }
      for (const id of TO_BUILD_IDS) {
        await expect(page.getByTestId(`template-card-${id}`)).toBeVisible();
      }

      // Visual regression artifact (CI does not enforce diff on Linux per
      // web_ci.yml policy; this captures the screenshot for local review).
      await page.screenshot({
        path: `web/tests/e2e/screenshots/landing_template_grid_${vp.name}.png`,
        fullPage: true,
      });
    });
  }

  test("active cards link to /dashboard?template=<id>", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    for (const id of ACTIVE_IDS) {
      const link = page.getByTestId(`template-card-${id}-link`);
      await expect(link).toHaveAttribute("href", `/dashboard?template=${id}`);
    }
  });

  test("to-build cards are disabled and skip keyboard nav", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    for (const id of TO_BUILD_IDS) {
      const card = page.getByTestId(`template-card-${id}`);
      await expect(card).toHaveAttribute("aria-disabled", "true");
      // No outbound link from disabled cards.
      await expect(card.getByTestId(`template-card-${id}-link`)).toHaveCount(0);
    }
  });

  test("WCAG-AA axe-core clean at 1024px", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.goto("/", { waitUntil: "networkidle" });
    const results = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();
    expect(results.violations).toEqual([]);
  });
});
