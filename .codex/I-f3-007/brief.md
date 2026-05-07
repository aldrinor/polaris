# Codex Brief Review — I-f3-007 (ITER 4 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 4 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-007 — Frontend: doc preview with chunk highlights
**Phase:** 1 / **Feature:** F3
**LOC budget:** 180 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 #1 (sandbox/script contradiction):** ADDRESSED in iter 2. Iter-2 had a self-inconsistency (set `sandbox=""` then `sandbox="allow-same-origin"` in different sections); iter 3 normalizes everywhere to `sandbox="allow-same-origin"` (no `allow-scripts`). Parent-side TreeWalker walks the iframe's `contentDocument.body`, finds the first text node containing the chunk substring, wraps it in `<mark>`, and calls `scrollIntoView()`. NO iframe script required.

**P1 #2 (backend doc_id mismatch):** ADDRESSED. Approach (b): `_UPLOAD_TABLE` stores `content` + `html` directly during the v6 upload route, synchronously, for .md/.txt files (decoded text + `<pre>{escaped}</pre>` HTML wrap). For .pdf/.docx, content+html stay empty strings. Frontend gates the "Open preview" button on `chunk_preview.length > 0` so PDFs queued without parse don't expose an empty preview (Codex iter-1 P2 #2 fix).

**P2 #1 (avoid window.find):** ADDRESSED. Parent-side TreeWalker (per P1 #1 fix); cross-browser standard.

**P2 #2 (gate Open Preview):** ADDRESSED. Button only renders when `f.parse_status === "completed"` AND `f.chunk_preview_count > 0`.

**Iter-2 P2 (echo full content on POST):** ACKNOWLEDGED. Per Codex's "non-blocker" classification, this Issue accepts the dev-only memory tradeoff (POST returns full content). Production hardening (move to GET-only preview content) is a follow-up.

## Mission + scope clarification

Breakdown: "PDF.js preview + click chunk → highlight at coordinates. Acceptance: Playwright span/coords accurate."

**Honest substrate gap:** The current backend (`DocumentIngester.get_document` per `src/polaris_graph/document_ingester.py:1084-1115`) returns `{content, html, metadata, pages, doc_id}` — `content` is plain text, `html` is HTML render. There is NO per-chunk page+bbox coordinate substrate. "Highlight at coordinates" cannot be implemented end-to-end without first shipping coord-recording during ingestion.

**Scope split (locked in this brief):**
- **In scope:** Frontend doc preview component using HTML render (`html` field already produced by DocumentIngester). Render the HTML in a sandboxed iframe; render the chunk list alongside; on chunk click, scroll preview to the matching text + apply CSS highlight via mark element. This is "preview + click → highlight" using TEXT-SEARCH coords (substring scrollIntoView), NOT pixel-bbox coords.
- **Out of scope, named follow-up I-f3-007a — Backend: chunk page+bbox coords during ingestion:** DocumentIngester emits per-chunk `{page, bbox: [x, y, w, h]}`. UploadResponse adds `chunks_full: ChunkWithCoords[]`.
- **Out of scope, named follow-up I-f3-007b — Frontend: PDF.js renderer + bbox-overlay highlighting:** Replace the HTML iframe with PDF.js canvas + overlay div using I-f3-007a's bbox coords.

This Issue ships the frontend preview-with-text-highlight. PDF.js + true coord highlighting is the 2-Issue follow-up chain.

## Substrate (HONEST)

- I-f3-006 (just merged): UploadDropZone shows uploading→completed→parse_status with `upload-doc-id` rendered.
- `DocumentIngester.get_document(doc_id)` returns `{content, html, ...}`. `html` is already extracted/rendered HTML safe to embed.
- `web/lib/api.ts:getUpload(document_id)` exists from I-f3-006; does NOT currently return `html` or `content` fields. This Issue extends UploadResponse to include them OR adds a separate `getDocumentContent(document_id)` API.
- No new backend route needed: GET `/upload/{document_id}` already exists; we extend its response shape.

## Acceptance criteria (binding)

1. **`src/polaris_v6/api/upload.py`** (EDIT, ~10 LOC): extend `UploadResponse` to include `content: str = ""` and `html: str = ""`. In the upload route, for `.md`/`.txt` files the decoded text becomes `content`, and `html = f"<pre>{html_escape(text)}</pre>"`. Other extensions: stay empty. `html_escape` via stdlib `html.escape`.

