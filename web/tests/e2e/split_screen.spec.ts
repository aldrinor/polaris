import { expect, test } from "@playwright/test";

const URL = "/sentence_hover_test/split_screen";

test("renders both panels with initial 50/50 split", async ({ page }) => {
  await page.goto(URL);
  await expect(page.getByTestId("split-left")).toBeVisible();
  await expect(page.getByTestId("split-right")).toBeVisible();
  await expect(page.getByTestId("split-divider")).toHaveAttribute(
    "aria-valuenow",
    "50",
  );
});

test("divider has resize semantics", async ({ page }) => {
  await page.goto(URL);
  const divider = page.getByRole("separator");
  await expect(divider).toHaveAttribute("aria-valuemin", "20");
  await expect(divider).toHaveAttribute("aria-valuemax", "80");
});

test("left panel content visible", async ({ page }) => {
  await page.goto(URL);
  await expect(page.getByTestId("left-content")).toContainText("LEFT-CONTENT");
});

test("right panel content visible", async ({ page }) => {
  await page.goto(URL);
  await expect(page.getByTestId("right-content")).toContainText(
    "RIGHT-CONTENT",
  );
});

test("pointer drag changes panel widths", async ({ page }) => {
  await page.goto(URL);
  const initial = await page.getByTestId("split-left").boundingBox();
  expect(initial).not.toBeNull();
  const divider = page.getByTestId("split-divider");
  const dividerBox = await divider.boundingBox();
  expect(dividerBox).not.toBeNull();
  const startX = dividerBox!.x + dividerBox!.width / 2;
  const startY = dividerBox!.y + dividerBox!.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 200, startY, { steps: 10 });
  await page.mouse.up();
  const after = await page.getByTestId("split-left").boundingBox();
  expect(after).not.toBeNull();
  expect(after!.width).toBeGreaterThan(initial!.width);
  const valueAfter = await divider.getAttribute("aria-valuenow");
  expect(valueAfter).not.toBe("50");
});
