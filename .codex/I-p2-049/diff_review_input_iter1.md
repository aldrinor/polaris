# Codex DIFF review — I-p2-049 (#845): Sign-in S-rebuild (honest sovereignty wording)

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings; reserve P0/P1 for real execution
risks. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

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
- Brief APPROVE (iter 2, narrowed wording). Visual `-i` APPROVE (iter 1: desktop A / mobile A).
- canonical-diff-sha256: 824b3eb3350439e161e6ef9f14af1d93b01d8b31febb60a9304b3780a7ae90e3

## What the diff does (web/app/sign-in/page.tsx + doc) — text only
Three present-tense sovereignty overclaims narrowed so none can be read as covering US-routed
LLM inference:
- trust point: "Sovereign Canadian processing, integrity-hashed." → "Canadian-hosted evidence
  records, integrity-hashed."
- left strip: "Sovereign Canadian deep research · auditable evidence" → "Canadian-hosted
  research workspace · auditable evidence"
- mobile lockup: "Sovereign Deep Research" → "Canadian-hosted Workspace"
No other change. Auth handleSubmit / JWT / redirect / testids untouched.

## Verification
- typecheck clean; prettier ok; eslint 0 errors. grep confirms ZERO "Sovereign" in the file.
- e2e sign_in: 4/8 pass (render + bad-creds → sign-in-error). The 4 valid-creds → JWT/redirect
  + ?next= specs need the auth backend (not up in dev) — text-only change, no auth logic.

## Review focus
- Confirm no residual present-tense sovereignty/processing claim that covers US inference;
  honest given the footer disclosure. testids/auth logic untouched. Tokens only; brand #c8102e.

## The diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index efc3ac90..ed30c1e0 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -111,5 +111,14 @@ span highlights, and verdict badges appear consistently across the product.
   makes the temporal-drift differentiator tangible. Known pre-existing (NOT this PR, proven on
   baseline): `pin_replay_g1_g8` G8 fails on a Next-16 RSC `Set`-serialization warning ("Set
   objects are not supported" server→client) — follow-up.
-- Pre-redo baseline (Codex, 2026-05-23): Sign-in B−. Target every screen at A++/S with the
-  signature move systematized.
+- **Sign-in** (#845, I-p2-049): **desktop A / mobile A** (Codex visual iter-1 APPROVE). Fixed
+  THREE present-tense sovereignty overclaims — narrowed (Codex P1) so they can't be read as
+  covering US-routed LLM inference: "Sovereign Canadian processing" → "Canadian-hosted evidence
+  records, integrity-hashed"; strip → "Canadian-hosted research workspace"; mobile lockup →
+  "Canadian-hosted Workspace". Institutional split-screen preserved.
+
+**All 7 PUBLIC pages now at the A bar** (Inspector A/A-/A/A- · Home A/A-/A- · Intake A-/A- ·
+Contracts A/A- · Upload A/A+/A · Pin Replay A/A- · Sign-in A/A), each dual-Codex-gated
+(visual `-i` + code) → merged → deployed → verified live. Remaining UI: the cred-gated journey
+(dashboard / benchmark / memory / source-review / Plan→Run→Compare) — blocked on demo creds in
+the VM `.env`.
diff --git a/web/app/sign-in/page.tsx b/web/app/sign-in/page.tsx
index 04066608..7a4d4d66 100644
--- a/web/app/sign-in/page.tsx
+++ b/web/app/sign-in/page.tsx
@@ -22,7 +22,7 @@ const TRUST_POINTS = [
   { icon: BadgeCheck, text: "Every claim span-anchored to a primary source." },
   {
     icon: ShieldCheck,
-    text: "Sovereign Canadian processing, integrity-hashed.",
+    text: "Canadian-hosted evidence records, integrity-hashed.",
   },
   { icon: Network, text: "A connected, auditable evidence graph per run." },
 ] as const;
@@ -138,7 +138,7 @@ function SignInPageContent() {
           </ul>
         </div>
         <p className="text-muted-foreground text-xs">
-          Sovereign Canadian deep research · auditable evidence
+          Canadian-hosted research workspace · auditable evidence
         </p>
       </aside>
 
@@ -152,7 +152,7 @@ function SignInPageContent() {
               POLARIS Canada
             </span>
             <span className="text-foreground text-base font-semibold">
-              Sovereign Deep Research
+              Canadian-hosted Workspace
             </span>
           </div>
 

# canonical-diff-sha256: 824b3eb3350439e161e6ef9f14af1d93b01d8b31febb60a9304b3780a7ae90e3

```
