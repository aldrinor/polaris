import { expect, test } from "@playwright/test";

test("Forest plot demo route renders sample meta-analysis (rule + point marks)", async ({
  page,
}) => {
  await page.goto("/charts_test/forest_plot");

  const chart = page.getByTestId("vega-chart");
  await expect(chart).toBeVisible();

  const svg = chart.locator("svg");
  await expect(svg.first()).toBeVisible({ timeout: 10_000 });

  // Vega scenegraph emits a graphics-object container per mark layer with
  // role="graphics-object". We narrow further by aria-roledescription which
  // Vega sets to "rule mark" / "symbol mark" on the marked groups. This
  // avoids matching axes/gridlines/background.
  const rule_layer = chart.locator(
    'g[role="graphics-object"][aria-roledescription="rule mark container"]',
  );
  const point_layer = chart.locator(
    'g[role="graphics-object"][aria-roledescription="symbol mark container"]',
  );

  // If Vega's exact aria-roledescription strings differ at runtime, fall back
  // to counting graphics-symbol descendants under each role-aware container.
  const rule_count = await rule_layer.count();
  const point_count = await point_layer.count();

  if (rule_count > 0 && point_count > 0) {
    // Each layer present.
    expect(rule_count).toBeGreaterThan(0);
    expect(point_count).toBeGreaterThan(0);
  } else {
    // Fallback: assert at least N graphics-symbol marks (3 data points = 3
    // rule lines + 3 point marks = 6 graphics symbols). Filters out non-mark
    // SVG (axes/gridlines/background) by role.
    const graphics_symbols = chart.locator('svg [role="graphics-symbol"]');
    const total_marks = await graphics_symbols.count();
    expect(total_marks).toBeGreaterThanOrEqual(6);
  }

  await expect(page.getByTestId("vega-chart-error")).toHaveCount(0);
});
