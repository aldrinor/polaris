# Codex DIFF review — I-p2-054 (#855): Compare S-audit (page + S-tier tracker)

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
- Visual `-i` APPROVE iter-2 (result desktop A / mobile A / picker A / empty A).
- canonical-diff-sha256: 8147c23789279d71ca7d27d7cf0cf1514366be75b0ab0d8c43de12480651e71c
- The codex-required CI gate hashes the PR diff EXCLUDING only .codex/<id>/ + outputs/audits/<id>/,
  so this canonical diff includes BOTH files below (the page + the docs tracker) and both are in
  scope for this review.

## What the diff does (2 files)
1. web/app/compare/page.tsx — added LoadingState + EmptyState (none before); Flag now renders a
   --verified Check (pass) / muted X (mismatch) instead of a brand-red ✓; tokenized RunPicker
   select (FIELD_CLASS); Card-wrapped picker/headline/evidence/frame/contradictions; optionLabel
   leads with run_id + shortDate("en-CA") + template + truncated question; ComparisonView header
   shows left_run_id ↔ right_run_id; mobile stat stacks.
2. docs/web/s_tier_design_system.md — appends the Compare row to the cred-gated tracker.

## Verification
- typecheck clean; eslint app/compare/page.tsx clean; prettier clean. Preserved: the state vars +
  distinct gate + onCompare + compareErrorMessage; testids compare-page/-left/-right/
  comparison-result; the real listCompletedRuns(50) + compareRuns(left,right) fetches.

## Review focus
- shortDate uses "en-CA" (deterministic English; same locale-safety as the dashboard fix).
- No fabricated SHIPPED data (the visual-audit fixture is not in the diff). Flag semantics: a
  mismatch is muted (informational), never destructive — confirm that reads correctly.
- The docs claims match the shipped grades + honest deferred-verification framing.

## The full canonical diff (page + docs)
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index a13da376..1994b739 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -142,5 +142,12 @@ Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Co
   3-line rows + "SAVED MEMORY · N". Fixed a `react-hooks/set-state-in-effect` lint blocker (Codex
   diff P1) via the codebase IIFE-in-effect idiom.
 
+- **Compare** (#855, I-p2-054): **result desktop A / result mobile A / picker A / empty A** (Codex
+  visual iter-2 APPROVE). Added a LoadingState + designed EmptyState; fixed a confusing brand-red
+  `✓` flag (now `--verified` green Check for pass, muted X for an informational mismatch);
+  tokenized the run-picker selects; Card-elevated the picker + headline + evidence + frame-coverage
+  + contradictions. Run identity made unambiguous (Codex iter-1 P1): option labels lead with the
+  unique run id + date, and the result header shows the compared pair (`left ↔ right`).
+
 Remaining cred-gated UI: source-review + the Plan→Run→Compare journey. LIVE-populated verification
 of all cred-gated pages awaits the demo reviewer credential.
diff --git a/web/app/compare/page.tsx b/web/app/compare/page.tsx
index 944c5017..9f27c8f9 100644
--- a/web/app/compare/page.tsx
+++ b/web/app/compare/page.tsx
@@ -1,9 +1,16 @@
 "use client";
 
+import { Check, GitCompareArrows, X } from "lucide-react";
+import Link from "next/link";
 import { useEffect, useState } from "react";
 
-import { ErrorState } from "@/components/states/state_kit";
+import {
+  EmptyState,
+  ErrorState,
+  LoadingState,
+} from "@/components/states/state_kit";
 import { Button } from "@/components/ui/button";
