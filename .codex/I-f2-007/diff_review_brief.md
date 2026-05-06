# Codex Diff Review — I-f2-007 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f2-007 — F2 edge: French / PDF drop
**Branch:** bot/I-f2-007
**Brief:** APPROVED iter 2 (iter1 REQ_CH 1P1 → iter2 APPROVE 0/0/2P2 accept_remaining; both P2 addressed in implementation)
**Canonical-diff-sha256:** `f44fb19702f66de1ec6ca20fb372e2abd4a24acbd01d055cce9ead13cc6108b5`
**LOC:** 141 net insertions / 3 deletions
**Format:** `npx prettier --check` clean. **Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/app/intake/components/intake_form.tsx        EDIT  +17
web/app/intake/components/pdf_drop_banner.tsx    NEW   +67
web/app/intake/page.tsx                          EDIT  +9 / -3
web/tests/e2e/intake_edge.spec.ts                NEW   +51
```

## What changed

### `intake_form.tsx`
- Added module-private `looksNonEnglish(s)` returning true iff ANY of:
  - char in `[éèêëàâäçîïôöùûüÿñ]` (case-insensitive), OR
  - ≥3 matches of `\b(le|la|les|de|des|du|que|qui|et|est|un|une|sont|pour|avec|sans|dans)\b`.
- In `submit()`: AFTER `length < 3` check, BEFORE `setState({kind:"loading"})`, gate on `looksNonEnglish(trimmed)` → set error state with message "POLARIS currently supports English questions only.", return without API call.

### `pdf_drop_banner.tsx` (NEW)
- `"use client"`.
- `useEffect` mounts `dragover` (preventDefault) + `drop` (filter PDFs by type/extension; preventDefault + setShown(true)) listeners on `window`. Cleanup on unmount.
- `setReady(true)` after listeners attached. Exposes `data-testid="pdf-drop-ready"` with `data-ready="1"` for hydration-race guard (Codex iter-2 P2 #2).
- When `shown`, renders banner with `data-testid="pdf-drop-banner"` + dismiss button `data-testid="pdf-drop-dismiss"`.
- NO `useRouter` / NO redirect — Codex iter-1 P1 fix (`/upload` route does not exist yet).

### `page.tsx`
- Imports + mounts `<PdfDropBanner />` inside `<main>` above the IntakeForm.

### `tests/e2e/intake_edge.spec.ts` (NEW)
- **Test 1 (French):** mock /api/intake returning 500 (should-not-be-called). Fill input with French question. Click submit. Assert `intake-error` visible + contains "POLARIS currently supports English". Assert `intakeCalls === 0`.
- **Test 2 (PDF drop):** wait for `pdf-drop-ready` `data-ready === "1"` BEFORE dispatching the synthetic DragEvent (`new DataTransfer(); dt.items.add(File)`). Assert `pdf-drop-banner` visible. Click `pdf-drop-dismiss`; assert banner hidden.

## Iter-2 brief P2 advisories addressed

- **P2 #1 (stale redirect language):** Implementation has zero redirect logic.
- **P2 #2 (hydration-race):** `data-ready="1"` waited on before dispatch.

## Risks for Codex Red-Team

1. **`looksNonEnglish` false positives in clinical English.** "Le Bel" — proper noun "le" might match the stopword regex but only if it's a whitespace-bounded token. Unlikely in actual clinical questions. Brief-confirmed conservatively.

2. **Stopword threshold.** ≥3 matches required. A single English question with one accidental "de" / "le" passes. Three together is a strong French signal.

3. **`window` drag-drop listener scope.** Mounted only inside `/intake` route. Other pages unaffected.

4. **`dragover preventDefault`.** Required for `drop` to fire. Without it, the OS handles drop = open file in tab.

5. **PDF detection.** `file.type === "application/pdf"` for browser-recognized PDFs; `file.name.toLowerCase().endsWith(".pdf")` as fallback for cases where MIME type is empty.

6. **Hydration-race guard.** Test waits for `data-ready="1"` (set inside the `useEffect` after listeners attached) before dispatching the synthetic event. No race.

7. **Synthetic DragEvent in test.** Standard W3C pattern: `new DataTransfer()` + `dt.items.add(file)` + `new DragEvent("drop", {dataTransfer: dt})`. Works in Chromium, Firefox, WebKit.

8. **No `useRouter` / no redirect.** Reflects the missing `/upload` route. Future Issue replaces banner CTA with `<Link href="/upload">`.

9. **Dismiss button idempotency.** `setShown(false)` after first click hides; subsequent clicks no-op.

10. **No new package.json dep.**

11. **CHARTER §1 LOC cap.** 141 net insertions; well under 200.

12. **`<output>` vs `<div>` for ready signal.** Used `<span data-testid="pdf-drop-ready">` with `sr-only` class — invisible to users; readable to Playwright. Acceptable.

13. **`data-testid="pdf-drop-ready"` lifecycle.** Visible only when `!shown`. Once banner shows, the ready span unmounts. This is fine for the test pattern (read-once hydration-readiness signal).

## Out of scope (do NOT regress on these)

- /upload route → follow-up Issue.
- Sophisticated language detection → follow-up Issue.
- Backend `non_english` status code → follow-up if needed.
- Evaluator walkthrough → I-f2-008.

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
