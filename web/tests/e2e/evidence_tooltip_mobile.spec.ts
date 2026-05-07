import { devices, expect, test } from "@playwright/test";

test.use({ ...devices["iPhone 12"] });

test("Mobile tap opens evidence tooltip and auto-closes after 3s", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/evidence_tooltip");
  await expect(page.getByTestId("evidence-tooltip-harness")).toBeVisible();

  // Popup absent before tap.
  await expect(page.getByTestId("evidence-tooltip-popup")).toHaveCount(0);

  // Tap (touch) the trigger.
  await page.tap('[data-testid="evidence-tooltip-trigger"]');

  // Popup visible within 500ms — touch path skips the 300ms hover debounce.
  await expect(page.getByTestId("evidence-tooltip-popup")).toBeVisible({
    timeout: 500,
  });

  const popup = page.getByTestId("evidence-tooltip-popup");
  await expect(popup).toContainText("tier T1");
  await expect(page.getByTestId("evidence-tooltip-published")).toContainText(
    "Published: 2024-03-15",
  );
  await expect(popup).toContainText("randomized trial enrolled 1247 adults");

  // Auto-close fires at 3000ms; allow 600ms slack for timer scheduling.
  await expect(page.getByTestId("evidence-tooltip-popup")).toHaveCount(0, {
    timeout: 3600,
  });
});
