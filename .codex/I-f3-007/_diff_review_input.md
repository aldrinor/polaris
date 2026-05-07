# Codex Diff Review — I-f3-007 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-007 — doc preview with chunk highlights
**Brief:** APPROVED iter 4 (3 sandbox-config iterations → 0/0/1P2)
**Canonical-diff-sha256:** `5d2eeefb15fd2e93d778679543bf8887f8e46e3c616323d84fcc8957d1b0384e`
**LOC:** 230 net — **OVER CHARTER §1 200-cap by 30. Explicit exemption ask.**

## CHARTER §1 LOC-cap exemption ask

Pattern of I-f2-008 + I-f3-005 (both granted). Multi-deliverable scope (backend + types + component + dropzone wiring + e2e test). If denied, split into I-f3-007a + I-f3-007b at iter 2.

## Files

```
src/polaris_v6/api/upload.py                          EDIT  +9
web/lib/api.ts                                        EDIT  +2
web/app/upload/components/document_preview.tsx        NEW   +112
web/app/upload/components/upload_drop_zone.tsx        EDIT  +23
web/tests/e2e/upload_doc_preview.spec.ts              NEW   +84
```

## What changed

1. Backend: `UploadResponse` adds `content` + `html` fields. For .md/.txt: decoded text + `<pre>{escape}</pre>` HTML wrap. Other extensions: empty. Uses stdlib `html.escape` for safety.
2. Frontend types: optional `content?` + `html?` in `UploadResponse`.
3. `DocumentPreview` (NEW): fetches via `getUpload(documentId)`; renders 2-pane (`<iframe sandbox="allow-same-origin" srcDoc={html}>` + chunk list). On chunk click: parent-side TreeWalker walks contentDocument.body, wraps first match in `<mark data-polaris-mark>`, scrollIntoView. Previous mark unwrapped first.
4. `UploadDropZone`: new `openPreviewDocId` state + `Open preview` button (gated on `parse_status === "completed" && chunk_preview_count > 0`). Mounts `<DocumentPreview>` panel below the file list.
5. e2e test: drop .md → click open-preview → click chunk-1 → assert iframe `<mark>` text equals chunk-1 string.

## Iter-4 brief P2 addressed

P2 (test_api_upload.py assertions for content+html): Acknowledged as follow-up backend-test PR. Not added here to stay near LOC cap.

## Risks for Codex Red-Team

1. **`sandbox="allow-same-origin"` no `allow-scripts`.** Parent DOM access works; uploaded HTML cannot run scripts. Final brief AC matches.
2. **TreeWalker single-match.** First text-node containing snippet → split + wrap. Previous mark cleared first. Single-highlight invariant.
3. **`html.escape` for HTML wrap.** Prevents XSS of escape characters in user-uploaded text content.
4. **Open Preview gating.** `parse_status === "completed"` AND `chunk_preview_count > 0`. PDFs queued without parse → no button.
5. **Same-origin iframe contentDocument access.** Works because srcDoc same-origin AND `allow-same-origin` flag present. Playwright reads `iframe.contentDocument.querySelector` cleanly.
6. **Memory tradeoff (iter-2 P2):** POST returns full content. Acknowledged dev-only.
7. **No new package.json dep.** No PDF.js (deferred to follow-up I-f3-007a/b).
8. **CHARTER §1 LOC cap.** 230 — exemption requested.

## Out of scope (per scope split)

- PDF.js canvas renderer → I-f3-007b follow-up.
- Per-chunk bbox coords from ingester → I-f3-007a follow-up.
- True coord-based highlighting → blocked on I-f3-007a + I-f3-007b.

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
index 8ed5393..2c1b065 100644
--- a/src/polaris_v6/api/upload.py
+++ b/src/polaris_v6/api/upload.py
@@ -14,6 +14,7 @@ the caller; default is UNKNOWN and triggers conservative routing.
 from __future__ import annotations
 
 import hashlib
+import html as _html
 import uuid
 from typing import Literal
 
@@ -42,6 +43,8 @@ class UploadResponse(BaseModel):
     classification: DataClassification
     parse_status: Literal["queued", "completed", "failed"]
     chunk_preview: list[str]
+    content: str = ""
+    html: str = ""
 
 
 _UPLOAD_TABLE: dict[str, UploadResponse] = {}
