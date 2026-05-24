# Codex DIFF review — I-p2-057 (#861): Run progress S-audit — iter 4 of 5

HARD ITERATION CAP: 5. iter 4. iter-3 was REQUEST_CHANGES on a real §9.1 bug: the verified-result
copy AND the FollowupPanel were gated on lifecycle status === "completed", but mark_aborted()
persists lifecycle 'completed' for abort_* runs → an abort_no_verified_sections run would claim a
"verified result" + render follow-up.

## Fix applied (this iter)
- Added `hasVerifiedResult` = (status === "completed") && pipeline_status is NOT abort_*/error_*
  (a completed run with null pipeline_status is trusted as success, matching RunProgress's own
  fallback at run_progress.tsx). BOTH the actions-card "verified result" copy AND the FollowupPanel
  now gate on `hasVerifiedResult`, not lifecycle 'completed'. An abort_* run → "Open or export what
  this run produced:" + NO follow-up. Updated the inline comment + the S-tier doc note to match.

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
- Visual `-i` APPROVE iter-2 (the done capture is pipeline success → hasVerifiedResult true → copy
  + follow-up unchanged). canonical-diff-sha256: b21755dd226a93ffc06b04d715308703e9491f28277ce8d5fb38832b26335133. tsc/eslint/prettier clean.

## The full canonical diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index 691c8aba..fd5b4f27 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -165,5 +165,25 @@ Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Co
   reserved for the single Start-run action). The scope/concurrent guards + honest framing
   preserved. Residual P2 (accept_remaining): no-question empty state vertical rhythm.
 