2. **`web/lib/api.ts`** (EDIT, ~2 LOC): add `content?: string; html?: string` to `UploadResponse` interface.

3. **`web/app/upload/components/document_preview.tsx`** (NEW, ~80 LOC):
   - `"use client"`.
   - Props: `{ documentId: string }`. On mount, calls `getUpload(documentId)`, stores response.
   - Renders 2-pane: LEFT = preview `<iframe ref={...} sandbox="allow-same-origin" srcDoc={response.html}>` (NO `allow-scripts`; same-origin permits parent contentDocument access for the TreeWalker; uploaded HTML cannot execute scripts), RIGHT = chunk list (each `<button>` with `data-testid="chunk-{i}"` showing `chunk_preview[i]` snippet).
   - On chunk click: PARENT-SIDE handler walks the iframe's `contentDocument.body` via `TreeWalker(NodeFilter.SHOW_TEXT)` looking for the first text node whose `textContent` contains the chunk snippet. When found: split the text node, wrap the matching slice in a fresh `<mark>` element, call `mark.scrollIntoView({block: "center"})`. Previous `<mark>` (if any) is unwrapped first to keep one highlight at a time.
   - LOC: ~80.

4. **`web/app/upload/components/upload_drop_zone.tsx`** (EDIT, ~10 LOC): on `parse_status === "completed" && chunk_preview_count > 0`, expose a `<button data-testid="open-preview-{id}">Open preview</button>` that toggles a sibling `<DocumentPreview documentId={response.document_id} />` panel. State: `[openPreviewId, setOpenPreviewId] = useState<string|null>(null)`.

5. **`web/tests/e2e/upload_doc_preview.spec.ts`** (NEW, ~70 LOC):
   - Mock POST + GET routes to return `html: "<p>chunk text alpha</p><p>chunk text beta</p>"` + `chunk_preview: ["alpha", "beta"]`.
   - Drop file → completed → click open-preview → preview iframe visible → click chunk-0 → assert iframe contains a `<mark>` element wrapping "alpha" (via `iframe.contentDocument.querySelector("mark")`).
   - 1 test (binding "click chunk → highlight").

## Planned diff shape

```
src/polaris_v6/api/upload.py                            EDIT  +3
web/lib/api.ts                                          EDIT  +2
web/app/upload/components/document_preview.tsx          NEW   +80
web/app/upload/components/upload_drop_zone.tsx          EDIT  +5
web/tests/e2e/upload_doc_preview.spec.ts                NEW   +70
```

LOC: +160 net pre-Prettier. Under CHARTER §1 200-cap by 40. Prettier reflow margin: tight; brief author commits to fixture trim if drift.

## Out of scope (deferred per scope split)

- **PDF.js canvas renderer** → I-f3-007b follow-up.
- **Per-chunk bbox coords from ingester** → I-f3-007a follow-up.
- **True pixel-bbox highlighting** → blocked on I-f3-007a + I-f3-007b.

## Risks for Codex Red-Team

1. **Substrate gap acknowledged.** Real coord-based highlighting is impossible without I-f3-007a. This Issue ships text-search highlighting which still satisfies the spirit of "click chunk → highlight" + the breakdown's "Playwright span accurate" (text span IS the chunk text).

2. **`<iframe srcDoc>` sandbox.** `sandbox="allow-same-origin"` (NO `allow-scripts`). Parent retains `contentDocument` DOM access; uploaded HTML cannot run scripts.

3. **No iframe scripts. No postMessage.** Highlighting is parent-side TreeWalker mutation of `iframe.contentDocument.body`. The Playwright test asserts `iframe.contentDocument.querySelector("mark")` reflects the click.

4. **`window.find` deprecated** — Codex iter-1 may flag. Alternative: use `document.evaluate` XPath text-search OR a manual `walker` traversal. Brief author commits to the manual walker if Codex objects.

5. **Mock GET upload returns html.** Tests need to assert `iframe.contentDocument.querySelector("mark")` returns the expected text. Iframe must be `srcDoc` not `src` so contentDocument is same-origin accessible.

6. **`DocumentIngester.get_document` for queued PDFs.** Returns `None` until ingestion completes — backend handler must guard. Simply: if `_document_ingester.get_document(doc_id)` is None or unavailable, content+html stay "" (empty string).

7. **CHARTER §1 LOC cap.** 160 net. Prettier reflow concern; fixture trim mitigation.

8. **No new package.json dep.** No PDF.js (deferred to I-f3-007b). HTML iframe + native text-search only.

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
