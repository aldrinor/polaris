import { expect, test } from "@playwright/test";

/**
 * Slice 005 — full demo walkthrough (updated for I-f1-001 template grid).
 *
 * Drives the four-step flow in the same order a non-developer follows
 * during the Sep 6 tracer demo:
 *   home (clinical template card) → intake → retrieval → generation → benchmark
 *
 * I-f1-001 replaced the demo-slice cards on `/` with the F1 template grid
 * (3 active + 5 to-build). The home entry-point now clicks the clinical
 * template card → /intake?template=clinical, instead of the legacy
 * demo-slice-intake card.
 *
 * This is a STRUCTURAL test — it asserts that each page loads and exposes
 * its core testid hooks. It does NOT validate content (which would require
 * real OPENROUTER_API_KEY / SERPER_API_KEY at runtime). For content
 * verification, use the runbook in docs/demo_runbook.md.
 */

test.describe("Slice 005 — full demo walkthrough", () => {
  test("home → intake → retrieval → generation → benchmark", async ({
    page,
  }) => {
    // Step 0 — home (template grid)
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("template-grid")).toBeVisible();

    // Step 1 — intake (click the clinical template card)
    await page.getByTestId("template-card-clinical-link").click();
    await page.waitForURL("**/intake?template=clinical");
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

  test("home template grid surfaces 3 active + 5 to-build cards", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    const active = ["clinical", "housing", "climate"];
    const to_build = [
      "ai_sovereignty",
      "canada_us",
      "defense",
      "trade",
      "workforce",
    ];
    for (const id of active) {
      await expect(page.getByTestId(`template-card-${id}`)).toBeVisible();
    }
    for (const id of to_build) {
      await expect(page.getByTestId(`template-card-${id}`)).toBeVisible();
    }
  });
});
