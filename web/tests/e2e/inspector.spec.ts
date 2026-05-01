import { expect, test } from "@playwright/test";

/**
 * Phase 2C.1 — cross-feature integration tests for the Inspector route.
 *
 * Each test exercises one user-visible flow against live golden bundles.
 * No mocks — the backend serves real EvidenceContract JSON from
 * `tests/v6/fixtures/evidence_contract_v1/*.json`.
 */

test.describe("Inspector — golden_clinical_001", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
  });

  test("renders title and three KPI cards", async ({ page }) => {
    await expect(page.getByText(/Run golden_clinical_001/i)).toBeVisible();
    await expect(page.getByText(/Pipeline status/i)).toBeVisible();
    await expect(page.getByText(/Two-family invariant/i)).toBeVisible();
    await expect(page.getByText(/^Cost$/i)).toBeVisible();
  });

  test("two-family invariant shows PASS for golden run", async ({ page }) => {
    await expect(page.getByText(/PASS .* deepseek-v4-flash/i)).toBeVisible();
  });

  test("default tab is Executive summary and lands on KPI strip", async ({
    page,
  }) => {
    await expect(page.getByText(/Executive briefing/i)).toBeVisible();
    await expect(page.getByText(/^Verified$/i)).toBeVisible();
    await expect(page.getByText(/^Sources$/i)).toBeVisible();
  });

  test("clicking Verified sentences tab shows provenance tokens", async ({
    page,
  }) => {
    await page
      .getByRole("button", { name: /Verified sentences/ })
      .first()
      .click();
    await expect(page.getByText(/\[#ev:ev_clin_001:1200-1450\]/)).toBeVisible();
  });

  test("Export bundle JSON button is present", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: /Export bundle JSON/ }),
    ).toBeVisible();
  });
});

test.describe("Inspector — golden_housing_002 (contradiction)", () => {
  test("shows contradiction count and resolution badge", async ({ page }) => {
    await page.goto("/inspector/golden_housing_002", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /Contradictions/ })
      .first()
      .click();
    await expect(page.getByText(/noted_both/)).toBeVisible();
  });
});

test.describe("Inspector — Charts tab end-to-end", () => {
  test("Vega-Lite SVG renders for forest_plot on climate run", async ({
    page,
  }) => {
    await page.goto("/inspector/golden_climate_005", {
      waitUntil: "networkidle",
    });
    await page
      .getByRole("button", { name: /^Charts/ })
      .first()
      .click();
    await page.waitForSelector(".polaris-vega-chart svg", { timeout: 10_000 });
    const svgCount = await page.locator(".polaris-vega-chart svg").count();
    expect(svgCount).toBeGreaterThanOrEqual(1);
  });
});

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
