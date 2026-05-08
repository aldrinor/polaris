import { expect, test } from "@playwright/test";

test("Timeline demo route renders quarter + date period_kind charts", async ({
  page,
}) => {
  await page.goto("/charts_test/timeline");

  for (const n_id of ["timeline-quarter", "timeline-date"] as const) {
    const section = page.getByTestId(n_id);
    await expect(section).toBeVisible();
    const chart = section.getByTestId("vega-chart");
    await expect(chart).toBeVisible();
    const svg = chart.locator("svg");
    await expect(svg.first()).toBeVisible({ timeout: 10_000 });
    // 4 datums × line+point mark → at least 4 graphics-symbol marks per chart.
    const marks = chart.locator('svg [role="graphics-symbol"]');
    expect(await marks.count()).toBeGreaterThanOrEqual(4);
  }

  await expect(page.getByTestId("vega-chart-error")).toHaveCount(0);
});
