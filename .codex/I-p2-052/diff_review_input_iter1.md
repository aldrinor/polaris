# Codex DIFF review — I-p2-052 (#851): Benchmark S-rebuild

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
- Visual `-i` APPROVE iter-2 (desktop A / mobile A- / empty A- / error A- / list A).
- canonical-diff-sha256: ebd980f899b170e8f66eac2c78ce12ad46be1deb6e76471d13cef3ab3ede5ec6

## What the diff does (2 files: app/benchmark/page.tsx + components/benchmark_board.tsx)
1. States: replaced bespoke amber/rose dev-language cards (exposed POLARIS_BENCHMARK_RESULTS_DIR
   + scripts/run_benchmark.py) with the shared state-kit (EmptyState/ErrorState/LoadingState),
   tokens only. Preserved testids benchmark-loading / -no-results-dir / -empty / -error /
   -loading-scoreboard by wrapping the kit components in a div carrying the testid.
2. Loaded view: headline tally; brand POLARIS column; tabular-nums; tone_class now returns
   --verified for the strict winner (was raw text-emerald-700). Added POLARIS_ONLY_DIMENSIONS set
   (refusal_correctness, auditability) → "POLARIS-only" tag + dash for null peers. Added a mobile
   stacked per-dimension block (sm:hidden) so the 3rd peer column isn't clipped; desktop keeps the
   table (hidden sm:block).
3. page.tsx: intro reworded off a hardcoded "scores 1.0" claim to a capability claim.

## Verification
- typecheck clean; prettier ok. State machine (loading_health → no_results_dir/no_benchmarks/
  benchmark_list → loading_scoreboard → loaded/error) unchanged; the real getBenchmarkHealth/
  getBenchmarkScoreboard fetches unchanged; "BEAT-BOTH benchmark" H1 (e2e-asserted) unchanged.

## Review focus
- testid preservation across the state refactor (e2e benchmark.spec asserts benchmark-page +
  /BEAT-BOTH benchmark/ + benchmark-no-results-dir|benchmark-empty|benchmark-list visibility).
