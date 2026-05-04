import { expect, test } from "@playwright/test";

/**
 * Slice 005 — BEAT-BOTH benchmark e2e.
 *
 * The /benchmark page reads the live /api/benchmark catalog. Without
 * POLARIS_BENCHMARK_RESULTS_DIR set, the page shows the
 * 'no-results-dir' card; with it set + at least one benchmark
 * present, the list-then-scoreboard flow renders.
 */

test.describe("Slice 005 — /benchmark", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/benchmark", { waitUntil: "networkidle" });
  });

  test("renders title and intro", async ({ page }) => {
    await expect(page.getByTestId("benchmark-page")).toBeVisible();
    await expect(page.getByText(/BEAT-BOTH benchmark/i).first()).toBeVisible();
  });

  test("shows configuration help when no results dir", async ({ page }) => {
    // Either the 'no-results-dir' card OR an actual list/scoreboard renders;
    // accept either based on backend state.
    await Promise.race([
      page.getByTestId("benchmark-no-results-dir").waitFor({
        state: "visible",
        timeout: 10_000,
      }),
      page.getByTestId("benchmark-empty").waitFor({
        state: "visible",
        timeout: 10_000,
      }),
      page.getByTestId("benchmark-list").waitFor({
        state: "visible",
        timeout: 10_000,
      }),
    ]);

    const states = await Promise.all([
      page.getByTestId("benchmark-no-results-dir").isVisible(),
      page.getByTestId("benchmark-empty").isVisible(),
      page.getByTestId("benchmark-list").isVisible(),
    ]);
    expect(states.some(Boolean)).toBe(true);
  });
});
