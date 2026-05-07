import { expect, test } from "@playwright/test";

test("Inspector renders Agree badge when evaluator_agrees=true", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:10"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-agree")).toBeVisible();
});

test("Inspector renders Disagree badge when evaluator_agrees=false", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:11"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-disagree")).toBeVisible();
});

test("Inspector renders Pending badge when evaluator_agrees=null", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:12"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-agree-pending")).toBeVisible();
});

test("Report header shows family-segregated badge", async ({ page }) => {
  await page.goto("/sentence_hover_test");
  await expect(page.getByTestId("family-segregated")).toBeVisible();
  await expect(page.getByTestId("report-evaluator")).toContainText(
    "strict_verify_v1",
  );
});
