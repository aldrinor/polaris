import { expect, test } from "@playwright/test";

test("Inspector renders paywalled badge when source.full_text_available=false", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:23"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-paywalled-0")).toBeVisible();
  // URL still actionable.
  await expect(page.getByTestId("inspector-source-url-0")).toHaveAttribute(
    "href",
    /nejm\.org/,
  );
});

test("Inspector flags out-of-range second span in multi-span case", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:24"]').click();
  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  // First span valid (0-30 within full_text length).
  await expect(page.getByTestId("inspector-span-0-0")).toBeVisible();
  // Second span out-of-range (5000-5050 beyond full_text length).
  await expect(
    page.getByTestId("inspector-span-out-of-range-0-1"),
  ).toBeVisible();
});

test("Row shows T1-conflict heuristic when ≥2 T1 sources cited", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  const row = page.locator('[data-sentence-id="sec_x:25"]');
  await expect(row).toBeVisible();
  await expect(row.getByTestId("inspector-t1-conflict")).toBeVisible();
});

test("Row does NOT show T1-conflict for single-T1-source sentence", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  const row = page.locator('[data-sentence-id="sec_x:5"]');
  await expect(row.getByTestId("inspector-t1-conflict")).toHaveCount(0);
});
