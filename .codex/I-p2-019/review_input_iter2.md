# Codex DESIGN+DIFF review — I-p2-019 (#758): knowledge-graph page (the snowball)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `dd13cabc97ebcb4a5cfb71fbfa6950f54a93f1d0d329071fe0c8b9589e08e660`. web/ only, 120-line diff (under 200-LOC cap). MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## iter-1 → iter-2 delta (your iter-1 P1, fixed)
You flagged: `web/tests/e2e/graph_page_smoke.spec.ts:64` still asserted the removed copy "Failed to load graph". **Fixed** — that 404→error test now asserts the #750 ErrorState title "Couldn't load the graph" + the friendly not-found message "This run was not found". Verified by grep that this was the ONLY staled assertion (the other 4 tests assert `graph-page`/`claim-graph` testids + export downloads, all unaffected by chromeless + relabel). The test file is now part of the canonical diff (hence the new hash + 120 lines).

## Context
#758 = "Page: Knowledge-graph (the snowball)". The page `web/app/runs/[runId]/graph/page.tsx` was ALREADY feature-complete from #751 (I-p2-012): cytoscape ClaimGraph + AccessibleGraphList (a11y fallback) + GraphExportButtons (PNG/JSON) + 2-hop snowball expansion + node search + Open-Inspector deep-link. This PR is the design-system + landmark + honesty delta only — NOT a rebuild.

## Diff (2 files)
1. `web/components/app_shell_gate.tsx`: added `CHROMELESS_PATTERNS = [/^\/runs\/[^/]+\/graph$/]` + `isChromeless()` helper. The graph page renders its OWN `<header>` (with "Back to Inspector") + `<main data-testid="graph-page">`. Before this, AppShellGate wrapped it in AppShell → **G1 double-header + G6 nested-main**. Now the route is chromeless and owns its full viewport, exactly like `/` and `/sign-in`.
2. `web/app/runs/[runId]/graph/page.tsx`:
   - **G2**: header dev-language `POLARIS — F-snowball` → `Knowledge graph` / `How this run's claims + sources connect`.
   - **#750 swap**: hand-rolled error banner (`border-destructive text-destructive`) + hand-rolled spinner (no motion-reduce) → `ErrorState` + `LoadingState` from the #750 kit (design tokens + role=alert/status + motion-reduce honored).
   - **G4 (raw-error leak)**: `.catch` was `setError(e.message)` → leaked `getRunGraph(demo-1) HTTP 500: Internal Server Error` to the user. Now maps to friendly copy ("This run was not found…" / "We couldn't load the knowledge graph right now…"), mirroring the existing `/runs/[runId]` G4 fix.

