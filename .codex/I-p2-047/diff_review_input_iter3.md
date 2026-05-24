# Codex DIFF review — I-p2-047 (#841): Upload S-rebuild — iter 3 of 5

HARD ITERATION CAP: 5. iter 3. iter-2 P1: metadata.description still said "for grounding".
FIXED. APPROVE iff zero P0/P1.

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

## Fix since iter 2
- metadata.description "Upload documents for grounding. Drag PDFs..." → "Upload documents —
  POLARIS parses and chunks supported files so you can preview exactly how each is split (PDF,
  MD, TXT, DOCX; 50MB max)." Grep confirms ZERO remaining grounding/intake-grounding claims in
  web/app/upload/page.tsx (visible copy, band, CTA, subtitle, AND metadata).

## Full canonical diff (3 files)
- canonical-diff-sha256: 1b635c46a514b6052acac8bf456dd3d132f59cf5e16d38b954349cad895d06c0
- All prior: visual `-i` APPROVE (desktop A / drag-active A+ / mobile A); typecheck clean;
  eslint 0; upload_g1_g8 4/4. Logic/testids preserved; brand #c8102e untouched.

## The diff
```diff
diff --git a/docs/web/s_tier_design_system.md b/docs/web/s_tier_design_system.md
index f0143fdd..e0dd8251 100644
--- a/docs/web/s_tier_design_system.md
+++ b/docs/web/s_tier_design_system.md
@@ -100,5 +100,10 @@ span highlights, and verdict badges appear consistently across the product.
   version overlaid fields → made static), entity-type select height matched to inputs, chips +
   selects on the shared motion primitive, mobile entity row stacks. All field logic/testids
   preserved.
-- Pre-redo baseline (Codex, 2026-05-23): Sign-in B−, Upload C+, Pin Replay C. Target every
-  screen at A++/S with the signature move systematized.
+- **Upload** (#841, I-p2-047): **desktop A / drag-active A+ / mobile A** (Codex visual iter-1
+  APPROVE). Crafted drop zone (UploadCloud icon + real drag-active brand-tint state + hover +
+  focus + motion; drag-depth counter to avoid child-flicker), tokenized error, and a factual
+  3-step "what happens after upload" band + /intake link filling the empty surface. Logic +
+  testids preserved.
+- Pre-redo baseline (Codex, 2026-05-23): Sign-in B−, Pin Replay C. Target every screen at
+  A++/S with the signature move systematized.
diff --git a/web/app/upload/components/upload_drop_zone.tsx b/web/app/upload/components/upload_drop_zone.tsx
index c1b32c9e..b65c3580 100644
--- a/web/app/upload/components/upload_drop_zone.tsx
+++ b/web/app/upload/components/upload_drop_zone.tsx
@@ -2,6 +2,8 @@
 
 import { useEffect, useId, useRef, useState } from "react";
 
+import { UploadCloud } from "lucide-react";
+
 import { getUpload, uploadDocument, type UploadResponse } from "@/lib/api";
 
 import { DocumentPreview } from "./document_preview";
@@ -56,6 +58,11 @@ export function UploadDropZone({
   const baseId = useId();
   const [files, setFiles] = useState<FileEntry[]>([]);
   const [openPreviewDocId, setOpenPreviewDocId] = useState<string | null>(null);
+  const [dragActive, setDragActive] = useState(false);
+  // Drag-depth counter (Codex P2): naive onDragLeave flickers when the pointer
+  // crosses child elements inside the zone; count enter/leave so active is true
+  // iff the pointer is genuinely within the zone subtree.
+  const dragDepth = useRef(0);
   const inputRef = useRef<HTMLInputElement>(null);
   let counter = 0;
 
@@ -150,18 +157,46 @@ export function UploadDropZone({
         role="button"
         tabIndex={0}
         aria-label="Drop files here or click to browse"
+        data-drag-active={dragActive}
+        onDragEnter={(e) => {
+          e.preventDefault();
+          dragDepth.current += 1;
+          setDragActive(true);
+        }}
         onDragOver={(e) => e.preventDefault()}
+        onDragLeave={(e) => {
+          e.preventDefault();
+          dragDepth.current = Math.max(0, dragDepth.current - 1);
+          if (dragDepth.current === 0) setDragActive(false);
+        }}
         onDrop={(e) => {
           e.preventDefault();
+          dragDepth.current = 0;
+          setDragActive(false);
           if (e.dataTransfer?.files) handleFiles(e.dataTransfer.files);
         }}
         onClick={() => inputRef.current?.click()}
         onKeyDown={(e) => {
           if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
         }}
-        className="border-border bg-muted/10 flex min-h-32 flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center"
+        className={`ease-standard focus-visible:ring-ring/70 flex min-h-40 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors duration-150 outline-none focus-visible:ring-2 ${
+          dragActive
+            ? "border-primary bg-primary/10"
+            : "border-border bg-muted/10 hover:border-primary/40 hover:bg-muted/30"
+        }`}
       >
-        <p className="text-foreground text-sm font-medium">Drop files here</p>
+        <span
+          className={`ease-standard flex h-11 w-11 items-center justify-center rounded-full transition-colors duration-150 ${
+            dragActive
+              ? "bg-primary/15 text-primary"
+              : "bg-muted text-muted-foreground"
+          }`}
+        >
+          <UploadCloud aria-hidden className="h-5 w-5" />
+        </span>
+        <p className="text-foreground text-sm font-medium">
+          {dragActive ? "Drop to upload" : "Drop files here"}
+        </p>
         <p className="text-muted-foreground text-xs">
           or click to browse · PDF, DOCX, MD, TXT · max 50MB
         </p>
@@ -234,7 +269,7 @@ export function UploadDropZone({
                   </span>
                 )}
                 {f.status === "error" && (
-                  <span className="text-rose-700">{f.error}</span>
+                  <span className="text-destructive">{f.error}</span>
                 )}
               </span>
             </li>
diff --git a/web/app/upload/page.tsx b/web/app/upload/page.tsx
index b69d6464..a4ba2a81 100644
--- a/web/app/upload/page.tsx
+++ b/web/app/upload/page.tsx
@@ -1,11 +1,35 @@
+import { ArrowRight, FileText, Layers, Sparkles } from "lucide-react";
+import Link from "next/link";
+
 import { UploadWorkspace } from "./components/upload_workspace";
 
 export const metadata = {
   title: "Upload — POLARIS Canada",
   description:
-    "Upload documents for grounding. Drag PDFs, MD, TXT, or DOCX (50MB max).",
+    "Upload documents — POLARIS parses and chunks supported files so you can preview exactly how each is split (PDF, MD, TXT, DOCX; 50MB max).",
 };
 
+// I-p2-047 (#841): factual post-upload flow — describes the real
+// parse → chunk → ground-intake path (no fabricated claims) — so the page
+// reads intentional instead of a drop zone above empty space.
+const STEPS = [
+  {
+    icon: FileText,
+    title: "Drop your files",
+    body: "PDF, DOCX, MD, or TXT — up to 50MB each.",
+  },
+  {
+    icon: Layers,
+    title: "Parsed into chunks",
+    body: "Supported documents are split into retrievable chunks.",
+  },
+  {
+    icon: Sparkles,
+    title: "Preview the result",
+    body: "Open any uploaded document to see exactly how POLARIS chunked it.",
+  },
+] as const;
+
 // I-cd-026 (#616): /upload rebuild — G6 fix. Page no longer renders its
 // own <main>; AppShell (via AppShellGate, I-cd-022) is the single
 // landmark provider. testid preserved on the <section> wrapper.
@@ -20,13 +44,42 @@ export default function UploadPage() {
           Upload documents
         </h1>
         <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
-          Drop PDFs, MD, TXT, or DOCX files. POLARIS will parse and chunk each
-          document so you can ground intake queries against your uploads (50MB
-          per file max).
+          Drop PDFs, MD, TXT, or DOCX files. POLARIS parses and chunks supported
+          documents so you can preview exactly how each one is split (50MB per
+          file max).
         </p>
       </div>
 
       <UploadWorkspace />
+
+      {/* What happens after upload — sibling band (no nested card / no landmark) */}
+      <div className="border-border/60 flex flex-col gap-5 border-t pt-8">
+        <div className="grid gap-x-6 gap-y-5 sm:grid-cols-3">
+          {STEPS.map((step, i) => (
+            <div key={step.title} className="flex flex-col gap-1.5">
+              <div className="text-muted-foreground flex items-center gap-2">
+                <span className="bg-muted text-foreground inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold tabular-nums">
+                  {i + 1}
+                </span>
+                <step.icon aria-hidden className="text-primary h-4 w-4" />
+              </div>
+              <h2 className="text-foreground text-sm font-semibold">
+                {step.title}
+              </h2>
+              <p className="text-muted-foreground text-sm leading-relaxed">
+                {step.body}
+              </p>
+            </div>
+          ))}
+        </div>
+        <Link
+          href="/intake"
+          className="text-primary focus-visible:ring-ring/70 inline-flex w-fit items-center gap-1 rounded text-sm font-medium underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
+        >
+          Ask a research question
+          <ArrowRight aria-hidden className="h-4 w-4" />
+        </Link>
+      </div>
     </section>
   );
 }

# canonical-diff-sha256: 1b635c46a514b6052acac8bf456dd3d132f59cf5e16d38b954349cad895d06c0

```
