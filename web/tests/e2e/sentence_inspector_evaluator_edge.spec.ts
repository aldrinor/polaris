import { expect, test } from "@playwright/test";

const N = 12;

test("mode=none — 12 rows, zero evaluator-flag badges", async ({ page }) => {
  await page.goto("/sentence_hover_test/evaluator_edge?mode=none");
  await expect(page.getByTestId("evaluator-edge-none")).toBeVisible();
  // Codex iter-1 P2: explicitly assert kept-sentence count BEFORE asserting
  // zero badges, so an empty/broken route can't false-pass.
  await expect(page.getByTestId("kept-sentence")).toHaveCount(N);
  await expect(page.locator('[data-testid^="evaluator-flag-"]')).toHaveCount(0);
});

test("mode=all — 12 rows, twelve evaluator-flag badges", async ({ page }) => {
  await page.goto("/sentence_hover_test/evaluator_edge?mode=all");
  await expect(page.getByTestId("evaluator-edge-all")).toBeVisible();
  await expect(page.getByTestId("kept-sentence")).toHaveCount(N);
  await expect(page.locator('[data-testid^="evaluator-flag-"]')).toHaveCount(N);
});

test("mode=all — first flagged badge opens EvaluatorPane with both readings", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/evaluator_edge?mode=all");
  await page.getByTestId("evaluator-flag-sec_x:0").click();
  await expect(page.getByTestId("evaluator-pane")).toBeVisible({
    timeout: 500,
  });
  await expect(
    page.getByTestId("evaluator-pane-generator-reading"),
  ).toContainText("Generator reading");
  await expect(
    page.getByTestId("evaluator-pane-evaluator-reading"),
  ).toContainText("Evaluator reading");
});
