import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

/**
 * Phase 2C.5 — WCAG 2.2-AA accessibility audit.
 *
 * For each user-facing route we run axe-core with the WCAG 2A + 2AA + 2.1AA
 * + 2.2AA + best-practice rule sets and assert zero violations. Any new
 * violation should fail CI rather than silently regress accessibility.
 *
 * Failure mode is intentionally LOUD — if axe surfaces a violation we
 * print the rule id, impact, and the affected node selectors so the fix
 * is one click away.
 */

const WCAG_TAGS = [
  "wcag2a",
  "wcag2aa",
  "wcag21a",
  "wcag21aa",
  "wcag22aa",
  "best-practice",
];

async function expectNoA11yViolations(page: import("@playwright/test").Page) {
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();

  if (results.violations.length > 0) {
    const summary = results.violations
      .map(
        (v) =>
          `\n  - [${v.impact}] ${v.id}: ${v.description}\n    nodes: ${v.nodes
            .map((n) => n.target.join(" ") + (n.failureSummary ? ` — ${n.failureSummary.replace(/\n/g, " ")}` : ""))
            .join("\n           ")}`,
      )
      .join("");
    throw new Error(
      `axe-core found ${results.violations.length} WCAG-AA violation(s):${summary}`,
    );
  }
}

test.describe("WCAG-AA — research dashboard", () => {
  test("/dashboard initial render is WCAG-AA clean", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await expectNoA11yViolations(page);
  });

  test("/dashboard after scope rejection is WCAG-AA clean", async ({ page }) => {
    await page.goto("/dashboard", { waitUntil: "networkidle" });
    await page.fill("#question", "Should I take ozempic for my diabetes?");
    await page.getByRole("button", { name: /Check scope/ }).click();
    await expect(page.getByText(/Rejected/i)).toBeVisible({ timeout: 8_000 });
    await expectNoA11yViolations(page);
  });
});

test.describe("WCAG-AA — Inspector golden_clinical_001", () => {
  test("Executive summary tab (default) is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await expectNoA11yViolations(page);
  });

  test("Verified sentences tab is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();
    await expectNoA11yViolations(page);
  });

  test("Charts tab is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_climate_005", {
      waitUntil: "networkidle",
    });
    await page.getByRole("button", { name: /^Charts/ }).first().click();
    await page.waitForSelector(".polaris-vega-chart svg", { timeout: 10_000 });
    await expectNoA11yViolations(page);
  });
});

test.describe("WCAG-AA — Inspector golden_housing_002 (contradictions)", () => {
  test("Contradictions tab is WCAG-AA clean", async ({ page }) => {
    await page.goto("/inspector/golden_housing_002", {
      waitUntil: "networkidle",
    });
    await page.getByRole("button", { name: /Contradictions/ }).first().click();
    await expectNoA11yViolations(page);
  });
});

test.describe("WCAG-AA — Inspector error states", () => {
  test("Inspector destructive error banner (invalid runId) is WCAG-AA clean", async ({
    page,
  }) => {
    await page.goto("/inspector/does_not_exist_runid_404", {
      waitUntil: "networkidle",
    });
    // Error banner pattern (border-only + text-foreground font-medium) —
    // verify axe doesn't flag the destructive surface.
    await expect(page.getByText(/POLARIS backend returned 404/i)).toBeVisible({
      timeout: 8_000,
    });
    await expectNoA11yViolations(page);
  });

  test("Run-detail destructive error banner (invalid runId) is WCAG-AA clean", async ({
    page,
  }) => {
    // /runs/[runId] page also uses the destructive error pattern; verify it.
    await page.goto("/runs/does_not_exist_runid_404", {
      waitUntil: "networkidle",
    });
    await expect(page.getByText(/POLARIS backend returned 404/i)).toBeVisible({
      timeout: 8_000,
    });
    await expectNoA11yViolations(page);
  });
});