+import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
 import {
   compareRuns,
   listCompletedRuns,
@@ -14,10 +21,23 @@ import {
 // I-ui-004 (#543): two-run compare. Pick two completed runs → GET
 // /runs/{l}/compare/{r}. Distinct from /benchmark (POLARIS-vs-external).
 
+const FIELD_CLASS =
+  "border-input bg-transparent focus-visible:border-ring focus-visible:ring-ring/70 w-full rounded-lg border px-2.5 py-2 text-sm transition-colors outline-none focus-visible:ring-3";
+
+function shortDate(value: string | null | undefined): string {
+  if (!value) return "—";
+  const d = new Date(value);
+  if (Number.isNaN(d.getTime())) return "—";
+  return d.toLocaleDateString("en-CA", { month: "short", day: "numeric" });
+}
+
+// Lead with the unique run id + completion date so two runs that share a
+// template/question are still distinguishable (the id never truncates off the
+// end of the select); the question follows for context (Codex visual iter-1 P1).
 function optionLabel(run: RunStatusResponse): string {
   const q =
-    run.question.length > 60 ? `${run.question.slice(0, 60)}…` : run.question;
-  return `${run.template} · ${q} · ${run.run_id.slice(0, 8)}`;
+    run.question.length > 44 ? `${run.question.slice(0, 44)}…` : run.question;
+  return `${run.run_id} · ${shortDate(run.finished_at ?? run.queued_at)} · ${run.template} · ${q}`;
 }
 
 function compareErrorMessage(err: unknown): string {
@@ -83,57 +103,68 @@ export default function ComparePage() {
         </p>
       </div>
 
-      {runs !== null && runs.length === 0 && (
-        <p className="text-muted-foreground text-sm">
-          No completed runs to compare yet.{" "}
-          <a className="text-primary underline" href="/intake">
-            Start a run
-          </a>
-          .
-        </p>
-      )}
+      {runs === null ? (
+        <LoadingState label="Loading completed runs…" rows={3} />
+      ) : null}
 
-      {runs !== null && runs.length > 0 && (
-        <div className="flex flex-col gap-3">
-          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
-            <RunPicker
-              label="Left run"
-              testid="compare-left"
-              runs={runs}
-              value={left}
-              onChange={setLeft}
-            />
-            <RunPicker
-              label="Right run"
-              testid="compare-right"
-              runs={runs}
-              value={right}
-              onChange={setRight}
-            />
-          </div>
-          <div className="flex items-center gap-3">
+      {runs !== null && runs.length === 0 ? (
+        <EmptyState
+          icon={GitCompareArrows}
+          title="No completed runs to compare yet"
+          description="Once two research runs have finished, pick any two here to diff their evidence, frame coverage, and contradictions."
+          action={
             <Button
-              type="button"
-              onClick={onCompare}
-              disabled={!distinct || submitting}
-            >
-              {submitting ? "Comparing…" : "Compare"}
-            </Button>
-            {left !== "" && right !== "" && left === right && (
-              <span className="text-muted-foreground text-xs">
-                Pick two distinct runs.
-              </span>
-            )}
-          </div>
-        </div>
-      )}
+              nativeButton={false}
+              variant="outline"
+              render={<Link href="/intake">Start a run</Link>}
+            />
+          }
+        />
+      ) : null}
+
+      {runs !== null && runs.length > 0 ? (
+        <Card>
+          <CardContent className="flex flex-col gap-4">
+            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
+              <RunPicker
+                label="Left run"
+                testid="compare-left"
+                runs={runs}
+                value={left}
+                onChange={setLeft}
+              />
+              <RunPicker
+                label="Right run"
+                testid="compare-right"
+                runs={runs}
+                value={right}
+                onChange={setRight}
+              />
+            </div>
+            <div className="flex items-center gap-3">
+              <Button
+                type="button"
+                onClick={onCompare}
+                disabled={!distinct || submitting}
+              >
+                {submitting ? "Comparing…" : "Compare"}
+              </Button>
+              {left !== "" && right !== "" && left === right ? (
+                <span className="text-muted-foreground text-xs">
+                  Pick two distinct runs.
+                </span>
+              ) : null}
+            </div>
+          </CardContent>
+        </Card>
+      ) : null}
 
       {/* I-p2-018 (#757): #750 ErrorState for design-system consistency. */}
-      {error && (
+      {error ? (
         <ErrorState title="Couldn't compare those runs" message={error} />
-      )}
+      ) : null}
 
-      {result && <ComparisonView result={result} />}
+      {result ? <ComparisonView result={result} /> : null}
     </section>
   );
 }
@@ -152,7 +183,7 @@ function RunPicker({
   onChange: (v: string) => void;
 }) {
   return (
-    <label className="flex flex-col gap-1">
+    <label className="flex flex-col gap-1.5">
       <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
         {label}
       </span>
@@ -160,7 +191,7 @@ function RunPicker({
         data-testid={testid}
         value={value}
         onChange={(e) => onChange(e.target.value)}
-        className="border-input focus-visible:border-ring focus-visible:ring-ring rounded-lg border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2"
+        className={FIELD_CLASS}
       >
         <option value="">Select a run…</option>
         {runs.map((run) => (
@@ -173,40 +204,50 @@ function RunPicker({
   );
 }
 
+// A boolean run-property flag. A pass reads as verified-green; a mismatch is
+// neutral (two runs differing on template/question is informational, not an
+// error) — so it's muted, never the alarm/destructive token.
 function Flag({ label, ok }: { label: string; ok: boolean }) {
   return (
-    <span className="text-muted-foreground flex items-center gap-1 text-xs">
-      <span className={ok ? "text-primary" : "text-muted-foreground"}>
-        {ok ? "✓" : "✗"}
+    <span className="flex items-center gap-1.5 text-xs">
+      {ok ? (
+        <Check aria-hidden className="text-verified h-3.5 w-3.5" />
+      ) : (
+        <X aria-hidden className="text-muted-foreground h-3.5 w-3.5" />
+      )}
+      <span className={ok ? "text-foreground" : "text-muted-foreground"}>
+        {label}
       </span>
-      {label}
     </span>
   );
 }
 
 function EvidenceColumn({ title, ids }: { title: string; ids: string[] }) {
   return (
-    <div className="border-border bg-card flex flex-col gap-1 rounded-lg border p-3">
+    <div className="border-border bg-muted/20 flex flex-col gap-1.5 rounded-lg border p-3">
       <span className="text-foreground text-xs font-semibold">
-        {title} ({ids.length})
+        {title}{" "}
+        <span className="text-muted-foreground tabular-nums">
+          ({ids.length})
+        </span>
       </span>
       <div className="flex flex-wrap gap-1">
         {ids.slice(0, 20).map((id) => (
           <span
             key={id}
-            className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono text-[10px]"
+            className="bg-card text-muted-foreground border-border/60 rounded border px-1.5 py-0.5 font-mono text-[10px]"
           >
             {id}
           </span>
         ))}
-        {ids.length > 20 && (
+        {ids.length > 20 ? (
           <span className="text-muted-foreground text-[10px]">
             + {ids.length - 20} more
           </span>
-        )}
-        {ids.length === 0 && (
+        ) : null}
+        {ids.length === 0 ? (
           <span className="text-muted-foreground text-[10px]">—</span>
-        )}
+        ) : null}
       </div>
     </div>
   );
@@ -215,60 +256,89 @@ function EvidenceColumn({ title, ids }: { title: string; ids: string[] }) {
 function ComparisonView({ result }: { result: ReportComparison }) {
   const pct = Math.round((result.shared_evidence_pct ?? 0) * 100);
   return (
-    <div data-testid="comparison-result" className="flex flex-col gap-5">
-      <div className="border-border bg-card flex flex-wrap items-center gap-4 rounded-lg border p-4">
-        <span className="text-foreground text-sm font-semibold">
-          {pct}% shared evidence
-        </span>
-        <Flag label="Same template" ok={result.same_template} />
-        <Flag label="Same question" ok={result.same_question} />
-        <Flag label="Pipeline status match" ok={result.pipeline_status_match} />
-        <Flag
-          label="Two-family segregation (both)"
-          ok={result.family_segregation_both_pass}
-        />
-      </div>
+    <div data-testid="comparison-result" className="flex flex-col gap-4">
+      {/* Headline: which two runs, shared-evidence overlap, run-property flags. */}
+      <Card>
+        <CardContent className="flex flex-col gap-4">
+          <div className="text-muted-foreground flex flex-wrap items-center gap-2 font-mono text-xs">
+            <span className="text-foreground">{result.left_run_id}</span>
+            <span aria-hidden>↔</span>
+            <span className="text-foreground">{result.right_run_id}</span>
+          </div>
+          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-2">
+            <span className="text-foreground text-4xl font-semibold tabular-nums">
+              {pct}%
+            </span>
+            <span className="text-muted-foreground text-sm">
+              shared evidence between the two runs
+            </span>
+          </div>
+          <div className="flex flex-wrap gap-x-5 gap-y-2">
+            <Flag label="Same template" ok={result.same_template} />
+            <Flag label="Same question" ok={result.same_question} />
+            <Flag
+              label="Pipeline status match"
+              ok={result.pipeline_status_match}
+            />
+            <Flag
+              label="Two-family segregation (both)"
+              ok={result.family_segregation_both_pass}
+            />
+          </div>
+        </CardContent>
+      </Card>
 
-      <div className="flex flex-col gap-2">
-        <h2 className="text-foreground text-sm font-semibold">Evidence</h2>
-        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
-          <EvidenceColumn title="Shared" ids={result.shared_evidence_ids} />
-          <EvidenceColumn
-            title="Only left"
-            ids={result.only_left_evidence_ids}
-          />
-          <EvidenceColumn
-            title="Only right"
-            ids={result.only_right_evidence_ids}
-          />
-        </div>
-      </div>
+      <Card>
+        <CardHeader>
+          <CardTitle className="text-base">Evidence</CardTitle>
+        </CardHeader>
+        <CardContent>
+          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
+            <EvidenceColumn title="Shared" ids={result.shared_evidence_ids} />
+            <EvidenceColumn
+              title="Only left"
+              ids={result.only_left_evidence_ids}
+            />
+            <EvidenceColumn
+              title="Only right"
+              ids={result.only_right_evidence_ids}
+            />
+          </div>
+        </CardContent>
+      </Card>
 
-      <div className="flex flex-col gap-2">
-        <h2 className="text-foreground text-sm font-semibold">
-          Frame coverage
-        </h2>
-        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
-          <EvidenceColumn title="Overlap" ids={result.frame_coverage_overlap} />
-          <EvidenceColumn title="Only left" ids={result.only_left_frames} />
-          <EvidenceColumn title="Only right" ids={result.only_right_frames} />
-        </div>
-      </div>
+      <Card>
+        <CardHeader>
+          <CardTitle className="text-base">Frame coverage</CardTitle>
+        </CardHeader>
+        <CardContent>
+          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
+            <EvidenceColumn
+              title="Overlap"
+              ids={result.frame_coverage_overlap}
+            />
+            <EvidenceColumn title="Only left" ids={result.only_left_frames} />
+            <EvidenceColumn title="Only right" ids={result.only_right_frames} />
+          </div>
+        </CardContent>
+      </Card>
 
-      <div className="border-border flex gap-6 rounded-lg border p-4 text-sm">
-        <span className="text-muted-foreground">
-          Left contradictions:{" "}
-          <span className="text-foreground font-mono">
-            {result.left_contradictions}
+      <Card>
+        <CardContent className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
+          <span className="text-muted-foreground">
+            Left contradictions{" "}
+            <span className="text-foreground font-mono tabular-nums">
+              {result.left_contradictions}
+            </span>
           </span>
-        </span>
-        <span className="text-muted-foreground">
-          Right contradictions:{" "}
-          <span className="text-foreground font-mono">
-            {result.right_contradictions}
+          <span className="text-muted-foreground">
+            Right contradictions{" "}
+            <span className="text-foreground font-mono tabular-nums">
+              {result.right_contradictions}
+            </span>
           </span>
-        </span>
-      </div>
+        </CardContent>
+      </Card>
     </div>
   );
 }

# canonical-diff-sha256: 8147c23789279d71ca7d27d7cf0cf1514366be75b0ab0d8c43de12480651e71c

```
