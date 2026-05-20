import { expect, test } from "@playwright/test";

/**
 * Phase 2C.1 — cross-feature integration tests for the Inspector route.
 *
 * Each test exercises one user-visible flow against a real
 * `polaris_v6.api.app` backend. No mocks — the inspector page reads the
 * faithful AuditIR via `GET /api/inspector/runs/{id}` and the verified
 * evidence spans via `GET /api/inspector/runs/{id}/evidence`. The
 * golden-fixture-only `getBundle()`/`EvidenceContract` dependency was
 * removed in I-rdy-008 (#504) slice 7b (PR #597).
 */

// I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
test.describe.skip("Inspector — golden_clinical_001", () => {
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

  test("Evidence pool tab settles into a terminal PoolTab state", async ({
    page,
  }) => {
    // I-rdy-008 (#504) slice 7b migrated PoolTab off the golden-fixture-only
    // getBundle() onto GET /api/inspector/runs/{id}/evidence (the bundle
    // Export button was removed in the same slice). The tab resolves to one
    // of three terminal states: grouped evidence rows ("<id> · tier <T> ·
    // <N> span(s)"), "No verified evidence spans for this run.", or
    // "Evidence unavailable:". The transient "Loading evidence…"
    // (evidence === null) state is NOT terminal — a test that accepts it
    // would pass even if the evidence fetch never resolved.
    await page
      .getByRole("button", { name: /Evidence pool/ })
      .first()
      .click();
    const terminalState = page.getByText(
      /· tier .+ · \d+ span|No verified evidence spans for this run\.|Evidence unavailable:/,
    );
    await expect(terminalState.first()).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("Loading evidence…")).toHaveCount(0);
  });
});

// I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
test.describe.skip("Inspector — golden_housing_002 (contradiction)", () => {
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

// I-cd-013a (GH#609): legacy AuditIR Inspector — migrated by I-cd-013b (#669).
test.describe.skip("Inspector — Charts tab end-to-end", () => {
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
