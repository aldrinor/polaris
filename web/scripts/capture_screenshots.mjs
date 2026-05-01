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
    description: "Landing page (empty dashboard with 3 template cards)",
  },
  {
    name: "sign_in",
    path: "/sign-in",
    description: "Sign-in screen (placeholder form)",
  },
  {
    name: "research_dashboard",
    path: "/dashboard",
    description: "Research-run dashboard with 8-template selector",
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
    const out = resolve(screenshots_dir, `${target.name}.png`);
    await page.screenshot({ path: out, fullPage: true });
    console.log(`  -> ${out} (title="${title}")`);
  }
} finally {
  await browser.close();
}
