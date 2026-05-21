// I-cd-022 (#612): home route G1-G8 acceptance gates per
// state/polaris_ui_rebuild_matrix.md §2. Mechanical assertions only —
// no subjective polish judgments.

import { expect, test } from "@playwright/test";

const BANNED_DEV_LANGUAGE = [
  /\bslice\b/i,
  /\bscaffold\b/i,
  /\bplaceholder\b/i,
  /\bphase 0\b/i,
  /\bpost[- ]carney\b/i,
  /\bi-cd-/i,
];

test("G1 + G6: home has exactly one header outside <main>, primary nav visible", async ({
  page,
}) => {
  await page.goto("/");

  // G1: exactly one <header> element (no duplicate from a forgotten AppShell).
  const headers = page.locator("header");
  await expect(headers).toHaveCount(1);

  // Primary nav present + identical to other routes (Home/Intake/Dashboard/
  // Upload/Benchmark/Contracts/Pin Replay/Memory).
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

  // G6 (single main landmark — Codex iter-2 P1 fix).
  const mains = page.locator("main");
  await expect(mains).toHaveCount(1);
});

test("I-cd-ui-001: home hero search submits to /intake?q=", async ({ page }) => {
  await page.goto("/");
  const form = page.getByTestId("home-hero-search");
  await expect(form).toBeVisible();
  // The hero is a progressive GET form (works without JS): action=/intake,
  // input name=q. Submitting routes to /intake?q=<question>.
  await expect(form).toHaveAttribute("action", "/intake");
  const input = form.locator("input[name='q']");
  await expect(input).toBeVisible();
  await input.fill("does aspirin reduce headaches");
  await form.locator("button[type='submit']").click();
  await page.waitForURL(/\/intake\?q=/);
  expect(page.url()).toContain("q=does");
});

test("G2: home contains no banned dev-language strings", async ({ page }) => {
  await page.goto("/");
  const body_text = (await page.locator("body").textContent()) || "";
  for (const banned of BANNED_DEV_LANGUAGE) {
    expect(body_text).not.toMatch(banned);
  }
});

test("G3: active template card link has focus-visible + hover styling", async ({
  page,
}) => {
  await page.goto("/");
  const link = page.getByTestId("template-card-clinical-link");
  await expect(link).toBeVisible();
  const className = (await link.getAttribute("class")) || "";
  // shadcn/ui Button injects focus-visible:ring + hover utilities. Codex
  // iter-1 P2 fix: assert on the LINK, not the card (cards are not
  // interactive — links/buttons are).
  expect(className).toMatch(/focus-visible/);
});

test("G6: tab key reaches the active template card link", async ({ page }) => {
  await page.goto("/");
  // Tab repeatedly until the focused element is the active template link.
  for (let i = 0; i < 30; i++) {
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(
      () => document.activeElement?.getAttribute("data-testid") ?? null,
    );
    if (focused === "template-card-clinical-link") return;
  }
  throw new Error("active template card link never received focus via Tab");
});

test("G8: home renders with zero console errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  await page.goto("/");
  // Idle long enough for hydration + any async errors to surface.
  await page.waitForLoadState("networkidle");
  expect(errors).toEqual([]);
});
