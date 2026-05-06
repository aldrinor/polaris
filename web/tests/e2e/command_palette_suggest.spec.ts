import { expect, test } from "@playwright/test";

/**
 * I-f1-003 — Live template suggestion as user types.
 *
 * Validates the debounced + scored search inside the command palette:
 *  - "tirzepatide" (synonym) → exactly one visible item: clinical.
 *  - "BPEI" (no match) → empty list (zero false-positives).
 *  - "tirzepatide" + Enter → /intake?template=clinical via scoring path.
 *
 * Each test waits for header-sign-in-link visible after networkidle to
 * prove client shell hydration; then opens palette via Ctrl+K.
 */

const SUGGEST_BUDGET_MS = 250; // 150ms debounce + 100ms render budget

test.describe("Command palette suggest — I-f1-003", () => {
  test("synonym 'tirzepatide' yields exactly one item: clinical", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();

    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();

    // Empty palette opens with all 8 templates visible (initial state).
    const items = page.locator('[data-testid^="palette-item-"]');
    await expect(items).toHaveCount(8);

    await page.getByTestId("command-palette-input").fill("tirzepatide");
    // Post-debounce post-scoring: synonym map fires and only clinical
    // survives the filter. Plain substring filter would yield 0 items
    // (no template name/summary contains "tirzepatide"), so this
    // assertion proves scoring + synonym map ran.
    await expect(items).toHaveCount(1, { timeout: SUGGEST_BUDGET_MS + 100 });
    await expect(page.getByTestId("palette-item-clinical")).toBeVisible();
  });

  test("'BPEI' yields zero items (no false-positive)", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();

    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();

    await page.getByTestId("command-palette-input").fill("BPEI");
    // After debounce + render, nothing should match.
    await page.waitForTimeout(SUGGEST_BUDGET_MS);
    const items = page.locator('[data-testid^="palette-item-"]');
    await expect(items).toHaveCount(0);
  });

  test("'tirzepatide' + Enter navigates to /intake?template=clinical", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();

    await page.keyboard.press("Control+k");
    const items = page.locator('[data-testid^="palette-item-"]');
    await expect(items).toHaveCount(8);

    await page.getByTestId("command-palette-input").fill("tirzepatide");
    // Wait for post-debounce post-scoring state (count=1 → only clinical).
    await expect(items).toHaveCount(1, { timeout: SUGGEST_BUDGET_MS + 100 });
    await page.keyboard.press("Enter");
    await page.waitForURL("**/intake?template=clinical");
  });
});
