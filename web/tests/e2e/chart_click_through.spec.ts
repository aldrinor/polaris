import { expect, test } from "@playwright/test";

test("Click chart point opens source inspector with URL/tier/excerpt", async ({
  page,
}) => {
  await page.goto("/charts_test/click_through");

  const chart = page.getByTestId("vega-chart");
  await expect(chart).toBeVisible();
  const svg = chart.locator("svg");
  await expect(svg.first()).toBeVisible({ timeout: 10_000 });

  // Prefer Vega's role-aware symbol mark container per I-f10-002 pattern.
  let mark = chart
    .locator(
      'g[role="graphics-object"][aria-roledescription="symbol mark container"] [role="graphics-symbol"]',
    )
    .first();
  if ((await mark.count()) === 0) {
    mark = chart.locator('svg [role="graphics-symbol"]').first();
  }
  await mark.click();

  await expect(page.getByTestId("chart-source-pane")).toBeVisible();
  await expect(page.getByTestId("chart-source-pane-evidence-id")).toContainText(
    "demo-clin-",
  );
  await expect(page.getByTestId("chart-source-pane-url")).toHaveAttribute(
    "href",
    /^https:\/\/example\.org\/select-trial-/,
  );
  await expect(page.getByTestId("chart-source-pane-tier")).toContainText("T1");
  await expect(page.getByTestId("chart-source-pane-excerpt")).toContainText(
    /MACE|Myocardial infarction|Stroke/,
  );
  await expect(page.getByTestId("vega-chart-error")).toHaveCount(0);
});
