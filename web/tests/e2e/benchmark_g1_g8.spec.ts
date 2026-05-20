// I-cd-027 (#617): /benchmark route G1-G8 acceptance gates.

import { expect, test } from "@playwright/test";

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
];

test("G1 + G6: /benchmark has exactly one header + one main", async ({
  page,
}) => {
  await page.goto("/benchmark");
  await expect(page.locator("header")).toHaveCount(1);
  await expect(page.locator("main")).toHaveCount(1);
});

test("G2: /benchmark contains no banned dev-language strings (body + titles + aria-labels)", async ({
  page,
}) => {
  await page.goto("/benchmark");
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

test("G1 nav parity: primary nav visible on /benchmark", async ({ page }) => {
  await page.goto("/benchmark");
  const nav = page.locator("nav[aria-label='Primary']");
  await expect(nav).toBeVisible();
  for (const label of [
    "Home",
    "Intake",
    "Dashboard",
    "Upload",
    "Benchmark",
    "Contracts",
    "Pin Replay",
    "Memory",
  ]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }
});

test("G8: /benchmark renders with zero console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto("/benchmark");
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(1500);
  expect(errors).toEqual([]);
});
