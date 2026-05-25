// I-ux-001c sub-PR 5 (GH #889): e2e Playwright for the v6 /plan chrome
// rebuild.
//
// Asserts the spec from `.codex/I-ux-001c-5/brief.md` iter-1 APPROVE:
//   - Brand-red eyebrow + display H1 + tightened subtitle render
//   - Edit-question link sits in the eyebrow row and still navigates to
//     /intake (preserves back-link behavior)
//
// Mocks the runIntake endpoint so the auth-gated re-check on mount
// doesn't race with header-link assertions.
import { expect, test } from "@playwright/test";

const PLAN_PATH =
  "/plan?q=Does%20aspirin%20reduce%20headaches%20in%20adults%3F&template=clinical";

// Minimal valid runIntake response so the page's gate doesn't error.
const FAKE_INTAKE_OK = {
  decision: {
    status: "in_scope",
    scope_class: "clinical_efficacy",
    needs_disambiguation: false,
    candidate_snippets: [],
  },
};

test.describe("I-ux-001c · Plan Review v6 chrome", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/v6/intake**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FAKE_INTAKE_OK),
      });
    });
  });

  test("eyebrow + H1 + subtitle render with v6 copy", async ({ page }) => {
    await page.goto(PLAN_PATH, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("plan-page")).toBeVisible();
    await expect(page.getByTestId("plan-eyebrow")).toContainText(
      /PLAN.*POLARIS CLINICAL RESEARCH/i,
    );
    await expect(page.getByTestId("plan-h1")).toContainText(
      "Confirm the plan before the run",
    );
    await expect(page.getByTestId("plan-subtitle")).toContainText(
      /Re-checked end-to-end.*question, scope, and template are all clear/i,
    );
  });

  test("Edit-question link still navigates to /intake", async ({ page }) => {
    await page.goto(PLAN_PATH, { waitUntil: "domcontentloaded" });
    const link = page.getByTestId("plan-edit-question-link");
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/intake");
  });
});
