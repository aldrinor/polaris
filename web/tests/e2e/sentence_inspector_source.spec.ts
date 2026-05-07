import { expect, test } from "@playwright/test";

test("Inspector renders source URL + tier + span + retrieval trace", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:5"]').click();

  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-source-url-0")).toHaveAttribute(
    "href",
    /cochrane.org/,
  );
  await expect(page.getByTestId("inspector-tier-T1")).toBeVisible();
  await expect(page.getByTestId("inspector-span-0-0")).toContainText(
    "randomized trial",
  );
  await expect(page.getByTestId("inspector-trace-0")).toContainText(
    "Cochrane review",
  );
  await expect(page.getByTestId("inspector-trace-0")).toContainText(
    "2024-03-15",
  );
  await expect(page.getByTestId("inspector-trace-0")).toContainText("Smith J");
});

test("Inspector shows missing-source badge when token references unknown source", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");
  await page.locator('[data-sentence-id="sec_x:9"]').click();

  await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
    timeout: 500,
  });
  await expect(page.getByTestId("inspector-source-missing-0")).toBeVisible();
  await expect(page.getByTestId("inspector-source-missing-0")).toContainText(
    "src-ghost",
  );
});
