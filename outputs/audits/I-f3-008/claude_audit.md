# Claude Architect Audit — I-f3-008 (evidence toggle)

**Branch:** bot/I-f3-008 / **Diff SHA256:** `a829357bba248248c58cb6a7de22087b805e31fdc9ecea26536068ecf0ccb07a`
**LOC:** 145 net (under CHARTER §1 200-cap by 55)
**Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/app/upload/components/upload_drop_zone.tsx           EDIT  +41/-5
web/app/upload/components/selected_docs_indicator.tsx    NEW   +19
web/app/upload/components/upload_workspace.tsx           NEW   +16
web/app/upload/page.tsx                                  EDIT  +2/-2
web/tests/e2e/upload_evidence_toggle.spec.ts             NEW   +70
```

## Architecture review

1. **Server/client boundary fix (Codex iter-1 P1).** New `UploadWorkspace` client component owns `selectedDocIds` state. Server `page.tsx` keeps metadata export and renders `<UploadWorkspace />`. No callback escape.
2. **`onSelectionChange` callback** in `UploadDropZone`. `useEffect([files])` recomputes the included-doc-id list and calls back on every state change. Auto-includes newly-completed files (default `included=true`).
3. **`SelectedDocsIndicator`** — pure display; no internal state; ids prop only (Codex iter-2 P2 wording fix).
4. **Toggle UI.** `<input type="checkbox" data-testid="include-toggle-{id}">` rendered next to filename; only when status==="completed" AND parse_status==="completed".
5. **Tests preserved.** Backwards-compat: old open-preview test, parse-status test, etc. still pass (UploadDropZone signature is `props={onSelectionChange?}`).

## LAW + invariant checks

- LAW V: snake_case file naming. ✓
- §9.4: No `unittest.mock`. ✓
- CHARTER §1 200-cap: 145 net. ✓

## Verdict

APPROVE for Codex diff review.
