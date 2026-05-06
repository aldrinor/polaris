# Claude Architect Audit — I-f2-007 (F2 edge: French / PDF drop)

**Branch:** bot/I-f2-007 / **Diff SHA256:** `f44fb19702f66de1ec6ca20fb372e2abd4a24acbd01d055cce9ead13cc6108b5`
**LOC:** 141 net insertions / 3 deletions (under CHARTER §1 200-cap)
**Format:** `npx prettier --check` clean. **Type-check:** `npx tsc --noEmit` clean.

## Files

```
web/app/intake/components/intake_form.tsx        EDIT  +17
web/app/intake/components/pdf_drop_banner.tsx    NEW   +67
web/app/intake/page.tsx                          EDIT  +9 / -3
web/tests/e2e/intake_edge.spec.ts                NEW   +51
```

## Iter-2 brief P2 advisories — addressed in implementation

- **P2 #1 (stale redirect/upload language):** Implementation ships banner only — no redirect / no `useRouter.push("/upload")` / no `pdf_drop_redirect`.
- **P2 #2 (hydration-racy drop event):** `<PdfDropBanner>` exposes `data-testid="pdf-drop-ready"` with `data-ready="0|1"`. Test waits `await expect(page.getByTestId("pdf-drop-ready")).toHaveAttribute("data-ready", "1")` BEFORE dispatching the synthetic DragEvent, eliminating the race.

## Architecture review

1. **French heuristic.** `looksNonEnglish` returns true if either:
   - any of `[éèêëàâäçîïôöùûüÿñ]` is present (case-insensitive), OR
   - ≥3 matches of common French stopwords (`\b(le|la|les|de|des|du|que|qui|et|est|un|une|sont|pour|avec|sans|dans)\b`, case-insensitive).
   - Acceptable false-positive rate: English clinical questions don't contain those stopwords as ≥3-token clusters; "café"-style loanwords trigger but are rare in clinical questions.
   - English baseline: short clinical questions like "Does aspirin reduce headaches in adults?" pass cleanly (no accented chars; only "in"/"reduce"/"headaches" — not in stopword list).

2. **Pre-submit gate placement.** `looksNonEnglish` check fires AFTER `length < 3` and BEFORE `setState({kind: "loading"})`. No API call. Reuses the existing `state.kind === "error"` UI. Test asserts `intakeCalls === 0`.

3. **PDF drop banner — no redirect (Codex iter-1 P1 fix).** Component shows a banner only; the binding criterion was changed to "banner appears" since `/upload` does not exist. When `/upload` is built, the banner becomes a `<Link>` (separate Issue).

4. **Hydration-readiness signal.** `setReady(true)` after listeners are attached. Test waits for `data-ready="1"` before dispatching the drop event. Codex iter-2 P2 #2 fix.

5. **`window`-level listeners.** Mounted on `window` (not the form div) so dropping anywhere on `/intake` is intercepted. PDF type filter via `file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")`. Non-PDF drops fall through to browser default.

6. **`dragover preventDefault`.** Required to enable the `drop` event handler — without it, browser's default behavior takes over.

7. **Dismiss button.** `setShown(false)` resets the banner. Idempotent — clicking twice has no effect after the first.

8. **Page-level mount only.** `<PdfDropBanner>` lives inside `/intake` page only. Other routes are unaffected.

## LAW + invariant checks

- **LAW II:** Pre-submit French check fails loudly (sets error state); does NOT silently accept and call API. ✓
- **LAW V:** snake_case file naming (`pdf_drop_banner.tsx`); PascalCase exports. ✓
- **LAW VI:** No magic numbers (3-stopword threshold lifted to inline + obvious). The list of stopwords is narrow and documented. ✓
- **§9.4:** No `unittest.mock`; tests use `page.route` + `page.evaluate`. ✓
- **§8.4:** No real network in tests; route mocks + synthetic DragEvent. ✓
- **CHARTER §1 200-cap:** 141 net insertions; well under. ✓

## Test plan coverage

| Test | Assertions |
|---|---|
| 1. French question | Inline error visible + contains "POLARIS currently supports English"; `intakeCalls === 0` (NO API call) |
| 2. PDF drop | Wait for `pdf-drop-ready === "1"` (hydration-race guard); synthetic DragEvent via `new DataTransfer(); dt.items.add(File)`; banner visible; dismiss → banner hidden |

## Out of scope (deferred per breakdown)

- Sophisticated language detection → follow-up Issue (e.g. franc/eld).
- `/upload` route + active redirect → follow-up Issue.
- Backend `non_english` status code → follow-up if needed.
- Evaluator walkthrough → I-f2-008.

## Verdict

APPROVE for Codex diff review.
