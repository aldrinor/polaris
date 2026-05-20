// I-cd-025 (#615): /runs/[runId] route G1-G8 acceptance gates.

import { expect, test } from "@playwright/test";

const BANNED_DEV_LANGUAGE = [
  /\bslice\b/i,
  /\bscaffold\b/i,
  /\bplaceholder\b/i,
  /\bphase 0\b/i,
  /\bpost[- ]carney\b/i,
  /\bi-cd-/i,
];

// Use a deterministic run id; the live route 404s the SSE stream and
// status fetch, but the page still renders its shell (G1-G8 gates assert
// landmarks/nav, not data).
const TEST_RUN_ID = "g1-g8-test-runid";

test("G1 + G6: /runs/[runId] has exactly one header + one main", async ({
  page,
}) => {
  await page.goto(`/runs/${TEST_RUN_ID}`);
  await expect(page.locator("header")).toHaveCount(1);
  await expect(page.locator("main")).toHaveCount(1);
});

test("G2: /runs/[runId] contains no banned dev-language strings", async ({
  page,
}) => {
  await page.goto(`/runs/${TEST_RUN_ID}`);
  const body_text = (await page.locator("body").textContent()) || "";
  for (const banned of BANNED_DEV_LANGUAGE) {
    expect(body_text).not.toMatch(banned);
  }
});

test("G1 nav parity: primary nav visible on /runs/[runId]", async ({ page }) => {
  await page.goto(`/runs/${TEST_RUN_ID}`);
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
