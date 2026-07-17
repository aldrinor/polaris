// I-ux-001c sub-PR 4 (GH #887): e2e Playwright for the v6 /source_review
// chrome rebuild.
//
// Asserts the spec from `.codex/I-ux-001c-4/brief.md` iter-3 APPROVE:
//   - Brand-red eyebrow + display H1 + tightened subtitle render
//   - Edit-question link sits in the eyebrow row and still navigates to
//     /intake?q=<encoded> (preserves back-link behavior)
//
// Per the iter-2 P2 fix: mocks GET /api/v6/templates so the auth-gated
// listTemplates fetch doesn't race with header-link assertions.
import { expect, test } from "@playwright/test";

const SOURCE_REVIEW_PATH =
  "/source_review?q=Does%20aspirin%20reduce%20headaches%20in%20adults%3F&template=clinical";

// Minimal valid TemplateContent shape so listTemplates resolves without
// the auth-gated backend call. Mirrors the shape from
// config/v6_templates/clinical.json (id + per-tier source-domain lists +
// min_sources_per_tier). The exact contents don't matter for chrome
// assertions; they just need to render without errors.
const FAKE_TEMPLATE = {
  id: "clinical",
  display_name: "Clinical drug audit",
  source_set: {
    T1: { domains: ["nejm.org", "thelancet.com"], min_sources_per_tier: 2 },
    T2: { domains: ["cochranelibrary.com"], min_sources_per_tier: 1 },
    T3: { domains: ["uptodate.com"], min_sources_per_tier: 0 },
  },
};

test.describe("I-ux-001c · Source Review v6 chrome", () => {
  test.beforeEach(async ({ page }) => {
    // Mock the templates endpoint so the page renders without hitting
    // the real auth-gated backend.
    await page.route("**/api/v6/templates**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ templates: [FAKE_TEMPLATE] }),
      });
    });
  });

  test("eyebrow + H1 + subtitle render with v6 copy", async ({ page }) => {
    await page.goto(SOURCE_REVIEW_PATH, { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("source-review-page")).toBeVisible();
    await expect(page.getByTestId("source-review-eyebrow")).toContainText(
      /SOURCES.*POLARIS CLINICAL RESEARCH/i,
    );
    await expect(page.getByTestId("source-review-h1")).toContainText(
      "Review the sources POLARIS will check",
    );
    await expect(page.getByTestId("source-review-subtitle")).toContainText(
      /per-tier evidence bar the corpus must clear before any claim is written/i,
    );
  });

  test("Edit-question link still navigates to /intake?q=<encoded>", async ({
    page,
  }) => {
    await page.goto(SOURCE_REVIEW_PATH, { waitUntil: "domcontentloaded" });
    const link = page.getByTestId("source-review-edit-question-link");
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute(
      "href",
      "/intake?q=Does%20aspirin%20reduce%20headaches%20in%20adults%3F",
    );
  });
});