- No fabricated SHIPPED data (the fixture used to render for the visual audit is NOT in the diff;
  null/dash handling is honest). tone_class: null score → muted, no populated peers → neutral
  (can't claim "leads" with no peer) — verify the logic reads correctly.
- Mobile/desktop dual-render duplicates the row mapping — confirm no key collisions / both use the
  same module-level tone_class + format_pct.

## The diff
```diff
diff --git a/web/app/benchmark/components/benchmark_board.tsx b/web/app/benchmark/components/benchmark_board.tsx
index dc59718f..44a54e68 100644
--- a/web/app/benchmark/components/benchmark_board.tsx
+++ b/web/app/benchmark/components/benchmark_board.tsx
@@ -1,7 +1,13 @@
 "use client";
 
+import { BarChart3 } from "lucide-react";
 import { useEffect, useState } from "react";
 
+import {
+  EmptyState,
+  ErrorState,
+  LoadingState,
+} from "@/components/states/state_kit";
 import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
 import { cn } from "@/lib/utils";
 import {
@@ -22,21 +28,29 @@ type BoardState =
   | { kind: "loaded"; benchmark_id: string; scoreboard: BenchmarkScoreboard }
   | { kind: "error"; message: string };
 
+// Refusal correctness + auditability are dimensions no commercial deep-research
+// product reports against — they're the POLARIS differentiators. We mark them so
+// a reviewer reads the table honestly (a blank peer cell = "not reported", not 0).
+const POLARIS_ONLY_DIMENSIONS: ReadonlySet<BenchmarkDimension> = new Set([
+  "refusal_correctness",
+  "auditability",
+]);
+
 function format_pct(v: number | null | undefined): string {
-  if (v === null || v === undefined) return "N/A";
+  if (v === null || v === undefined) return "—";
   return `${Math.round(v * 100)}%`;
 }
 
+// Winner = strictly ahead of every populated peer → brand "verified" token.
+// Behind = muted. Tie / no peers = default. (Tokens only, never raw palette.)
 function tone_class(score: number | null, peers: (number | null)[]): string {
-  if (score === null) return "text-muted-foreground italic";
+  if (score === null) return "text-muted-foreground/60";
   const populated = peers.filter((p): p is number => p !== null);
-  if (populated.length === 0) return "";
+  if (populated.length === 0) return "text-foreground";
   const max_peer = Math.max(...populated);
-  if (score > max_peer) {
-    return "text-emerald-700 dark:text-emerald-300 font-semibold";
-  }
+  if (score > max_peer) return "text-verified font-semibold";
   if (score < max_peer) return "text-muted-foreground";
-  return "";
+  return "text-foreground";
 }
 
 export function BenchmarkBoard() {
@@ -87,60 +101,47 @@ export function BenchmarkBoard() {
 
   if (state.kind === "loading_health") {
     return (
-      <Card data-testid="benchmark-loading">
-        <CardContent>Loading benchmark catalog…</CardContent>
-      </Card>
+      <div data-testid="benchmark-loading">
+        <LoadingState label="Loading benchmark catalog…" rows={4} />
+      </div>
     );
   }
 
+  // Both "no results directory configured" and "directory configured but empty"
+  // are, to a reviewer, the same fact: no scoreboard has been published to this
+  // workspace yet. Designed empty state (no internal env-var / script names).
   if (state.kind === "no_results_dir") {
     return (
-      <Card
-        data-testid="benchmark-no-results-dir"
-        className="border-amber-500/40 bg-amber-500/5"
-      >
-        <CardContent className="text-amber-700 dark:text-amber-300">
-          <strong className="block">Benchmark results not configured</strong>
-          POLARIS_BENCHMARK_RESULTS_DIR is not set in the live server&rsquo;s
-          environment. Run{" "}
-          <code className="bg-muted rounded px-1">
-            scripts/run_benchmark.py
-          </code>{" "}
-          first, then point the server at the results directory.
-        </CardContent>
-      </Card>
+      <div data-testid="benchmark-no-results-dir">
+        <EmptyState
+          icon={BarChart3}
+          title="No benchmark published yet"
+          description="When a head-to-head run completes, its dimension-by-dimension scoreboard — POLARIS against commercial deep-research products — appears here, reproducible byte-for-byte."
+        />
+      </div>
     );
   }
 
   if (state.kind === "no_benchmarks") {
     return (
-      <Card
-        data-testid="benchmark-empty"
-        className="border-amber-500/40 bg-amber-500/5"
-      >
-        <CardContent className="text-amber-700 dark:text-amber-300">
-          <strong className="block">No benchmark results yet</strong>
-          The results directory is configured (<code>{state.results_root}</code>
-          ) but no benchmark subdirs contain a scoreboard.json. Run{" "}
-          <code className="bg-muted rounded px-1">
-            scripts/run_benchmark.py
-          </code>
-          .
-        </CardContent>
-      </Card>
+      <div data-testid="benchmark-empty">
+        <EmptyState
+          icon={BarChart3}
+          title="No benchmark published yet"
+          description="This workspace has no published scoreboard. Once a head-to-head run completes, its results appear here, reproducible byte-for-byte."
+        />
+      </div>
     );
   }
 
   if (state.kind === "error") {
     return (
-      <Card
-        data-testid="benchmark-error"
-        className="border-rose-500/40 bg-rose-500/5"
-      >
-        <CardContent className="text-rose-700 dark:text-rose-300">
-          {state.message}
-        </CardContent>
-      </Card>
+      <div data-testid="benchmark-error">
+        <ErrorState
+          title="Couldn't load the benchmark catalog"
+          message={state.message}
+        />
+      </div>
     );
   }
 
@@ -148,7 +149,7 @@ export function BenchmarkBoard() {
     return (
       <Card data-testid="benchmark-list">
         <CardHeader>
-          <CardTitle className="text-lg">Available benchmarks</CardTitle>
+          <CardTitle className="text-lg">Published benchmarks</CardTitle>
         </CardHeader>
         <CardContent className="flex flex-col gap-2">
           {state.available.map((bench_id) => (
@@ -157,9 +158,12 @@ export function BenchmarkBoard() {
               type="button"
               onClick={() => load_benchmark(bench_id)}
               data-testid={`benchmark-link-${bench_id}`}
-              className="border-border bg-background hover:bg-muted text-foreground rounded-lg border px-4 py-2 text-left text-sm transition-colors"
+              className="border-border bg-background hover:border-primary/40 hover:bg-muted/40 focus-visible:ring-ring/70 ease-standard text-foreground flex items-center justify-between gap-3 rounded-lg border px-4 py-3 text-left font-mono text-sm transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none"
             >
-              {bench_id}
+              <span>{bench_id}</span>
+              <span className="text-muted-foreground text-xs">
+                View scoreboard →
+              </span>
             </button>
           ))}
         </CardContent>
@@ -169,93 +173,196 @@ export function BenchmarkBoard() {
 
   if (state.kind === "loading_scoreboard") {
     return (
-      <Card data-testid="benchmark-loading-scoreboard">
-        <CardContent>
-          Loading scoreboard for <code>{state.benchmark_id}</code>…
-        </CardContent>
-      </Card>
+      <div data-testid="benchmark-loading-scoreboard">
+        <LoadingState
+          label={`Loading scoreboard ${state.benchmark_id}…`}
+          rows={6}
+        />
+      </div>
     );
   }
 
   // state.kind === "loaded"
   const sb = state.scoreboard;
+  const total = sb.polaris_wins + sb.external_wins + sb.ties;
   return (
     <div data-testid="benchmark-board" className="flex flex-col gap-4">
+      {/* Headline tally — the single number a reviewer should leave with. */}
       <Card>
-        <CardHeader className="flex flex-row items-center justify-between gap-3">
-          <CardTitle className="text-lg">{sb.benchmark_id}</CardTitle>
+        <CardHeader className="flex flex-col items-start gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
+          <CardTitle className="font-mono text-base">
+            {sb.benchmark_id}
+          </CardTitle>
           <span className="text-muted-foreground text-xs">
             {sb.aggregate.n_questions} questions ·{" "}
             {ALL_BENCHMARK_DIMENSIONS.length} dimensions
           </span>
         </CardHeader>
-        <CardContent>
-          <p className="text-sm" data-testid="benchmark-tally">
-            POLARIS won{" "}
-            <span className="font-semibold text-emerald-700 dark:text-emerald-300">
+        <CardContent className="flex flex-col gap-3">
+          <div
+            className="flex items-baseline gap-2"
+            data-testid="benchmark-tally"
+          >
+            <span className="text-verified text-4xl font-semibold tabular-nums">
               {sb.polaris_wins}
-            </span>{" "}
-            per-question per-dimension comparisons; commercial DR products won{" "}
-            {sb.external_wins}; {sb.ties} ties.
-          </p>
+            </span>
+            <span className="text-muted-foreground text-sm">
+              of {total} per-question · per-dimension comparisons won by POLARIS
+            </span>
+          </div>
+          <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
+            <span>
+              Commercial products won{" "}
+              <span className="text-foreground font-medium tabular-nums">
+                {sb.external_wins}
+              </span>
+            </span>
+            <span>
+              Ties{" "}
+              <span className="text-foreground font-medium tabular-nums">
+                {sb.ties}
+              </span>
+            </span>
+          </div>
         </CardContent>
       </Card>
 
       <Card>
         <CardHeader>
-          <CardTitle className="text-base">Aggregate means</CardTitle>
+          <CardTitle className="text-base">
+            Aggregate means by dimension
+          </CardTitle>
         </CardHeader>
         <CardContent>
-          <table className="w-full border-collapse text-sm">
-            <thead>
-              <tr className="border-border border-b">
-                <th className="py-2 text-left">Dimension</th>
-                <th className="py-2 text-right">POLARIS</th>
-                <th className="py-2 text-right">ChatGPT DR</th>
-                <th className="py-2 text-right">Gemini DR</th>
-              </tr>
-            </thead>
-            <tbody>
-              {ALL_BENCHMARK_DIMENSIONS.map((dim) => {
-                const p = sb.aggregate.polaris_mean[dim];
-                const c = sb.aggregate.chatgpt_mean[dim];
-                const g = sb.aggregate.gemini_mean[dim];
-                return (
-                  <tr
-                    key={dim}
-                    data-testid={`agg-row-${dim}`}
-                    className="border-border border-b"
-                  >
-                    <td className="py-2">{BENCHMARK_DIMENSION_LABELS[dim]}</td>
-                    <td
-                      className={cn(
-                        "py-2 text-right font-mono",
-                        tone_class(p, [c, g]),
-                      )}
+          {/* Desktop: dense comparison table. */}
+          <div className="hidden sm:block">
+            <table className="w-full border-collapse text-sm">
+              <thead>
+                <tr className="border-border text-muted-foreground border-b text-xs tracking-wide uppercase">
+                  <th className="py-2 pr-4 text-left font-medium">Dimension</th>
+                  <th className="text-primary py-2 pl-4 text-right font-semibold">
+                    POLARIS
+                  </th>
+                  <th className="py-2 pl-4 text-right font-medium">
+                    ChatGPT DR
+                  </th>
+                  <th className="py-2 pl-4 text-right font-medium">
+                    Gemini DR
+                  </th>
+                </tr>
+              </thead>
+              <tbody>
+                {ALL_BENCHMARK_DIMENSIONS.map((dim) => {
+                  const p = sb.aggregate.polaris_mean[dim];
+                  const c = sb.aggregate.chatgpt_mean[dim];
+                  const g = sb.aggregate.gemini_mean[dim];
+                  const polaris_only = POLARIS_ONLY_DIMENSIONS.has(dim);
+                  return (
+                    <tr
+                      key={dim}
+                      data-testid={`agg-row-${dim}`}
+                      className="border-border/60 border-b last:border-0"
                     >
-                      {format_pct(p)}
-                    </td>
-                    <td
-                      className={cn(
-                        "py-2 text-right font-mono",
-                        tone_class(c, [p, g]),
-                      )}
-                    >
-                      {format_pct(c)}
-                    </td>
-                    <td
-                      className={cn(
-                        "py-2 text-right font-mono",
-                        tone_class(g, [p, c]),
-                      )}
-                    >
-                      {format_pct(g)}
-                    </td>
-                  </tr>
-                );
-              })}
-            </tbody>
-          </table>
+                      <td className="text-foreground py-2.5 pr-4">
+                        {BENCHMARK_DIMENSION_LABELS[dim]}
+                        {polaris_only ? (
+                          <span className="text-muted-foreground ml-1.5 align-middle text-[10px] tracking-wide uppercase">
+                            POLARIS-only
+                          </span>
+                        ) : null}
+                      </td>
+                      <td
+                        className={cn(
+                          "py-2.5 pl-4 text-right font-mono tabular-nums",
+                          tone_class(p, [c, g]),
+                        )}
+                      >
+                        {format_pct(p)}
+                      </td>
+                      <td
+                        className={cn(
+                          "py-2.5 pl-4 text-right font-mono tabular-nums",
+                          tone_class(c, [p, g]),
+                        )}
+                      >
+                        {format_pct(c)}
+                      </td>
+                      <td
+                        className={cn(
+                          "py-2.5 pl-4 text-right font-mono tabular-nums",
+                          tone_class(g, [p, c]),
+                        )}
+                      >
+                        {format_pct(g)}
+                      </td>
+                    </tr>
+                  );
+                })}
+              </tbody>
+            </table>
+          </div>
+
+          {/* Mobile: per-dimension stacked blocks — the 4-column table clips the
+              third peer column below sm, so all three systems get their own
+              labelled cell here (Codex visual iter-1 P1). */}
+          <div className="flex flex-col gap-3 sm:hidden">
+            {ALL_BENCHMARK_DIMENSIONS.map((dim) => {
+              const p = sb.aggregate.polaris_mean[dim];
+              const c = sb.aggregate.chatgpt_mean[dim];
+              const g = sb.aggregate.gemini_mean[dim];
+              const polaris_only = POLARIS_ONLY_DIMENSIONS.has(dim);
+              const cells = [
+                { label: "POLARIS", value: p, peers: [c, g], brand: true },
+                { label: "ChatGPT DR", value: c, peers: [p, g], brand: false },
+                { label: "Gemini DR", value: g, peers: [p, c], brand: false },
+              ];
+              return (
+                <div
+                  key={dim}
+                  className="border-border/60 border-b pb-3 last:border-0 last:pb-0"
+                >
+                  <div className="text-foreground flex flex-wrap items-center gap-x-1.5 text-sm font-medium">
+                    {BENCHMARK_DIMENSION_LABELS[dim]}
+                    {polaris_only ? (
+                      <span className="text-muted-foreground text-[10px] tracking-wide uppercase">
+                        POLARIS-only
+                      </span>
+                    ) : null}
+                  </div>
+                  <div className="mt-2 grid grid-cols-3 gap-2 text-center">
+                    {cells.map((cell) => (
+                      <div key={cell.label} className="flex flex-col gap-0.5">
+                        <span
+                          className={cn(
+                            "text-[10px] tracking-wide uppercase",
+                            cell.brand
+                              ? "text-primary font-semibold"
+                              : "text-muted-foreground",
+                          )}
+                        >
+                          {cell.label}
+                        </span>
+                        <span
+                          className={cn(
+                            "font-mono text-sm tabular-nums",
+                            tone_class(cell.value, cell.peers),
+                          )}
+                        >
+                          {format_pct(cell.value)}
+                        </span>
+                      </div>
+                    ))}
+                  </div>
+                </div>
+              );
+            })}
+          </div>
+
+          <p className="text-muted-foreground mt-3 text-xs">
+            <span className="text-verified font-medium">Green</span> = leads
+            every reported peer. A dash (—) means the system does not report
+            that dimension.
+          </p>
         </CardContent>
       </Card>
     </div>
diff --git a/web/app/benchmark/page.tsx b/web/app/benchmark/page.tsx
index 02df9f09..9a659ca6 100644
--- a/web/app/benchmark/page.tsx
+++ b/web/app/benchmark/page.tsx
@@ -25,9 +25,10 @@ export default function BenchmarkPage() {
           Head-to-head comparison of POLARIS vs commercial deep-research
           products on 7 dimensions: sourcing tier mix, numeric grounding,
           provenance density, refusal correctness, coverage completeness,
-          latency, and auditability. POLARIS uniquely scores 1.0 on refusal
-          correctness and auditability — these are features no commercial system
-          attempts.
+          latency, and auditability. Refusal correctness and auditability are
+          dimensions no commercial deep-research product reports against —
+          POLARIS is built to be graded on them. Every score below comes from
+          the published scoreboard, not this page.
         </p>
       </div>
 

# canonical-diff-sha256: ebd980f899b170e8f66eac2c78ce12ad46be1deb6e76471d13cef3ab3ede5ec6

```