-Remaining cred-gated UI: the Run-progress page (the last journey leg). LIVE-populated verification
-of all cred-gated pages awaits the demo reviewer credential.
+- **Run progress** (#861, I-p2-057): **live desktop A / live mobile A / done desktop A** (Codex
+  visual iter-2 APPROVE). The live-run surface (depth-visible 4-stage progress consuming SSE
+  events) — already exemplary (honest stream-loss handling, the "never green-check an unobserved
+  stage" rule, the Thinking-Toggle, honest "—" elapsed when not watched live). Assess-first: moved
+  the "done" stage chip + retrieval ✓ from brand-red to `--verified` green (a red done-checkmark
+  reads as an alarm); gave the stage cards + counters + the page actions card `shadow-card` +
+  `rounded-xl`; reworded the actions card heading off UX jargon ("Affordances during this run" →
+  "While this run works") and branched it by verdict — live → "While this run works"; terminal with
+  a verified PIPELINE result (success / partial_*) → "This run" / "Open, export, or follow up on the
+  verified result:"; terminal aborted / failed / cancelled → "Open or export what this run
+  produced:" (no "verified result" claim, and no follow-up panel, for a run that produced none).
+  The verified-result copy + the follow-up panel are gated on `pipeline_status`, NOT lifecycle
+  `status === "completed"` — per §9.1 `mark_aborted()` persists lifecycle 'completed' for abort_*
+  runs (Codex visual iter-1 P2 + diff iter-1/2/3 P2).
+
+**The full cred-gated journey is now at the A bar** (Dashboard A/A-/A · Benchmark A/A-/A-/A-/A ·
+Memory A/A-/A · Compare A/A/A/A · Source Review S-/A++/A+ · Plan A/A/A/A- · Run progress A/A/A),
+each rendered locally (seeded session + route-mocked fixture, visual-audit-only) under the dual
+Codex gate (visual `-i` + code) → merged → deployed. LIVE-populated verification of every
+cred-gated page awaits the demo reviewer credential — the pages 401-redirect on
+polarisresearch.ca without it; layout/states are verified against route-mocked fixtures + the
+natural empty/error states (which ARE what render live).
diff --git a/web/app/runs/[runId]/components/run_progress.tsx b/web/app/runs/[runId]/components/run_progress.tsx
index 82db8ee7..0b714e4c 100644
--- a/web/app/runs/[runId]/components/run_progress.tsx
+++ b/web/app/runs/[runId]/components/run_progress.tsx
@@ -250,7 +250,7 @@ export function RunProgress({ events, status }: RunProgressProps) {
               key={stage.key}
               data-testid={`stage-${stage.key}`}
               data-state={state}
-              className="border-border bg-card flex flex-col gap-2 rounded-lg border p-4"
+              className="border-border bg-card shadow-card flex flex-col gap-2 rounded-xl border p-4"
             >
               <div className="flex items-center gap-2">
                 <StageChip state={state} />
@@ -282,7 +282,7 @@ export function RunProgress({ events, status }: RunProgressProps) {
 
 function Counter({ label, value }: { label: string; value: string }) {
   return (
-    <div className="border-border bg-card flex flex-col gap-1 rounded-lg border px-3 py-2">
+    <div className="border-border bg-card shadow-card flex flex-col gap-1 rounded-xl border px-3 py-2">
       <span className="text-muted-foreground text-[10px] font-medium tracking-widest uppercase">
         {label}
       </span>
@@ -301,10 +301,12 @@ function StageChip({ state }: { state: StageState }) {
     );
   }
   if (state === "done") {
+    // A done/verified stage reads in the product's verdict language: green
+    // (--verified), not the brand-red accent (a red ✓ reads as an alarm).
     return (
       <span
         aria-label="done"
-        className="bg-primary text-primary-foreground flex size-4 items-center justify-center rounded-full text-[10px]"
+        className="bg-verified text-verified-foreground flex size-4 items-center justify-center rounded-full text-[10px]"
       >
         ✓
       </span>
@@ -397,7 +399,7 @@ function StageBody({
             className="text-muted-foreground truncate text-xs"
             title={s.url || s.id}
           >
-            <span className="text-primary">✓</span> {s.url || s.id}
+            <span className="text-verified">✓</span> {s.url || s.id}
           </li>
         ))}
         {sources.length > 12 && (
diff --git a/web/app/runs/[runId]/page.tsx b/web/app/runs/[runId]/page.tsx
index 2d78ec1b..a96ea84c 100644
--- a/web/app/runs/[runId]/page.tsx
+++ b/web/app/runs/[runId]/page.tsx
@@ -86,6 +86,22 @@ export default function RunDetailPage({ params }: RunPageProps) {
     status !== null && TERMINAL_STATUSES.includes(status.status);
   const cancelRequested = status?.cancel_requested ?? false;
 
+  // A genuinely verified, followable result. Per §9.1, the lifecycle `status`
+  // is NOT authoritative — mark_aborted() persists lifecycle 'completed' for
+  // abort_* runs too, so an abort_no_verified_sections run is lifecycle
+  // 'completed' but has NO verified result. The run-store PIPELINE status is
+  // the verdict: treat 'completed' as verified UNLESS pipeline_status is an
+  // abort_*/error_* (a completed run with null pipeline_status predates the
+  // field → trusted as success, matching RunProgress's own fallback). This
+  // gates both the "verified result" copy and the follow-up panel so neither
+  // overclaims on an aborted run.
+  const pipelineStatus = status?.pipeline_status ?? null;
+  const isAbortedOrError =
+    pipelineStatus !== null &&
+    (pipelineStatus.startsWith("abort_") ||
+      pipelineStatus.startsWith("error_"));
+  const hasVerifiedResult = status?.status === "completed" && !isAbortedOrError;
+
   const onCancel = async () => {
     setCancelling(true);
     setError(null);
@@ -164,12 +180,18 @@ export default function RunDetailPage({ params }: RunPageProps) {
         {error && <ErrorState title="Couldn't load this run" message={error} />}
       </div>
 
-      <div className="border-border flex flex-col gap-2 rounded-md border p-4">
+      <div className="border-border bg-card shadow-card flex flex-col gap-2 rounded-xl border p-4">
         <h2 className="text-foreground text-sm font-semibold">
-          Affordances during this run
+          {isTerminal ? "This run" : "While this run works"}
         </h2>
         <p className="text-muted-foreground text-xs">
-          Actions you can take while POLARIS works:
+          {/* hasVerifiedResult is pipeline-verdict-based (see above): an
+              aborted/failed/cancelled run must not claim a "verified result". */}
+          {!isTerminal
+            ? "Actions you can take while POLARIS works:"
+            : hasVerifiedResult
+              ? "Open, export, or follow up on the verified result:"
+              : "Open or export what this run produced:"}
         </p>
         <div className="flex flex-wrap gap-2">
           <Button
@@ -237,10 +259,12 @@ export default function RunDetailPage({ params }: RunPageProps) {
 
       <RunProgress events={events} status={status} />
 
-      {/* I-ui-003 (#542): follow-up is meaningful only for a completed run
-          (it has an answerable, verified report). Failed/cancelled/in-progress
-          runs don't render it. */}
-      {status?.status === "completed" && <FollowupPanel runId={runId} />}
+      {/* I-ui-003 (#542): follow-up is meaningful only for a run with a
+          verified report. Per §9.1, gate on the PIPELINE verdict, not lifecycle
+          'completed' — an abort_* run is lifecycle 'completed' but has no
+          verified result to follow up on (I-p2-057 Codex diff iter-3 P2).
+          Failed/cancelled/in-progress runs don't render it either. */}
+      {hasVerifiedResult && <FollowupPanel runId={runId} />}
     </section>
   );
 }

# canonical-diff-sha256: b21755dd226a93ffc06b04d715308703e9491f28277ce8d5fb38832b26335133

```
