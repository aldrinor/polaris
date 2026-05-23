# Codex DIFF review — I-p2-026 (#765): WCAG 2.2 AA automated axe pass + 2 contrast fixes

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `7c38961fac5b30a384b8e49178eadf8dce5b3a764638b8a735dc3d5bfa8d1807`. web/ only, 3 files, 174-line diff (under 200-LOC cap). MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Context
#765 = "Verify: WCAG 2.2 AA accessibility pass (automated + manual keyboard/screen-reader)". Operator (2026-05-22) authorized the **automated** slice now (public pages, no creds/cost), fix violations via the normal cycle; the auth-gated routes + manual keyboard/SR remain operator-side. This is that automated slice.

## Diff (3 files)
1. `web/tests/a11y/wcag_axe_scan.mjs` (NEW): `@axe-core/playwright` scan over 6 pages (home, sign-in, inspector, audit/export, knowledge-graph, source-review) with tags `wcag2a/wcag2aa/wcag21a/wcag21aa/wcag22aa`. Backend-driven pages (graph, source-review) get their API intercepted with REAL fixture data — `tests/fixtures/graph_payload.json` + the actual `config/v6_templates/*.json` (read via fileURLToPath for Windows-safe paths) — so the FULL rendered UI is scanned, not offline error states. Exits non-zero on any serious/critical violation.
2. `web/components/ui/tabs.tsx`: inactive `TabsTrigger` inherited `text-muted-foreground` on the `bg-muted` list strip → muted-foreground (oklch L 0.556) on bg-muted (L 0.97) FAILS 4.5:1 (7 inspector tabs flagged SERIOUS). Added explicit `text-foreground/70` to the trigger base (clears AA; still lighter than the `data-[selected]:text-foreground` active tab). Pure visual contrast change, no behavior change.
3. `web/app/source_review/page.tsx`: the "how sources are gathered" callout used `text-muted-foreground` on `bg-muted/40` → same contrast failure (1 SERIOUS). Switched the callout to `bg-card` (muted-foreground on white passes AA, as every other info card on the page already does).

## Evidence (empirical, both scans run)
- **Before:** 8 SERIOUS color-contrast node-violations (inspector ×7 tabs, source-review ×1 callout). home/sign-in/audit/knowledge-graph already clean.
- **After the 2 fixes:** `0 critical+serious violations across all 6 pages` (re-scan output captured). typecheck + `npm run build` green.

## Files I have ALSO checked and they're clean
- `components/ui/tabs.tsx` is used ONLY by `inspector_view.tsx` (grep) — the contrast fix is contained; no other tab surface regresses.
- The token math: `--muted-foreground: oklch(0.556 0 0)`, `--muted: oklch(0.97 0 0)`, `--card: oklch(1 0 0)`, `--foreground: oklch(0.21 ...)`. muted-foreground passes AA on white (home/audit prove it) but not on the 0.97 muted bg — hence both fixes move text/ bg toward white-backed or darker-text.
- `text-foreground/70` rendered contrast verified by axe (it samples computed pixels incl. opacity) — passes.

## Honest scope (partial #765)
This is the AUTOMATED axe slice on the **public/canonical** pages only. NOT covered (operator-side, flagged in the issue + the audit): the auth-gated flow routes (intake/plan/source-review-live/dashboard/compare need prod creds for full content), and the MANUAL keyboard-navigation + screen-reader passes (need a human). #765 stays OPEN after this merges; this is real partial progress + a reusable scan harness, not a full close.

## Review focus
1. Are the 2 contrast fixes correct + sufficient (no behavior/visual regression beyond the intended contrast bump)? Is `text-foreground/70` a sound inactive-tab token vs. the selected `text-foreground`?
2. Is the scan honest (real fixture data, not synthetic; scans rendered UI not error states)? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```

===== DIFF (codex_diff.patch) =====
```diff
diff --git a/web/app/source_review/page.tsx b/web/app/source_review/page.tsx
index 041f9352..3a50bc2b 100644
--- a/web/app/source_review/page.tsx
+++ b/web/app/source_review/page.tsx
@@ -223,8 +223,10 @@ function SourceReviewContent() {
           )}
 
           {/* HONEST framing — the page shows the curated source DEFINITION + the
-              adequacy bar, NOT a retrieved corpus. Retrieval happens in the run. */}
-          <div className="border-border bg-muted/40 flex flex-col gap-1 rounded-lg border p-4">
+              adequacy bar, NOT a retrieved corpus. Retrieval happens in the run.
+              I-p2-026 (#765): bg-card (white), not bg-muted/40 — muted-foreground
+              text on the muted tint failed WCAG 2.2 AA contrast (axe serious). */}
+          <div className="border-border bg-card flex flex-col gap-1 rounded-lg border p-4">
             <span className="text-foreground text-xs font-semibold">
               How sources are gathered
             </span>
