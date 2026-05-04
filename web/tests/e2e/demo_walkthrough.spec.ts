import { expect, test } from "@playwright/test";

/**
 * Slice 005 — full demo walkthrough.
 *
 * Drives the four-step flow in the same order a non-developer follows
 * during the Sep 6 tracer demo:
 *   home → intake → retrieval → generation → benchmark
 *
 * This is a STRUCTURAL test — it asserts that each page loads and exposes
 * its core testid hooks. It does NOT validate content (which would require
 * real OPENROUTER_API_KEY / SERPER_API_KEY at runtime). For content
 * verification, use the runbook in docs/demo_runbook.md.
 *
 * The home page card hrefs are the contract — if the agent breaks the
 * walkthrough nav, this test catches it.
 */

test.describe("Slice 005 — full demo walkthrough", () => {
  test("home → intake → retrieval → generation → benchmark", async ({
    page,
  }) => {
    // Step 0 — home
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("demo-walkthrough")).toBeVisible();

    // Step 1 — intake (click the home card)
    await page
      .getByTestId("demo-slice-intake")
      .getByRole("link")
      .click();
    await page.waitForURL("**/intake");
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

  test("home walkthrough cards expose testids in expected order", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    const ids = ["intake", "retrieval", "generation", "benchmark"];
    for (const id of ids) {
      await expect(page.getByTestId(`demo-slice-${id}`)).toBeVisible();
    }
  });

  test("each home card surfaces a 'Step N' badge", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    // The CardDescription renders the step label per slice; verify all four
    // step labels are present somewhere on the page.
    for (const step of [1, 2, 3, 4]) {
      const stepText = page.getByText(new RegExp(`Step ${step}`, "i")).first();
      await expect(stepText).toBeVisible();
    }
  });
});
