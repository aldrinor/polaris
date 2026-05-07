# Codex Brief Review — I-f3-006 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-006 — Frontend: per-file parse status (chunks progression)
**Phase:** 1 / **Feature:** F3
**LOC budget:** 120 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Extend the I-f3-005 upload UI to show per-file parse-status progression: when a file uploads with `parse_status="queued"`, frontend polls `GET /upload/{document_id}` until status is `completed` or `failed`, then renders the parsed chunk count.

## Substrate (HONEST)

- I-f3-005 (just merged): `UploadDropZone` shows uploading→completed with `document_id`.
- `src/polaris_v6/api/upload.py:99` — `GET /{document_id}` already exists, returns `UploadResponse` with current `parse_status` + `chunk_preview`.
- Currently the backend `/upload` POST handler chunks `.md`/`.txt` synchronously and returns `parse_status="completed"`. PDFs return `"queued"` with `chunks=[]`. Polling the GET endpoint returns the same record (no async parser exists yet).
- This Issue ships the FRONTEND polling + progression UI. Tests use a mocked GET endpoint that simulates queued→completed.

## Acceptance criteria (binding)

1. **`web/app/upload/components/upload_drop_zone.tsx`** (EDIT, ~30 LOC):
   - Add `getUpload(document_id)` import (new export from `@/lib/api`).
   - Extend `FileEntry` to include `parse_status?: "queued" | "completed" | "failed"`, `chunk_count?: number`.
   - On upload-completed (POST resolves): set `parse_status` = response.parse_status; `chunk_count` = response.chunk_preview.length.
   - If `parse_status === "queued"`, START a poll loop (max 10 attempts, 1s interval) calling `getUpload(document_id)`. On each tick, update `parse_status` + `chunk_count`. Stop when status is `completed`/`failed` OR cap hit.
   - Render: when status is queued, show "parsing… (N chunks so far)". When completed, show "completed · N chunks". When failed, show "parse failed".

2. **`web/lib/api.ts`** (EDIT, ~10 LOC):
   - Add `export async function getUpload(document_id: string): Promise<UploadResponse>` — GETs `/upload/{document_id}`. Mirrors existing `uploadDocument()` shape.

3. **`web/tests/e2e/upload_parse_status.spec.ts`** (NEW, ~80 LOC):
   - Mock POST `/upload` returns `parse_status="queued"`, chunk_preview=[].
   - Mock GET `/upload/{id}` returns: 1st call queued+0chunks, 2nd call queued+1chunk, 3rd call completed+3chunks (simulates progression).
   - Test 1 (`watches_progression_to_completed`): drop file → assert "parsing…" visible → wait → assert "completed · 3 chunks" visible.
   - Test 2 (`stops_polling_after_completed`): GET call counter == 3 (not 4+).

## Planned diff shape

```
web/lib/api.ts                                          EDIT  +10
web/app/upload/components/upload_drop_zone.tsx          EDIT  +30
web/tests/e2e/upload_parse_status.spec.ts               NEW   +80
```

LOC: +120 net pre-Prettier. At breakdown budget. Under CHARTER §1 200-cap by 80. Pre-Prettier headroom: tight; if reflow drives over, brief author commits to test trim.

## Out of scope

- Backend async parse worker (PDFs actually completing) — out of scope; existing backend PDFs stay "queued" forever in production until a separate worker Issue.
- Per-chunk preview text rendering → I-f3-007 (PDF.js preview).

## Risks for Codex Red-Team

1. **Polling cap.** Max 10 polls (10s total). Prevents runaway polling on backend-stuck-queued (like real PDFs today).
2. **Polling stop on completed/failed.** Single-shot guard in the polling closure.
3. **Backward-compat.** UploadDropZone signature unchanged; new fields are optional. Existing 3 tests from I-f3-005 should not regress.
4. **Mock GET endpoint.** Multi-call mock with internal counter to simulate progression.
5. **CHARTER §1 LOC cap.** 120 net; under 200.
6. **No new package.json dep.**
7. **`getUpload` typing.** `Promise<UploadResponse>`; same shape as `uploadDocument` response.

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
