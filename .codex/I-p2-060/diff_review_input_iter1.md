# Codex DIFF review — I-p2-060 (#867): Offline Inspector dropzone polish

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings; reserve P0/P1 for real risks. APPROVE iff
zero NOVEL P0 + zero continuing P0 + zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Already gated
- Visual `-i` APPROVE iter-1 (default desktop A / mobile A-).
- canonical-diff-sha256: fc59b62b0bf4337b823a7a5a4c3df55eefa7e1268abee64d57ed52ea77cbfabc

## What the diff does (2 files; presentation only)
1. app/inspector/offline/page.tsx — dropzone div restyled (icon + drag-active brand-tint + hover +
   motion + rounded-xl + loading/idle copy with UploadCloud/FileCheck2 icons); the raw
   bg-rose-500/text-rose-700 error block → the shared ErrorState component. Imports added
   (UploadCloud, FileCheck2, ErrorState).
2. docs tracker.

## Verification
- typecheck clean; eslint clean; prettier clean. Preserved: handleFile/onDrop/onInputChange/onKeyDown
  logic, loadBundleFromTarGz, the SHA-256/GPG honest copy, and testids (inspector-offline,
  inspector-offline-dropzone, inspector-offline-file-input, inspector-offline-error).

## Review focus
- The dropzone is still a keyboard-operable role=button (tabIndex/onKeyDown Enter/Space) + the
  hidden file input is intact — confirm the icon/copy change didn't drop the a11y affordances or
  the testid the e2e uses. ErrorState message is the loader's code:message (specific, not generic).

## The full diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index 87906443..c4128fec 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -201,6 +201,17 @@ Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Co
   ledger + integrity manifest tables made RESPONSIVE — dense table on sm+, stacked cards on mobile
   so the abort reason / threshold / full SHA-256 are fully readable, not clipped (Codex iter-1 P1).
 
+- **Offline Inspector** (#867, I-p2-060): **default desktop A / mobile A-** (Codex visual iter-1
+  APPROVE). The disconnected-reviewer entry (drop a signed `.tar.gz` → SHA-256-verified + rendered
+  in-browser, no backend/GPU); the LOADED state reuses the S-tier InspectorView (#833). Assess-first:
+  the plain text dropzone + a raw `bg-rose-500` error block → a crafted drop zone (UploadCloud icon,
+  drag-active brand-tint, hover, motion, `rounded-xl`, a "Verifying bundle… checking SHA-256"
+  loading state) + the shared `ErrorState` (tokens). Honest SHA-256-checked / GPG-out-of-scope copy
+  preserved.
+
+**With Inspector ✓, the knowledge graph, audit/export, and offline inspector at the A bar, every
+production page (public + cred-gated journey + secondary) has now passed the dual Codex gate.**
+
 **The full cred-gated journey is now at the A bar** (Dashboard A/A-/A · Benchmark A/A-/A-/A-/A ·
 Memory A/A-/A · Compare A/A/A/A · Source Review S-/A++/A+ · Plan A/A/A/A- · Run progress A/A/A),
 each rendered locally (seeded session + route-mocked fixture, visual-audit-only) under the dual
diff --git a/web/app/inspector/offline/page.tsx b/web/app/inspector/offline/page.tsx
index e7b67225..015ba450 100644
--- a/web/app/inspector/offline/page.tsx
+++ b/web/app/inspector/offline/page.tsx
@@ -3,9 +3,11 @@
 // No GPU, no backend, no API call.
 "use client";
 
+import { FileCheck2, UploadCloud } from "lucide-react";
 import { useState } from "react";
 
 import { InspectorView } from "@/app/inspector/[runId]/inspector_view";
+import { ErrorState } from "@/components/states/state_kit";
 import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
 import {
   BundleClientLoaderError,
@@ -96,13 +98,40 @@ export default function InspectorOfflinePage() {
             onClick={() =>
               document.getElementById("inspector-offline-input")?.click()
             }
-            className={`border-border focus-visible:ring-ring flex min-h-32 cursor-pointer items-center justify-center rounded border-2 border-dashed px-6 py-8 text-center text-sm focus-visible:ring-2 focus-visible:outline-none ${
-              dragOver ? "bg-muted/60" : "bg-muted/20"
+            className={`focus-visible:ring-ring/70 ease-standard flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-8 text-center transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none ${
+              dragOver
+                ? "border-primary/50 bg-primary/5"
+                : "border-border bg-muted/20 hover:border-primary/30 hover:bg-muted/40"
             }`}
           >
-            {loading
-              ? "Loading bundle…"
-              : "Drop bundle.tar.gz here or press Enter to pick a file"}
+            {loading ? (
+              <>
+                <FileCheck2
+                  aria-hidden
+                  className="text-muted-foreground h-7 w-7 animate-pulse motion-reduce:animate-none"
+                />
+                <span className="text-foreground text-sm font-medium">
+                  Verifying bundle…
+                </span>
+                <span className="text-muted-foreground text-xs">
+                  Checking SHA-256 of every file against the manifest
+                </span>
+              </>
+            ) : (
+              <>
+                <UploadCloud
+                  aria-hidden
+                  className={`h-7 w-7 ${dragOver ? "text-primary" : "text-muted-foreground"}`}
+                />
+                <span className="text-foreground text-sm font-medium">
+                  {dragOver ? "Drop to verify" : "Drop a signed bundle"}
+                </span>
+                <span className="text-muted-foreground text-xs">
+                  <code className="font-mono">.tar.gz</code> — or press Enter /
+                  click to pick a file
+                </span>
+              </>
+            )}
           </div>
           <input
             id="inspector-offline-input"
@@ -113,13 +142,8 @@ export default function InspectorOfflinePage() {
             onChange={onInputChange}
           />
           {error ? (
-            <div
-              data-testid="inspector-offline-error"
-              role="alert"
-              className="rounded border border-rose-500/40 bg-rose-500/5 p-3 text-sm text-rose-700 dark:text-rose-300"
-            >
-              <strong className="block">Bundle could not be loaded</strong>
-              <code className="mt-1 block text-xs">{error}</code>
+            <div data-testid="inspector-offline-error">
+              <ErrorState title="Bundle could not be loaded" message={error} />
             </div>
           ) : null}
         </CardContent>

# canonical-diff-sha256: fc59b62b0bf4337b823a7a5a4c3df55eefa7e1268abee64d57ed52ea77cbfabc

```
