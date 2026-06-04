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

// I-ux-001c sub-PR 6 (#891): v6 chrome cases folded into this CI-run
// spec per brief iter-4 P1 fix (web_ci.yml line 185 runs this file;
// standalone dashboard_v6.spec.ts would be dead in CI).

test.describe("I-ux-001c v6 chrome", () => {
  test.beforeEach(async ({ page }) => {
    // Mock /api/v6/runs so the auth-gated listCompletedRuns doesn't
    // race with chrome assertions.
    await page.route("**/api/v6/runs**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ runs: [] }),
      });
    });
  });

  test("v6 chrome: eyebrow + H1 + subtitle render with locked copy", async ({
    page,
  }) => {
    await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("dashboard-eyebrow")).toContainText(
      /RUNS.*POLARIS CLINICAL RESEARCH/i,
    );
    await expect(page.getByTestId("dashboard-h1")).toContainText(
      "Your recent runs",
    );
    await expect(page.getByTestId("dashboard-subtitle")).toContainText(
      /Open one to replay the proof.*every brief carries its own audit bundle/i,
    );
  });

  test("v6 chrome: Start-new-research link still navigates to /intake", async ({
    page,
  }) => {
    await page.goto("/dashboard", { waitUntil: "domcontentloaded" });
    const link = page.getByTestId("dashboard-start-run");
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/intake");
  });
});
