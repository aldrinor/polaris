// I-cd-024 (#614): /dashboard route G1-G8 acceptance gates.

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

test("G1 + G6: /dashboard has exactly one header + one main", async ({
  page,
}) => {
  await page.goto("/dashboard");
  await expect(page.locator("header")).toHaveCount(1);
  await expect(page.locator("main")).toHaveCount(1);
});

test("G2: /dashboard contains no banned dev-language strings", async ({
  page,
}) => {
  await page.goto("/dashboard");
  const body_text = (await page.locator("body").textContent()) || "";
  for (const banned of BANNED_DEV_LANGUAGE) {
    expect(body_text).not.toMatch(banned);
  }
});

test("G1 nav parity: primary nav visible on /dashboard", async ({ page }) => {
  await setupAuthedNav(page);
  await page.goto("/dashboard");
  await expectAuthedNav(page);
});

test("G8: /dashboard renders with zero console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto("/dashboard");
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
});