## Files I have ALSO checked and they're clean
- `web/app/runs/[runId]/graph/components/{claim_graph,accessible_graph_list,graph_export_buttons,snowball,use_graph_state}.tsx` — unchanged; the page only re-labels its header + swaps error/loading. GraphSurface (the actual graph UI) is untouched.
- `web/components/states/state_kit.tsx` — ErrorState(title,message)/LoadingState(label,rows) signatures match the call sites (verified against #755/#757 usage).
- `web/components/app_shell.tsx` — unchanged; AppShellGate is the only gate, single landmark provider for non-chromeless routes.
- Chromeless regex tested against `/runs/demo-1/graph` (matches) and `/runs/demo-1` (does NOT match — the run-detail page stays inside AppShell, correct).

## Claude visual audit (standalone harness @1366, NOT next dev)
Rendered `/runs/demo-1/graph` in the standalone server (no v6 backend → getRunGraph 500 → error path):
- Chromeless verified: `grep -c 'aria-label="Primary"'` = 0 (no global nav), `<header` count = 1 (own header only). No double-header, no nested-main.
- Header reads "KNOWLEDGE GRAPH / How this run's claims + sources connect" + "Back to Inspector" button. No dev-language.
- Error path shows the #750 ErrorState card: "Couldn't load the graph" + friendly "We couldn't load the knowledge graph right now. Please retry shortly." (no HTTP 500 / fn-name leak). Design-token red-tint bordered card, role=alert.

## Review focus
1. Is the chromeless regex correct + scoped (only `/runs/<id>/graph`, not `/runs/<id>` or `/runs/<id>/graph/foo`)? Any route that should NOT be chromeless now caught?
2. ErrorState/LoadingState swaps clean (no unused imports, props match)?
3. G4 error mapping honest (404→not-found, else→generic-retry; no swallowed error)?
4. Any P0/P1 (landmark regression, a11y regression, behavior change to GraphSurface).

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```

===== ACTUAL DIFF (codex_diff.patch, canonical body) =====
```diff
diff --git a/web/app/runs/[runId]/graph/page.tsx b/web/app/runs/[runId]/graph/page.tsx
index a0446f6e..e5a20cad 100644
--- a/web/app/runs/[runId]/graph/page.tsx
+++ b/web/app/runs/[runId]/graph/page.tsx
@@ -4,6 +4,7 @@ import Link from "next/link";
 import { useRouter } from "next/navigation";
 import { use, useEffect, useRef, useState } from "react";
 
+import { ErrorState, LoadingState } from "@/components/states/state_kit";
 import { Button } from "@/components/ui/button";
 import { Input } from "@/components/ui/input";
 import { getRunGraph, type GraphPayload } from "@/lib/api";
@@ -32,7 +33,16 @@ export default function GraphPage({ params }: GraphPageProps) {
         if (!cancelled) setPayload(p);
       })
       .catch((e: Error) => {
-        if (!cancelled) setError(e.message);
+        // I-p2-019 (#758): map raw API errors to friendly copy (mirrors the
+        // /runs/[runId] G4 fix) — never leak "HTTP 500" / fn names to the user.
+        if (!cancelled) {
+          const raw = e.message.toLowerCase();
+          setError(
+            raw.includes("404")
+              ? "This run was not found. Check the URL or start a new run."
+              : "We couldn't load the knowledge graph right now. Please retry shortly.",
+          );
+        }
       });
     return () => {
       cancelled = true;
@@ -44,11 +54,12 @@ export default function GraphPage({ params }: GraphPageProps) {
       <header className="border-border bg-background border-b">
         <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
           <div className="flex flex-col">
+            {/* I-p2-019 (#758): G2 — dropped the "F-snowball" dev-language. */}
             <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
-              POLARIS — F-snowball
+              Knowledge graph
             </span>
             <span className="text-foreground text-base font-semibold">
-              Claim graph: {runId}
+              How this run&apos;s claims + sources connect
             </span>
           </div>
           <Button
@@ -65,26 +76,14 @@ export default function GraphPage({ params }: GraphPageProps) {
         data-testid="graph-page"
         className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-6 py-6"
       >
+        {/* I-p2-019 (#758): #750 ErrorState/LoadingState (design tokens +
+            role=alert/status + motion-reduce) instead of hand-rolled. */}
         {error && (
-          <div
-            role="alert"
-            className="border-destructive text-destructive rounded-md border p-4"
-          >
-            Failed to load graph: {error}
-          </div>
+          <ErrorState title="Couldn't load the graph" message={error} />
         )}
 
         {!payload && !error && (
-          <div
-            role="status"
-            className="text-muted-foreground flex items-center gap-2"
-          >
-            <span
-              aria-hidden
-              className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent"
-            />
-            Loading graph for run {runId}…
-          </div>
+          <LoadingState label="Loading the knowledge graph…" rows={6} />
         )}
 
         {payload && <GraphSurface payload={payload} runId={runId} />}
diff --git a/web/components/app_shell_gate.tsx b/web/components/app_shell_gate.tsx
index 7c4c3650..28bf9e95 100644
--- a/web/components/app_shell_gate.tsx
+++ b/web/components/app_shell_gate.tsx
@@ -21,9 +21,22 @@ interface AppShellGateProps {
 //                 nav is auth-gated anyway, so it must not show pre-login.
 const CHROMELESS_ROUTES = new Set(["/", "/sign-in"]);
 
+// I-p2-019 (#762): the claim-graph drill-down (/runs/<id>/graph) is a focused
+// full-screen view that renders its OWN header (with "Back to Inspector") +
+// <main>. It must be chromeless too, else AppShell double-wraps it (G1 double
+// header + G6 nested main).
+const CHROMELESS_PATTERNS = [/^\/runs\/[^/]+\/graph$/];
+
+function isChromeless(pathname: string): boolean {
+  return (
+    CHROMELESS_ROUTES.has(pathname) ||
+    CHROMELESS_PATTERNS.some((re) => re.test(pathname))
+  );
+}
+
 export function AppShellGate({ children }: AppShellGateProps) {
   const pathname = usePathname();
-  if (CHROMELESS_ROUTES.has(pathname)) {
+  if (isChromeless(pathname)) {
     return <>{children}</>;
   }
   return <AppShell>{children}</AppShell>;
diff --git a/web/tests/e2e/graph_page_smoke.spec.ts b/web/tests/e2e/graph_page_smoke.spec.ts
index b4cb65d6..5c9b9990 100644
--- a/web/tests/e2e/graph_page_smoke.spec.ts
+++ b/web/tests/e2e/graph_page_smoke.spec.ts
@@ -61,6 +61,10 @@ test.describe("Claim graph page (I-snowball-006)", () => {
       route.fulfill({ status: 404, body: "run not found" }),
     );
     await page.goto("/runs/no_such_run/graph");
-    await expect(page.getByRole("alert")).toContainText("Failed to load graph");
+    // I-p2-019 (#758): error UI is now the #750 ErrorState (role=alert, title
+    // + friendly message). 404 → not-found copy; raw "HTTP 404" is not leaked.
+    const alert = page.getByRole("alert");
+    await expect(alert).toContainText("Couldn't load the graph");
+    await expect(alert).toContainText("This run was not found");
   });
 });

# canonical-diff-sha256: dd13cabc97ebcb4a5cfb71fbfa6950f54a93f1d0d329071fe0c8b9589e08e660
```

===== FULL FILE: web/app/runs/[runId]/graph/page.tsx =====
```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";

import { ErrorState, LoadingState } from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getRunGraph, type GraphPayload } from "@/lib/api";

import type cytoscape from "cytoscape";

import { AccessibleGraphList } from "./components/accessible_graph_list";
import { ClaimGraph } from "./components/claim_graph";
import { GraphExportButtons } from "./components/graph_export_buttons";
import { snowballNeighbors } from "./components/snowball";
import { useGraphState } from "./components/use_graph_state";

interface GraphPageProps {
  params: Promise<{ runId: string }>;
}

export default function GraphPage({ params }: GraphPageProps) {
  const { runId } = use(params);
  const [payload, setPayload] = useState<GraphPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getRunGraph(runId)
      .then((p) => {
        if (!cancelled) setPayload(p);
      })
      .catch((e: Error) => {
        // I-p2-019 (#758): map raw API errors to friendly copy (mirrors the
        // /runs/[runId] G4 fix) — never leak "HTTP 500" / fn names to the user.
        if (!cancelled) {
          const raw = e.message.toLowerCase();
          setError(
            raw.includes("404")
              ? "This run was not found. Check the URL or start a new run."
              : "We couldn't load the knowledge graph right now. Please retry shortly.",
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [runId]);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            {/* I-p2-019 (#758): G2 — dropped the "F-snowball" dev-language. */}
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              Knowledge graph
            </span>
            <span className="text-foreground text-base font-semibold">
              How this run&apos;s claims + sources connect
            </span>
          </div>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href={`/inspector/${runId}`} />}
          >
            Back to Inspector
          </Button>
        </div>
      </header>

      <main
        data-testid="graph-page"
        className="mx-auto flex w-full max-w-7xl flex-1 flex-col gap-4 px-6 py-6"
      >
        {/* I-p2-019 (#758): #750 ErrorState/LoadingState (design tokens +
            role=alert/status + motion-reduce) instead of hand-rolled. */}
        {error && (
          <ErrorState title="Couldn't load the graph" message={error} />
        )}

        {!payload && !error && (
          <LoadingState label="Loading the knowledge graph…" rows={6} />
        )}

        {payload && <GraphSurface payload={payload} runId={runId} />}
      </main>
    </div>
  );
}

interface GraphSurfaceProps {
  payload: GraphPayload;
  runId: string;
}

function GraphSurface({ payload, runId }: GraphSurfaceProps) {
  const [state, adjacency, actions] = useGraphState(payload);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [cy, setCy] = useState<cytoscape.Core | null>(null);
  const inspectorHref = (id: string) =>
    `/inspector/${runId}?${new URLSearchParams({ focused_node: id }).toString()}`;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          ref={searchInputRef}
          type="search"
          placeholder="Search nodes (press / to focus)…"
          value={state.search_query}
          onChange={(e) => actions.setSearchQuery(e.target.value)}
          className="max-w-md"
          aria-label="Search graph nodes"
        />
        <span className="text-muted-foreground text-xs">
          {state.visible_node_ids.size}/{payload.elements.nodes.length} visible
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={!state.selected_node_id}
          onClick={() => {
            if (state.selected_node_id)
              router.push(inspectorHref(state.selected_node_id));
          }}
        >
          Open Inspector
        </Button>
        <Button
          variant="outline"
          size="sm"
          disabled={!state.selected_node_id}
          onClick={() => {
            if (!state.selected_node_id) return;
            actions.setSnowballHighlight(
              snowballNeighbors(payload, state.selected_node_id, 2),
            );
          }}
        >
          Expand snowball (2 hops)
        </Button>
        {state.snowball_highlight_ids && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => actions.setSnowballHighlight(null)}
          >
            Clear ({state.snowball_highlight_ids.size} nodes)
          </Button>
        )}
        <GraphExportButtons cy={cy} payload={payload} />
      </div>
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <ClaimGraph
          payload={payload}
          selectedNodeId={state.selected_node_id}
          searchQuery={state.search_query}
          snowballHighlightIds={state.snowball_highlight_ids}
          setSelectedNodeId={actions.setSelectedNodeId}
          onCyReady={setCy}
        />
        <AccessibleGraphList
          payload={payload}
          state={state}
          adjacency={adjacency}
          runId={runId}
          searchInputRef={searchInputRef}
          setSelectedNodeId={actions.setSelectedNodeId}
        />
      </div>
    </div>
  );
}
```

===== FULL FILE: web/tests/e2e/graph_page_smoke.spec.ts =====
```ts
/**
 * I-snowball-006 — Playwright smoke for /runs/[runId]/graph.
 *
 * Mocks the backend `/api/runs/<id>/graph` endpoint with a deterministic
 * fixture so the test is hermetic and does not depend on a live FastAPI
 * server.
 */

