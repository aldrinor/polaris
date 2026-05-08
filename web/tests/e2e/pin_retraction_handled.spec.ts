import { expect, test } from "@playwright/test";

test("Pin replay attributes sentence-count regression to newly retracted sources", async ({
  page,
}) => {
  await page.goto("/pin_replay");

  // A=2026-04-30 (retracted: demo-clin-002),
  // B=2026-05-15 (retracted: demo-clin-002 + demo-clin-005).
  // Sentence-count drops 23 → 17 = 6 (>3 threshold).
  // Pass-rate drops 85% → 83% = 2pp (<5pp threshold), so NO pass-rate alert.
  await page.getByTestId("pin-snapshot-a-date").selectOption("2026-04-30");
  await page.getByTestId("pin-snapshot-b-date").selectOption("2026-05-15");

  await expect(page.getByTestId("regression-alert")).toBeVisible();
  await expect(
    page.getByTestId("regression-alert-verified_sentence_count"),
  ).toBeVisible();

  // Pass-rate alert must NOT fire (2pp drop is under threshold).
  await expect(page.getByTestId("regression-alert-pass_rate")).toHaveCount(0);

  // Retraction attribution shows demo-clin-005 (newly retracted between A and B).
  const attribution = page.getByTestId("regression-retraction-attribution");
  await expect(attribution).toBeVisible();
  await expect(attribution).toContainText("demo-clin-005");
  // demo-clin-002 was already retracted in A, so it must NOT be attributed.
  await expect(attribution).not.toContainText("demo-clin-002");
});
