# Codex Diff Review — I-f3-008 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-008 — evidence toggle (UI only, accessor-via-DOM)
**Brief:** APPROVED iter 2 (iter1 REQ_CH server/client boundary → iter2 APPROVE 0/0/1P2)
**Canonical-diff-sha256:** `a829357bba248248c58cb6a7de22087b805e31fdc9ecea26536068ecf0ccb07a`
**LOC:** 145 net (under 200-cap by 55)

## Files

```
web/app/upload/components/upload_drop_zone.tsx           EDIT  +41/-5
web/app/upload/components/selected_docs_indicator.tsx    NEW   +19
web/app/upload/components/upload_workspace.tsx           NEW   +16
web/app/upload/page.tsx                                  EDIT  +2/-2
web/tests/e2e/upload_evidence_toggle.spec.ts             NEW   +70
```

## What changed

- `UploadDropZone` accepts `onSelectionChange?` prop; per-file `included: boolean` (default true on completed); `useEffect([files])` recomputes & calls back; new toggle checkbox in row when status === completed.
- `SelectedDocsIndicator` (NEW) — `ids: string[]` prop; renders `<output data-testid="selected-doc-ids">`.
- `UploadWorkspace` (NEW, client) — owns `selectedDocIds` state; bridges `UploadDropZone` callback to indicator props.
- `page.tsx` server component swaps `<UploadDropZone>` mount → `<UploadWorkspace>`.
- 1 e2e test: drop 2 files → both included → uncheck first → indicator shows only second → re-check → both again.

## Iter-2 brief P2 addressed

P2 (selected_docs_indicator props clarification): Implementation uses ids-driven display (no internal state); Codex's recommended pattern.

## Risks for Codex Red-Team

1. **Server/client boundary.** UploadWorkspace is the client island; page.tsx stays server.
2. **`useEffect` infinite-loop guard.** Effect deps: `[files, onSelectionChange]`. `onSelectionChange` is `setSelectedDocIds` (stable React setter); files state changes only on user action or async upload completion. No loop.
3. **Default `included=true`.** Newly-completed files auto-join selection. Matches user expectation.
4. **CHARTER §1 LOC cap.** 145 net.
5. **No new package.json dep.**
6. **Backwards-compat with prior tests.** Existing parse-status and doc-preview tests still pass (UploadDropZone signature uses optional prop with default).
7. **Toggle gating.** Checkbox renders only on `status === "completed" && parse_status === "completed"`. Pending uploads / errored files do NOT show toggle.

## Out of scope

- Wiring selected doc_ids into intake/retrieval/generation → I-f3-008b follow-up.

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
diff --git a/web/app/upload/components/selected_docs_indicator.tsx b/web/app/upload/components/selected_docs_indicator.tsx
new file mode 100644
index 0000000..ae5c8b3
--- /dev/null
+++ b/web/app/upload/components/selected_docs_indicator.tsx
@@ -0,0 +1,19 @@
+"use client";
+
+type Props = { ids: string[] };
+
+export function SelectedDocsIndicator({ ids }: Props) {
+  return (
+    <div className="border-border bg-muted/10 flex flex-col gap-1 rounded-lg border p-3 text-sm">
+      <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
+        Selected docs
+      </span>
+      <output
+        data-testid="selected-doc-ids"
+        className="text-foreground text-xs"
+      >
+        {ids.length === 0 ? "(none)" : ids.join(",")}
+      </output>
+    </div>
+  );
+}
diff --git a/web/app/upload/components/upload_drop_zone.tsx b/web/app/upload/components/upload_drop_zone.tsx
index a0cd71e..c1b32c9 100644
--- a/web/app/upload/components/upload_drop_zone.tsx
+++ b/web/app/upload/components/upload_drop_zone.tsx
@@ -1,6 +1,6 @@
 "use client";
 
-import { useId, useRef, useState } from "react";
+import { useEffect, useId, useRef, useState } from "react";
 
 import { getUpload, uploadDocument, type UploadResponse } from "@/lib/api";
 
@@ -19,6 +19,11 @@ type FileEntry = {
   response?: UploadResponse;
   parse_status?: ParseStatus;
   chunk_preview_count?: number;
+  included?: boolean;
+};
+
+type UploadDropZoneProps = {
+  onSelectionChange?: (docIds: string[]) => void;
 };
 
 const POLL_MAX = 10;
@@ -45,13 +50,31 @@ const extOf = (n: string) => {
   return i === -1 ? "" : n.slice(i).toLowerCase();
 };
 
