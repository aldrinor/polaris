import { expect, test, type Page } from "@playwright/test";

/**
 * Phase 2C.4 — performance gates.
 *
 * Each test measures one user-facing latency budget against the live build.
 * Targets are deliberately loose-but-meaningful: we want regressions to fail
 * the gate, not flaky perf numbers from a busy CI runner.
 *
 * Budgets:
 *   - Inspector cold load → DOMContentLoaded < 2.0s
 *   - Inspector tab switch → first paint of new tab < 250ms
 *   - Hover → tooltip-visible after open-delay completes < 1.0s (cap on open-delay)
 *   - Charts tab → first Vega SVG inserted in DOM < 2.5s
 */

async function measureLoadMs(page: Page, url: string): Promise<number> {
  const start = Date.now();
  await page.goto(url, { waitUntil: "domcontentloaded" });
  return Date.now() - start;
}

test.describe("Performance — Inspector cold load", () => {
  test("DOMContentLoaded < 2000ms on golden_clinical_001", async ({ page }) => {
    const loadMs = await measureLoadMs(page, "/inspector/golden_clinical_001");
    expect(loadMs).toBeLessThan(2000);
  });

  test("DOMContentLoaded < 2000ms on golden_climate_005", async ({ page }) => {
    const loadMs = await measureLoadMs(page, "/inspector/golden_climate_005");
    expect(loadMs).toBeLessThan(2000);
  });
});

test.describe("Performance — Inspector tab switch latency", () => {
  test("Verified sentences tab switch < 250ms", async ({ page }) => {
    await page.goto("/inspector/golden_clinical_001", {
      waitUntil: "networkidle",
    });
    const tab = page.getByRole("button", { name: /Verified sentences/ }).first();

    const start = Date.now();
    await tab.click();
    // The verified-sentences tab renders provenance tokens; wait for one to
    // be visible as proof the tab has actually painted.
    await page.locator("text=/\\[#ev:ev_clin_001:1200-1450\\]/").first().waitFor({
      state: "visible",
      timeout: 1_000,
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
    await page.getByText(/noted_both/).first().waitFor({
      state: "visible",
      timeout: 1_000,
    });
    const switchMs = Date.now() - start;
    expect(switchMs).toBeLessThan(250);
  });
});

test.describe("Performance — Charts tab first SVG", () => {
  test("Charts tab Vega-Lite SVG appears < 2500ms", async ({ page }) => {
    await page.goto("/inspector/golden_climate_005", {
      waitUntil: "networkidle",
    });
    const tab = page.getByRole("button", { name: /^Charts/ }).first();

    const start = Date.now();
    await tab.click();
    await page.waitForSelector(".polaris-vega-chart svg", { timeout: 2_500 });
    const renderMs = Date.now() - start;
    expect(renderMs).toBeLessThan(2500);
  });
});

test.describe("Performance — page-load Web Vitals", () => {
  test("Inspector first contentful paint < 1500ms after navigation", async ({
    page,
  }) => {
    await page.goto("/inspector/golden_clinical_001", { waitUntil: "load" });

    // Wait until at least one paint entry is recorded, then assert FCP budget.
    const fcpMs = await page.evaluate<number>(() => {
      return new Promise((resolve) => {
        const entries = performance.getEntriesByType("paint");
        const existing = entries.find((e) => e.name === "first-contentful-paint");
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
    expect(fcpMs).toBeLessThan(1500);
  });
});
