// scripts/capture_screenshots.mjs
// Captures landing page and sign-in page screenshots for Phase 0 Task 0.4
// acceptance evidence. Assumes a local server is already running on the
// host:port given by SCREENSHOT_BASE_URL (default http://127.0.0.1:3737/).

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const screenshots_dir = resolve(here, "..", "screenshots");
mkdirSync(screenshots_dir, { recursive: true });

const base_url = (
  process.env.SCREENSHOT_BASE_URL ?? "http://127.0.0.1:3737"
).replace(/\/$/, "");

const targets = [
  {
    name: "dashboard_empty",
    path: "/",
    description: "Landing page (template grid: 3 active + 5 to-build cards)",
  },
  {
    name: "sign_in",
    path: "/sign-in",
    description: "Sign-in screen (placeholder form)",
  },
  {
    name: "research_dashboard",
    path: "/dashboard",
    description: "Runs monitoring dashboard (recent verified briefs)",
  },
  {
    // I-p2-022 (#761): scope-check relocated to /plan (run-start surface).
    name: "plan_scope_rejected",
    path: "/plan?q=Should%20I%20take%20ozempic%20for%20my%20diabetes",
    description: "Plan page: an out-of-scope question is blocked from running",
  },
  {
    // I-p2-022 (#761): scope-check + run-start relocated to /plan.
    name: "plan_scope_accepted",
    path: "/plan?q=What%20is%20the%20efficacy%20of%20tirzepatide%20for%20type%202%20diabetes",
    description: "Plan page: an in-scope question ready to start a run",
  },
  {
    name: "inspector_clinical_golden",
    path: "/inspector/golden_clinical_001",
    description: "Inspector view of clinical golden run",
    interact: async (page) => {
      await page.waitForSelector("text=/Verified sentences/i", {
        timeout: 8000,
      });
    },
  },
  {
    name: "inspector_contradiction_golden",
    path: "/inspector/golden_housing_002",
    description: "Inspector view of housing contradiction golden run",
    interact: async (page) => {
      await page.waitForSelector("text=/Contradictions/i", { timeout: 8000 });
      await page
        .getByRole("button", { name: /Contradictions/ })
        .first()
        .click();
      await page.waitForTimeout(300);
    },
  },
  {
    name: "inspector_charts_tab",
    path: "/inspector/golden_climate_005",
    description: "Inspector charts tab — rendered Vega-Lite forest plot",
    interact: async (page) => {
      await page.waitForSelector("text=/Executive summary/i", {
        timeout: 8000,
      });
      await page
        .getByRole("button", { name: /^Charts/ })
        .first()
        .click();
      await page.waitForSelector(".polaris-vega-chart svg", { timeout: 8000 });
    },
  },
  {
    name: "inspector_executive_summary",
    path: "/inspector/golden_climate_005",
    description: "F10c executive summary tab — KPI strip + 3 charts stacked",
    interact: async (page) => {
      await page.waitForSelector(".polaris-vega-chart svg", { timeout: 12000 });
    },
  },
];

const viewport = { width: 1440, height: 900 };

const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 2,
    colorScheme: "light",
  });
  const page = await context.newPage();
  for (const target of targets) {
    const url = `${base_url}${target.path}`;
    console.log(`Capturing ${target.name} <- ${url}`);
    await page.goto(url, { waitUntil: "networkidle", timeout: 30000 });
    // Allow any client-side font loading to settle.
    await page.waitForTimeout(500);
    const title = await page.title();
    if (!/POLARIS/i.test(title)) {
      throw new Error(
        `Unexpected page title at ${url}: "${title}". Wrong server bound to this port?`,
      );
    }
    if (target.interact) {
      try {
        await target.interact(page);
        await page.waitForTimeout(300);
      } catch (err) {
        console.warn(`  (interact failed for ${target.name}: ${err.message})`);
      }
    }
    const out = resolve(screenshots_dir, `${target.name}.png`);
    await page.screenshot({ path: out, fullPage: true });
    console.log(`  -> ${out} (title="${title}")`);
  }
} finally {
  await browser.close();
}
