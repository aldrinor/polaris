import { expect, test } from "@playwright/test";

test("Row shows evaluator-flag badge when evaluator_agrees=false", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  const badge = page.getByTestId("evaluator-flag-sec_x:11");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("Internal evaluator flagged this");
});

test("Row does NOT show evaluator-flag for evaluator_agrees=true", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await expect(page.getByTestId("evaluator-flag-sec_x:5")).toHaveCount(0);
});

test("Row does NOT show evaluator-flag for evaluator_agrees=null pending", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await expect(page.getByTestId("evaluator-flag-sec_x:12")).toHaveCount(0);
});
