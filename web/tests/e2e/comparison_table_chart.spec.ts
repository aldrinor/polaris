import { expect, test } from "@playwright/test";

test("Comparison table demo route renders N=2/3/5 charts correctly", async ({
  page,
}) => {
  await page.goto("/charts_test/comparison_table");

  for (const [n_id, expected_min] of [
    ["comparison-table-n2", 2],
    ["comparison-table-n3", 3],
    ["comparison-table-n5", 5],
  ] as const) {
    const section = page.getByTestId(n_id);
    await expect(section).toBeVisible();
    const chart = section.getByTestId("vega-chart");
    await expect(chart).toBeVisible();
    const svg = chart.locator("svg");
    await expect(svg.first()).toBeVisible({ timeout: 10_000 });
    // role-aware mark count: at least N graphics-symbol marks per chart
    // (one bar per entity × metric; conservative lower bound = N).
    const marks = chart.locator('svg [role="graphics-symbol"]');
    const count = await marks.count();
    expect(count).toBeGreaterThanOrEqual(expected_min);
  }

  await expect(page.getByTestId("vega-chart-error")).toHaveCount(0);
});
