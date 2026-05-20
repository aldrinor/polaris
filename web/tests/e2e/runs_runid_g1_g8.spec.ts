// I-cd-025 (#615): /runs/[runId] route G1-G8 acceptance gates.

import { expect, test } from "@playwright/test";

const BANNED_DEV_LANGUAGE = [
  /\bslice\b/i,
  /\bscaffold\b/i,
  /\bplaceholder\b/i,
  /\bphase 0\b/i,
  /\bphase 1\b/i, // Codex iter-2 P1: guard against reintroduction.
  /\bphase 2[a-z]?\b/i, // Phase 2A / Phase 2B
  /\bF4 plan\b/i,
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

test("G2: /runs/[runId] contains no banned dev-language strings (body + titles + aria-labels)", async ({
  page,
}) => {
  await page.goto(`/runs/${TEST_RUN_ID}`);
  const body_text = (await page.locator("body").textContent()) || "";
  // Also inspect title attributes + aria-labels (Codex iter-1 P1 fix).
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

test("G8: /runs/[runId] renders with zero console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto(`/runs/${TEST_RUN_ID}`);
  // Use domcontentloaded; networkidle would hang on the live SSE
  // EventSource subscription this page opens (Codex iter-2 P1 fix).
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(1500); // surface async post-mount errors
  expect(errors).toEqual([]);
});

test("G1 nav parity: primary nav visible on /runs/[runId]", async ({
  page,
}) => {
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
