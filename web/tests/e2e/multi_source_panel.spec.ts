import { expect, test } from "@playwright/test";

test("Multi-source claim badge shows distinct source count and opens cross-ref panel", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test");

  const row = page.locator('[data-sentence-id="sec_x:31"]');
  const badge = row.getByTestId("multi-source-sec_x:31");
  await expect(badge).toBeVisible();
  await expect(badge).toContainText("5 sources");

  // Sentences with <3 distinct sources MUST NOT render the badge.
  // sec_x:0 cites src-0 only (1 source).
  await expect(
    page
      .locator('[data-sentence-id="sec_x:0"]')
      .getByTestId("multi-source-sec_x:0"),
  ).toHaveCount(0);

  await badge.click();

  // Codex iter-1 P2: badge click MUST NOT also open SentenceInspector.
  await expect(page.getByTestId("sentence-inspector-sheet")).toHaveCount(0);

  await expect(page.getByTestId("multi-source-pane")).toBeVisible();
  await expect(page.getByTestId("multi-source-pane-title")).toContainText(
    "Multi-source claim — 5 sources",
  );

  for (const id of ["src-0", "src-1", "src-2", "src-3", "src-4"]) {
    await expect(
      page.getByTestId(`multi-source-pane-source-${id}`),
    ).toBeVisible();
    await expect(
      page.getByTestId(`multi-source-pane-tier-${id}`),
    ).toBeVisible();
  }
});
