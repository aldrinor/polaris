import { expect, test } from "@playwright/test";

/**
 * Slice 005 — full demo walkthrough.
 *
 * Drives the flow a non-developer follows during the demo:
 *   home (v6 marketing-auth hero) → intake → retrieval → generation → benchmark
 *
 * I-ux-001c sub-PR 2 (#882) replaced the previous one-CTA search-bar hero
 * with the v6 marketing-auth hero: brand-red eyebrow + H1 + subtitle +
 * proof-as-CTA card (REAL verified claim) + ONE primary CTA → /intake.
 *
 * STRUCTURAL test — asserts each page loads + exposes its core testid hooks.
 * It does NOT validate content (which needs real API keys at runtime).
 */

test.describe("Slice 005 — full demo walkthrough", () => {
  test("home → intake → retrieval → generation → benchmark", async ({
    page,
  }) => {
    // Step 0 — home (v6 marketing-auth hero; I-ux-001c sub-PR 2)
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("home-h1")).toBeVisible();
    await expect(page.getByTestId("proof-as-cta")).toBeVisible();

    // Step 1 — intake (the primary CTA funnels to /intake)
    await page.getByTestId("home-primary-cta").click();
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

  test("home surfaces the v6 marketing-auth hero + proof-as-CTA card", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    // One primary CTA (the v6 "Try a verified brief" button), not a
    // grid of cards or a search bar.
    await expect(page.getByTestId("home-primary-cta")).toBeVisible();
    await expect(page.getByTestId("home-primary-cta")).toContainText(
      "Try a verified brief",
    );
    // The proof-as-CTA card is the HERO climax (replaces both the old
    // search bar and the three pillar cards).
    await expect(page.getByTestId("proof-as-cta")).toBeVisible();
    // Eyebrow + H1 + subtitle present.
    await expect(page.getByTestId("home-eyebrow")).toBeVisible();
    await expect(page.getByTestId("home-h1")).toContainText(
      "Every sentence proves itself",
    );
    await expect(page.getByTestId("home-subtitle")).toBeVisible();
    // Old surfaces are gone.
    await expect(page.getByTestId("template-grid")).toHaveCount(0);
    await expect(page.getByTestId("home-hero-search")).toHaveCount(0);
  });
});
