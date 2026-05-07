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
