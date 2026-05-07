import { expect, test, type Page } from "@playwright/test";

/**
 * Phase 2C.4 — performance gates.
 *
 * Each test measures one user-facing latency budget against the live build.
 * Budgets follow the rule `max(2 × baseline_observed, hard_floor)` — tight
 * enough to catch a 2-3x regression, loose enough not to flake on a busy
 * CI runner. F-3 fix from outputs/audits/continuous/4fe03f7_audit.md
 * tightened these from the original 2x-5x slack baselines.
 *
 * Budgets:
 *   - Inspector cold load → DOMContentLoaded < 1000ms (observed: ~270-450ms)
 *   - Inspector tab switch → click-to-content < 250ms (observed: ~100ms)
 *   - Charts tab → first Vega SVG inserted in DOM < 2000ms (observed: ~1.0s)
 *   - Inspector first contentful paint < 800ms (observed: ~400ms)
 *
 * Hover-latency budget is measured separately in
 * `tests/e2e/performance_hover.spec.ts` (instruments PerformanceMark on
 * mouseenter → [role="tooltip"] visible).
 */

async function measureLoadMs(page: Page, url: string): Promise<number> {
  const start = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  return Date.now() - start;
}

test.describe("Performance — Inspector cold load", () => {
  test("DOMContentLoaded < 1000ms on golden_clinical_001", async ({ page }) => {
    const loadMs = await measureLoadMs(page, "/inspector/golden_clinical_001");
    expect(loadMs).toBeLessThan(1000);
  });

  test("DOMContentLoaded < 1000ms on golden_climate_005", async ({ page }) => {
    const loadMs = await measureLoadMs(page, "/inspector/golden_climate_005");
    expect(loadMs).toBeLessThan(1000);
  });
});

test.describe("Performance — Inspector tab switch latency", () => {
  test("Verified sentences tab switch < 250ms", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    const tab = page
      .getByRole("button", { name: /Verified sentences/ })
      .first();

    const start = Date.now();
    await tab.click();
    // F-4: wait timeout > budget so a slow render surfaces as a budget
    // failure (`expected < 250, got ${switchMs}`) rather than a misleading
    // locator-timeout.
    await page
      .locator("text=/\\[#ev:ev_clin_001:1200-1450\\]/")
      .first()
      .waitFor({
        state: "visible",
        timeout: 5_000,
      });
    const switchMs = Date.now() - start;
    expect(switchMs).toBeLessThan(250);
  });

  test("Contradictions tab switch < 250ms", async ({ page }) => {
    await page.goto("/inspector/golden_housing_002", {
      waitUntil: "networkidle",
    });
    const tab = page.getByRole("button", { name: /Contradictions/ }).first();

    const start = Date.now();
    await tab.click();
    await page
      .getByText(/noted_both/)
      .first()
      .waitFor({
        state: "visible",
        timeout: 5_000,
      });
    const switchMs = Date.now() - start;
    expect(switchMs).toBeLessThan(250);
  });
});

test.describe("Performance — Charts tab first SVG", () => {
  test("Charts tab Vega-Lite SVG appears < 2000ms", async ({ page }) => {
    await page.goto("/inspector/golden_climate_005", {
      waitUntil: "networkidle",
    });
    const tab = page.getByRole("button", { name: /^Charts/ }).first();

    const start = Date.now();
    await tab.click();
    await page.waitForSelector(".polaris-vega-chart svg", { timeout: 5_000 });
    const renderMs = Date.now() - start;
    expect(renderMs).toBeLessThan(2000);
  });
});

test.describe("Performance — page-load Web Vitals", () => {
  test("Inspector first contentful paint < 800ms after navigation", async ({
    page,
  }) => {
    await page.goto("/inspector/golden_clinical_001", { waitUntil: "load" });

    // Wait until at least one paint entry is recorded, then assert FCP budget.
    const fcpMs = await page.evaluate<number>(() => {
      return new Promise((resolve) => {
        const entries = performance.getEntriesByType("paint");
        const existing = entries.find(
          (e) => e.name === "first-contentful-paint",
        );
        if (existing) {
          resolve(existing.startTime);
          return;
        }
        const obs = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            if (entry.name === "first-contentful-paint") {
              obs.disconnect();
              resolve(entry.startTime);
              return;
            }
          }
        });
        obs.observe({ type: "paint", buffered: true });
        // Hard timeout so we don't hang the test if FCP never fires.
        setTimeout(() => {
          obs.disconnect();
          resolve(-1);
        }, 3_000);
      });
    });
    expect(fcpMs).toBeGreaterThanOrEqual(0);
    expect(fcpMs).toBeLessThan(800);
  });
});
