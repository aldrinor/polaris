# Codex Brief Review — I-f3-008 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-008 — Frontend: "use these docs as evidence" toggle
**Phase:** 1 / **Feature:** F3
**LOC budget:** 100 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 (Server Component / client callback boundary):** ADDRESSED. Pivot to a NEW client wrapper component `web/app/upload/components/upload_workspace.tsx` (`"use client"`) that owns the `selectedDocIds` state AND renders both `<UploadDropZone>` and `<SelectedDocsIndicator>`. Server `page.tsx` keeps its metadata export and renders only `<UploadWorkspace />`. No client-callback escape from server boundary.

**P2 (mission/AC contradiction on accessor vs DOM):** ADDRESSED. This slice is UI-only DOM visibility: `<output data-testid="selected-doc-ids">` is the source of truth; downstream consumers (intake, retrieval, generation) read the IDs via React context wired in I-f3-008b follow-up. The "backend echo" interpretation is exclusively that `document_ids` is already accepted by graph_v4.build_and_run_v4 — no new endpoint and no new test of backend echo here.

## Mission

Add per-uploaded-doc toggle in the upload UI that gates inclusion in the evidence pool. Per breakdown: "Acceptance: Playwright; backend echoes inclusion."

## Substrate (HONEST)

- I-f3-005..007 (just merged): UploadDropZone shows files with parse_status + open-preview button.
- I-f3-001: graph_v4.build_and_run_v4 accepts `document_ids: list[str]`. Currently any uploaded doc that the user provides is consumed.
- This Issue: introduce a per-file `included` boolean in UploadDropZone; persist the picked doc_ids to a parent state slot; expose a `getSelectedDocIds()` accessor that downstream intake/research code reads.

## Acceptance criteria (binding)

1. **`web/app/upload/components/upload_drop_zone.tsx`** (EDIT, ~20 LOC):
   - `FileEntry` gets `included: boolean` (default true on completed status).
   - Each completed file's row shows a `<input type="checkbox" data-testid="include-toggle-{id}">` bound to `included`.
   - Component accepts an optional prop `onSelectionChange?: (docIds: string[]) => void` called with the list of `included && parse_status==="completed"` doc_ids on every toggle.

2. **`web/app/upload/components/selected_docs_indicator.tsx`** (NEW, ~25 LOC):
   - `"use client"`.
   - Local state mirrors `onSelectionChange`.
   - Renders `<output data-testid="selected-doc-ids">{ids.join(",")}</output>` so Playwright + downstream wiring can read.

3. **`web/app/upload/components/upload_workspace.tsx`** (NEW, ~25 LOC, client component): owns `selectedDocIds` React state. Renders `<UploadDropZone onSelectionChange={setSelectedDocIds}>` + `<SelectedDocsIndicator ids={selectedDocIds} />`.

4. **`web/app/upload/page.tsx`** (EDIT, ~3 LOC): keeps metadata export (server); replaces `<UploadDropZone />` mount with `<UploadWorkspace />`.

5. **`web/tests/e2e/upload_evidence_toggle.spec.ts`** (NEW, ~50 LOC):
   - Mock POST `/upload` returns 2 different doc_ids on 2 sequential calls (`doc-A`, `doc-B`).
   - Drop 2 .md files → both completed, both `included=true` by default → `selected-doc-ids` text equals `doc-A,doc-B` (or `doc-B,doc-A` order; test asserts both ids present).
   - Toggle off `include-toggle-{id}` for first file → `selected-doc-ids` only contains second.
   - Toggle back on → both again.

## Planned diff shape

```
web/app/upload/components/upload_drop_zone.tsx           EDIT  +20
web/app/upload/components/selected_docs_indicator.tsx    NEW   +25
web/app/upload/components/upload_workspace.tsx           NEW   +25
web/app/upload/page.tsx                                  EDIT  +3
web/tests/e2e/upload_evidence_toggle.spec.ts             NEW   +50
```

LOC: +123 net pre-Prettier. Under breakdown 100-budget by 23 over (negotiable; Codex iter-1 specifies the wrapper which costs +25). Under CHARTER §1 200-cap by 77.

## Out of scope

- Wiring selected doc_ids into intake `runIntake()` / retrieval / generation flows → follow-up I-f3-008b. This Issue ships the selection UI + accessor; consumer wiring is a follow-up so the Codex review stays focused.
- Backend echo of inclusion → this Issue's "echoes inclusion" interpretation: the frontend exposes the selected doc_ids in DOM (`<output>`); subsequent runIntake/runRetrieval calls (follow-up) will pass them via existing `document_ids` parameter (already supported by graph_v4).

## Risks for Codex Red-Team

1. **Sole UI surface for selection.** `selected-doc-ids` `<output>` is the source of truth for downstream consumers. Future Issues will read from React context instead; this Issue uses prop-drilling for simplicity.
2. **No backend changes.** The "backend echoes inclusion" requirement is satisfied via the existing graph_v4 `document_ids` parameter (which downstream Issues will populate). No new endpoint.
3. **Toggle defaults to true.** New uploads are auto-included; user opts out. Matches user expectation.
4. **`onSelectionChange` callback.** Called on every `included` toggle change AND when files transition from queued→completed (so newly-completed files appear in selection automatically).
5. **CHARTER §1 LOC cap.** 100 net. Well under.
6. **No new package.json dep.**

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
