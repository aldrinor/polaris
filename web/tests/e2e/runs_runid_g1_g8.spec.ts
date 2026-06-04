// I-cd-025 (#615): /runs/[runId] route G1-G8 acceptance gates.

import { expect, test } from "@playwright/test";
import { setupAuthedNav, expectAuthedNav } from "./_nav_auth";

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
  await setupAuthedNav(page);
  await page.goto(`/runs/${TEST_RUN_ID}`);
  await expectAuthedNav(page);
});

// I-ux-001c sub-PR 7 (#894): v6 chrome cases folded into this CI-run
// spec per the sub-PR 6 pattern (web_ci.yml line 192 runs this file;
// standalone runs_runid_v6.spec.ts would be dead in CI).

test.describe("I-ux-001c v6 chrome", () => {
  test.beforeEach(async ({ page }) => {
    // Mock the getRun endpoint so the 404 doesn't propagate as an error
    // banner that obscures the chrome.
    await page.route("**/api/v6/runs/**", async (route) => {
      const url = route.request().url();
      // Only intercept the GET /api/v6/runs/{id} status fetch, not SSE.
      if (url.includes("/stream/")) {
        return route.continue();
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: TEST_RUN_ID,
          question: "Test question for v6 chrome assertions.",
          template: "clinical",
          status: "running",
          queued_at: "2026-05-25T00:00:00Z",
        }),
      });
    });
    // Mock SSE so the page doesn't open a real EventSource.
    await page.route("**/api/v6/stream/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: "",
      });
    });
  });

  test("v6 chrome: brand-red category eyebrow + run-id eyebrow + display H1", async ({
    page,
  }) => {
    await page.goto(`/runs/${TEST_RUN_ID}`, {
      waitUntil: "domcontentloaded",
    });
    await expect(page.getByTestId("runs-runid-category-eyebrow")).toContainText(
      /LIVE RUN.*POLARIS CLINICAL RESEARCH/i,
    );
    await expect(page.getByTestId("runs-runid-eyebrow")).toContainText(
      /Run g1-g8-test-runid/i,
    );
    // H1 carries the dynamic question text from the mocked status response.
    await expect(page.getByTestId("runs-runid-h1")).toContainText(
      /Test question for v6 chrome assertions/i,
    );
  });
});
