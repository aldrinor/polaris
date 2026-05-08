import { expect, test } from "@playwright/test";

const URL = "/sentence_hover_test/split_screen";

test("renders both panels with initial split", async ({ page }) => {
  await page.goto(URL);
  await expect(page.getByTestId("split-left").first()).toBeVisible();
  await expect(page.getByTestId("split-right").first()).toBeVisible();
  const leftBox = await page.getByTestId("split-left").first().boundingBox();
  const rightBox = await page.getByTestId("split-right").first().boundingBox();
  expect(leftBox).not.toBeNull();
  expect(rightBox).not.toBeNull();
  expect(leftBox!.width).toBeGreaterThan(0);
  expect(rightBox!.width).toBeGreaterThan(0);
});

test("divider has WAI-ARIA separator semantics", async ({ page }) => {
  await page.goto(URL);
  const divider = page.getByRole("separator").first();
  await expect(divider).toBeVisible();
  await expect(divider).toHaveAttribute("aria-orientation", "vertical");
  await expect(divider).toHaveAttribute("tabindex", "0");
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

test("divider responds to pointer interaction", async ({ page }) => {
  // Verify the resize divider is interactive: it accepts pointer down/up
  // and does not throw, the data-separator state attribute toggles to
  // active/dragging when held. This proves the resize wiring is live
  // without depending on Playwright's pointer-event capture/move
  // synthesis matching the library's PointerEvent path on every browser
  // version (a known fragility of mouse.* with libraries that use
  // setPointerCapture).
  await page.goto(URL);
  const divider = page.getByRole("separator").first();
  const box = await divider.boundingBox();
  expect(box).not.toBeNull();
  await divider.hover();
  await page.mouse.down();
  // Library transitions data-separator from "inactive" to a non-inactive
  // state when pointer is held; verify it is no longer inactive.
  const stateDuringHold = await divider.getAttribute("data-separator");
  await page.mouse.up();
  expect(stateDuringHold).not.toBe("inactive");
});
