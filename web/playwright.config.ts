import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e config for POLARIS frontend.
 *
 * Tests assume both servers are already running (frontend on
 * SCREENSHOT_BASE_URL, backend on POLARIS_V6_BACKEND_URL). Phase 0 ships the
 * tests; CI wiring (auto-spawn servers + run on push) lands when the v6 dev
 * cluster is live (Task 0.3).
 *
 * Run locally:
 *   1. Terminal A: PYTHONPATH=src python -m uvicorn polaris_v6.api.app:app --port 8000
 *   2. Terminal B: cd web && npx next start -p 3738
 *   3. Terminal C: cd web && SCREENSHOT_BASE_URL=http://127.0.0.1:3738 npx playwright test
 */
export default defineConfig({
  testDir: "./tests/e2e",
  // F-5 from outputs/audits/continuous/4fe03f7_audit.md: visual baselines
  // are *-chromium-win32.png. On Linux CI the snapshot filename resolves
  // to *-chromium-linux.png and is missing → Playwright would auto-write
  // a new baseline (silent regression). Skip visual.spec.ts on Linux until
  // Linux baselines are generated.
  // I-cd-013a (GH#609): inspector_route.spec.ts visual baselines are
  // authored for chromium-win32 only; Linux baselines are deferred per the
  // existing visual.spec.ts convention.
  testIgnore:
    process.platform === "linux"
      ? ["**/visual.spec.ts", "**/inspector_route.spec.ts"]
      : undefined,
  timeout: 30_000,
  fullyParallel: false, // single browser instance to keep memory bounded on dev
  retries: 0,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: process.env.SCREENSHOT_BASE_URL ?? "http://127.0.0.1:3738",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 1,
    colorScheme: "light",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
});
