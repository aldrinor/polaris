import { expect, test } from "@playwright/test";

/**
 * I-f1-006 — F1 multi-tab safety: 3 same-context tabs, no state pollution.
 *
 * Same-context tabs share storage (cookies/localStorage) but each
 * <iframe>/<page> has independent React component state. The test:
 *  - Opens 3 sibling tabs in ONE context (real "Ctrl+T new tab" model).
 *  - Each tab opens the palette and types a different query.
 *  - Asserts each tab sees ONLY its own scored result.
 *  - Manipulates active_index in tab A + tab B (multi-result), asserts
 *    they remain independent (tab A's leak would push tab B's active).
 *  - Asserts symmetric isolation (clearing tab A doesn't change B/C lists).
 */

const SUGGEST_BUDGET_MS = 350;

async function open_palette(page: import("@playwright/test").Page) {
  await page.goto("/", { waitUntil: "networkidle" });
  await expect(page.getByTestId("header-sign-in-link")).toBeVisible();
  await page.keyboard.press("Control+k");
  await expect(page.getByTestId("command-palette")).toBeVisible();
}

test("3 same-context tabs do not leak palette state", async ({ browser }) => {
  const context = await browser.newContext();
  const [pageA, pageB, pageC] = await Promise.all([
    context.newPage(),
    context.newPage(),
    context.newPage(),
  ]);

  await Promise.all([
    open_palette(pageA),
    open_palette(pageB),
    open_palette(pageC),
  ]);

  // Each tab types its distinct query.
  await pageA.getByTestId("command-palette-input").fill("tirzepatide");
  await pageB.getByTestId("command-palette-input").fill("public policy");
  await pageC.getByTestId("command-palette-input").fill("due diligence");

  // Each settles on its own scored single result.
  await expect(pageA.getByTestId("palette-item-clinical")).toBeVisible({
    timeout: SUGGEST_BUDGET_MS,
  });
  await expect(pageB.getByTestId("palette-item-policy")).toBeVisible({
    timeout: SUGGEST_BUDGET_MS,
  });
  await expect(pageC.getByTestId("palette-item-due_diligence")).toBeVisible({
    timeout: SUGGEST_BUDGET_MS,
  });
  await expect(pageA.locator('[data-testid^="palette-item-"]')).toHaveCount(1);
  await expect(pageB.locator('[data-testid^="palette-item-"]')).toHaveCount(1);
  await expect(pageC.locator('[data-testid^="palette-item-"]')).toHaveCount(1);

  // Active-index isolation: make tab B multi-result + active=1, then move
  // tab A active=2 over its own multi-result list. A leak would force B to
  // index 2 (tech). Tab C (still single-result due_diligence) is the symmetric
  // list-isolation control.
  await pageB.getByTestId("command-palette-input").fill("");
  await expect(pageB.locator('[data-testid^="palette-item-"]')).toHaveCount(8, {
    timeout: SUGGEST_BUDGET_MS,
  });
  await pageB.keyboard.press("ArrowDown");
  await expect(pageB.getByTestId("palette-item-policy")).toHaveAttribute(
    "data-active",
    "true",
  );

  await pageA.getByTestId("command-palette-input").fill("");
  await expect(pageA.locator('[data-testid^="palette-item-"]')).toHaveCount(8, {
    timeout: SUGGEST_BUDGET_MS,
  });
  await pageA.keyboard.press("ArrowDown");
  await pageA.keyboard.press("ArrowDown");
  await expect(pageA.getByTestId("palette-item-tech")).toHaveAttribute(
    "data-active",
    "true",
  );

  // Stability window: wait for the debounce + render budget so any
  // asynchronous cross-tab leak (BroadcastChannel, storage event,
  // debounced sync) has time to arrive before the unchanged-B/C checks.
  await pageB.waitForTimeout(SUGGEST_BUDGET_MS);

  // Tab B unchanged (active still on policy).
  await expect(pageB.getByTestId("palette-item-policy")).toHaveAttribute(
    "data-active",
    "true",
  );
  await expect(pageB.getByTestId("palette-item-tech")).not.toHaveAttribute(
    "data-active",
    "true",
  );
  // Tab C unchanged (single-result due_diligence still active).
  await expect(pageC.locator('[data-testid^="palette-item-"]')).toHaveCount(1);
  await expect(pageC.getByTestId("palette-item-due_diligence")).toHaveAttribute(
    "data-active",
    "true",
  );

  await context.close();
});
