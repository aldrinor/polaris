import { expect, test } from "@playwright/test";

/**
 * Slice 005 — full demo walkthrough.
 *
 * Drives the flow a non-developer follows during the demo:
 *   home (one-CTA hero) → intake → retrieval → generation → benchmark
 *
 * I-p2-013 (#752) replaced the home template grid with a one-CTA hero; the
 * home entry-point now fills the hero search and submits → /intake.
 *
 * STRUCTURAL test — asserts each page loads + exposes its core testid hooks.
 * It does NOT validate content (which needs real API keys at runtime).
 */

test.describe("Slice 005 — full demo walkthrough", () => {
  test("home → intake → retrieval → generation → benchmark", async ({
    page,
  }) => {
    // Step 0 — home (one-CTA hero; I-p2-013 replaced the template grid)
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("home-hero-search")).toBeVisible();

    // Step 1 — intake (the hero search funnels to /intake)
    await page
      .getByTestId("home-hero-search")
      .getByRole("searchbox")
      .fill("What did the SELECT trial show on cardiovascular outcomes?");
    await page
      .getByTestId("home-hero-search")
      .getByRole("button", { name: "Verify" })
      .click();
    await page.waitForURL("**/intake**");
    await expect(page.getByTestId("intake-page")).toBeVisible();
    await expect(page.getByTestId("intake-question-input")).toBeVisible();

    // Step 2 — retrieval (navigate directly; no nav bar mid-flow yet)
    await page.goto("/retrieval", { waitUntil: "networkidle" });
    await expect(page.getByTestId("retrieval-page")).toBeVisible();

    // Step 3 — generation
    await page.goto("/generation", { waitUntil: "networkidle" });
    await expect(page.getByTestId("generation-page")).toBeVisible();

    // Step 4 — benchmark
    await page.goto("/benchmark", { waitUntil: "networkidle" });
    await expect(page.getByTestId("benchmark-page")).toBeVisible();
  });

  test("home surfaces the one-CTA hero + three differentiator pillars", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    // One primary CTA (the hero search + Verify), not a grid of cards.
    await expect(page.getByTestId("home-hero-search")).toBeVisible();
    await expect(
      page.getByTestId("home-hero-search").getByRole("button", {
        name: "Verify",
      }),
    ).toBeVisible();
    // The three differentiator pillars replace the old template grid.
    for (const pillar of ["Provable", "Sovereign", "Snowball"]) {
      await expect(
        page.getByRole("heading", { name: pillar }),
      ).toBeVisible();
    }
    // The old templates grid is gone.
    await expect(page.getByTestId("template-grid")).toHaveCount(0);
  });
});