@@ -80,8 +83,12 @@ async def upload_document(
         except Exception:
             text = ""
         chunks = [text[i : i + 280] for i in range(0, min(len(text), 840), 280) if text]
+        preview_text = text
+        preview_html = f"<pre>{_html.escape(text)}</pre>" if text else ""
     else:
         chunks = []
+        preview_text = ""
+        preview_html = ""
 
     response = UploadResponse(
         document_id=document_id,
@@ -91,6 +98,8 @@ async def upload_document(
         classification=classification,
         parse_status="completed" if chunks else "queued",
         chunk_preview=chunks[:3],
+        content=preview_text,
+        html=preview_html,
     )
     _UPLOAD_TABLE[document_id] = response
     return response
diff --git a/web/app/upload/components/document_preview.tsx b/web/app/upload/components/document_preview.tsx
new file mode 100644
index 0000000..098fdaf
--- /dev/null
+++ b/web/app/upload/components/document_preview.tsx
@@ -0,0 +1,112 @@
+"use client";
+
+import { useEffect, useRef, useState } from "react";
+
+import { getUpload, type UploadResponse } from "@/lib/api";
+
+type Props = { documentId: string };
+
+function clearMarks(doc: Document) {
+  const marks = doc.querySelectorAll("mark[data-polaris-mark]");
+  marks.forEach((m) => {
+    const text = doc.createTextNode(m.textContent ?? "");
+    m.replaceWith(text);
+    m.parentNode?.normalize();
+  });
+}
+
+function highlightFirstMatch(
+  doc: Document,
+  snippet: string,
+): HTMLElement | null {
+  if (!snippet) return null;
+  clearMarks(doc);
+  const walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT);
+  let node: Node | null = walker.nextNode();
+  while (node) {
+    const text = node.textContent ?? "";
+    const idx = text.indexOf(snippet);
+    if (idx !== -1) {
+      const before = text.slice(0, idx);
+      const matched = text.slice(idx, idx + snippet.length);
+      const after = text.slice(idx + snippet.length);
+      const parent = node.parentNode;
+      if (!parent) return null;
+      const beforeNode = doc.createTextNode(before);
+      const mark = doc.createElement("mark");
+      mark.setAttribute("data-polaris-mark", "1");
+      mark.textContent = matched;
+      const afterNode = doc.createTextNode(after);
+      parent.insertBefore(beforeNode, node);
+      parent.insertBefore(mark, node);
+      parent.insertBefore(afterNode, node);
+      parent.removeChild(node);
+      return mark;
+    }
+    node = walker.nextNode();
+  }
+  return null;
+}
+
+export function DocumentPreview({ documentId }: Props) {
+  const [response, setResponse] = useState<UploadResponse | null>(null);
+  const [loading, setLoading] = useState(true);
+  const iframeRef = useRef<HTMLIFrameElement>(null);
+
+  useEffect(() => {
+    let cancelled = false;
+    getUpload(documentId)
+      .then((r) => {
+        if (!cancelled) {
+          setResponse(r);
+          setLoading(false);
+        }
+      })
+      .catch(() => {
+        if (!cancelled) setLoading(false);
+      });
+    return () => {
+      cancelled = true;
+    };
+  }, [documentId]);
+
+  const handleChunkClick = (snippet: string) => {
+    const doc = iframeRef.current?.contentDocument;
+    if (!doc) return;
+    const mark = highlightFirstMatch(doc, snippet);
+    if (mark) mark.scrollIntoView({ block: "center" });
+  };
+
+  if (loading) return <div data-testid="preview-loading">Loading…</div>;
+  if (!response) return <div data-testid="preview-error">Failed to load</div>;
+
+  return (
+    <div
+      className="border-border flex h-96 gap-2 rounded-lg border p-2"
+      data-testid="document-preview"
+    >
+      <iframe
+        ref={iframeRef}
+        sandbox="allow-same-origin"
+        srcDoc={response.html ?? ""}
+        title={`preview-${documentId}`}
+        className="border-border bg-background flex-1 rounded border"
+        data-testid="preview-iframe"
+      />
+      <ul className="border-border flex w-64 flex-col gap-1 overflow-y-auto rounded border p-2">
+        {response.chunk_preview.map((c, i) => (
+          <li key={i}>
+            <button
+              type="button"
+              data-testid={`chunk-${i}`}
+              onClick={() => handleChunkClick(c)}
+              className="hover:bg-muted/40 w-full truncate rounded p-1 text-left text-xs"
+            >
+              {c.slice(0, 80)}
+            </button>
+          </li>
+        ))}
+      </ul>
+    </div>
+  );
+}
diff --git a/web/app/upload/components/upload_drop_zone.tsx b/web/app/upload/components/upload_drop_zone.tsx
index 13e9356..a0cd71e 100644
--- a/web/app/upload/components/upload_drop_zone.tsx
+++ b/web/app/upload/components/upload_drop_zone.tsx
@@ -4,6 +4,8 @@ import { useId, useRef, useState } from "react";
 
 import { getUpload, uploadDocument, type UploadResponse } from "@/lib/api";
 
+import { DocumentPreview } from "./document_preview";
+
 const MAX_BYTES = 50 * 1024 * 1024;
 const ALLOWED_EXT = new Set([".pdf", ".docx", ".md", ".txt"]);
 
@@ -46,6 +48,7 @@ const extOf = (n: string) => {
 export function UploadDropZone() {
   const baseId = useId();
   const [files, setFiles] = useState<FileEntry[]>([]);
+  const [openPreviewDocId, setOpenPreviewDocId] = useState<string | null>(null);
   const inputRef = useRef<HTMLInputElement>(null);
   let counter = 0;
 
@@ -174,6 +177,25 @@ export function UploadDropZone() {
                         `completed · ${f.chunk_preview_count ?? 0} chunks`}
                       {f.parse_status === "failed" && "parse failed"}
                     </span>
+                    {f.parse_status === "completed" &&
+                      (f.chunk_preview_count ?? 0) > 0 && (
+                        <button
+                          type="button"
+                          data-testid={`open-preview-${f.id}`}
+                          onClick={() =>
+                            setOpenPreviewDocId(
+                              openPreviewDocId === f.response!.document_id
+                                ? null
+                                : f.response!.document_id,
+                            )
+                          }
+                          className="text-xs underline"
+                        >
+                          {openPreviewDocId === f.response.document_id
+                            ? "Close preview"
+                            : "Open preview"}
+                        </button>
+                      )}
                   </span>
                 )}
                 {f.status === "error" && (
@@ -184,6 +206,7 @@ export function UploadDropZone() {
           ))}
         </ul>
       )}
