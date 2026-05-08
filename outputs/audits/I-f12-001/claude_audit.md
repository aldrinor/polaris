# Claude architect audit — I-f12-001

## Issue scope

F12 two-run picker UI: pick any 2 completed runs. Acceptance: Playwright pick.

## What landed

- `web/app/generation/components/two_run_picker.tsx` — `"use client"` component with native `<input type="checkbox">` rows enforcing exactly-2 selection and a Compare button gated until precisely 2 are selected.
- `web/app/sentence_hover_test/two_run_picker/page.tsx` — `"use client"` fixture page with 4 STUB_RUNS for Playwright e2e.
- `web/tests/e2e/two_run_picker.spec.ts` — 4 Playwright specs validating pick + emit, disabled-until-2, max-2 enforcement, uncheck.

## Architectural alignment

- **Plan F12 (compare runs):** picker UI is the entry point. Result rendering against `/runs/{left}/compare/{right}` (already in `src/polaris_v6/api/compare.py`) is downstream (I-f12-002+).
- **CLAUDE.md §9.4 hygiene:** no try/except, no magic numbers (the literal `2` is the explicit business rule pinned via type signature `[string, string]`).
- **CHARTER §3 LOC cap:** 185 net.
- **Client-component boundary:** both component + fixture page declare `"use client"`. The `onCompare` callback flows entirely within client space.

## Risks considered

- **Third-checkbox refusal semantics:** Playwright's `.check()` would error if the UI refuses the state change; spec 3 deliberately uses `.click()` followed by `not.toBeChecked()` to validate the rejection.
- **No production mount yet:** the picker only renders inside the fixture page; mounting at a real `/compare` route is downstream.

## Verdict

Ready to merge. 4/4 Playwright specs pass locally on chromium. Codex brief APPROVE iter 3; Codex diff APPROVE iter 1.
