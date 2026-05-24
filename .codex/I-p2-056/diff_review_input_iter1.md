# Codex DIFF review — I-p2-056 (#859): Plan review S-audit (page + S-tier tracker)

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
- Visual `-i` APPROVE iter-1 (ready desktop A / ready mobile A / blocked A / no-question A-).
- canonical-diff-sha256: 7518b871a40c077f02584e3c1c5ce60fe732aa15780f9c524213b2cba6b5af27
- CI hashes the PR diff excluding only .codex/<id>/ + outputs/audits/<id>/, so this canonical diff
  includes BOTH the page + the docs tracker row.

## What the diff does (2 files, small/CSS-only on the page)
1. web/app/plan/page.tsx — `shadow-card` + `rounded-xl` on the "Your question" card and the step
   cards (were flat rounded-lg); step-icon container `text-primary` → `text-muted-foreground`
   (reserve brand for the Start button). NO logic change.
2. docs/web/s_tier_design_system.md — appends the Plan row to the cred-gated tracker.

## Verification
- typecheck clean; eslint app/plan/page.tsx clean; prettier clean. Preserved: the runIntake gate +
  runDisambiguation + createRun flow, the canStart = inScope && disambigResolved gate (button +
  call-time re-assertion), testids (plan-page/plan-start-run/plan-blocked/plan-concurrent), honest
  framing.

## Review focus
- Confirm the step-icon colour change is the ONLY semantic shift (icons were decorative; the title
  stays text-foreground). No gate/logic touched. Docs claims match shipped grades.

## The full canonical diff (page + docs)
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index c284f853..691c8aba 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -157,5 +157,13 @@ Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Co
   "Try again" retry to the error state (Codex iter-1 P2). The honest no-fabricated-corpus framing
   is preserved.
 
-Remaining cred-gated UI: the Plan→Run→Compare journey. LIVE-populated verification of all
-cred-gated pages awaits the demo reviewer credential.
+- **Plan review** (#859, I-p2-056): **ready desktop A / ready mobile A / blocked A / no-question
+  A-** (Codex visual iter-1 APPROVE). The run-start surface (intake → plan → run); on mount it
+  re-runs the full intake gate, and Start is enabled only for an in_scope, disambiguation-resolved
+  question. Assess-first: gave the question card + the four "What POLARIS will do" step cards
+  `shadow-card` + `rounded-xl`, and toned the four step icons from brand-red to muted (brand
+  reserved for the single Start-run action). The scope/concurrent guards + honest framing
+  preserved. Residual P2 (accept_remaining): no-question empty state vertical rhythm.
+
+Remaining cred-gated UI: the Run-progress page (the last journey leg). LIVE-populated verification
+of all cred-gated pages awaits the demo reviewer credential.
diff --git a/web/app/plan/page.tsx b/web/app/plan/page.tsx
index 5df298a7..e19c88b2 100644
--- a/web/app/plan/page.tsx
+++ b/web/app/plan/page.tsx
@@ -236,7 +236,7 @@ function PlanContent() {
       </div>
 
       {/* The vetted question (display-only) */}
-      <div className="border-border bg-card flex flex-col gap-2 rounded-xl border p-5">
+      <div className="border-border bg-card shadow-card flex flex-col gap-2 rounded-xl border p-5">
         <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
           Your question
         </span>
@@ -267,9 +267,9 @@ function PlanContent() {
           {PLAN_STEPS.map((step, i) => (
             <li
               key={step.title}
-              className="border-border bg-card flex flex-col gap-1.5 rounded-lg border p-4"
+              className="border-border bg-card shadow-card flex flex-col gap-1.5 rounded-xl border p-4"
             >
-              <div className="text-primary flex items-center gap-2">
+              <div className="text-muted-foreground flex items-center gap-2">
                 <step.icon aria-hidden className="h-4 w-4 shrink-0" />
                 <span className="text-foreground text-sm font-medium">
                   {i + 1}. {step.title}

# canonical-diff-sha256: 7518b871a40c077f02584e3c1c5ce60fe732aa15780f9c524213b2cba6b5af27

```