+      {openPreviewDocId && <DocumentPreview documentId={openPreviewDocId} />}
     </div>
   );
 }
diff --git a/web/lib/api.ts b/web/lib/api.ts
index f64ebac..49c0fd7 100644
--- a/web/lib/api.ts
+++ b/web/lib/api.ts
@@ -95,6 +95,8 @@ export interface UploadResponse {
   classification: DataClassification;
   parse_status: "queued" | "completed" | "failed";
   chunk_preview: string[];
+  content?: string;
+  html?: string;
 }
 
 export async function getUpload(document_id: string): Promise<UploadResponse> {
diff --git a/web/tests/e2e/upload_doc_preview.spec.ts b/web/tests/e2e/upload_doc_preview.spec.ts
new file mode 100644
index 0000000..5423a06
--- /dev/null
+++ b/web/tests/e2e/upload_doc_preview.spec.ts
@@ -0,0 +1,84 @@
+import { expect, test } from "@playwright/test";
+
+const DOC_ID = "doc-preview-id-0001";
+
+test("open preview → click chunk → mark wraps text in iframe", async ({
+  page,
+}) => {
+  await page.route("**/upload", async (route) => {
+    if (route.request().method() !== "POST") return route.continue();
+    await route.fulfill({
+      status: 201,
+      contentType: "application/json",
+      body: JSON.stringify({
+        document_id: DOC_ID,
+        filename: "doc.md",
+        bytes: 100,
+        sha256: "stub",
+        classification: "UNKNOWN",
+        parse_status: "completed",
+        chunk_preview: ["alpha sentence here", "beta sentence here"],
+        content: "alpha sentence here\nbeta sentence here",
+        html: "<p>alpha sentence here</p><p>beta sentence here</p>",
+      }),
+    });
+  });
+  await page.route(`**/upload/${DOC_ID}`, async (route) => {
+    if (route.request().method() !== "GET") return route.continue();
+    await route.fulfill({
+      status: 200,
+      contentType: "application/json",
+      body: JSON.stringify({
+        document_id: DOC_ID,
+        filename: "doc.md",
+        bytes: 100,
+        sha256: "stub",
+        classification: "UNKNOWN",
+        parse_status: "completed",
+        chunk_preview: ["alpha sentence here", "beta sentence here"],
+        content: "alpha sentence here\nbeta sentence here",
+        html: "<p>alpha sentence here</p><p>beta sentence here</p>",
+      }),
+    });
+  });
+
+  await page.goto("/upload");
+  await page.evaluate(() => {
+    const dt = new DataTransfer();
+    dt.items.add(
+      new File([new Uint8Array(100)], "doc.md", { type: "text/markdown" }),
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
+  // Open preview button visible
+  const openBtn = page.locator('[data-testid^="open-preview-"]').first();
+  await expect(openBtn).toBeVisible();
+  await openBtn.click();
+
+  // Preview iframe rendered
+  const iframe = page.locator('[data-testid="preview-iframe"]');
+  await expect(iframe).toBeVisible();
+
+  // Click chunk-1 (the "beta" chunk)
+  await page.getByTestId("chunk-1").click();
+
+  // Inspect iframe contentDocument for the <mark> element
+  const markText = await page.evaluate(() => {
+    const iframe = document.querySelector(
+      '[data-testid="preview-iframe"]',
+    ) as HTMLIFrameElement | null;
+    const mark = iframe?.contentDocument?.querySelector(
+      "mark[data-polaris-mark]",
+    );
+    return mark?.textContent ?? null;
+  });
+
+  expect(markText).toBe("beta sentence here");
+});

```
