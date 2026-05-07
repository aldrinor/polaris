import { expect, test } from "@playwright/test";

test("0/15 — all gaps, no coverage; gap-14 visible + 15 gaps text", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/coverage?covered=0&gap_count=15");
  await expect(page.getByTestId("coverage-harness-0-15")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gaps")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gap-14")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gap-count")).toContainText(
    "15 gaps",
  );
  await expect(page.getByTestId("frame-coverage-gaps")).toContainText("0/15");
});

test("15/15 — all covered, no gaps; complete state", async ({ page }) => {
  await page.goto("/sentence_hover_test/coverage?covered=15&gap_count=0");
  await expect(page.getByTestId("coverage-harness-15-0")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-complete")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gap-0")).toHaveCount(0);
  await expect(page.getByTestId("frame-coverage-complete")).toContainText(
    "15/15",
  );
});

test("1/15 — single covered, 14 gaps; gap-13 visible + 14 gaps text", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/coverage?covered=1&gap_count=14");
  await expect(page.getByTestId("coverage-harness-1-14")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gaps")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gap-13")).toBeVisible();
  await expect(page.getByTestId("frame-coverage-gap-14")).toHaveCount(0);
  await expect(page.getByTestId("frame-coverage-gap-count")).toContainText(
    "14 gaps",
  );
  await expect(page.getByTestId("frame-coverage-gaps")).toContainText("1/15");
});
