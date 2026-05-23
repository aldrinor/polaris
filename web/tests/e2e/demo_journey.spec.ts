// I-cd-031 (#621): demo journey end-to-end — home → template → ask
// (intake) → run-step (dashboard) → inspector → claim-source.
//
// Verifies each step's landing page renders + links forward to the next
// step. The "run" step itself is hardware-bound (real pipeline-A), so the
// test pivots at /dashboard to /inspector/v1-canonical-success — the
// frozen I-A-02b fixture (I-cd-012) that the gold-route Inspector
// renders. That step's assertions cover the verified-report → claim →
// source provenance UI surface.

import { expect, test } from "@playwright/test";

test("demo journey: home → intake → dashboard → inspector (canonical fixture)", async ({
  page,
}) => {
  // Step 1: home renders the one-CTA hero (I-p2-013 replaced the template
  // grid); the hero search funnels to /intake.
  await page.goto("/");
  await expect(page.getByTestId("home-hero-search")).toBeVisible();
  await page
    .getByTestId("home-hero-search")
    .getByRole("searchbox")
    .fill("What did the SELECT trial show on cardiovascular outcomes?");
  await page
    .getByTestId("home-hero-search")
    .getByRole("button", { name: "Verify" })
    .click();

  // Step 2: lands on /intake with the intake form.
  await expect(page).toHaveURL(/\/intake/);
  await expect(page.getByTestId("intake-page")).toBeVisible();

  // Step 3: the monitoring dashboard is reachable (run-start lives at
  // intake→plan now, I-p2-022 #761; the dashboard is monitoring-only).
  await page.goto("/dashboard");
  await expect(page.getByTestId("dashboard-page")).toBeVisible();

  // Step 4: inspector renders the canonical v1.0 fixture (I-A-02b
  // frozen schema, the contract Carney's office reviews).
  await page.goto("/inspector/v1-canonical-success");
  await expect(page.getByTestId("inspector-view")).toBeVisible({
    timeout: 10_000,
  });

  // Step 5: claim → source UI surface — the family-segregation badge
  // proves the two-family invariant (CLAUDE.md §9.1 invariant 1)
  // surfaces to the reviewer. Tightened per Codex iter-1 P2: assert
  // the dedicated badge testid instead of a broad text match.
  await expect(
    page
      .getByTestId("family-segregation-badge")
      .or(page.locator("[data-testid*='family-segregation']").first()),
  ).toBeVisible({ timeout: 5_000 });
});

// Codex iter-1 P1 fix: the previous version had an
// `if (label === "Upload")` guard that silently skipped Home/Intake/
// Dashboard/etc — so a broken nav with most labels missing would still
// pass. This version unconditionally asserts every primary-nav label.
test("demo journey nav-parity: header + primary nav identical across journey routes", async ({
  page,
}) => {
  const PRIMARY_NAV_LABELS = [
    "Home",
    "Intake",
    "Dashboard",
    "Upload",
    "Benchmark",
    "Contracts",
    "Pin Replay",
    "Memory",
  ];
  for (const path of [
    "/",
    "/intake",
    "/dashboard",
    "/inspector/v1-canonical-success",
  ]) {
    await page.goto(path);
    await expect(page.locator("header")).toHaveCount(1);
    const nav = page.locator("nav[aria-label='Primary']");
    await expect(nav).toBeVisible();
    for (const label of PRIMARY_NAV_LABELS) {
      await expect(nav.getByRole("link", { name: label })).toBeVisible();
    }
  }
});
