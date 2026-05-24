# Codex DIFF review — I-p2-044 (#835): Home S-rebuild

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; polish is P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

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
- Brief APPROVE (iter 1). Visual `-i` APPROVE (iter 2: desktop A / fold A- / mobile A-).
- canonical-diff-sha256: 38e6f595b7a1c592aa93ed82ffddfe89f6a1183b626c7c3d5fc7a03da6d67f7a

## What the diff does (web/app/page.tsx + web/app/components/proof_showcase.tsx + doc)
1. page.tsx: hero pill "Sovereign Canadian deep research" -> "Canadian-hosted deep research"
   (correctness: honest sovereignty); pillar "Sovereign" -> "Canadian-hosted" (honest body);
   compacted hero spacing (gap-12 py-10/12, hero gap-4) so ProofShowcase enters first viewport;
   pillars plain columns -> crafted elevation cards (bg-card ring shadow-card hover). Preserved:
   home-hero-search (testid + action=/intake + Verify focus-visible), MapleLeafSignatureLazy,
   ProofShowcase, RecentRunsStrip, SiteFooter, single <header> via HomeKeyboardShell.
2. proof_showcase.tsx: shadow-sm -> shadow-card + hover (it's the front-door centerpiece now);
   mobile overflow fix (grid cells min-w-0; claim + blockquote break-words/hyphens; CTA row
   flex-wrap). data-testid="proof-showcase" + real-data logic unchanged.
3. docs/web/s_tier_design_system.md: Home per-screen grade.

## Verification
- typecheck clean; prettier ok; eslint 0 errors.
- e2e home_g1_g8: 4/6 pass (G1 header, G3 focus-visible, G5 3 viewports, form->/intake). G2
  (no-banned-dev-language) + G8 (zero-console) FAIL — but PROVEN PRE-EXISTING: G2 uses
  body.textContent() which includes the RSC `<script>` payload, catching the unchanged Input's
  `placeholder:text-muted-foreground` class + `placeholder=` attr (`/\bplaceholder\b/i`). Ran
  the same check against the live BASELINE prod home (pre-this-change) → it matches too. My
  diff is CSS+copy only; touches no Input, no test, adds no "placeholder". Follow-up: switch G2
  to innerText like the inspector spec.

## Review focus
- Honest-sovereignty: confirm no residual present-tense overclaim copy.
- e2e contract preserved (single <header>/<main>, home-hero-search -> /intake, Verify
  focus-visible). Confirm my read that G2/G8 are pre-existing (not introduced here).
- No fabricated proof (ProofShowcase real-data path untouched). Tokens only; brand #c8102e.

## The diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index a608c8bf..4d684daf 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -79,6 +79,14 @@ span highlights, and verdict badges appear consistently across the product.
   mobile evidence-card density lives in the Proof Replay split-view internals (separate
   component issue); the lower-left "N" badge in dev captures is the Next.js dev indicator
   (absent in production builds).
-- Pre-redo baseline (Codex, 2026-05-23): Home B, Intake B−, Contracts B− (post first
-  rebuild), Sign-in B−, Upload C+, Pin Replay C. Target every screen at A++/S with the
-  signature move systematized.
+- **Home** (#835, I-p2-044): **desktop A / fold A− / mobile A−** (Codex visual iter-2
+  APPROVE). Fixed the "Sovereign Canadian deep research" present-tense overclaim → honest
+  "Canadian-hosted deep research"; compacted the hero so the real ProofShowcase enters the
+  first viewport as the front-door artifact (brand-tinted elevation); pillars are crafted
+  cards; mobile proof overflow fixed (min-w-0 + break-words). Known pre-existing (not this
+  PR): `home_g1_g8` G2/G8 use `body.textContent()` (catches the Input's `placeholder:` class
+  in the RSC payload) — proven to fail on the baseline too; fix = switch to `innerText` like
+  the inspector spec (follow-up).
+- Pre-redo baseline (Codex, 2026-05-23): Intake B−, Contracts B− (post first rebuild),
+  Sign-in B−, Upload C+, Pin Replay C. Target every screen at A++/S with the signature move
+  systematized.
diff --git a/web/app/components/proof_showcase.tsx b/web/app/components/proof_showcase.tsx
index affe06fe..f7d70201 100644
--- a/web/app/components/proof_showcase.tsx
+++ b/web/app/components/proof_showcase.tsx
@@ -74,7 +74,7 @@ export async function ProofShowcase() {
     <section
       aria-label="A real verified claim"
       data-testid="proof-showcase"
-      className="border-border bg-card relative overflow-hidden rounded-2xl border shadow-sm"
+      className="ring-foreground/10 bg-card shadow-card ease-standard hover:shadow-card-hover relative overflow-hidden rounded-2xl ring-1 transition-shadow duration-150"
     >
       <div className="border-border/70 bg-muted/30 flex items-center justify-between gap-3 border-b px-5 py-3">
         <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
@@ -89,12 +89,12 @@ export async function ProofShowcase() {
 
       <div className="grid gap-0 md:grid-cols-2">
         {/* The claim + verdict */}
-        <div className="flex flex-col gap-3 p-6">
+        <div className="flex min-w-0 flex-col gap-3 p-6">
           <div className="text-verified inline-flex items-center gap-1.5 text-xs font-semibold">
             <BadgeCheck aria-hidden className="h-4 w-4" />
             Verified against a primary source
           </div>
-          <p className="text-foreground text-lg leading-relaxed font-medium text-pretty">
+          <p className="text-foreground text-lg leading-relaxed font-medium text-pretty break-words">
             {claim}
           </p>
           {question ? (
@@ -106,12 +106,12 @@ export async function ProofShowcase() {
         </div>
 
         {/* The exact real source span — the proof */}
-        <div className="border-border/70 bg-muted/20 flex flex-col gap-3 border-t p-6 md:border-t-0 md:border-l">
+        <div className="border-border/70 bg-muted/20 flex min-w-0 flex-col gap-3 border-t p-6 md:border-t-0 md:border-l">
           <div className="text-muted-foreground inline-flex items-center gap-1.5 text-xs font-medium">
             <Quote aria-hidden className="h-4 w-4" />
             The exact passage it came from
           </div>
-          <blockquote className="border-primary/40 text-muted-foreground border-l-2 pl-3 text-sm leading-relaxed">
+          <blockquote className="border-primary/40 text-muted-foreground border-l-2 pl-3 text-sm leading-relaxed break-words hyphens-auto">
             {ctx ? (
               <span className="font-serif">
                 {ctx.leadingEllipsis ? "… " : "“"}
@@ -148,7 +148,7 @@ export async function ProofShowcase() {
         </div>
       </div>
 
-      <div className="border-border/70 flex items-center justify-between gap-3 border-t px-5 py-3">
+      <div className="border-border/70 flex flex-wrap items-center justify-between gap-x-3 gap-y-2 border-t px-5 py-3">
         <span className="text-muted-foreground text-xs">
           Every sentence in a POLARIS brief is checked this way.
         </span>
diff --git a/web/app/page.tsx b/web/app/page.tsx
index 2d5f9e23..ad50b0bb 100644
--- a/web/app/page.tsx
+++ b/web/app/page.tsx
@@ -110,8 +110,8 @@ const PILLARS = [
   },
   {
     icon: ShieldCheck,
-    title: "Sovereign",
-    body: "Built for Canadian-hosted, sovereign deployment. Public sources are fetched via logged Canadian egress, and every brief is integrity-hashed and auditable.",
+    title: "Canadian-hosted",
+    body: "Built for Canadian-hosted deployment. Public sources are fetched via logged Canadian egress, and every brief is integrity-hashed and auditable.",
   },
   {
     icon: Network,
@@ -124,13 +124,17 @@ export default function HomePage() {
   return (
     <div className="flex min-h-screen flex-col">
       <HomeKeyboardShell templates={templates} signInHref="/sign-in">
-        <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-14 px-6 py-14 sm:py-16">
-          {/* Hero — one primary action */}
-          <section className="flex flex-col items-center gap-5 text-center">
+        <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-12 px-6 py-10 sm:py-12">
+          {/* Hero — one primary action, compact so the proof artifact enters the
+              first viewport (I-p2-044 #835, Codex visual direction: proof leads). */}
+          <section className="flex flex-col items-center gap-4 text-center">
             {/* I-p2-028 (#767): Braille maple-leaf signature (decorative). */}
             <MapleLeafSignatureLazy />
-            <span className="text-muted-foreground border-border inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs">
-              ⬡ Sovereign Canadian deep research
+            {/* I-p2-044 (#835): honest wording — "Canadian-hosted", not the
+                present-tense "Sovereign" overclaim (LLM inference is routed via
+                OpenRouter-US, disclosed at /transparency). */}
+            <span className="text-muted-foreground border-border bg-card inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs">
+              ⬡ Canadian-hosted deep research
             </span>
             <h1 className="text-foreground max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
               Deep research you can check, line by line.
@@ -160,16 +164,20 @@ export default function HomePage() {
             </form>
           </section>
 
-          {/* Proof-as-hero — a REAL verified claim + its real source span */}
+          {/* Proof IS the hero — a REAL verified claim + its real source span, the
+              central front-door artifact (not a card below the fold). */}
           <ProofShowcase />
 
-          {/* Differentiator pillars */}
+          {/* Differentiator pillars — crafted cards (was plain text columns) */}
           <section
             aria-label="Why POLARIS"
-            className="border-border/60 grid gap-8 border-t pt-12 sm:grid-cols-3"
+            className="grid gap-4 sm:grid-cols-3"
           >
             {PILLARS.map((pillar) => (
-              <div key={pillar.title} className="flex flex-col gap-2">
+              <div
+                key={pillar.title}
+                className="group/pillar bg-card ring-foreground/10 shadow-card ease-standard hover:shadow-card-hover flex flex-col gap-2 rounded-xl p-5 ring-1 transition-shadow duration-150"
+              >
                 <pillar.icon
                   aria-hidden
                   className="text-primary h-5 w-5 shrink-0"

# canonical-diff-sha256: 38e6f595b7a1c592aa93ed82ffddfe89f6a1183b626c7c3d5fc7a03da6d67f7a

```
