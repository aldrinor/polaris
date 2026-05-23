// I-cd-023 (#613): /intake route G1-G8 acceptance gates per
// state/polaris_ui_rebuild_matrix.md §2. Pattern mirrors home_g1_g8.spec.ts.

import { expect, test } from "@playwright/test";
import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";

const BANNED_DEV_LANGUAGE = [
  /\bslice\b/i,
  /\bscaffold\b/i,
  /\bplaceholder\b/i,
  /\bphase 0\b/i,
  /\bpost[- ]carney\b/i,
  /\bi-cd-/i,
];

test("G1 + G6: /intake has exactly one header + one main (AppShell-provided)", async ({
  page,
}) => {
  await page.goto("/intake");
  await expect(page.locator("header")).toHaveCount(1);
  await expect(page.locator("main")).toHaveCount(1);
});

test("G2: /intake contains no banned dev-language strings", async ({
  page,
}) => {
  await page.goto("/intake");
  const body_text = (await page.locator("body").textContent()) || "";
  for (const banned of BANNED_DEV_LANGUAGE) {
    expect(body_text).not.toMatch(banned);
  }
});

test("G8: /intake renders with zero console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto("/intake");
  await page.waitForLoadState("networkidle");
  // Existing intake form sub-component may surface known harmless warnings;
  // we only fail on errors per state/polaris_ui_rebuild_matrix.md G8.
  expect(errors).toEqual([]);
});

test("G1 nav parity: primary nav is visible on /intake", async ({ page }) => {
  await setupAuthedNav(page);
  await page.goto("/intake");
  await expectAuthedNav(page);
});
