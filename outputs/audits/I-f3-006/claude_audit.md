# Claude Architect Audit — I-f3-006 (parse status progression)

**Branch:** bot/I-f3-006 / **Diff SHA256:** `e655d01e0eda44b2f9f392e32b0d4ea7f56b8e58accc767e237f067951fb93fb`
**LOC:** 144 net (under CHARTER §1 200-cap by 56)
**Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/lib/api.ts                                          EDIT  +7
web/app/upload/components/upload_drop_zone.tsx          EDIT  +62/-4
web/tests/e2e/upload_parse_status.spec.ts               NEW   +79
```

## Architecture review

1. **`getUpload(document_id)`** added to `web/lib/api.ts` — encodes document_id, GETs `/upload/{id}`, returns UploadResponse.
2. **`pollParseStatus(document_id, onUpdate)`** module-level async helper — max 10 polls × 1s = 10s cap; stops when status is non-queued OR error/network failure.
3. **`UploadDropZone` extension** — on POST resolution, captures `parse_status` + `chunk_preview_count` from response. If queued, fires polling loop. UI rendering DOES NOT replace `upload-doc-id` — it's stacked alongside in a flex column (Codex iter-1 P2 #3 fix).
4. **No regression on I-f3-005 tests** — backwards-compat: new fields are optional; uploading→completed transition unchanged.

## Iter-1 brief P2 advisories addressed

- P2 #1 (chunk_preview is preview-only count) — UI text is "N chunks so far" (queued) or "N chunks" (completed) — does not claim total parsed.
- P2 #2 (10-poll cap leaves real PDFs in `parsing…` state) — acknowledged; documented in audit. PDF async parsing is out of scope.
- P2 #3 (don't replace `upload-doc-id`) — both `upload-doc-id` AND `upload-parse-{id}` rendered side by side.

## LAW + invariant checks

- LAW II: Polling fails-stop on non-queued OR error. ✓
- LAW V: snake_case file naming. ✓
- §9.4: No `unittest.mock`. ✓
- CHARTER §1 200-cap: 144 net. ✓

## Verdict

APPROVE for Codex diff review.
