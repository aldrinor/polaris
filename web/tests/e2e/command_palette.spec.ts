import { expect, test } from "@playwright/test";

/**
 * I-f1-002 — Command palette (⌘K) keyboard-only behavior.
 *
 * Acceptance per `.codex/I-f1-002/brief.md` (Codex APPROVE iter 5):
 *  - Ctrl+K opens palette; Enter on active template navigates.
 *  - Enter on to-build template is no-op (URL unchanged, palette stays open).
 *  - Esc closes palette + restores focus to header Sign in link.
 *
 * Hydration race avoidance: every test waits for the header Sign in link
 * to be visible before pressing Ctrl+K (proves client shell hydrated).
 */

test.describe("Command palette — I-f1-002", () => {
  test("Ctrl+K opens palette; type clinical + Enter navigates", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();

    await page.keyboard.press("Control+k");
    const palette = page.getByTestId("command-palette");
    await expect(palette).toBeVisible();

    await page.getByTestId("command-palette-input").fill("clinical");
    await page.keyboard.press("Enter");
    await page.waitForURL("**/intake?template=clinical");
  });

  test("Enter on disabled template is a no-op (URL unchanged)", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();

    const before = page.url();
    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();

    // Arrow-down 3 times to first to-build (ai_sovereignty, after 3 active).
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Enter");

    await expect(page.getByTestId("command-palette")).toBeVisible();
    await expect(page).toHaveURL(before);
  });

  test("Esc closes palette + restores focus to header Sign in link", async ({
    page,
  }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await expect(page.getByTestId("header-sign-in-link")).toBeVisible();

    await page.keyboard.press("Control+k");
    await expect(page.getByTestId("command-palette")).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(page.getByTestId("command-palette")).toBeHidden();
    await expect(page.getByTestId("header-sign-in-link")).toBeFocused();
  });
});
