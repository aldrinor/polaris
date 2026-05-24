# Codex DIFF review — I-p2-048 (#843): Pin Replay empty-state S-rebuild

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
- Brief APPROVE (iter 1). Visual `-i` APPROVE (iter 1: desktop A / mobile A-).
- canonical-diff-sha256: e3ea3c19a0ebc5e3632b71822855d14d3f861450ef34615b7ab6068416caaed8

## What the diff does (web/app/pin_replay/page.tsx EmptyPinReplay + doc)
- Inside EmptyPinReplay only: added a ghost-timeline preview card (a `bg-card ring/shadow`
  block) with a caption + an aria-hidden skeleton (a flex row of 7 `bg-muted` bars of fixed
  Tailwind heights — a chart silhouette — each with a `bg-primary/15` ghost node + a
  `bg-muted/70` ghost label) + a one-line concept caption. SKELETON SHAPES ONLY: no dates,
  counts, verdicts, deltas, or source names. Mobile: bars are flex-1 min-w-0 so they shrink.
- `pin-replay-empty` testid + the EmptyState (icon/title/CTA) preserved.
- doc grade.

## Verification
- typecheck clean; prettier ok; eslint 0 errors.
- e2e pin_replay_g1_g8: 3/4 pass (G1/G6 single header+main, G2 no banned dev-language, nav
  parity). G8 (zero console) FAILS on a Next-16 RSC warning "Only plain objects can be passed
  to Client Components from Server Components. Set objects are not supported." PROVEN
  PRE-EXISTING: I stashed my edit and re-ran G8 against baseline — it fails identically. My
  diff adds only static JSX (string-array of height classes + spans) — no Set, no server→client
  prop. The populated-state spec needs pinned data the demo lacks (#627) — untouched.

## Review focus
- Confirm the skeleton is data-free (no fabricated values) + aria-hidden; `pin-replay-empty`
  + EmptyState preserved; populated path byte-identical; G8 is pre-existing (not introduced).
  Tokens only; brand #c8102e.

## The diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index e0dd8251..efc3ac90 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -105,5 +105,11 @@ span highlights, and verdict badges appear consistently across the product.
   focus + motion; drag-depth counter to avoid child-flicker), tokenized error, and a factual
   3-step "what happens after upload" band + /intake link filling the empty surface. Logic +
   testids preserved.
-- Pre-redo baseline (Codex, 2026-05-23): Sign-in B−, Pin Replay C. Target every screen at
-  A++/S with the signature move systematized.
+- **Pin Replay** (#843, I-p2-048): **empty state desktop A / mobile A−** (Codex visual iter-1
+  APPROVE). In the demo the registry is empty (since #627) so the empty state is the only
+  visible state; added a ghost-timeline skeleton (data-free) + concept caption so the page
+  makes the temporal-drift differentiator tangible. Known pre-existing (NOT this PR, proven on
+  baseline): `pin_replay_g1_g8` G8 fails on a Next-16 RSC `Set`-serialization warning ("Set
+  objects are not supported" server→client) — follow-up.
+- Pre-redo baseline (Codex, 2026-05-23): Sign-in B−. Target every screen at A++/S with the
+  signature move systematized.
diff --git a/web/app/pin_replay/page.tsx b/web/app/pin_replay/page.tsx
index 9d13252e..ea60777a 100644
--- a/web/app/pin_replay/page.tsx
+++ b/web/app/pin_replay/page.tsx
@@ -95,6 +95,40 @@ function EmptyPinReplay() {
         up the snapshots so you can see how the evidence and the verified answer
         shift over time.
       </p>
+
+      {/* I-p2-048 (#843): a ghost-timeline preview — skeleton shapes only, NO
+          data (no dates/counts/verdicts) — makes the temporal-drift concept
+          tangible while there are no pins yet. Decorative: aria-hidden + one
+          caption. */}
+      <div className="border-border bg-card shadow-card mb-6 flex flex-col gap-5 rounded-xl border p-6">
+        <p className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
+          Your pinned runs line up here as a timeline
+        </p>
+        <div
+          aria-hidden
+          className="flex items-end justify-between gap-2 sm:gap-4"
+        >
+          {["h-10", "h-16", "h-12", "h-20", "h-14", "h-24", "h-16"].map(
+            (h, i) => (
+              <div
+                key={i}
+                className="flex min-w-0 flex-1 flex-col items-center gap-2"
+              >
+                <span
+                  className={`bg-muted w-full rounded-md ${h} ${i % 2 ? "" : "animate-pulse"}`}
+                />
+                <span className="bg-primary/15 h-2.5 w-2.5 rounded-full" />
+                <span className="bg-muted/70 h-1.5 w-8 max-w-full rounded-full" />
+              </div>
+            ),
+          )}
+        </div>
+        <p className="text-muted-foreground/70 text-xs">
+          Each pin becomes a point on this timeline — verified-claim rate and
+          evidence shifts, side by side.
+        </p>
+      </div>
+
       <EmptyState
         icon={History}
         title="No pinned runs yet"

# canonical-diff-sha256: e3ea3c19a0ebc5e3632b71822855d14d3f861450ef34615b7ab6068416caaed8

```