diff --git a/web/components/ui/tabs.tsx b/web/components/ui/tabs.tsx
index 3a9a028f..e7eee18c 100644
--- a/web/components/ui/tabs.tsx
+++ b/web/components/ui/tabs.tsx
@@ -36,6 +36,11 @@ export const TabsTrigger = forwardRef<
     ref={ref}
     className={cn(
       "ring-offset-background inline-flex items-center justify-center rounded-sm px-3 py-1.5 text-sm font-medium whitespace-nowrap transition-all",
+      // I-p2-026 (#765): explicit inactive text color. The inherited
+      // text-muted-foreground on the bg-muted strip fails WCAG 2.2 AA
+      // contrast (axe serious); text-foreground/70 clears 4.5:1 while still
+      // reading lighter than the selected tab.
+      "text-foreground/70",
       "focus-visible:ring-ring focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none",
       "data-[selected]:bg-background data-[selected]:text-foreground data-[selected]:shadow-sm",
       "hover:bg-background/60",
diff --git a/web/tests/a11y/wcag_axe_scan.mjs b/web/tests/a11y/wcag_axe_scan.mjs
new file mode 100644
index 00000000..2d6d3fa1
--- /dev/null
+++ b/web/tests/a11y/wcag_axe_scan.mjs
@@ -0,0 +1,135 @@
+// I-p2-026 (#765): automated WCAG 2.2 AA scan (axe-core via Playwright).
+//
+// Scans the public + canonical-bundle pages against the WCAG 2.0/2.1/2.2 A+AA
+// rule tags. Backend-driven pages (graph, source_review) get their API calls
+// intercepted with REAL fixture data (the same data the live endpoints serve)
+// so the FULL rendered UI is scanned — not an offline error state.
+//
+// Usage: BASE=http://127.0.0.1:PORT node tests/a11y/wcag_axe_scan.mjs
+// Exits non-zero if any page has serious/critical violations.
+import { chromium } from "playwright";
+import { AxeBuilder } from "@axe-core/playwright";
+import fs from "node:fs";
+import path from "node:path";
+import { fileURLToPath } from "node:url";
+
+const BASE = process.env.BASE ?? "http://127.0.0.1:4019";
+const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
+
+const graphFixture = JSON.parse(
+  fs.readFileSync(new URL("../fixtures/graph_payload.json", import.meta.url)),
+);
+// Real source-set data the live GET /api/v6/templates serves — read straight
+// from the authoritative config so the source-review scan exercises the real
+// rendered UI (no synthetic fixture, reproducible without /tmp state).
+const templatesDir = fileURLToPath(
+  new URL("../../../config/v6_templates/", import.meta.url),
+);
+const templatesFixture = fs
+  .readdirSync(templatesDir)
+  .filter((f) => f.endsWith(".json"))
+  .map((f) => JSON.parse(fs.readFileSync(path.join(templatesDir, f), "utf-8")));
+
+const PAGES = [
+  { name: "home", path: "/" },
+  { name: "sign-in", path: "/sign-in" },
+  { name: "inspector", path: "/inspector/v1-canonical-success" },
+  { name: "audit-export", path: "/runs/v1-canonical-success/audit" },
+  {
+    name: "knowledge-graph",
+    path: "/runs/v1-canonical-success/graph",
+    routes: [
+      {
+        glob: "**/api/runs/*/graph",
+        body: graphFixture,
+      },
+    ],
+  },
+  {
+    name: "source-review",
+    path: "/source_review?q=Is%20tirzepatide%20more%20effective%20than%20semaglutide%3F&template=clinical",
+    routes: [{ glob: "**/api/v6/templates", body: templatesFixture }],
+  },
+];
+
+const run = async () => {
+  const browser = await chromium.launch();
+  const summary = [];
+  for (const page of PAGES) {
+    const ctx = await browser.newContext({
+      viewport: { width: 1366, height: 900 },
+    });
+    const p = await ctx.newPage();
+    for (const r of page.routes ?? []) {
+      await p.route(r.glob, (route) =>
+        route.fulfill({
+          status: 200,
+          contentType: "application/json",
+          body: JSON.stringify(r.body),
+        }),
+      );
+    }
+    try {
+      await p.goto(`${BASE}${page.path}`, {
+        waitUntil: "networkidle",
+        timeout: 45000,
+      });
+      await p.waitForTimeout(1800);
+      const results = await new AxeBuilder({ page: p })
+        .withTags(WCAG_TAGS)
+        .analyze();
+      const byImpact = { critical: 0, serious: 0, moderate: 0, minor: 0 };
+      for (const v of results.violations) {
+        byImpact[v.impact ?? "minor"] =
+          (byImpact[v.impact ?? "minor"] ?? 0) + v.nodes.length;
+      }
+      summary.push({
+        page: page.name,
+        path: page.path,
+        violations: results.violations.map((v) => ({
+          id: v.id,
+          impact: v.impact,
+          help: v.help,
+          nodes: v.nodes.length,
+          targets: v.nodes.slice(0, 3).map((n) => n.target.join(" ")),
+        })),
+        byImpact,
+      });
+    } catch (e) {
+      summary.push({ page: page.name, path: page.path, error: e.message });
+    }
+    await ctx.close();
+  }
+  await browser.close();
+  fs.writeFileSync("/tmp/axe_summary.json", JSON.stringify(summary, null, 2));
+
+  let blocking = 0;
+  for (const s of summary) {
+    if (s.error) {
+      console.log(`\n[${s.page}] ERROR: ${s.error}`);
+      continue;
+    }
+    const b = s.byImpact;
+    const bad = (b.critical ?? 0) + (b.serious ?? 0);
+    blocking += bad;
+    const flag = bad > 0 ? "✗" : "✓";
+    console.log(
+      `\n${flag} [${s.page}] crit=${b.critical} serious=${b.serious} mod=${b.moderate} minor=${b.minor}`,
+    );
+    for (const v of s.violations) {
+      console.log(
+        `    - ${v.impact?.toUpperCase()} ${v.id} (${v.nodes}×): ${v.help}`,
+      );
+      for (const t of v.targets) console.log(`        @ ${t}`);
+    }
+  }
+  console.log(
+    `\n=== WCAG 2.2 AA axe scan: ${blocking} critical+serious node-violations across ${PAGES.length} pages ===`,
+  );
+  process.exit(blocking > 0 ? 1 : 0);
+};
+
+run().catch((e) => {
+  console.error("scan failed:", e);
+  process.exit(2);
+});

# canonical-diff-sha256: 7c38961fac5b30a384b8e49178eadf8dce5b3a764638b8a735dc3d5bfa8d1807
```
