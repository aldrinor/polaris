// I-cd-014 (GH#610) — /sign-in route e2e.
//
// REQUIRED ENV ORCHESTRATION (Codex iter-2 P2 #3):
//
//   # Terminal A — FastAPI backend with test-fixture static_accounts:
//   POLARIS_JWT_SECRET="local-dev-32char-secret-for-tests-only" \
//   POLARIS_STATIC_ACCOUNTS_PATH="$PWD/tests/fixtures/auth/test_static_accounts.yaml" \
//     PYTHONPATH=src python -m uvicorn polaris_v6.api.app:app --port 8000
//
//   # Terminal B — Next.js (use `next dev` for local iteration OR
//   # `npm run build && next start -p 3738` for production-build coverage):
//   cd web && npx next dev -p 3738
//   # OR: cd web && npm run build && npx next start -p 3738
//
//   # Terminal C — run the spec:
//   cd web && SCREENSHOT_BASE_URL=http://127.0.0.1:3738 \
//     npx playwright test --project=chromium tests/e2e/sign_in.spec.ts
//
// Visual baseline ships as `test.fixme()` — chromium-win32 baselines
// captured by operator via `--update-snapshots` after first dev-server
// run; a follow-up PR commits the PNGs.

import { expect, test } from "@playwright/test";

const CARNEY_USERNAME = "carney_office";
const CARNEY_PASSWORD = "carney-test-password";

test.describe("Sign-in route — render + accessibility (G1-G8)", () => {
  test("renders sign-in form with username + password fields (G1 app shell)", async ({
    page,
  }) => {
    await page.goto("/sign-in");
    await expect(page.getByTestId("sign-in-form")).toBeVisible();
    await expect(page.getByLabel("Username")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByTestId("sign-in-submit")).toBeVisible();
  });

  test("no console errors on render (G8)", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    page.on("console", (msg) => {
      if (msg.type() === "error") errors.push(msg.text());
    });
    await page.goto("/sign-in", { waitUntil: "networkidle" });
    expect(errors).toEqual([]);
  });

  test("responsive at 1280/768/375 viewports (G5)", async ({ page }) => {
    for (const vp of [
      { w: 1280, h: 800 },
      { w: 768, h: 1024 },
      { w: 375, h: 667 },
    ]) {
      await page.setViewportSize({ width: vp.w, height: vp.h });
      await page.goto("/sign-in");
      await expect(page.getByTestId("sign-in-form")).toBeVisible();
      await expect(page.getByTestId("sign-in-submit")).toBeVisible();
    }
  });
});

test.describe("Sign-in route — credential validation", () => {
  test("invalid creds → error banner visible", async ({ page }) => {
    await page.goto("/sign-in");
    await page.getByLabel("Username").fill("does-not-exist");
    await page.getByLabel("Password").fill("wrong-password");
    await page.getByTestId("sign-in-submit").click();
    const errorBanner = page.getByTestId("sign-in-error");
    await expect(errorBanner).toBeVisible({ timeout: 8_000 });
    await expect(errorBanner).toHaveAttribute("role", "alert");
  });

  test("valid creds → JWT stored + redirect to /", async ({ page }) => {
    await page.goto("/sign-in");
    await page.getByLabel("Username").fill(CARNEY_USERNAME);
    await page.getByLabel("Password").fill(CARNEY_PASSWORD);
    await page.getByTestId("sign-in-submit").click();
    await expect(page).toHaveURL(/\/$/, { timeout: 8_000 });
    // JWT in sessionStorage (per web/lib/auth.ts).
    const token = await page.evaluate(() =>
      window.sessionStorage.getItem("polaris_jwt"),
    );
    expect(token).toBeTruthy();
  });
});

test.describe("Sign-in route — ?next= same-origin validation", () => {
  test("valid same-origin `?next=` honored after login", async ({ page }) => {
    await page.goto("/sign-in?next=%2Fdashboard");
    await page.getByLabel("Username").fill(CARNEY_USERNAME);
    await page.getByLabel("Password").fill(CARNEY_PASSWORD);
    await page.getByTestId("sign-in-submit").click();
    await expect(page).toHaveURL(/\/dashboard$/, { timeout: 8_000 });
  });

  test("absolute-URL `?next=` falls back to / (cross-origin reject)", async ({
    page,
  }) => {
    // Sign out any leftover session from prior test.
    await page.goto("/sign-in");
    await page.evaluate(() => window.sessionStorage.clear());
    await page.goto("/sign-in?next=https%3A%2F%2Fevil.com%2Fphish");
    await page.getByLabel("Username").fill(CARNEY_USERNAME);
    await page.getByLabel("Password").fill(CARNEY_PASSWORD);
    await page.getByTestId("sign-in-submit").click();
    await expect(page).toHaveURL(/\/$/, { timeout: 8_000 });
  });

  test("protocol-relative `?next=` falls back to /", async ({ page }) => {
    await page.goto("/sign-in");
    await page.evaluate(() => window.sessionStorage.clear());
    await page.goto("/sign-in?next=%2F%2Fevil.com%2Fphish");
    await page.getByLabel("Username").fill(CARNEY_USERNAME);
    await page.getByLabel("Password").fill(CARNEY_PASSWORD);
    await page.getByTestId("sign-in-submit").click();
    await expect(page).toHaveURL(/\/$/, { timeout: 8_000 });
  });
});

// I-cd-014 (GH#610): visual baseline for the sign-in route. test.fixme()
// because chromium-win32 baseline not captured yet; operator runs
// `--update-snapshots` to write the PNG; follow-up PR commits it.
test.describe("Sign-in route — visual baseline (chromium-win32; deferred)", () => {
  test.fixme("sign-in default render visual baseline", async ({ page }) => {
    await page.goto("/sign-in", { waitUntil: "networkidle" });
    await expect(page).toHaveScreenshot("sign-in-default.png", {
      fullPage: true,
      animations: "disabled",
      maxDiffPixelRatio: 0.02,
    });
  });
});
