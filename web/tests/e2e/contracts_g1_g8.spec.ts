// I-cd-028 (#618): /contracts route G1-G8 acceptance gates.

import { expect, test } from "@playwright/test";
import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";

const BANNED_DEV_LANGUAGE = [
  /\bslice\b/i,
  /\bscaffold\b/i,
  /\bplaceholder\b/i,
  /\bphase 0\b/i,
  /\bphase 1\b/i,
  /\bphase 2[a-z]?\b/i,
  /\bF4 plan\b/i,
  /\bpost[- ]carney\b/i,
  /\bi-cd-/i,
  /\bi-ecg-/i,
  /POLARIS_REQUIRE_CONTRACT/i,
];

test("G1 + G6: /contracts has exactly one header + one main", async ({
  page,
}) => {
  await page.goto("/contracts");
  await expect(page.locator("header")).toHaveCount(1);
  await expect(page.locator("main")).toHaveCount(1);
});

test("G2: /contracts contains no banned dev-language strings (body + titles + aria-labels)", async ({
  page,
}) => {
  await page.goto("/contracts");
  const body_text = (await page.locator("body").textContent()) || "";
  const title_text =
    (await page
      .locator("[title]")
      .evaluateAll((els: Element[]) =>
        els.map((el) => el.getAttribute("title") || "").join(" · "),
      )) || "";
  const aria_text =
    (await page
      .locator("[aria-label]")
      .evaluateAll((els: Element[]) =>
        els.map((el) => el.getAttribute("aria-label") || "").join(" · "),
      )) || "";
  const all_text = `${body_text} · ${title_text} · ${aria_text}`;
  for (const banned of BANNED_DEV_LANGUAGE) {
    expect(all_text).not.toMatch(banned);
  }
});

test("G1 nav parity: primary nav visible on /contracts", async ({ page }) => {
  await setupAuthedNav(page);
  await page.goto("/contracts");
  await expectAuthedNav(page);
});

test("G8: /contracts renders with zero console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto("/contracts");
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(1500);
  expect(errors).toEqual([]);
});
