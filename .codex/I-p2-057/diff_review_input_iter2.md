# Codex DIFF review — I-p2-057 (#861): Run progress S-audit — iter 2 of 5

HARD ITERATION CAP: 5. iter 2. iter-1 APPROVE'd with one P2 (honesty): the terminal sub-copy said
"verified result" for ALL terminal states, including failed/cancelled.

## Fix applied (this iter, addressing the iter-1 P2)
- The actions-card sub-copy now branches three ways: live → "Actions you can take while POLARIS
  works:"; terminal + completed → "Open, export, or follow up on the verified result:"; terminal +
  failed/cancelled → "Open or export what this run produced:" (no "verified result" claim). The
  follow-up panel remains gated to completed. Nothing else changed since iter-1.

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
- Visual `-i` APPROVE iter-2 (live desktop A / live mobile A / done desktop A; the done capture is
  a COMPLETED run so its copy is unchanged). canonical-diff-sha256: 
- typecheck/eslint/prettier clean.

## The full canonical diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index 691c8aba..abc97fae 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -165,5 +165,20 @@ Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Co
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
+  "While this run works"), and branched it by status (terminal → "This run" / "Open, export, or
+  follow up on the verified result:") (Codex visual iter-1 P2).
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
index 2d78ec1b..05f6f5b3 100644
--- a/web/app/runs/[runId]/page.tsx
+++ b/web/app/runs/[runId]/page.tsx
@@ -164,12 +164,19 @@ export default function RunDetailPage({ params }: RunPageProps) {
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
+          {/* Only a COMPLETED run has a verified, followable result — a failed/
+              cancelled run must not claim one (honesty; follow-up is gated to
+              completed below regardless). */}
+          {!isTerminal
+            ? "Actions you can take while POLARIS works:"
+            : status?.status === "completed"
+              ? "Open, export, or follow up on the verified result:"
+              : "Open or export what this run produced:"}
         </p>
         <div className="flex flex-wrap gap-2">
           <Button

# canonical-diff-sha256: a25afdea2282fcfbf0f4b24a925341685a54ba4a7102e0a65628ff39d2cbb7ec

```
