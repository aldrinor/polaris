import { expect, test } from "@playwright/test";

// I-cd-017 (#627): demo-data dependency; live-route wiring at Seq 29 / #619.
test.describe.skip("legacy pin-replay demo (Seq 29 / #619 will re-enable)", () => {
test("Regression alert fires when comparing later-A to earlier-B (metric drop)", async ({
  page,
}) => {
  await page.goto("/pin_replay");

  // Initial load: A=2026-01-15 (72%), B=2026-04-30 (85%) — improvement, no alert.
  await expect(page.getByTestId("regression-alert")).toHaveCount(0);

  // Swap: A=2026-04-30 (85%), B=2026-01-15 (72%) — pass rate dropped 13 pct points.
  await page.getByTestId("pin-snapshot-a-date").selectOption("2026-04-30");
  await page.getByTestId("pin-snapshot-b-date").selectOption("2026-01-15");

  await expect(page.getByTestId("regression-alert")).toBeVisible();
  await expect(page.getByTestId("regression-alert-pass_rate")).toContainText(
    /dropped 13/,
  );
  // Sentence count also dropped 23 → 18 = 5 (> threshold 3).
  await expect(
    page.getByTestId("regression-alert-verified_sentence_count"),
  ).toContainText(/dropped 5/);

  // Switch back to improvement: A=2026-01-15, B=2026-04-30 — alert disappears.
  await page.getByTestId("pin-snapshot-a-date").selectOption("2026-01-15");
  await page.getByTestId("pin-snapshot-b-date").selectOption("2026-04-30");
  await expect(page.getByTestId("regression-alert")).toHaveCount(0);
});
});
