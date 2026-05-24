# Codex DIFF review — I-p2-051 (#849): Dashboard CJK-date fix + elevation

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings; reserve P0/P1 for real execution risks.
APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

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
- Visual `-i` APPROVE (iter 1: desktop A / mobile A- / empty A) on mock-rendered states.
- canonical-diff-sha256: 159334464d2ad6beac3b280cdffa2dec6fc8e90be8612e44b45190253232c2df

## What the diff does (dashboard/page.tsx + components/recent_runs_strip.tsx) — 2 files, +9/-4
1. formatWhen (both files): `toLocaleDateString(undefined, …)` → `toLocaleDateString("en-CA", …)`
   — fixes CJK dates ("2026年5月21日") on a non-English host; deterministic English dates.
2. dashboard runs-list <ul>: added `bg-card shadow-card overflow-hidden` (brand elevation).
3. dashboard run-row title: `line-clamp-1` → `line-clamp-2` (Codex visual P2; mobile scanability).

## Verification
- typecheck clean; prettier ok; eslint 0 errors. The real listCompletedRuns fetch, verdict
  logic, and testids (dashboard-page/dashboard-start-run/runs-list/run-row-*) unchanged.

## Review focus
- "en-CA" is a valid BCP-47 locale (deterministic English-Canada dates); no behavior risk.
- No fabricated SHIPPED data (the fixture used to render for audit is NOT in the diff). Tokens
  only; brand #c8102e. recent_runs_strip is Home's component — same bug, same fix, in scope as
  the date-locale-class fix.

## The diff
```diff
diff --git a/web/app/components/recent_runs_strip.tsx b/web/app/components/recent_runs_strip.tsx
index 350da12b..ea99b41a 100644
--- a/web/app/components/recent_runs_strip.tsx
+++ b/web/app/components/recent_runs_strip.tsx
@@ -22,7 +22,9 @@ function formatFinished(value: string | null): string | null {
   if (!value) return null;
   const d = new Date(value);
   if (Number.isNaN(d.getTime())) return null; // tolerate malformed finished_at
-  return d.toLocaleDateString(undefined, {
+  // I-p2-051 (#849): force en-CA — `undefined` uses the host locale, which
+  // rendered CJK dates on a non-English server. Deterministic English dates.
+  return d.toLocaleDateString("en-CA", {
     month: "short",
     day: "numeric",
   });
diff --git a/web/app/dashboard/page.tsx b/web/app/dashboard/page.tsx
index 0393370c..3891d3ed 100644
--- a/web/app/dashboard/page.tsx
+++ b/web/app/dashboard/page.tsx
@@ -26,7 +26,10 @@ function formatWhen(value: string | null | undefined): string | null {
   if (!value) return null;
   const d = new Date(value);
   if (Number.isNaN(d.getTime())) return null;
-  return d.toLocaleDateString(undefined, {
+  // I-p2-051 (#849): force en-CA — `undefined` uses the runtime/system locale,
+  // which rendered CJK dates ("2026年5月21日") on a non-English server. The demo
+  // is Canadian/English; dates must be deterministic regardless of host locale.
+  return d.toLocaleDateString("en-CA", {
     month: "short",
     day: "numeric",
     year: "numeric",
@@ -141,7 +144,7 @@ export default function DashboardPage() {
 
       {state.kind === "ok" && state.runs.length > 0 ? (
         <ul
-          className="border-border divide-border divide-y rounded-xl border"
+          className="border-border divide-border bg-card shadow-card divide-y overflow-hidden rounded-xl border"
           data-testid="runs-list"
         >
           {state.runs.map((run) => {
@@ -155,7 +158,7 @@ export default function DashboardPage() {
                   className="hover:bg-muted/40 focus-visible:ring-ring/70 flex items-center justify-between gap-4 px-4 py-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                 >
                   <div className="flex min-w-0 flex-col gap-1">
-                    <span className="text-foreground line-clamp-1 text-sm font-medium">
+                    <span className="text-foreground line-clamp-2 text-sm font-medium">
                       {run.question || run.run_id}
                     </span>
                     <span className="text-muted-foreground text-xs">

# canonical-diff-sha256: 159334464d2ad6beac3b280cdffa2dec6fc8e90be8612e44b45190253232c2df

```
