import { expect, test } from "@playwright/test";

test("Sentence row with contradiction signal shows ⚠ badge", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  const row = page.locator('[data-sentence-id="sec_x:26"]');
  const badge = row.getByTestId("inspector-contradiction-sec_x:26");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("3 sources disagree");
  await expect(badge).toHaveAttribute(
    "title",
    /Three Cochrane reviews disagree on dose-response curve/,
  );
});

test("Sentence row without contradiction shows NO contradiction badge", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  const row = page.locator('[data-sentence-id="sec_x:5"]');
  await expect(row.getByTestId("inspector-contradiction-sec_x:5")).toHaveCount(
    0,
  );
});
