/**
 * I-p2c-002: 60 visual baselines (4 viewports × 15 features).
 *
 * Playwright-native `toHaveScreenshot()` baselines stored as PNGs alongside
 * the spec. Restricted to Windows + chromium per CLAUDE.md F-5 visual-baseline
 * convention; Linux + firefox/webkit baselines are follow-up I-p2c-002d.
 *
 * Percy.io integration deferred to follow-up I-p2c-002b (paid SaaS — needs
 * user-side credentials).
 *
 * Initial baselines generated via `--update-snapshots`. Subsequent runs
 * assert pixel-equality with `maxDiffPixelRatio: 0.01`.
 */

import { expect, test } from "@playwright/test";

interface PageEntry {
  feature: string;
  path: string;
  testid: string;
  wait_svg_count?: number;
  mock_memory?: boolean;
  mock_benchmark?: boolean;
}

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 667 },
  { name: "tablet", width: 768, height: 1024 },
  { name: "laptop", width: 1280, height: 800 },
  { name: "desktop", width: 1920, height: 1080 },
] as const;

const PAGES: PageEntry[] = [
  { feature: "F1", path: "/intake", testid: "intake-form" },
  {
    feature: "F2",
    path: "/disambiguation_modal_preview",
    testid: "disambiguation-cluster-0",
  },
  { feature: "F3", path: "/upload", testid: "upload-dropzone" },
  { feature: "F4", path: "/sse", testid: "sse-harness" },
  {
    feature: "F5",
    path: "/sentence_hover_test/evidence_tooltip",
    testid: "evidence-tooltip-harness",
  },
  { feature: "F6", path: "/sentence_hover_test", testid: "verified-report-view" },
  {
    feature: "F7",
    path: "/sentence_hover_test/coverage",
    testid: "frame-coverage-gaps",
  },
  { feature: "F8", path: "/sentence_hover_test", testid: "verified-report-view" },
  {
    feature: "F9",
    path: "/sentence_hover_test/evaluator_edge",
    testid: "verified-report-view",
  },
  {
    feature: "F10",
    path: "/charts_test/forest_plot",
    testid: "vega-chart",
    wait_svg_count: 1,
  },
  { feature: "F11", path: "/contracts", testid: "contract-form" },
  {
    feature: "F12",
    path: "/sentence_hover_test/perf",
    testid: "perf-trigger",
  },
  {
    feature: "F13",
    path: "/pin_replay",
    testid: "pin-snapshot-a",
    wait_svg_count: 2,
  },
  {
    feature: "F14",
    path: "/memory",
    testid: "memory-banner",
    mock_memory: true,
  },
  {
    feature: "F15",
    path: "/benchmark",
    testid: "benchmark-page",
    mock_benchmark: true,
  },
];

for (const viewport of VIEWPORTS) {
  for (const p of PAGES) {
    test(`${p.feature} ${viewport.name}`, async ({ page }, testInfo) => {
      test.skip(
        process.platform !== "win32" || testInfo.project.name !== "chromium",
        "I-p2c-002 baselines restricted to Windows+chromium; cross-OS in I-p2c-002d",
      );
      if (p.mock_memory) {
        await page.route("**/workspaces/ws_demo/memory", async (route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify([]),
          });
        });
      }
      if (p.mock_benchmark) {
        await page.route("**/api/benchmark/**", async (route) => {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              available_benchmarks: [],
              results_root: "/seeded/benchmarks",
            }),
          });
        });
      }
      await page.setViewportSize({
        width: viewport.width,
        height: viewport.height,
      });
      await page.goto(p.path, { waitUntil: "domcontentloaded" });
      await expect(page.getByTestId(p.testid)).toBeVisible();
      if (p.wait_svg_count && p.wait_svg_count > 0) {
        const svgs = page.locator("[data-testid='vega-chart'] svg");
        await expect(svgs).toHaveCount(p.wait_svg_count, { timeout: 10_000 });
      }
      await expect(page).toHaveScreenshot(`${p.feature}-${viewport.name}.png`, {
        animations: "disabled",
        maxDiffPixelRatio: 0.01,
      });
    });
  }
}
