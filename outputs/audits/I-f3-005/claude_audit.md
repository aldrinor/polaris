# Claude Architect Audit — I-f3-005 (upload dropzone)

**Branch:** bot/I-f3-005 / **Diff SHA256:** `87e11d29210961875ee346838aa6d588f4f040f5031d2041dd8a2e3037efd53f`
**LOC:** 258 net — **58 over CHARTER §1 200-cap. Explicit exemption requested below.**

## CHARTER §1 LOC-cap exemption request

Same structural case as I-f2-008 (granted exemption):
- Breakdown LOC budget = 150; CHARTER cap = 200; binding multi-scenario test coverage (3 tests covering drop-pdf, drop-oversize, drop-multi) requires the upload component + page + tests.
- Per Codex iter-1 P2 #2: "Trim implementation/tests instead of removing that scenario." — All 3 scenarios preserved; component already at minimum (handleFiles, drop-zone div, list rendering — Prettier expands each).
- Backend +1 LOC (MAX_BYTES bump) is non-negotiable to match the 50MB binding contract.

If exemption denied, brief author commits to splitting into I-f3-005a (backend + page + single-file test) + I-f3-005b (multi-file + oversize tests). Total LOC unchanged.

## Files

```
src/polaris_v6/api/upload.py                          EDIT  +1/-1 (MAX_BYTES 25→50MB)
web/app/upload/page.tsx                               NEW   +29
web/app/upload/components/upload_drop_zone.tsx        NEW   +135
web/tests/e2e/upload_dropzone.spec.ts                 NEW   +93
```

## Architecture review

1. **Backend MAX_BYTES bump (Codex iter-1 P1).** 25→50MB; matches breakdown's 50MB binding contract.
2. **Native HTML5 drag-drop** (Option A per brief). No new package dep. Same pattern as `pdf_drop_banner.tsx`.
3. **Zone-level (not window-level) drop listener.** Drop-zone div has `onDragOver` + `onDrop`; window-wide drops on /upload page elsewhere fall through.
4. **3-tier validation.** Extension (whitelist of .pdf/.docx/.md/.txt) → size (50MB cap) → upload via `uploadDocument()`.
5. **Per-file status state.** Each entry tracks `uploading | completed | error`; UI renders status text + document_id-on-success.
6. **Accessibility.** Drop-zone has `role="button"`, `tabIndex=0`, Enter/Space keyboard activation. `<input type="file" multiple>` fallback for keyboard browsers.
7. **Playwright synthetic DragEvent + DataTransfer + File (51MB Uint8Array).** Per W3C pattern. Mock `/upload` route is POST-only (Codex iter-1 P2 #1 fix).
8. **Tests preserve all 3 binding scenarios.** Codex iter-1 P2 #2 satisfied.

## LAW + invariant checks

- LAW II: Backend + frontend both gate at 50MB. Errors fail-loud as visible UI status. ✓
- LAW V: snake_case file naming. ✓
- LAW VI: `MAX_BYTES`, `ALLOWED_EXT` are module constants. ✓
- §9.4: No `unittest.mock`. ✓

## Verdict

APPROVE for Codex diff review WITH explicit LOC-cap exemption ask.
