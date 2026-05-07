import { expect, test } from "@playwright/test";

test("Inspector groups multi-span same-source into one card with N blockquotes", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:13"]').click();

  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  // ONE source card (src-0 grouped).
  await expect(page.getByTestId("inspector-source-0")).toBeVisible();
  await expect(page.getByTestId("inspector-source-1")).toHaveCount(0);
  // TWO span blockquotes inside that one card.
  await expect(page.getByTestId("inspector-span-0-0")).toBeVisible();
  await expect(page.getByTestId("inspector-span-0-1")).toBeVisible();
  // Source URL + tier + trace rendered ONCE.
  await expect(page.getByTestId("inspector-source-url-0")).toHaveCount(1);
  await expect(page.getByTestId("inspector-trace-0")).toHaveCount(1);
});

test("Inspector renders multi-source spans as separate cards", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:14"]').click();

  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  // TWO source cards (src-1 then src-2 in token order).
  await expect(page.getByTestId("inspector-source-0")).toBeVisible();
  await expect(page.getByTestId("inspector-source-1")).toBeVisible();
  await expect(page.getByTestId("inspector-source-2")).toHaveCount(0);
  // Each card has one span.
  await expect(page.getByTestId("inspector-span-0-0")).toBeVisible();
  await expect(page.getByTestId("inspector-span-1-0")).toBeVisible();
  await expect(page.getByTestId("inspector-span-0-1")).toHaveCount(0);
});
