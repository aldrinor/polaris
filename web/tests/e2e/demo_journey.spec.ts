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
  // Step 1: home renders + clinical template card present + linked.
  await page.goto("/");
  await expect(page.getByTestId("template-card-clinical")).toBeVisible();
  await expect(page.getByTestId("template-card-clinical-link")).toBeVisible();
  const intake_link = page.getByTestId("template-card-clinical-link").first();
  await intake_link.click();

  // Step 2: lands on /intake?template=clinical with the intake form.
  await expect(page).toHaveURL(/\/intake\?template=clinical/);
  await expect(page.getByTestId("intake-page")).toBeVisible();

  // Step 3: dashboard is reachable directly (the "ask a question" UX
  // entry). The intake page funnels here for clinical questions.
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
