# Codex Brief Review — I-f2-007 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-007 — F2 edge: French / PDF drop
**Phase:** 1 / **Feature:** F2 (disambiguation modal)
**LOC budget:** 100 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict resolution (REQUEST_CHANGES → addressed in this iter 2)

**P1 (`/upload` route does not exist):** ADDRESSED. Verified via `ls web/app/`: `upload/` is absent. Pivot: PDF drop now shows a banner with `data-testid="pdf-drop-banner"` reading "PDFs go through the upload flow (coming soon)" + a disabled button placeholder. NO automatic navigation. When `/upload` is built (separate Issue, not in scope here), the banner button becomes an active `<Link href="/upload">`.

**P2 #1 (synthetic DragEvent + read-only `dataTransfer.files`):** ADDRESSED. Test uses `const dt = new DataTransfer(); dt.items.add(new File([], "test.pdf", {type: "application/pdf"})); window.dispatchEvent(new DragEvent("drop", {dataTransfer: dt, bubbles: true, cancelable: true}));`. This is the W3C-spec-compliant pattern.

**P2 #2 (heuristic only catches French):** ADDRESSED. Mission narrowed to "French specifically" — the heuristic targets the documented edge case; broader-language detection is a follow-up Issue.

## Mission

Two MVP edge cases on /intake:
1. **French input → English-only message.** POLARIS Phase 1 is English-only. A user typing a French question must see an inline message instead of submitting. Heuristic targets French specifically (accented chars + French stopwords).
2. **PDF dropped on /intake → banner with upload-flow message.** Users dropping a PDF onto the intake page see a banner ("PDFs go through the upload flow (coming soon)") instead of the browser default file-open. NO automatic navigation in this Issue (the `/upload` route does not exist yet; a follow-up Issue creates it and updates the banner CTA).

## Substrate (HONEST)

