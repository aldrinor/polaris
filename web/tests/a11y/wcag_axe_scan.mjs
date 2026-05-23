// I-p2-026 (#765): automated WCAG 2.2 AA scan (axe-core via Playwright).
//
// Scans the public + canonical-bundle pages against the WCAG 2.0/2.1/2.2 A+AA
// rule tags. Backend-driven pages (graph, source_review) get their API calls
// intercepted with REAL fixture data (graph_payload.json + the authoritative
// config/v6_templates/*.json) so the FULL rendered UI is scanned — not an
// offline error state.
//
// FAIL-LOUD (LAW II): a non-2xx response, a missing expected-content selector,
// a navigation error, OR any WCAG-tagged violation (ANY impact) is BLOCKING and
// exits non-zero. The harness must never pass on a page that didn't actually
// render. The inspector cycles every tab so hidden tab-panel content is scanned.
//
// Usage: BASE=http://127.0.0.1:PORT node tests/a11y/wcag_axe_scan.mjs
import { chromium } from "playwright";
import { AxeBuilder } from "@axe-core/playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.BASE ?? "http://127.0.0.1:4019";
const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

const graphFixture = JSON.parse(
  fs.readFileSync(new URL("../fixtures/graph_payload.json", import.meta.url)),
);
const templatesDir = fileURLToPath(
  new URL("../../../config/v6_templates/", import.meta.url),
);
const templatesFixture = fs
  .readdirSync(templatesDir)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(fs.readFileSync(path.join(templatesDir, f), "utf-8")));

// `expect`: a selector that MUST be visible after load (readiness assertion).
// `cycleTabs`: if true, click every [role=tab] and re-scan the revealed panel.
const PAGES = [
  { name: "home", path: "/", expect: "h1" },
  { name: "sign-in", path: "/sign-in", expect: "form" },
  {
    name: "inspector",
    path: "/inspector/v1-canonical-success",
    expect: "[data-testid=inspector-view]",
    cycleTabs: true,
  },
  {
    name: "audit-export",
    path: "/runs/v1-canonical-success/audit",
    expect: "[data-testid=audit-export-page]",
  },
  {
    name: "knowledge-graph",
    path: "/runs/v1-canonical-success/graph",
    expect: "[data-testid=graph-page]",
    routes: [{ glob: "**/api/runs/*/graph", body: graphFixture }],
  },
  {
    name: "source-review",
    path: "/source_review?q=Is%20tirzepatide%20more%20effective%20than%20semaglutide%3F&template=clinical",
    expect: "[data-testid=source-review-page]",
    routes: [{ glob: "**/api/v6/templates", body: templatesFixture }],
  },
];

const analyze = (p) =>
  new AxeBuilder({ page: p }).withTags(WCAG_TAGS).analyze();

const run = async () => {
  const browser = await chromium.launch();
  const summary = [];
  for (const page of PAGES) {
    const ctx = await browser.newContext({
      viewport: { width: 1366, height: 900 },
    });
    const p = await ctx.newPage();
    for (const r of page.routes ?? []) {
      await p.route(r.glob, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(r.body),
        }),
      );
    }
    const entry = { page: page.name, path: page.path, violations: [] };
    try {
      const resp = await p.goto(`${BASE}${page.path}`, {
        waitUntil: "networkidle",
        timeout: 45000,
      });
      // Readiness gate 1: HTTP status must be 2xx/3xx.
      if (!resp || resp.status() >= 400) {
        throw new Error(`HTTP ${resp ? resp.status() : "no-response"}`);
      }
      // Readiness gate 2: the expected content selector must be visible —
      // otherwise the page errored/redirected and an "all clear" axe run is
      // meaningless.
      await p.waitForSelector(page.expect, {
        state: "visible",
        timeout: 15000,
      });
      await p.waitForTimeout(1200);

      const seen = new Set();
      const collect = (results) => {
        for (const v of results.violations) {
          for (const node of v.nodes) {
            const key = `${v.id}::${node.target.join(" ")}`;
            if (seen.has(key)) continue;
            seen.add(key);
            entry.violations.push({
              id: v.id,
              impact: v.impact,
              help: v.help,
              target: node.target.join(" "),
            });
          }
        }
      };

      collect(await analyze(p));

      // P2b: scan hidden tab-panel content by cycling every tab.
      if (page.cycleTabs) {
        const tabs = await p.locator("[role=tab]").all();
        for (const tab of tabs) {
          await tab.click();
          await p.waitForTimeout(400);
          collect(await analyze(p));
        }
      }
    } catch (e) {
      entry.error = e.message;
    }
    summary.push(entry);
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync("/tmp/axe_summary.json", JSON.stringify(summary, null, 2));

  // FAIL-LOUD: blocking = page errors + ALL WCAG-tagged violations (any impact).
  let blocking = 0;
  for (const s of summary) {
    if (s.error) {
      blocking += 1;
      console.log(`\n✗ [${s.page}] PAGE ERROR (counts as failure): ${s.error}`);
      continue;
    }
    const n = s.violations.length;
    blocking += n;
    console.log(`\n${n === 0 ? "✓" : "✗"} [${s.page}] ${n} WCAG violation(s)`);
    for (const v of s.violations) {
      console.log(`    - ${v.impact?.toUpperCase()} ${v.id}: ${v.help}`);
      console.log(`        @ ${v.target}`);
    }
  }
  console.log(
    `\n=== WCAG 2.2 AA axe scan: ${blocking} blocking (page-errors + all WCAG violations) across ${PAGES.length} pages ===`,
  );
  process.exit(blocking > 0 ? 1 : 0);
};

run().catch((e) => {
  console.error("scan harness failed:", e);
  process.exit(2);
});
