# Codex Diff Review — I-f3-005 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-005 — frontend drag-drop upload zone
**Brief:** APPROVED iter 2 (iter1 REQ_CH 50MB backend mismatch → iter2 APPROVE 0/0/1P2 stale-text-only)
**Canonical-diff-sha256:** `87e11d29210961875ee346838aa6d588f4f040f5031d2041dd8a2e3037efd53f`
**LOC:** 258 net — **OVER CHARTER §1 200-cap by 58. Explicit exemption ask below.**

## CHARTER §1 LOC-cap exemption ask

Same structural case as I-f2-008 (Codex granted exemption). Binding multi-scenario test coverage requires this LOC after Prettier reflow. Codex iter-1 P2 #2 explicitly said "trim implementation/tests instead of removing that scenario" — all 3 scenarios preserved.

**Ask:** APPROVE despite 258 LOC. If denied → split into I-f3-005a (backend + page + single-file test) + I-f3-005b (multi + oversize). Total LOC unchanged.

## Files

```
src/polaris_v6/api/upload.py                          EDIT  +1/-1 (25→50MB)
web/app/upload/page.tsx                               NEW   +29
web/app/upload/components/upload_drop_zone.tsx        NEW   +135
web/tests/e2e/upload_dropzone.spec.ts                 NEW   +93
```

## What changed

1. `upload.py:34` `MAX_BYTES` 25→50MB.
2. `/upload` route page.tsx with metadata + UploadDropZone client child.
3. `UploadDropZone`: native HTML5 dragover/drop on zone div; 3-tier validation (extension, size, upload); per-file `uploading|completed|error` status with `data-status` attr + `data-testid="upload-doc-id"` on success.
4. 3 Playwright tests using `page.route("**/upload", ...)` POST-only mock with backend-origin glob (iter-1 P2 #1 fix). Synthetic DragEvent + DataTransfer + 51MB Uint8Array.

## Iter-2 brief P2 advisory addressed

P2 (stale risk-register text): N/A — final brief has updated LOC + scope notes.

## Risks for Codex Red-Team

1. **LOC-cap exemption.** See ask above.
2. **Backend gate matches frontend gate** — defense in depth.
3. **POST-only mock** — non-POST requests (page nav) fall through.
4. **Synthetic 51MB Uint8Array.** ~50MB heap during the oversize test; acceptable.
5. **No new package.json dep.**
6. **Accessibility** via role + tabIndex + keyboard handler.
7. **`uploadDocument` from `@/lib/api`** — existing; no API change.
8. **Backend `MAX_BYTES`** also affects every other route consuming this constant (none others currently per grep).

## Out of scope

- Per-file parse status (queued → parsing → completed) → I-f3-006.
- Doc preview with chunk highlights → I-f3-007.

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
diff --git a/src/polaris_v6/api/upload.py b/src/polaris_v6/api/upload.py
index 718f0d3..8ed5393 100644
--- a/src/polaris_v6/api/upload.py
+++ b/src/polaris_v6/api/upload.py
@@ -31,7 +31,7 @@ DataClassification = Literal[
 ]
 
 ALLOWED_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}
-MAX_BYTES = 25 * 1024 * 1024  # 25 MB per upload (Phase 0)
+MAX_BYTES = 50 * 1024 * 1024  # 50 MB per upload (I-f3-005 frontend dropzone)
 
 
 class UploadResponse(BaseModel):