import { test, expect } from "@playwright/test";
import fixture from "../fixtures/graph_payload.json";

test.describe("Claim graph page (I-snowball-006)", () => {
  test.beforeEach(async ({ page }) => {
    await page.route("**/api/runs/*/graph", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
    });
  });

  test("loads page and renders graph canvas", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    await expect(page.getByTestId("graph-page")).toBeVisible();
    await expect(page.getByTestId("claim-graph")).toBeVisible();
  });

  test("search filters AccessibleGraphList", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    await page.getByPlaceholder(/Search nodes/).fill("safety");
    await expect(
      page.getByTestId("graph-list-row-section:safety"),
    ).toBeVisible();
    await expect(
      page.getByTestId("graph-list-row-frame:efficacy_endpoint"),
    ).toHaveCount(0);
  });

  test("PNG download triggers", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    // Wait for cytoscape mount (Download PNG enables once cy is ready).
    const pngButton = page.getByTestId("graph-export-png");
    await expect(pngButton).toBeEnabled({ timeout: 10_000 });
    const downloadPromise = page.waitForEvent("download");
    await pngButton.click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.png$/);
  });

  test("JSON download triggers", async ({ page }) => {
    await page.goto("/runs/test_fixture_001/graph");
    const downloadPromise = page.waitForEvent("download");
    await page.getByTestId("graph-export-json").click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.json$/);
  });

  test("404 backend → error UI", async ({ page }) => {
    await page.route("**/api/runs/no_such_run/graph", (route) =>
      route.fulfill({ status: 404, body: "run not found" }),
    );
    await page.goto("/runs/no_such_run/graph");
    // I-p2-019 (#758): error UI is now the #750 ErrorState (role=alert, title
    // + friendly message). 404 → not-found copy; raw "HTTP 404" is not leaked.
    const alert = page.getByRole("alert");
    await expect(alert).toContainText("Couldn't load the graph");
    await expect(alert).toContainText("This run was not found");
  });
});
```
