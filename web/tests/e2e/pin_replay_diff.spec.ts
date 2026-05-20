import { expect, test } from "@playwright/test";

// I-cd-017 (#627): demo-data dependency; live-route wiring at Seq 29 / #619.
test.describe.skip("legacy pin-replay demo (Seq 29 / #619 will re-enable)", () => {
test("Pin replay renders timeseries charts and diff side-panel on demand", async ({
  page,
}) => {
  await page.goto("/pin_replay");

  // Two timeseries charts render with svg.
  const pass_rate_section = page.getByTestId("pin-timeseries-pass-rate");
  const sentence_section = page.getByTestId("pin-timeseries-sentence-count");
  await expect(pass_rate_section).toBeVisible();
  await expect(sentence_section).toBeVisible();
  await expect(pass_rate_section.locator("svg").first()).toBeVisible({
    timeout: 10_000,
  });
  await expect(sentence_section.locator("svg").first()).toBeVisible({
    timeout: 10_000,
  });

  // Open the diff side-panel.
  await page.getByTestId("pin-show-diff").click();
  await expect(page.getByTestId("pin-diff-pane")).toBeVisible();

  // Per-field rows visible.
  await expect(page.getByTestId("pin-diff-row-pass_rate")).toBeVisible();
  await expect(
    page.getByTestId("pin-diff-row-verified_sentence_count"),
  ).toBeVisible();
  await expect(page.getByTestId("pin-diff-row-query")).toBeVisible();

  // Numeric delta on pass_rate is "+13%" (B=2026-04-30 85% − A=2026-01-15 72%).
  await expect(page.getByTestId("pin-diff-delta-pass_rate")).toContainText(
    "+13%",
  );
  // String field delta is "(unchanged)" since same query string.
  await expect(page.getByTestId("pin-diff-delta-query")).toContainText(
    "unchanged",
  );

  await expect(page.getByTestId("vega-chart-error")).toHaveCount(0);
});
});
