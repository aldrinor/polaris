import { expect, test } from "@playwright/test";

test("Inspector renders synthesis-claim badge for is_synthesis_claim=true", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:15"]').click();

  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-synthesis-claim")).toBeVisible();
});

test("Inspector does NOT render synthesis-claim badge for non-synthesis sentence", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:5"]').click();

  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-synthesis-claim")).toHaveCount(0);
});
