# Codex Diff Review — I-f2-004 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-004 — Frontend disambiguation modal (2/3/5 variants)
**Branch:** bot/I-f2-004
**Brief:** APPROVED iter 3 (iter1 REQ_CH 2P1 → iter2 REQ_CH 1P1 → iter3 APPROVE 0/0 + 3 P2 advisories addressed in implementation)
**Canonical-diff-sha256:** `d02a17d71965141a4f45cd2b2d4f5462130bff1da0e7860524a3f6a47d014782`
**LOC:** 196 net (CHARTER §1 hard cap = 200; 4 under)
**Type-check:** `npx tsc --noEmit` clean.
**Format:** `npx prettier --check` clean (iter-1 P1 Prettier finding addressed in this iter 2).

## Files

```
web/app/intake/components/disambiguation_modal.tsx                    NEW +101
web/app/(test_harness)/disambiguation_modal_preview/page.tsx          NEW +15
web/app/(test_harness)/disambiguation_modal_preview/_client.tsx       NEW +46
web/tests/e2e/disambiguation_modal.spec.ts                            NEW +34
```

## Iter-1 P1 resolution (Prettier)

`npx prettier --write` ran on all 4 files; `npx prettier --check` now reports
"All matched files use Prettier code style!" Files reflowed by Prettier; the
diff is functionally identical to iter-1 modulo formatting.

## What changed

### `disambiguation_modal.tsx` (Client Component)

Exports:
- `DisambiguationCluster` type: `{cluster_id, label, sample_snippets}`.
- `DisambiguationModalProps` type: `{open, clusters, onSelectCluster, onCancel}`.
- `DisambiguationModal` function (PascalCase exception per CLAUDE.md §4.1).

Renders DialogPrimitive Root+Portal+Backdrop+Popup mirroring `ambiguity_modal.tsx:25-49`. Title "Did you mean…" + Description "We found multiple meanings. Pick one to focus the search."

Body: `<ul>` of `<button>` cluster cards. Each has:
- `data-testid="disambiguation-cluster-${cluster_id}"`,
- `aria-label="Pick {label}"`,
- focus-visible ring,
- bold label + first 2 sample_snippets joined with " · " (truncated to MAX_SAMPLE_LEN=80 chars).

Footer: single Cancel button (DialogPrimitive.Close render-prop).

Cancel idempotency latch: `is_cancelled_ref = useRef(false)`. `handleCancel` short-circuits second invocation. Reset on `open` → true via `useEffect([open])`.

Empty `clusters=[]` defensive: renders Title+Description+Cancel only.

### `(test_harness)/disambiguation_modal_preview/page.tsx` (Server Component)

- `export const metadata = {robots: {index: false, follow: false}}`.
- `async function Page({ searchParams }: { searchParams: Promise<{n?: string}> })` awaits searchParams, computes `count = n === "5" ? 5 : n === "3" ? 3 : 2`, renders `<DisambiguationModalHarnessClient count={count} />`.
- No `notFound()` — keeps the route reachable under `next start` (CI). `metadata.robots.index = false` is the production gate.

### `(test_harness)/disambiguation_modal_preview/_client.tsx` (Client Component)

- `"use client"`.
- `FIXTURE_CLUSTERS` constant: 5 entries (syndrome, institute, chemical, company, course).
- `DisambiguationModalHarnessClient({count})`: state `[open, lastPicked]`. Renders modal with `clusters=FIXTURE_CLUSTERS.slice(0, count)`. `<output data-testid="last-picked">` + `<button data-testid="reopen">` for Playwright assertions.

### `tests/e2e/disambiguation_modal.spec.ts`

