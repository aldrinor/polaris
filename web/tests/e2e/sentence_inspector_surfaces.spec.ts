import { expect, test } from "@playwright/test";

const SURFACES: { id: number; surface: string }[] = [
  { id: 18, surface: "table" },
  { id: 19, surface: "summary_bullet" },
  { id: 20, surface: "limitation" },
  { id: 21, surface: "caption" },
  { id: 22, surface: "heading" },
];

test("Report header shows assertion-surface legend", async ({ page }) => {
  await page.goto("/sentence_hover_test");
  await expect(page.getByTestId("assertion-surface-legend")).toBeVisible();
  await expect(page.getByTestId("assertion-surface-legend")).toContainText(
    "Prose",
  );
  await expect(page.getByTestId("assertion-surface-legend")).toContainText(
    "Heading",
  );
});

for (const { id, surface } of SURFACES) {
  test(`${surface} sentence is clickable and opens Inspector`, async ({
    page,
  }) => {
    await page.goto("/sentence_hover_test");
    const row = page.locator(`[data-sentence-id="sec_x:${id}"]`);
    await expect(row.getByTestId(`surface-badge-${surface}`)).toBeVisible();
    await row.click();
    await expect(page.getByTestId("sentence-inspector-sheet")).toBeVisible({
      timeout: 500,
    });
  });
}
