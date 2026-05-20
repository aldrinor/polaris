import { expect, test } from "@playwright/test";

/**
 * Dashboard scope-discovery flow tests.
 *
 * Originally part of a broader Inspector + Dashboard suite; the 3 legacy
 * `/inspector/golden_*` describes (AuditIR shape) were deleted at
 * I-cd-013b (#669) after I-cd-013a (#609) rebuilt the Inspector to
 * consume signed-bundle fixtures. The new Inspector e2e lives at
 * `tests/e2e/inspector_route.spec.ts`.
 *
 * The Dashboard scope-discovery describe below is preserved verbatim
 * (it does not touch the Inspector route).
 */

test.describe("Dashboard — scope discovery flow", () => {
  test("rejects clinical-treatment-recommendation prompt", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await page.fill("#question", "Should I take ozempic for my diabetes?");
    await page.getByRole("button", { name: /Check scope/ }).click();
    await expect(page.getByText(/Rejected/i)).toBeVisible({ timeout: 8_000 });
    await expect(
      page.getByText(/clinical_treatment_recommendation/),
    ).toBeVisible();
  });

  test("accepts a research-framed CMHC question", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await page.fill(
      "#question",
      "What does the latest CMHC data say about Q3 2025 housing starts across Canadian metros?",
    );
    await page.getByRole("button", { name: /Check scope/ }).click();
    await expect(page.getByText(/Accepted/i)).toBeVisible({ timeout: 8_000 });
  });
});
