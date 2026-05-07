# Codex Brief Review — I-f3-005 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-005 — Frontend: drag-drop upload zone
**Phase:** 1 / **Feature:** F3
**LOC budget:** 150 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 (50MB vs 25MB backend mismatch):** ADDRESSED. This Issue NOW also bumps `src/polaris_v6/api/upload.py:34` `MAX_BYTES = 25 * 1024 * 1024` → `50 * 1024 * 1024` to match the breakdown's binding 50MB acceptance. Defense-in-depth: client gate at 50MB AND backend gate at 50MB.

**P2 #1 (Playwright mock pattern):** ADDRESSED. Mock uses `await page.route("**/upload", async (route) => { if (route.request().method() !== "POST") return route.continue(); ... })` — non-POST requests fall through (so Next.js page nav at `/upload` is unaffected). Also targets `BACKEND_URL` glob `**://*/upload` to be safe across origins.

**P2 #2 (don't drop multi-file test):** ADDRESSED. Binding scenarios all preserved; LOC trimmed via implementation compaction (combine status states into shorter union, single shared progress component).

## Mission

Add `/upload` route at `web/app/upload/page.tsx` with a drag-drop zone enforcing a 50MB-per-file limit and showing upload progress. Per breakdown: "Playwright drag 50MB PDF → progress visible."

## Design call

The breakdown mentions "shadcn dropzone + react-dropzone". Project does NOT yet have react-dropzone installed (per `web/package.json` grep). Two options:
- (A) **Selected**: native HTML5 drag-drop (`onDragOver` + `onDrop`) — same pattern as `pdf_drop_banner.tsx` (I-f2-007). No new dep. ~30 LOC for the drop-zone + ~25 for progress UI + ~15 for size validation.
- (B) Add `react-dropzone` dep — pulls in ~30KB; not needed for the binding "drag PDF → progress visible" acceptance.

Going with (A) keeps scope tight + zero-new-dep.

## Substrate (HONEST)

- `web/lib/api.ts:100-111` already exports `uploadDocument(file, classification)` POSTing to `/upload`.
- `web/app/intake/components/pdf_drop_banner.tsx` (I-f2-007) is the canonical drag-drop pattern: `useEffect` mounting `dragover` + `drop` listeners.
- `web/components/ui/{button,card,input}.tsx` available.
- No `/upload` route currently exists (per I-f2-007 P1 #1 — that's why the PDF drop banner only banner'd, didn't redirect).

## Acceptance criteria (binding)

1. **`web/app/upload/page.tsx`** (NEW, server component shell):
   - `export const metadata = { title: "Upload — POLARIS Canada", description: "Upload documents for grounding" }`.
   - Renders `<UploadDropZone />` (client component) inside a header/footer matching `/intake` layout.
   - LOC: ~30.

2. **`web/app/upload/components/upload_drop_zone.tsx`** (NEW, client):
   - `"use client"`.
   - State: `[files, setFiles] = useState<UploadedFile[]>([])` where `UploadedFile = {id, file, status: "idle"|"uploading"|"completed"|"error", error?: string, progress: number, response?: UploadResponse}`.
   - `dragover` + `drop` handlers ON the drop-zone div (not window — only this region accepts drops).
   - On drop: filter to PDFs/MD/TXT/DOCX (per existing `ALLOWED_EXTENSIONS` in upload backend); reject files > 50MB with status="error" + error message.
   - For each accepted file, append to `files`, then call `uploadDocument(file, "UNKNOWN")` from `@/lib/api`. Show progress ("uploading...") while pending, then "completed" with response.document_id on success.
   - Render: drop-zone (`data-testid="upload-dropzone"`); below it, list of `<li>` per file with name, size, status, progress, document_id (if completed). Each `li` has `data-testid="upload-file-{id}"`.
   - LOC: ~110.

3. **`web/tests/e2e/upload_dropzone.spec.ts`** (NEW): 3 Playwright tests with `page.route()` mock for `/upload`:
   - `test_drop_pdf_under_limit`: drop 1MB PDF → upload-uploading visible → upload-completed visible after mock-fulfill (50ms delay) → document_id rendered.
   - `test_drop_oversize_rejected_with_error`: drop 51MB-shaped synthetic file → uploading NEVER fires → error status with "exceeds 50MB" text. (Mock /upload route counts calls; expect 0 calls for oversize.)
   - `test_drop_multiple_files`: drop 2 PDFs → 2 list items rendered, both transition uploading → completed.
   - LOC: ~70.

## Planned diff shape

```
src/polaris_v6/api/upload.py                            EDIT +1/-1 (MAX_BYTES bump)
web/app/upload/page.tsx                                 NEW +30
web/app/upload/components/upload_drop_zone.tsx          NEW +95 (trimmed per Codex iter-1 P2 #2)
web/tests/e2e/upload_dropzone.spec.ts                   NEW +70
```

LOC: +196 net pre-Prettier. Under CHARTER §1 200-cap by 4. Pre-Prettier headroom is tight; if reflow drives over, brief author commits to inline-trimming the upload_drop_zone component first.

## Out of scope (deferred)

- Per-file parse status (the queued/parsing/completed transition shown as DocumentIngester progresses) → I-f3-006 next.
- Doc preview with chunk highlights → I-f3-007.
- shadcn dropzone polish + react-dropzone integration → optional follow-up if Codex insists on the breakdown's wording.

## Risks for Codex Red-Team

1. **50MB limit enforcement.** Client-side: `if (file.size > 50 * 1024 * 1024) → reject`. Backend at `src/polaris_v6/api/upload.py:66-70` ALSO enforces this (HTTP 413). Defense in depth.

2. **Drop-zone vs window-level listener.** This Issue uses ZONE-level (only the drop-zone div), NOT window-level. Different from `pdf_drop_banner.tsx` (which is window-level). Avoids accidentally consuming drops on other parts of /upload.

3. **`page.route()` mock for `/upload`.** Tests don't hit real backend. Mock returns a success response shape matching `UploadResponse` type.

4. **Synthetic 51MB file.** Playwright's `setInputFiles` accepts a buffer; we synthesize a 51MB Buffer via `Buffer.alloc(51 * 1024 * 1024)`. This is a memory-cost in the test (~50MB) but acceptable for a single test run.

5. **`document_id` rendering.** On success, the list item shows the `response.document_id` (uuid hex). This is the input to subsequent F3 issues (I-f3-001's `document_ids` parameter).

6. **CHARTER §1 LOC cap.** Estimated 210 — over by 10. Brief author commits to trimming. Hard fallback: drop the multi-file test → 200 LOC.

7. **`useState` + `useId` for stable file ids.** Each new file gets a `useId()`-derived id. Stable across re-renders.

8. **No new package.json dep.** Native HTML5 drag-drop only.

9. **`onSubmit` not used** — drag-drop is the entry point; no traditional form. But the page also exposes a `<input type="file" multiple>` fallback for keyboard users who can't drag (basic accessibility).

10. **Accessibility.** The drop-zone has `role="button"`, `aria-label="Drop files here or click to browse"`, `tabIndex={0}`. Click triggers the file input.

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