-export function UploadDropZone() {
+export function UploadDropZone({
+  onSelectionChange,
+}: UploadDropZoneProps = {}) {
   const baseId = useId();
   const [files, setFiles] = useState<FileEntry[]>([]);
   const [openPreviewDocId, setOpenPreviewDocId] = useState<string | null>(null);
   const inputRef = useRef<HTMLInputElement>(null);
   let counter = 0;
 
+  useEffect(() => {
+    if (!onSelectionChange) return;
+    const ids = files
+      .filter((f) => f.included && f.parse_status === "completed" && f.response)
+      .map((f) => f.response!.document_id);
+    onSelectionChange(ids);
+  }, [files, onSelectionChange]);
+
+  const toggleIncluded = (id: string) => {
+    setFiles((p) =>
+      p.map((e) =>
+        e.id === id ? { ...e, included: !(e.included ?? true) } : e,
+      ),
+    );
+  };
+
   const handleFiles = async (incoming: FileList | File[]) => {
     for (const f of Array.from(incoming)) {
       const id = `${baseId}-${counter++}-${Date.now()}`;
@@ -93,6 +116,7 @@ export function UploadDropZone() {
                   response,
                   parse_status: ps,
                   chunk_preview_count: response.chunk_preview.length,
+                  included: true,
                 }
               : e,
           ),
@@ -159,7 +183,18 @@ export function UploadDropZone() {
               data-status={f.status}
               className="border-border bg-muted/20 flex items-center justify-between gap-2 rounded-lg border p-3 text-sm"
             >
-              <span className="text-foreground truncate">{f.name}</span>
+              <span className="flex items-center gap-2">
+                {f.status === "completed" && f.parse_status === "completed" && (
+                  <input
+                    type="checkbox"
+                    data-testid={`include-toggle-${f.id}`}
+                    checked={f.included ?? true}
+                    onChange={() => toggleIncluded(f.id)}
+                    aria-label={`Include ${f.name} in evidence pool`}
+                  />
+                )}
+                <span className="text-foreground truncate">{f.name}</span>
+              </span>
               <span className="text-muted-foreground text-xs">
                 {f.status === "uploading" && "uploading…"}
                 {f.status === "completed" && f.response && (
diff --git a/web/app/upload/components/upload_workspace.tsx b/web/app/upload/components/upload_workspace.tsx
new file mode 100644
index 0000000..cb3e006
--- /dev/null
+++ b/web/app/upload/components/upload_workspace.tsx
@@ -0,0 +1,16 @@
+"use client";
+
+import { useState } from "react";
+
+import { SelectedDocsIndicator } from "./selected_docs_indicator";
+import { UploadDropZone } from "./upload_drop_zone";
+
+export function UploadWorkspace() {
+  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([]);
+  return (
+    <div className="flex flex-col gap-4">
+      <UploadDropZone onSelectionChange={setSelectedDocIds} />
+      <SelectedDocsIndicator ids={selectedDocIds} />
+    </div>
+  );
+}
diff --git a/web/app/upload/page.tsx b/web/app/upload/page.tsx
index f308c1e..e6e38e9 100644
--- a/web/app/upload/page.tsx
+++ b/web/app/upload/page.tsx
@@ -1,4 +1,4 @@
-import { UploadDropZone } from "./components/upload_drop_zone";
+import { UploadWorkspace } from "./components/upload_workspace";
 
 export const metadata = {
   title: "Upload — POLARIS Canada",
@@ -23,7 +23,7 @@ export default function UploadPage() {
         </p>
       </section>
 
-      <UploadDropZone />
+      <UploadWorkspace />
     </main>
   );
 }
diff --git a/web/tests/e2e/upload_evidence_toggle.spec.ts b/web/tests/e2e/upload_evidence_toggle.spec.ts
new file mode 100644
index 0000000..6542d7f
--- /dev/null
+++ b/web/tests/e2e/upload_evidence_toggle.spec.ts
@@ -0,0 +1,70 @@
+import { expect, test } from "@playwright/test";
+
+const DOC_A = "doc-evidence-toggle-A";
+const DOC_B = "doc-evidence-toggle-B";
+
+test("evidence toggle: 2 docs upload → both included → toggle off → only one in selection", async ({
+  page,
+}) => {
+  let postCount = 0;
+  await page.route("**/upload", async (route) => {
+    if (route.request().method() !== "POST") return route.continue();
+    postCount++;
+    const docId = postCount === 1 ? DOC_A : DOC_B;
+    await route.fulfill({
+      status: 201,
+      contentType: "application/json",
+      body: JSON.stringify({
+        document_id: docId,
+        filename: `f${postCount}.md`,
+        bytes: 100,
+        sha256: "stub",
+        classification: "UNKNOWN",
+        parse_status: "completed",
+        chunk_preview: ["chunk a", "chunk b"],
+        content: "chunk a\nchunk b",
+        html: "<p>chunk a</p><p>chunk b</p>",
+      }),
+    });
+  });
+
+  await page.goto("/upload");
+
+  // Drop two .md files
+  await page.evaluate(() => {
+    const dt = new DataTransfer();
+    dt.items.add(
+      new File([new Uint8Array(100)], "a.md", { type: "text/markdown" }),
+    );
+    dt.items.add(
+      new File([new Uint8Array(100)], "b.md", { type: "text/markdown" }),
+    );
+    document.querySelector('[data-testid="upload-dropzone"]')!.dispatchEvent(
+      new DragEvent("drop", {
+        dataTransfer: dt,
+        bubbles: true,
+        cancelable: true,
+      }),
+    );
+  });
+
+  // Both completed; both included by default
+  await expect(page.locator('[data-testid^="include-toggle-"]')).toHaveCount(2);
+  const indicator = page.getByTestId("selected-doc-ids");
+  await expect(indicator).toContainText(DOC_A);
+  await expect(indicator).toContainText(DOC_B);
+
+  // Toggle off the first
+  const firstToggle = page.locator('[data-testid^="include-toggle-"]').first();
+  await firstToggle.uncheck();
+
+  // Indicator should now only contain ONE doc id
+  const text = (await indicator.textContent()) ?? "";
+  const idCount = (text.match(/doc-evidence-toggle-/g) ?? []).length;
+  expect(idCount).toBe(1);
+
+  // Toggle back on
+  await firstToggle.check();
+  await expect(indicator).toContainText(DOC_A);
+  await expect(indicator).toContainText(DOC_B);
+});

```
