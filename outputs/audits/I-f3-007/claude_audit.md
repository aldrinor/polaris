# Claude Architect Audit — I-f3-007 (doc preview)

**Branch:** bot/I-f3-007 / **Diff SHA256:** `5d2eeefb15fd2e93d778679543bf8887f8e46e3c616323d84fcc8957d1b0384e`
**LOC:** 230 net — **30 over CHARTER §1 200-cap. Exemption requested.**

## CHARTER §1 LOC-cap exemption ask

Same pattern as I-f2-008 (granted) and I-f3-005 (granted). Binding scope: backend content+html population + frontend preview component (TreeWalker + iframe + chunk list) + e2e test. Component already minified (single-mode highlighting, no animation, no scroll history).

If denied → split into I-f3-007a (backend content+html + lib/api types) + I-f3-007b (DocumentPreview component + dropzone wiring + test). Total LOC unchanged.

## Files

```
src/polaris_v6/api/upload.py                          EDIT  +9
web/lib/api.ts                                        EDIT  +2
web/app/upload/components/document_preview.tsx        NEW   +112
web/app/upload/components/upload_drop_zone.tsx        EDIT  +23
web/tests/e2e/upload_doc_preview.spec.ts              NEW   +84
```

## Iter-4 brief P2 advisory

P2 (test_api_upload.py assertions for content/html): Acknowledged; deferred to a follow-up backend-test PR. The test file does not currently exist; adding it here would push LOC further over.

## Architecture review

1. **Sandbox.** `sandbox="allow-same-origin"` (no scripts). Parent contentDocument access works; uploaded HTML cannot execute.
2. **TreeWalker highlighting.** Parent walks `iframe.contentDocument.body` for first text-node match; splits text node, wraps slice in `<mark data-polaris-mark>`, calls `scrollIntoView`. Previous `<mark>` is unwrapped via `clearMarks`.
3. **Open Preview gating.** Renders only when `parse_status === "completed"` AND `chunk_preview_count > 0`.
4. **Backend content+html.** Populated for .md/.txt only (raw text + `<pre>{escape(text)}</pre>`). PDF/DOCX stay empty until DocumentIngester wiring (separate substrate Issue).

## LAW + invariant checks

- LAW II: HTML escaped via stdlib `html.escape`. ✓
- LAW V: snake_case file naming. ✓
- §9.4: No `unittest.mock`. ✓

## Verdict

APPROVE for Codex diff review WITH explicit LOC-cap exemption ask.
