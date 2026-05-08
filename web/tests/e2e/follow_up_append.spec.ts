import { expect, test } from "@playwright/test";

test("follow-up append renders 2 reports + visible separator caption", async ({
  page,
}) => {
  await page.goto("/sentence_hover_test/follow_up_append");
  await expect(page.getByTestId("verified-report-view")).toHaveCount(2);
  await expect(page.getByTestId("follow-up-separator")).toBeVisible();
  await expect(page.getByTestId("follow-up-separator-caption")).toContainText(
    "Follow-up appended below",
  );
});
