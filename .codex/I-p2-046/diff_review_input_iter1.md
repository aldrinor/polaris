# Codex DIFF review — I-p2-046 (#839): Contracts editor S-rebuild

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
- Brief APPROVE (iter 1). Visual `-i` APPROVE (iter 2: desktop A / mobile A-; iter-1 P1 sticky
  overlay fixed by making the bar static).
- canonical-diff-sha256: 51106d3d19f2f4a7be6d5bf1327e5fb1262f8c49148ddb9a4113a91511c637e5

## What the diff does (web/app/contracts/_editor.tsx + doc)
1. SELECT_CLASS: h-8 → h-9 (match Input) + ease-standard/duration-150.
2. Submit area: bare `<div flex>` → a STATIC crafted action bar (bg-card ring-1 ring-foreground/10
   shadow-card rounded-xl px-4 py-3) holding the submit + an explainer span (or contract-saved).
   Still inside <form>; contract-submit + contract-saved testids unchanged. NOT sticky (iter-1
   sticky version overlaid fields).
3. Jurisdiction chip className: added ease-standard/duration-150.
4. Entity row: `flex items-center` → `flex flex-col gap-2 sm:flex-row sm:items-center` (mobile
   stacks so the name input doesn't truncate).
5. doc grade.

## Verification
- typecheck clean; prettier ok; eslint 0 errors.
- e2e contracts_g1_g8 4/4 pass (1 header/1 main, no banned dev-language, nav parity, no console
  errors). contract_editor submit spec needs the save backend (not up in dev) — unchanged path.

## Review focus
- contract-submit still inside <form> (submits) + contract-saved still rendered; no testid
  changed. The native <select> stays native (ce-ent-type-* fill/select compat). Tokens only;
  brand #c8102e untouched. No logic change to save/validation.

## The diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index ecf515b6..f0143fdd 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -95,5 +95,10 @@ span highlights, and verdict badges appear consistently across the product.
   + enlarged hero input + a factual 3-step "how it works" band (ask → scope-checked → verified
   brief) filling the surface. Restored the eyebrow string the existing `intake.spec` asserts
   (stale since the #613 rebuild) — a design element, not a test relaxation.
-- Pre-redo baseline (Codex, 2026-05-23): Contracts B− (post first rebuild), Sign-in B−,
-  Upload C+, Pin Replay C. Target every screen at A++/S with the signature move systematized.
+- **Contracts** (#839, I-p2-046): **desktop A / mobile A−** (Codex visual iter-2 APPROVE). A
+  crafted static "Save + download" action bar (ring + brand shadow + explainer; iter-1 sticky
+  version overlaid fields → made static), entity-type select height matched to inputs, chips +
+  selects on the shared motion primitive, mobile entity row stacks. All field logic/testids
+  preserved.
+- Pre-redo baseline (Codex, 2026-05-23): Sign-in B−, Upload C+, Pin Replay C. Target every
+  screen at A++/S with the signature move systematized.
diff --git a/web/app/contracts/_editor.tsx b/web/app/contracts/_editor.tsx
index 4fa161f2..0dc4f1c1 100644
--- a/web/app/contracts/_editor.tsx
+++ b/web/app/contracts/_editor.tsx
@@ -32,7 +32,7 @@ const TIER_META = [
 ] as const;
 
 const SELECT_CLASS =
-  "border-input focus-visible:border-ring focus-visible:ring-ring/70 h-8 rounded-lg border bg-transparent px-2.5 text-sm transition-colors outline-none focus-visible:ring-3";
+  "border-input focus-visible:border-ring focus-visible:ring-ring/70 ease-standard h-9 rounded-lg border bg-transparent px-2.5 text-sm transition-colors duration-150 outline-none focus-visible:ring-3";
 
 function FieldLabel({
   children,
@@ -172,7 +172,7 @@ export function ContractEditor() {
                 return (
                   <label
                     key={j}
-                    className={`focus-within:ring-ring/70 cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-within:ring-2 ${
+                    className={`focus-within:ring-ring/70 ease-standard cursor-pointer rounded-full border px-3 py-1 text-xs font-medium transition-colors duration-150 focus-within:ring-2 ${
                       active
                         ? "border-primary bg-primary/10 text-foreground"
                         : "border-border text-muted-foreground hover:bg-muted"
@@ -228,7 +228,10 @@ export function ContractEditor() {
         </CardHeader>
         <CardContent className="flex flex-col gap-3">
           {entities.map((ent, i) => (
-            <div key={i} className="flex items-center gap-2">
+            <div
+              key={i}
+              className="flex flex-col gap-2 sm:flex-row sm:items-center"
+            >
               <Input
                 data-testid={`ce-ent-name-${i}`}
                 placeholder="Entity name (e.g. tirzepatide)"
@@ -432,7 +435,11 @@ export function ContractEditor() {
         </div>
       )}
 
-      <div className="flex items-center gap-3">
+      {/* I-p2-046 (#839): crafted action bar (ring + brand shadow + explainer) — a
+          static dock at the form end, NOT sticky, so it never overlays editable
+          fields (Codex visual iter-1 P1). Inside <form> so contract-submit submits;
+          contract-saved + contract-errors testids unchanged. */}
+      <div className="bg-card ring-foreground/10 shadow-card mt-1 flex flex-wrap items-center gap-3 rounded-xl px-4 py-3 ring-1">
         <Button
           type="submit"
           data-testid="contract-submit"
@@ -440,13 +447,18 @@ export function ContractEditor() {
         >
           Save + download
         </Button>
-        {saved && (
+        {saved ? (
           <p
             data-testid="contract-saved"
             className="text-verified text-sm font-medium"
           >
             Contract {saved.contract_id.slice(0, 8)} saved.
           </p>
+        ) : (
+          <span className="text-muted-foreground text-xs">
+            Downloads the signed contract JSON. The Evidence Contract Gate
+            enforces it before generation runs.
+          </span>
         )}
       </div>
     </form>

# canonical-diff-sha256: 51106d3d19f2f4a7be6d5bf1327e5fb1262f8c49148ddb9a4113a91511c637e5

```
