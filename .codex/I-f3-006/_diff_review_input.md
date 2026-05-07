# Codex Diff Review — I-f3-006 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-006 — Frontend per-file parse status (chunks progression)
**Brief:** APPROVED iter 1 (0/0/3P2)
**Canonical-diff-sha256:** `e655d01e0eda44b2f9f392e32b0d4ea7f56b8e58accc767e237f067951fb93fb`
**LOC:** 144 net (under 200-cap by 56)
**Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/lib/api.ts                                          EDIT  +7
web/app/upload/components/upload_drop_zone.tsx          EDIT  +62/-4
web/tests/e2e/upload_parse_status.spec.ts               NEW   +79
```

## What changed

1. `getUpload(document_id)` API client.
2. `UploadDropZone` extension: `parse_status` + `chunk_preview_count` per file. On POST resolution if `parse_status === "queued"`, fire `pollParseStatus()` (10 × 1s cap).
3. UI: stacked rendering — `upload-doc-id` AND `upload-parse-{id}` side by side. Status text: "parsing…", "completed · N chunks", "parse failed".
4. Playwright test: mocks POST returning queued, then GET endpoint multi-call mock simulating progression. Asserts `parsing` → `completed · 3 chunks` transition; verifies polling stops post-completed (call counter ≤3).

## Iter-1 brief P2 advisories addressed

- P2 #1 (chunk_preview is preview, not total): UI text disambiguates ("N chunks so far" vs "N chunks").
- P2 #2 (PDFs stay in parsing… after cap): documented.
- P2 #3 (don't replace upload-doc-id): both rendered side-by-side in flex column.

## Risks for Codex Red-Team

1. **Polling cap (10 × 1s).** Prevents runaway.
2. **Polling stops on non-queued.** Single-shot guard via `if (... !== "queued") return;`.
3. **`upload-doc-id` regression-protected.** Renders alongside parse status (Codex iter-1 P2 #3 fix).
4. **No new package.json dep.**
5. **Test isolation.** Multi-call mock with internal counter; clean per-test state.
6. **Backward-compat with I-f3-005 tests.** New fields optional; uploading→completed transition unchanged.

## Out of scope

- Backend async PDF parser → separate Issue.
- Per-chunk preview text → I-f3-007.

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
diff --git a/web/app/upload/components/upload_drop_zone.tsx b/web/app/upload/components/upload_drop_zone.tsx
index d994949..13e9356 100644
--- a/web/app/upload/components/upload_drop_zone.tsx
+++ b/web/app/upload/components/upload_drop_zone.tsx
@@ -2,20 +2,42 @@
 
 import { useId, useRef, useState } from "react";
 
-import { uploadDocument, type UploadResponse } from "@/lib/api";
+import { getUpload, uploadDocument, type UploadResponse } from "@/lib/api";
 
 const MAX_BYTES = 50 * 1024 * 1024;
 const ALLOWED_EXT = new Set([".pdf", ".docx", ".md", ".txt"]);
 
 type Status = "uploading" | "completed" | "error";
+type ParseStatus = "queued" | "completed" | "failed";
 type FileEntry = {
   id: string;
   name: string;
   status: Status;
   error?: string;
   response?: UploadResponse;
+  parse_status?: ParseStatus;
+  chunk_preview_count?: number;
 };
 
+const POLL_MAX = 10;
+const POLL_INTERVAL_MS = 1000;
+
+async function pollParseStatus(
+  document_id: string,
+  onUpdate: (status: ParseStatus, count: number) => void,
+): Promise<void> {
+  for (let i = 0; i < POLL_MAX; i++) {
+    await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
+    try {
+      const fresh = await getUpload(document_id);
+      onUpdate(fresh.parse_status as ParseStatus, fresh.chunk_preview.length);
+      if (fresh.parse_status !== "queued") return;
+    } catch {
+      return;
+    }
+  }
+}
+
 const extOf = (n: string) => {
   const i = n.lastIndexOf(".");
   return i === -1 ? "" : n.slice(i).toLowerCase();
@@ -58,11 +80,31 @@ export function UploadDropZone() {
       setFiles((p) => [...p, { id, name: f.name, status: "uploading" }]);
       try {
         const response = await uploadDocument(f, "UNKNOWN");
+        const ps = response.parse_status as ParseStatus;
         setFiles((p) =>
           p.map((e) =>
-            e.id === id ? { ...e, status: "completed", response } : e,
+            e.id === id
+              ? {
+                  ...e,
+                  status: "completed",
+                  response,
+                  parse_status: ps,
+                  chunk_preview_count: response.chunk_preview.length,
+                }
+              : e,
           ),
         );
+        if (ps === "queued") {
+          pollParseStatus(response.document_id, (status, count) => {
+            setFiles((p) =>
+              p.map((e) =>
+                e.id === id
+                  ? { ...e, parse_status: status, chunk_preview_count: count }
+                  : e,
+              ),
+            );
+          });
+        }
       } catch (err) {
         const msg = err instanceof Error ? err.message : "upload failed";
         setFiles((p) =>
@@ -118,8 +160,20 @@ export function UploadDropZone() {
               <span className="text-muted-foreground text-xs">
                 {f.status === "uploading" && "uploading…"}
                 {f.status === "completed" && f.response && (
-                  <span data-testid="upload-doc-id">
-                    {f.response.document_id}
+                  <span className="flex flex-col items-end gap-0.5">
+                    <span data-testid="upload-doc-id">
+                      {f.response.document_id}
+                    </span>
+                    <span
+                      data-testid={`upload-parse-${f.id}`}
+                      data-parse-status={f.parse_status}
+                    >
+                      {f.parse_status === "queued" &&
+                        `parsing… (${f.chunk_preview_count ?? 0} chunks so far)`}
+                      {f.parse_status === "completed" &&
+                        `completed · ${f.chunk_preview_count ?? 0} chunks`}
+                      {f.parse_status === "failed" && "parse failed"}
+                    </span>
                   </span>
                 )}
                 {f.status === "error" && (
diff --git a/web/lib/api.ts b/web/lib/api.ts
index 9de7a7a..f64ebac 100644
--- a/web/lib/api.ts
+++ b/web/lib/api.ts
@@ -97,6 +97,13 @@ export interface UploadResponse {
   chunk_preview: string[];
 }
 
+export async function getUpload(document_id: string): Promise<UploadResponse> {
+  const response = await fetch(
+    `${BACKEND_URL}/upload/${encodeURIComponent(document_id)}`,
+  );
+  return asJsonOrThrow<UploadResponse>(response);
+}
+
 export async function uploadDocument(
   file: File,
   classification: DataClassification = "UNKNOWN",
diff --git a/web/tests/e2e/upload_parse_status.spec.ts b/web/tests/e2e/upload_parse_status.spec.ts
new file mode 100644
index 0000000..2d0f21f
--- /dev/null
+++ b/web/tests/e2e/upload_parse_status.spec.ts
@@ -0,0 +1,79 @@
+import { expect, test, type Page } from "@playwright/test";
+
+const DOC_ID = "doc-test-id-0001";
+
+async function dropFile(page: Page) {
+  await page.evaluate(() => {
+    const dt = new DataTransfer();
+    dt.items.add(
+      new File([new Uint8Array(1024)], "queued.pdf", {
+        type: "application/pdf",
+      }),
+    );
+    document.querySelector('[data-testid="upload-dropzone"]')!.dispatchEvent(
+      new DragEvent("drop", {
+        dataTransfer: dt,
+        bubbles: true,
+        cancelable: true,
+      }),
+    );
+  });
+}
+
+test("watches parse-status progression queued → completed", async ({
+  page,
+}) => {
+  let getCalls = 0;
+  await page.route("**/upload", async (route) => {
+    if (route.request().method() !== "POST") return route.continue();
+    await route.fulfill({
+      status: 201,
+      contentType: "application/json",
+      body: JSON.stringify({
+        document_id: DOC_ID,
+        filename: "queued.pdf",
+        bytes: 1024,
+        sha256: "stub",
+        classification: "UNKNOWN",
+        parse_status: "queued",
+        chunk_preview: [],
+      }),
+    });
+  });
+  await page.route(`**/upload/${DOC_ID}`, async (route) => {
+    if (route.request().method() !== "GET") return route.continue();
+    getCalls++;
+    const isComplete = getCalls >= 2;
+    await route.fulfill({
+      status: 200,
+      contentType: "application/json",
+      body: JSON.stringify({
+        document_id: DOC_ID,
+        filename: "queued.pdf",
+        bytes: 1024,
+        sha256: "stub",
+        classification: "UNKNOWN",
+        parse_status: isComplete ? "completed" : "queued",
+        chunk_preview: isComplete ? ["c1", "c2", "c3"] : ["c1"],
+      }),
+    });
+  });
+
+  await page.goto("/upload");
+  await dropFile(page);
+
+  // Initial: parsing visible
+  await expect(page.getByTestId(/upload-parse-/).first()).toContainText(
+    "parsing",
+  );
+
+  // After progression: completed visible
+  await expect(page.getByTestId(/upload-parse-/).first()).toContainText(
+    "completed · 3 chunks",
+    { timeout: 5000 },
+  );
+
+  // Polling stops after completed (cap-of-2 polls)
+  await page.waitForTimeout(1500);
+  expect(getCalls).toBeLessThanOrEqual(3);
+});

```
