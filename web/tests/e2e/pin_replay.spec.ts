import { expect, test } from "@playwright/test";

test("Pin replay route renders 2 snapshot cards + delta; switching dates updates", async ({
  page,
}) => {
  await page.goto("/pin_replay");

  await expect(page.getByTestId("pin-snapshot-a")).toBeVisible();
  await expect(page.getByTestId("pin-snapshot-b")).toBeVisible();
  await expect(page.getByTestId("pin-replay-delta")).toBeVisible();

  // Initial state: A = first registry date (2026-01-15), B = last (2026-04-30).
  await expect(page.getByTestId("pin-snapshot-a-date")).toHaveValue(
    "2026-01-15",
  );
  await expect(page.getByTestId("pin-snapshot-b-date")).toHaveValue(
    "2026-04-30",
  );
  await expect(page.getByTestId("pin-snapshot-a-pass-rate")).toContainText(
    "72%",
  );
  await expect(page.getByTestId("pin-snapshot-b-pass-rate")).toContainText(
    "85%",
  );
  await expect(page.getByTestId("pin-replay-delta-pass-rate")).toContainText(
    "+13%",
  );

  // Switch A to the later date — A and B now identical, delta should be 0.
  await page.getByTestId("pin-snapshot-a-date").selectOption("2026-04-30");
  await expect(page.getByTestId("pin-snapshot-a-pass-rate")).toContainText(
    "85%",
  );
  await expect(page.getByTestId("pin-replay-delta-pass-rate")).toContainText(
    "0%",
  );
  await expect(page.getByTestId("pin-replay-delta-sentences")).toContainText(
    "0",
  );
});
