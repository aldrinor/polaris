import { expect, test } from "@playwright/test";

test("Tooltip absent before hover; debounced; visible within 500ms after hover", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/evidence_tooltip");
  await expect(page.getByTestId("evidence-tooltip-harness")).toBeVisible();
  // (a) popup absent before any hover.
  await expect(page.getByTestId("evidence-tooltip-popup")).toHaveCount(0);

  // (b) Codex iter-1 P2: pop NOT visible immediately after hover (debounce).
  await page.getByTestId("evidence-tooltip-trigger").hover();
  // Take a near-immediate sample (~50ms): should still be absent because of
  // the 300ms Provider delay.
  await page.waitForTimeout(50);
  await expect(page.getByTestId("evidence-tooltip-popup")).toHaveCount(0);

  // (c) within 500ms the popup should be present (300ms delay + buffer).
  await expect(page.getByTestId("evidence-tooltip-popup")).toBeVisible({
    timeout: 500,
  });
  // Content checks.
  const popup = page.getByTestId("evidence-tooltip-popup");
  await expect(popup).toContainText("tier T1");
  await expect(page.getByTestId("evidence-tooltip-published")).toContainText(
    "Published: 2024-03-15",
  );
  await expect(popup).toContainText("randomized trial enrolled 1247 adults");
});
