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

test("Click evaluator-flag → EvaluatorPane shows generator + evaluator readings (I-f9-002)", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.getByTestId("evaluator-flag-sec_x:11").click();
  await expect(page.getByTestId("evaluator-pane")).toBeVisible({
    timeout: 500,
  });
  await expect(
    page.getByTestId("evaluator-pane-generator-reading"),
  ).toContainText("30%");
  await expect(
    page.getByTestId("evaluator-pane-evaluator-reading"),
  ).toContainText("confidence interval");
  await expect(page.getByTestId("evaluator-pane-source-0")).toContainText(
    "src-1",
  );
  await expect(page.getByTestId("evaluator-pane-model")).toContainText(
    "qwen-3.5-plus",
  );
  // SentenceInspector did NOT also open (propagation guard).
  await expect(page.getByTestId("sentence-inspector-sheet")).toHaveCount(0);
});
