import { expect, test } from "@playwright/test";

/**
 * I-rdy-014 (#510) — coherent demo journey + global navigation.
 *
 * Supersedes the slice-era `demo_walkthrough.spec.ts` (home → intake →
 * retrieval → generation → benchmark). Asserts the navigation skeleton:
 *  - GlobalNav renders on product pages and is suppressed on harness routes.
 *  - The land → template → ask entry point lands on /dashboard (not the
 *    slice-era /intake) from BOTH the card-click and command-palette paths.
 *  - Every GlobalNav top-level entry is reachable with no dead end.
 *  - No journey page links to a test-harness or slice-era dev route.
 *
 * Navigation-only: no backend run is created. The report / inspect / signed
 * bundle CONTENT for a freshly-created real run is tracked in I-rdy-014c;
 * follow-up and run-compare UI in I-rdy-014a / I-rdy-014b.
 */

const NAV = 'nav[aria-label="Primary"]';

test.describe("I-rdy-014 — demo journey navigation", () => {
  test("landing renders GlobalNav + template grid", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.locator(NAV)).toBeVisible();
    await expect(page.getByTestId("template-grid")).toBeVisible();
  });

  test("land → template → ask lands on /dashboard (card click)", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await page.getByTestId("template-card-clinical-link").click();
    await page.waitForURL("**/dashboard?template=clinical");
    await expect(
      page.getByRole("heading", { name: "Start a research run" }),
    ).toBeVisible();
  });

  test("land → template → ask lands on /dashboard (command palette)", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();
    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();
    await page.getByTestId("command-palette-input").fill("clinical");
    await page.keyboard.press("Enter");
    await page.waitForURL("**/dashboard?template=clinical");
  });

  test("every GlobalNav top-level entry is reachable", async ({ page }) => {
    const entries = [
      { testid: "global-nav-dashboard", path: "/dashboard" },
      { testid: "global-nav-memory", path: "/memory" },
      { testid: "global-nav-pin_replay", path: "/pin_replay" },
      { testid: "global-nav-home", path: "/" },
    ];
    for (const entry of entries) {
      await page.goto("/", { waitUntil: "networkidle" });
      await page.getByTestId(entry.testid).click();
      await page.waitForURL(`**${entry.path}`);
      // The destination loaded with the layout intact — not a dead end.
      await expect(page.locator(NAV)).toBeVisible();
    }
  });

  test("GlobalNav is suppressed on test-harness routes", async ({ page }) => {
    for (const harness of ["/sentence_hover_test", "/charts_test"]) {
      await page.goto(harness, { waitUntil: "networkidle" });
      await expect(page.locator(NAV)).toHaveCount(0);
    }
  });

  test("no journey page links to a harness or slice-era dev route", async ({
    page,
  }) => {
    const forbidden = [
      "/charts_test",
      "/sentence_hover_test",
      "/disambiguation_modal_preview",
      "/intake",
      "/retrieval",
      "/generation",
      "/sse",
      "/audit_live",
    ];
    for (const journeyPath of ["/", "/dashboard", "/memory", "/benchmark"]) {
      await page.goto(journeyPath, { waitUntil: "networkidle" });
      for (const bad of forbidden) {
        await expect(
          page.locator(`a[href^="${bad}"]`),
          `${journeyPath} must not link to ${bad}`,
        ).toHaveCount(0);
      }
    }
  });
});
