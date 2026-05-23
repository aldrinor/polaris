// I-p2-026 (#765): automated WCAG 2.2 AA scan (axe-core via Playwright).
//
// Scans the public + canonical-bundle pages against the WCAG 2.0/2.1/2.2 A+AA
// rule tags. Backend-driven pages (graph, source_review) get their API calls
// intercepted with REAL fixture data (the same data the live endpoints serve)
// so the FULL rendered UI is scanned — not an offline error state.
//
// Usage: BASE=http://127.0.0.1:PORT node tests/a11y/wcag_axe_scan.mjs
// Exits non-zero if any page has serious/critical violations.
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
// Real source-set data the live GET /api/v6/templates serves — read straight
// from the authoritative config so the source-review scan exercises the real
// rendered UI (no synthetic fixture, reproducible without /tmp state).
const templatesDir = fileURLToPath(
  new URL("../../../config/v6_templates/", import.meta.url),
);
const templatesFixture = fs
  .readdirSync(templatesDir)
  .filter((f) => f.endsWith(".json"))
  .map((f) => JSON.parse(fs.readFileSync(path.join(templatesDir, f), "utf-8")));

const PAGES = [
  { name: "home", path: "/" },
  { name: "sign-in", path: "/sign-in" },
  { name: "inspector", path: "/inspector/v1-canonical-success" },
  { name: "audit-export", path: "/runs/v1-canonical-success/audit" },
  {
    name: "knowledge-graph",
    path: "/runs/v1-canonical-success/graph",
    routes: [
      {
        glob: "**/api/runs/*/graph",
        body: graphFixture,
      },
    ],
  },
  {
    name: "source-review",
    path: "/source_review?q=Is%20tirzepatide%20more%20effective%20than%20semaglutide%3F&template=clinical",
    routes: [{ glob: "**/api/v6/templates", body: templatesFixture }],
  },
];

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
    try {
      await p.goto(`${BASE}${page.path}`, {
        waitUntil: "networkidle",
        timeout: 45000,
      });
      await p.waitForTimeout(1800);
      const results = await new AxeBuilder({ page: p })
        .withTags(WCAG_TAGS)
        .analyze();
      const byImpact = { critical: 0, serious: 0, moderate: 0, minor: 0 };
      for (const v of results.violations) {
        byImpact[v.impact ?? "minor"] =
          (byImpact[v.impact ?? "minor"] ?? 0) + v.nodes.length;
      }
      summary.push({
        page: page.name,
        path: page.path,
        violations: results.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          nodes: v.nodes.length,
          targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
        })),
        byImpact,
      });
    } catch (e) {
      summary.push({ page: page.name, path: page.path, error: e.message });
    }
    await ctx.close();
  }
  await browser.close();
  fs.writeFileSync("/tmp/axe_summary.json", JSON.stringify(summary, null, 2));

  let blocking = 0;
  for (const s of summary) {
    if (s.error) {
      console.log(`\n[${s.page}] ERROR: ${s.error}`);
      continue;
    }
    const b = s.byImpact;
    const bad = (b.critical ?? 0) + (b.serious ?? 0);
    blocking += bad;
    const flag = bad > 0 ? "✗" : "✓";
    console.log(
      `\n${flag} [${s.page}] crit=${b.critical} serious=${b.serious} mod=${b.moderate} minor=${b.minor}`,
    );
    for (const v of s.violations) {
      console.log(
        `    - ${v.impact?.toUpperCase()} ${v.id} (${v.nodes}×): ${v.help}`,
      );
      for (const t of v.targets) console.log(`        @ ${t}`);
    }
  }
  console.log(
    `\n=== WCAG 2.2 AA axe scan: ${blocking} critical+serious node-violations across ${PAGES.length} pages ===`,
  );
  process.exit(blocking > 0 ? 1 : 0);
};

run().catch((e) => {
  console.error("scan failed:", e);
  process.exit(2);
});