diff --git a/web/app/upload/components/upload_drop_zone.tsx b/web/app/upload/components/upload_drop_zone.tsx
new file mode 100644
index 0000000..d994949
--- /dev/null
+++ b/web/app/upload/components/upload_drop_zone.tsx
@@ -0,0 +1,135 @@
+"use client";
+
+import { useId, useRef, useState } from "react";
+
+import { uploadDocument, type UploadResponse } from "@/lib/api";
+
+const MAX_BYTES = 50 * 1024 * 1024;
+const ALLOWED_EXT = new Set([".pdf", ".docx", ".md", ".txt"]);
+
+type Status = "uploading" | "completed" | "error";
+type FileEntry = {
+  id: string;
+  name: string;
+  status: Status;
+  error?: string;
+  response?: UploadResponse;
+};
+
+const extOf = (n: string) => {
+  const i = n.lastIndexOf(".");
+  return i === -1 ? "" : n.slice(i).toLowerCase();
+};
+
+export function UploadDropZone() {
+  const baseId = useId();
+  const [files, setFiles] = useState<FileEntry[]>([]);
+  const inputRef = useRef<HTMLInputElement>(null);
+  let counter = 0;
+
+  const handleFiles = async (incoming: FileList | File[]) => {
+    for (const f of Array.from(incoming)) {
+      const id = `${baseId}-${counter++}-${Date.now()}`;
+      const ext = extOf(f.name);
+      if (!ALLOWED_EXT.has(ext)) {
+        setFiles((p) => [
+          ...p,
+          {
+            id,
+            name: f.name,
+            status: "error",
+            error: `unsupported extension ${ext}`,
+          },
+        ]);
+        continue;
+      }
+      if (f.size > MAX_BYTES) {
+        setFiles((p) => [
+          ...p,
+          {
+            id,
+            name: f.name,
+            status: "error",
+            error: `exceeds 50MB limit (${(f.size / 1024 / 1024).toFixed(1)}MB)`,
+          },
+        ]);
+        continue;
+      }
+      setFiles((p) => [...p, { id, name: f.name, status: "uploading" }]);
+      try {
+        const response = await uploadDocument(f, "UNKNOWN");
+        setFiles((p) =>
+          p.map((e) =>
+            e.id === id ? { ...e, status: "completed", response } : e,
+          ),
+        );
+      } catch (err) {
+        const msg = err instanceof Error ? err.message : "upload failed";
+        setFiles((p) =>
+          p.map((e) =>
+            e.id === id ? { ...e, status: "error", error: msg } : e,
+          ),
+        );
+      }
+    }
+  };
+
+  return (
+    <div className="flex flex-col gap-4">
+      <div
+        data-testid="upload-dropzone"
+        role="button"
+        tabIndex={0}
+        aria-label="Drop files here or click to browse"
+        onDragOver={(e) => e.preventDefault()}
+        onDrop={(e) => {
+          e.preventDefault();
+          if (e.dataTransfer?.files) handleFiles(e.dataTransfer.files);
+        }}
+        onClick={() => inputRef.current?.click()}
+        onKeyDown={(e) => {
+          if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
+        }}
+        className="border-border bg-muted/10 flex min-h-32 flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center"
+      >
+        <p className="text-foreground text-sm font-medium">Drop files here</p>
+        <p className="text-muted-foreground text-xs">
+          or click to browse · PDF, DOCX, MD, TXT · max 50MB
+        </p>
+        <input
+          ref={inputRef}
+          type="file"
+          multiple
+          accept=".pdf,.docx,.md,.txt"
+          onChange={(e) => e.target.files && handleFiles(e.target.files)}
+          className="sr-only"
+        />
+      </div>
+      {files.length > 0 && (
+        <ul className="flex flex-col gap-2">
+          {files.map((f) => (
+            <li
+              key={f.id}
+              data-testid={`upload-file-${f.id}`}
+              data-status={f.status}
+              className="border-border bg-muted/20 flex items-center justify-between gap-2 rounded-lg border p-3 text-sm"
+            >
+              <span className="text-foreground truncate">{f.name}</span>
+              <span className="text-muted-foreground text-xs">
+                {f.status === "uploading" && "uploading…"}
+                {f.status === "completed" && f.response && (
+                  <span data-testid="upload-doc-id">
+                    {f.response.document_id}
+                  </span>
+                )}
+                {f.status === "error" && (
+                  <span className="text-rose-700">{f.error}</span>
+                )}
+              </span>
+            </li>
+          ))}
+        </ul>
+      )}
+    </div>
+  );
+}
diff --git a/web/app/upload/page.tsx b/web/app/upload/page.tsx
new file mode 100644
index 0000000..f308c1e
--- /dev/null
+++ b/web/app/upload/page.tsx
@@ -0,0 +1,29 @@
+import { UploadDropZone } from "./components/upload_drop_zone";
+
+export const metadata = {
+  title: "Upload — POLARIS Canada",
+  description:
+    "Upload documents for grounding. Drag PDFs, MD, TXT, or DOCX (50MB max).",
+};
+
+export default function UploadPage() {
+  return (
+    <main
+      data-testid="upload-page"
+      className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10"
+    >
+      <section className="flex flex-col gap-2">
+        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
+          Upload documents
+        </h1>
+        <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
+          Drop PDFs, MD, TXT, or DOCX files. POLARIS will parse and chunk each
+          document so you can ground intake queries against your uploads (50MB
+          per file max).
+        </p>
+      </section>
+
+      <UploadDropZone />
+    </main>
+  );
+}
diff --git a/web/tests/e2e/upload_dropzone.spec.ts b/web/tests/e2e/upload_dropzone.spec.ts
new file mode 100644
index 0000000..1ac3c05
--- /dev/null
+++ b/web/tests/e2e/upload_dropzone.spec.ts
@@ -0,0 +1,93 @@
+import { expect, test } from "@playwright/test";
+
+async function mockUploadEndpoint(page: import("@playwright/test").Page) {
+  let calls = 0;
+  await page.route("**/upload", async (route) => {
+    if (route.request().method() !== "POST") return route.continue();
+    calls++;
+    await new Promise((r) => setTimeout(r, 50));
+    await route.fulfill({
+      status: 201,
+      contentType: "application/json",
+      body: JSON.stringify({
+        document_id: `doc-${calls.toString().padStart(16, "0")}`,
+        filename: "test.pdf",
+        bytes: 1024,
+        sha256: "stub",
+        classification: "UNKNOWN",
+        parse_status: "completed",
+        chunk_preview: [],
+      }),
+    });
+  });
+  return () => calls;
+}
+
+async function dropFile(
+  page: import("@playwright/test").Page,
+  name: string,
+  sizeBytes: number,
+) {
+  await page.evaluate(
+    ({ name, sizeBytes }) => {
+      const dt = new DataTransfer();
+      dt.items.add(
+        new File([new Uint8Array(sizeBytes)], name, {
+          type: "application/pdf",
+        }),
+      );
+      const zone = document.querySelector('[data-testid="upload-dropzone"]')!;
+      zone.dispatchEvent(
+        new DragEvent("drop", {
+          dataTransfer: dt,
+          bubbles: true,
+          cancelable: true,
+        }),
+      );
+    },
+    { name, sizeBytes },
+  );
+}
+
+test("drop pdf under limit → completed with document_id", async ({ page }) => {
+  const getCalls = await mockUploadEndpoint(page);
+  await page.goto("/upload");
+  await dropFile(page, "small.pdf", 1024);
+  await expect(page.getByTestId("upload-doc-id")).toBeVisible();
+  expect(getCalls()).toBe(1);
+});
+
+test("drop oversize → error, no upload call", async ({ page }) => {
+  const getCalls = await mockUploadEndpoint(page);
+  await page.goto("/upload");
+  await dropFile(page, "huge.pdf", 51 * 1024 * 1024);
+  await expect(page.locator('li[data-status="error"]').first()).toBeVisible();
+  await expect(page.locator('li[data-status="error"]').first()).toContainText(
+    "exceeds 50MB",
+  );
+  await page.waitForTimeout(150);
+  expect(getCalls()).toBe(0);
+});
+
+test("drop multiple files → all upload", async ({ page }) => {
+  const getCalls = await mockUploadEndpoint(page);
+  await page.goto("/upload");
+  await page.evaluate(() => {
+    const dt = new DataTransfer();
+    dt.items.add(
+      new File([new Uint8Array(1024)], "a.pdf", { type: "application/pdf" }),
+    );
+    dt.items.add(
+      new File([new Uint8Array(1024)], "b.pdf", { type: "application/pdf" }),
+    );
+    document.querySelector('[data-testid="upload-dropzone"]')!.dispatchEvent(
+      new DragEvent("drop", {
+        dataTransfer: dt,
+        bubbles: true,
+        cancelable: true,
+      }),
+    );
+  });
+  await expect(page.locator('li[data-status="completed"]')).toHaveCount(2);
+  expect(getCalls()).toBe(2);
+});

```
