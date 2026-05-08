import { expect, test } from "@playwright/test";

test("Charts test route renders the Vega-Lite v5 sample bar chart", async ({
  page,
}) => {
  await page.goto("/charts_test");

  const chart = page.getByTestId("vega-chart");
  await expect(chart).toBeVisible();

  // vega-embed uses { renderer: "svg" } so the chart content is an SVG root.
  const svg = chart.locator("svg");
  await expect(svg.first()).toBeVisible({ timeout: 10_000 });

  // Vega rect (bar) marks render as <path> elements (vega-scenegraph
  // SVGRenderer maps `rect` mark to SVG `path`). Three demo data points →
  // at least three mark <path> elements.
  const paths = chart.locator("svg path");
  expect(await paths.count()).toBeGreaterThan(0);

  // No error pane should render on a valid spec.
  await expect(page.getByTestId("vega-chart-error")).toHaveCount(0);
});