- `web/app/intake/components/intake_form.tsx`: existing form with `runIntake()` + 3-character minimum validation + error display. Add client-side language detection BEFORE the API call.
- `web/app/upload/page.tsx`: exists (per `web/app/intake/components/intake_form.tsx`'s sibling pattern; not verified — brief author commits to confirming during implementation; if missing, falls back to a banner with a `<Link href="/upload">` instead of an automatic navigation).
- `web/lib/api.ts:374-379`: existing `IntakeErrorBody.code` enumeration. Adding a new client-side error path (NOT an API code) is non-breaking.
- React + Next 16 client components: standard `onDragEnter/onDragOver/onDrop` handlers on the form's parent div.
- French detection: a simple heuristic — detect common French stopwords (`le`, `la`, `de`, `que`, `et`, `est`) AND/OR characteristic accented characters (`é`, `è`, `à`, `ç`, `ô`, `ù`). Heuristic is intentionally simple; sophisticated detection (e.g. franc, eld) is out of scope. The acceptance criterion is "non-English → English-only message" — false positives on heavily-accented English (e.g. "café") are acceptable in practice.

## Acceptance criteria (binding)

1. **`web/app/intake/components/intake_form.tsx`** (EDIT):
   - Add `function looksNonEnglish(s: string): boolean` (module-private):
     - Heuristic: returns true if ANY of:
       - Contains chars in `[éèêëàâäçîïôöùûüÿñ]` (case-insensitive).
       - Three or more whitespace-bounded tokens that match the regex `\b(le|la|les|de|des|du|que|qui|et|est|un|une|sont|pour|avec|sans|dans)\b` (case-insensitive). (Matches common French stopwords; English allows "the", "of", etc., NOT these.)
   - Pre-submit validation: if `looksNonEnglish(trimmed)`, set state to `{kind: "error", message: "POLARIS currently supports English questions only."}` and DO NOT call `runIntake`. Place this check AFTER the `length < 3` check and BEFORE `setState({kind: "loading"})`.
   - LOC: ~15 pre-Prettier.

2. **`web/app/intake/components/pdf_drop_banner.tsx`** (NEW, client component):
   - `"use client"`.
   - Local state: `[shown, setShown] = useState(false)`.
   - `useEffect` mounts `dragover` + `drop` listeners on `window` (with cleanup):
     - `dragover`: `e.preventDefault()` (otherwise browser handles drop = open file).
     - `drop`: if `e.dataTransfer?.files` contains any file with type `"application/pdf"` OR `name.endsWith(".pdf")`, calls `e.preventDefault()` + `setShown(true)`.
   - When `shown`, renders a banner div with `data-testid="pdf-drop-banner"` containing "PDFs go through the upload flow (coming soon)" + a dismiss button (`data-testid="pdf-drop-dismiss"` calls `setShown(false)`).
   - Mounted by `web/app/intake/page.tsx`.
   - LOC: ~35 pre-Prettier.

3. **`web/app/intake/page.tsx`** (EDIT): import + mount `<PdfDropBanner />` inside `<main>`.
   - LOC: +2 pre-Prettier.

4. **`web/tests/e2e/intake_edge.spec.ts`** (NEW): 2 Playwright tests.

   - **Test 1: `French question → English-only message`**:
     - Mock `**/api/intake` with a counter (`intakeCalls`).
     - `goto /intake`. Fill `intake-question-input` with `"Quels sont les effets secondaires de la metformine chez les adultes?"`.
     - Click `intake-submit`.
     - Assert `getByTestId("intake-error")` visible AND text contains "POLARIS currently supports English".
     - Assert `intakeCalls === 0` (proves /api/intake was NOT called).

   - **Test 2: `PDF drop on /intake → banner appears`**:
     - `goto /intake`.
     - Use Playwright's `page.evaluate()` to dispatch a W3C-compliant DragEvent:
       ```js
       const dt = new DataTransfer();
       dt.items.add(new File([], "test.pdf", {type: "application/pdf"}));
       window.dispatchEvent(new DragEvent("drop", {
         dataTransfer: dt,
         bubbles: true,
         cancelable: true,
       }));
       ```
     - Assert `getByTestId("pdf-drop-banner")` is visible.
     - Click `pdf-drop-dismiss`; assert banner is hidden.

   - LOC: ~55 pre-Prettier.

## Planned diff shape

```
web/app/intake/components/intake_form.tsx                NET +15
web/app/intake/components/pdf_drop_redirect.tsx          NEW +30
web/app/intake/page.tsx                                  NET +2
web/tests/e2e/intake_edge.spec.ts                        NEW +55
```

LOC: +102 net pre-Prettier. Prettier reflow target: ≤140. CHARTER §1 200-cap easily satisfied.

## Out of scope (deferred per breakdown)

- Sophisticated language detection (franc, eld, fastText) — heuristic suffices for MVP; full detection is a follow-up Issue.
- Backend `non_english` status code → backend follow-up if needed.
- Evaluator walkthrough → I-f2-008.

## Risks for Codex Red-Team

1. **`looksNonEnglish` heuristic false positives.** "café au lait" (English loanword) would match the accented-char branch. Acceptable trade-off per breakdown's "non-English → English-only message" framing — false positives lean conservative; users can re-phrase. False NEGATIVES are the bigger concern (a French question that slips through), addressed via stopword AND accented-char union.

2. **Stopword regex.** The 16-word list catches common French questions but NOT all (e.g. "Comment" ne pas listed, "pourquoi" not). Brief author commits to including only tokens that DO NOT appear in routine clinical English — verified by mental walk-through. Codex should flag any stopword that overlaps with English clinical questions.

3. **`/upload` route.** Brief author commits to verifying `web/app/upload/page.tsx` exists during implementation. If missing, redirect target falls back to `/` (home) with a query parameter `?pdf_dropped=1` and a toast — cleaner solution is a follow-up Issue.

4. **`window` drag-drop listeners.** Mounted in `useEffect` with cleanup. Listener fires on ANY drop ANYWHERE on the page, including form fields. The PDF check filters to PDFs only. If a non-PDF file is dropped, the default browser behavior (file open in tab) is NOT prevented — acceptable since /intake is text-only.

5. **`useRouter` from `next/navigation`.** App Router convention. Calls `router.push("/upload")`. If unmounted before push completes, no harm (router handles).

6. **Playwright synthetic drop event.** Programmatic `DragEvent` dispatch is the standard test pattern; OS-level drag-drop emulation is unreliable across browsers. Both Chromium + Firefox + WebKit support `DragEvent` constructor.

7. **`<output>` vs `<div>` for error.** Existing `intake-error` is a Card. Reuse the same display path: `state.kind === "error"` → renders the existing error Card. No new UI.

8. **No new package.json dep.**

9. **CHARTER §1 LOC cap.** 102 net pre-Prettier; well under.

10. **Empty file edge case.** Playwright's synthetic `File([new Uint8Array([])], "test.pdf", ...)` has 0 bytes but the type/name is what matters. The redirect doesn't read the file content.

11. **Race condition on submit-during-fill.** A user typing a French character + immediately clicking submit might encounter the React state update being batched. Checked via the `submit()` function reading the current `question` state directly — no race.

12. **`pdf_drop_redirect` placement.** Mounted INSIDE the intake page only (not the root layout) so the redirect only fires on /intake. Drag-drop on other pages is unaffected.

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
