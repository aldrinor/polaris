// I-ux-001c sub-PR 8 (#896): /compare route G1-G8 acceptance gates +
// v6 chrome cases. Mirrors the dashboard_g1_g8.spec.ts pattern.
//
// This is the first CI-wired e2e file for /compare. web_ci.yml gets a
// matching block enumerating this spec.

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

test.describe("/compare G1-G8 + v6 chrome", () => {
  test.beforeEach(async ({ page }) => {
    // Mock the auth-gated runs endpoint so listCompletedRuns doesn't
    // race / 401 during the chrome assertions.
    await page.route("**/api/v6/runs**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ runs: [] }),
      });
    });
  });

  test("G1 + G6: /compare has exactly one header + one main", async ({
    page,
  }) => {
    await page.goto("/compare");
    await expect(page.locator("header")).toHaveCount(1);
    await expect(page.locator("main")).toHaveCount(1);
  });

  test("G2: /compare contains no banned dev-language strings", async ({
    page,
  }) => {
    await page.goto("/compare");
    const body_text = (await page.locator("body").textContent()) || "";
    for (const banned of BANNED_DEV_LANGUAGE) {
      expect(body_text).not.toMatch(banned);
    }
  });

  test("G1 nav parity: primary nav visible on /compare", async ({ page }) => {
    await setupAuthedNav(page);
    await page.goto("/compare");
    await expectAuthedNav(page);
  });

  test("G8: /compare renders with zero console errors", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.goto("/compare");
    await page.waitForLoadState("networkidle");
    expect(errors).toEqual([]);
  });

  // v6 chrome
  test("v6 chrome: eyebrow + H1 + subtitle render with locked copy", async ({
    page,
  }) => {
    await page.goto("/compare", { waitUntil: "domcontentloaded" });
    await expect(page.getByTestId("compare-eyebrow")).toContainText(
      /COMPARE.*POLARIS CLINICAL RESEARCH/i,
    );
    await expect(page.getByTestId("compare-h1")).toContainText(
      "Compare two runs side-by-side",
    );
    await expect(page.getByTestId("compare-subtitle")).toContainText(
      /Shared evidence.*see what changes from one verified run to the next/i,
    );
  });
});
