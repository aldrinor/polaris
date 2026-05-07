import { expect, test } from "@playwright/test";

test("clicking a sentence opens the Inspector Sheet within 500ms", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await expect(page.getByTestId("verified-report-view")).toBeVisible();

  const target = page.locator('[data-sentence-id="sec_x:5"]');
  await target.click();

  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("sentence-inspector-id")).toContainText(
    "sec_x:5",
  );
  await expect(page.getByTestId("sentence-inspector-text")).toContainText(
    "Test sentence 5",
  );
});