3 tests, one per `n in [2, 3, 5]`:
1. `goto /disambiguation_modal_preview?n=N`.
2. Assert `disambiguation-cluster-0` is visible.
3. Assert `[data-testid^="disambiguation-cluster-"]` `toHaveCount(n)` (Codex iter-3 P2 #2 fix).
4. Assert each `disambiguation-cluster-${i}` for `i in [0, n)` is visible.
5. Click `disambiguation-cluster-1` → assert `last-picked` text == "1".
6. Click `reopen`; press Esc → `last-picked` text == "".
7. Assert `document.documentElement.scrollWidth <= 1280`.

## Iter-3 brief P2 advisories addressed in implementation

- **P2 #1 (harness 404 in prod vs `next start` in CI):** harness does NOT 404 in production; relies on `metadata.robots.index = false` + no nav linking.
- **P2 #2 (exact-count assertion):** `toHaveCount(n)` per variant.
- **P2 #3 (`count={count}` prop name):** consistent server→client wiring.

## Risks for Codex Red-Team

1. **Server/Client split.** `page.tsx` server-only (metadata + searchParams.await + render); `_client.tsx` client-only (`"use client"` + state). No `metadata` + `"use client"` collision.

2. **Underscore-prefixed `_client.tsx`.** Next 16 routes folders containing `page.tsx`/`route.ts` only; sibling `_client.tsx` is imported, not routed. Verified via Next docs.

3. **Route group `(test_harness)`.** Parens stripped from URL → resolves at `/disambiguation_modal_preview`.

4. **No `notFound()` in prod.** Codex iter-3 P2 #1 chose this trade-off: harness IS reachable in production but `noindex`'d. The route is unlinked from any user-facing surface, so it's effectively dead in production.

5. **Cancel idempotency.** `useRef` latch prevents double-invocation. Reset via `useEffect([open])`. Tested implicitly via reopen + Esc pattern.

6. **`searchParams: Promise<{n?: string}>`.** Next 16 convention. Server Component awaits.

7. **Empty clusters defensive.** Component renders Title+Description+Cancel only; no `<ul>` wrapper.

8. **Tailwind class strings.** Copy-paste from `ambiguity_modal.tsx`. Visual consistency.

9. **No new package.json dep.**

10. **`tsc --noEmit` clean.** No type errors.

11. **No `unittest.mock` in src.** N/A (UI module + harness; not in `src/`). Tests use a static fixture const.

12. **CHARTER §1 LOC cap.** 161 net; well under 200.

13. **Aspect ratio sanity.** Test asserts `scrollWidth <= 1280` (viewport is 1440×900). No horizontal overflow.

14. **`output` element semantics.** `<output data-testid="last-picked">` is a valid HTML5 form output element; semantically correct for displaying a computed value. Could also be a `<span>`; chose `<output>` for accessibility-tree clarity.

15. **`page.keyboard.press("Escape")` and modal Esc handler.** DialogPrimitive's default Esc-dismissal fires `onOpenChange(false)` → `handleCancel` → modal closes. Reopen + Esc + assert empty `last-picked` proves cancel doesn't write.

## Out of scope (do NOT regress on these)

- `runDisambiguation()` API client → I-f2-005.
- Wiring modal into intake page flow → I-f2-005.
- BPEI 3-cluster real-LLM smoke → I-f2-005.
- `ambiguity_modal.tsx` pre-existing potential double-cancel → follow-up Issue.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.


## Diff to review

```diff
diff --git a/web/app/(test_harness)/disambiguation_modal_preview/_client.tsx b/web/app/(test_harness)/disambiguation_modal_preview/_client.tsx
new file mode 100644
index 0000000..28ba523
--- /dev/null
+++ b/web/app/(test_harness)/disambiguation_modal_preview/_client.tsx
@@ -0,0 +1,46 @@
+"use client";
+
+import { useState } from "react";
+
+import {
+  DisambiguationModal,
+  type DisambiguationCluster,
+} from "@/app/intake/components/disambiguation_modal";
+
+const FIXTURE_CLUSTERS: DisambiguationCluster[] =
+  "syndrome,institute,chemical,company,course".split(",").map((label, i) => ({
+    cluster_id: i,
+    label,
+    sample_snippets: [`sample ${label} snippet`],
+  }));
+
+export function DisambiguationModalHarnessClient({ count }: { count: number }) {
+  const [open, setOpen] = useState(true);
+  const [lastPicked, setLastPicked] = useState<number | null>(null);
+  return (
+    <>
+      <DisambiguationModal
+        open={open}
+        clusters={FIXTURE_CLUSTERS.slice(0, count)}
+        onSelectCluster={(cid) => {
+          setLastPicked(cid);
+          setOpen(false);
+        }}
+        onCancel={() => setOpen(false)}
+      />
+      <output data-testid="last-picked">
+        {lastPicked === null ? "" : String(lastPicked)}
+      </output>
+      <button
+        type="button"
+        data-testid="reopen"
+        onClick={() => {
+          setLastPicked(null);
+          setOpen(true);
+        }}
+      >
+        Reopen
+      </button>
+    </>
+  );
+}
diff --git a/web/app/(test_harness)/disambiguation_modal_preview/page.tsx b/web/app/(test_harness)/disambiguation_modal_preview/page.tsx
new file mode 100644
index 0000000..c584610
--- /dev/null
+++ b/web/app/(test_harness)/disambiguation_modal_preview/page.tsx
@@ -0,0 +1,15 @@
+import { DisambiguationModalHarnessClient } from "./_client";
+
+export const metadata = {
+  robots: { index: false, follow: false },
+};
+
+export default async function Page({
+  searchParams,
+}: {
+  searchParams: Promise<{ n?: string }>;
+}) {
+  const { n } = await searchParams;
+  const count = n === "5" ? 5 : n === "3" ? 3 : 2;
+  return <DisambiguationModalHarnessClient count={count} />;
+}
diff --git a/web/app/intake/components/disambiguation_modal.tsx b/web/app/intake/components/disambiguation_modal.tsx
new file mode 100644
index 0000000..d0f0955
--- /dev/null
+++ b/web/app/intake/components/disambiguation_modal.tsx
@@ -0,0 +1,101 @@
+"use client";
+
+import { useEffect, useRef } from "react";
+import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";
+
+import { Button } from "@/components/ui/button";
+
+const MAX_SAMPLE_LEN = 80;
+
+export type DisambiguationCluster = {
+  cluster_id: number;
+  label: string;
+  sample_snippets: string[];
+};
+
+export type DisambiguationModalProps = {
+  open: boolean;
+  clusters: DisambiguationCluster[];
+  onSelectCluster: (cluster_id: number) => void;
+  onCancel: () => void;
+};
+
+function previewSnippets(snippets: string[]): string {
+  const joined = snippets.slice(0, 2).join(" · ");
+  return joined.length > MAX_SAMPLE_LEN
+    ? joined.slice(0, MAX_SAMPLE_LEN - 1) + "…"
+    : joined;
+}
+
+export function DisambiguationModal({
+  open,
+  clusters,
+  onSelectCluster,
+  onCancel,
+}: DisambiguationModalProps) {
+  const is_cancelled_ref = useRef(false);
+  useEffect(() => {
+    if (open) is_cancelled_ref.current = false;
+  }, [open]);
+  const handleCancel = () => {
+    if (is_cancelled_ref.current) return;
+    is_cancelled_ref.current = true;
+    onCancel();
+  };
+  return (
+    <DialogPrimitive.Root
+      open={open}
+      onOpenChange={(next_open) => {
+        if (!next_open) handleCancel();
+      }}
+    >
+      <DialogPrimitive.Portal>
+        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/20 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0 supports-backdrop-filter:backdrop-blur-xs" />
+        <DialogPrimitive.Popup
+          data-slot="disambiguation-modal"
+          className="bg-popover text-popover-foreground fixed top-1/2 left-1/2 z-50 flex w-full max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col gap-4 rounded-xl border p-6 shadow-lg transition duration-200 ease-in-out data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0"
+        >
+          <div className="flex flex-col gap-1">
+            <DialogPrimitive.Title className="text-foreground text-lg font-semibold">
+              Did you mean…
+            </DialogPrimitive.Title>
+            <DialogPrimitive.Description className="text-muted-foreground text-sm">
+              We found multiple meanings. Pick one to focus the search.
+            </DialogPrimitive.Description>
+          </div>
+          {clusters.length > 0 && (
+            <ul className="flex flex-col gap-3">
+              {clusters.map((c) => (
+                <li key={c.cluster_id}>
+                  <button
+                    type="button"
+                    data-testid={`disambiguation-cluster-${c.cluster_id}`}
+                    aria-label={`Pick ${c.label}`}
+                    onClick={() => onSelectCluster(c.cluster_id)}
+                    className="border-border bg-muted/30 hover:bg-muted/60 flex w-full flex-col gap-1 rounded-lg border p-3 text-left focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:outline-none"
+                  >
+                    <span className="text-foreground text-sm font-semibold">
+                      {c.label}
+                    </span>
+                    <span className="text-muted-foreground text-xs">
+                      {previewSnippets(c.sample_snippets)}
+                    </span>
+                  </button>
+                </li>
+              ))}
+            </ul>
+          )}
+          <div className="flex justify-end gap-2 pt-2">
+            <DialogPrimitive.Close
+              render={
+                <Button variant="outline" onClick={handleCancel}>
+                  Cancel
+                </Button>
+              }
+            />
+          </div>
+        </DialogPrimitive.Popup>
+      </DialogPrimitive.Portal>
+    </DialogPrimitive.Root>
+  );
+}
diff --git a/web/tests/e2e/disambiguation_modal.spec.ts b/web/tests/e2e/disambiguation_modal.spec.ts
new file mode 100644
index 0000000..cd97aef
--- /dev/null
+++ b/web/tests/e2e/disambiguation_modal.spec.ts
@@ -0,0 +1,34 @@
+import { expect, test } from "@playwright/test";
+
+const VARIANTS: Array<{ n: 2 | 3 | 5 }> = [{ n: 2 }, { n: 3 }, { n: 5 }];
+
+for (const { n } of VARIANTS) {
+  test(`disambiguation modal renders ${n} cluster cards and handles selection + cancel`, async ({
+    page,
+  }) => {
+    await page.goto(`/disambiguation_modal_preview?n=${n}`);
+
+    await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
+    const cards = page.locator('[data-testid^="disambiguation-cluster-"]');
+    await expect(cards).toHaveCount(n);
+
+    for (let i = 0; i < n; i++) {
+      await expect(
+        page.getByTestId(`disambiguation-cluster-${i}`),
+      ).toBeVisible();
+    }
+
+    await page.getByTestId("disambiguation-cluster-1").click();
+    await expect(page.getByTestId("last-picked")).toHaveText("1");
+
+    await page.getByTestId("reopen").click();
+    await expect(page.getByTestId("disambiguation-cluster-0")).toBeVisible();
+    await page.keyboard.press("Escape");
+    await expect(page.getByTestId("last-picked")).toHaveText("");
+
+    const overflows = await page.evaluate(
+      () => document.documentElement.scrollWidth > 1280,
+    );
+    expect(overflows).toBe(false);
+  });
+}

```
