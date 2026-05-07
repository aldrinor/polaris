# Codex Diff Review — I-f3-008 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-008 — evidence toggle (UI only, accessor-via-DOM)
**Brief:** APPROVED iter 2 (iter1 REQ_CH server/client boundary → iter2 APPROVE 0/0/1P2)
**Canonical-diff-sha256:** `a829357bba248248c58cb6a7de22087b805e31fdc9ecea26536068ecf0ccb07a`
**LOC:** 145 net (under 200-cap by 55)

## Files

```
web/app/upload/components/upload_drop_zone.tsx           EDIT  +41/-5
web/app/upload/components/selected_docs_indicator.tsx    NEW   +19
web/app/upload/components/upload_workspace.tsx           NEW   +16
web/app/upload/page.tsx                                  EDIT  +2/-2
web/tests/e2e/upload_evidence_toggle.spec.ts             NEW   +70
```

## What changed

- `UploadDropZone` accepts `onSelectionChange?` prop; per-file `included: boolean` (default true on completed); `useEffect([files])` recomputes & calls back; new toggle checkbox in row when status === completed.
- `SelectedDocsIndicator` (NEW) — `ids: string[]` prop; renders `<output data-testid="selected-doc-ids">`.
- `UploadWorkspace` (NEW, client) — owns `selectedDocIds` state; bridges `UploadDropZone` callback to indicator props.
- `page.tsx` server component swaps `<UploadDropZone>` mount → `<UploadWorkspace>`.
- 1 e2e test: drop 2 files → both included → uncheck first → indicator shows only second → re-check → both again.

## Iter-2 brief P2 addressed

P2 (selected_docs_indicator props clarification): Implementation uses ids-driven display (no internal state); Codex's recommended pattern.

## Risks for Codex Red-Team

1. **Server/client boundary.** UploadWorkspace is the client island; page.tsx stays server.
2. **`useEffect` infinite-loop guard.** Effect deps: `[files, onSelectionChange]`. `onSelectionChange` is `setSelectedDocIds` (stable React setter); files state changes only on user action or async upload completion. No loop.
3. **Default `included=true`.** Newly-completed files auto-join selection. Matches user expectation.
4. **CHARTER §1 LOC cap.** 145 net.
5. **No new package.json dep.**
6. **Backwards-compat with prior tests.** Existing parse-status and doc-preview tests still pass (UploadDropZone signature uses optional prop with default).
7. **Toggle gating.** Checkbox renders only on `status === "completed" && parse_status === "completed"`. Pending uploads / errored files do NOT show toggle.

## Out of scope

- Wiring selected doc_ids into intake/retrieval/generation → I-f3-008b follow-up.

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
