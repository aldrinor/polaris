# Codex DIFF review — I-p2-040 (#827): pin_replay empty state → EmptyState kit. Iter 1 of 5.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the doc is force-APPROVE'd on remaining non-P0/P1 findings.
- If you're holding back a P1 for the next round — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## You APPROVE'd the brief. This is the one-file diff.

Routes pin_replay's hand-rolled empty `<p>` through the shared `EmptyState` kit (#750) —
icon (History) + title + description + a `/intake` CTA — matching the 8 kit-using pages;
keeps the heading (jargon-killed "query"→"question") + an intro explaining the feature; the
populated view (SnapshotCard/timeseries) is untouched. `data-testid="pin-replay-empty"` kept.

Verified: next build compiled; eslint + prettier clean; local screenshot shows the structured
empty state (no more void). pin_replay_g1_g8 asserts no empty-state copy → no spec break.

## Review focus
1. Correct EmptyState usage (props match the kit signature).
2. No regression to the populated branch; imports correct; "use client" intact.
3. Any NEW issue.

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

## The diff
```diff
diff --git a/web/app/pin_replay/page.tsx b/web/app/pin_replay/page.tsx
index 0629c42c..9d13252e 100644
--- a/web/app/pin_replay/page.tsx
+++ b/web/app/pin_replay/page.tsx
@@ -1,7 +1,11 @@
 "use client";
 
+import { History } from "lucide-react";
+import Link from "next/link";
 import { useState } from "react";
 
+import { EmptyState } from "@/components/states/state_kit";
+import { Button } from "@/components/ui/button";
 import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
 import { DEMO_PIN_REGISTRY, type PinSnapshot } from "@/lib/pin_replay_demo";
 import { detectRegressions } from "@/lib/pin_regression";
@@ -73,21 +77,35 @@ function SnapshotCard({
 }
 
 function EmptyPinReplay() {
-  // I-cd-029 (#619): /pin_replay rebuild — empty-state copy. G1+G6 fix:
-  // <main> dropped (AppShell provides it). G2 fix: removed Issue id
-  // breadcrumbs from user-visible copy.
+  // I-cd-029 (#619): /pin_replay rebuild. I-p2-040 (#827): the empty state now
+  // routes through the shared EmptyState kit (#750) — matching the 8 other pages
+  // that use it — instead of a bare <p> that read as a void; + an intro that
+  // explains the feature and a CTA so the page is informative, not barren.
+  // "query"→"question" (jargon kill).
   return (
     <section
       data-testid="pin-replay-empty"
       className="mx-auto max-w-5xl px-6 py-8"
     >
-      <h1 className="text-2xl font-semibold tracking-tight">
-        Pin replay — same query on different dates
+      <h1 className="text-foreground text-2xl font-semibold tracking-tight">
+        Pin replay — same question on different dates
       </h1>
-      <p className="text-muted-foreground mt-4 text-sm">
-        No pin data available yet. Open a completed research run and the
-        timeseries of its pin snapshots will render here.
+      <p className="text-muted-foreground mt-1 mb-6 max-w-2xl text-sm">
+        Pin a completed run, then re-run the same question later — POLARIS lines
+        up the snapshots so you can see how the evidence and the verified answer
+        shift over time.
       </p>
+      <EmptyState
+        icon={History}
+        title="No pinned runs yet"
+        description="Run a research question and pin its result to start a timeline here."
+        action={
+          <Button
+            nativeButton={false}
+            render={<Link href="/intake">Ask a question</Link>}
+          />
+        }
+      />
     </section>
   );
 }

```
