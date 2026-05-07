import { expect, test } from "@playwright/test";

test("hovering a sentence applies bg-yellow-100; switching clears prior", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await expect(page.getByTestId("verified-report-view")).toBeVisible();

  const s7 = page.locator('[data-sentence-id="sec_x:7"]');
  const s3 = page.locator('[data-sentence-id="sec_x:3"]');

  await s7.hover();
  await expect(s7).toHaveClass(/bg-yellow-100/, { timeout: 500 });

  await s3.hover();
  await expect(s3).toHaveClass(/bg-yellow-100/, { timeout: 500 });
  await expect(s7).not.toHaveClass(/bg-yellow-100/);
});
