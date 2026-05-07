import { expect, test } from "@playwright/test";

test("Inspector renders retracted badge when source.retracted=true", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:16"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-retracted-0")).toBeVisible();
});

test("Inspector renders stale badge when publication_date >2y old", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:17"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-stale-0")).toBeVisible();
});

test("Inspector does NOT render retracted/stale badges for fresh non-retracted source", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:5"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-retracted-0")).toHaveCount(0);
  await expect(page.getByTestId("inspector-stale-0")).toHaveCount(0);
});
