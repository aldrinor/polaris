# Codex Diff Review — I-f12-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f12-001 — Two-run picker UI. Brief APPROVE iter 3.
- **Net LOC:** 185.
- **Branch:** `bot/I-f12-001`.

## What changed

1. `web/app/generation/components/two_run_picker.tsx` (NEW, 78 LOC, `"use client"`):
   - `RunListItem` exported type.
   - `TwoRunPicker({ runs, onCompare })` with native `<input type="checkbox">` controls.
   - Local `useState<string[]>` selection. Toggle handler refuses a 3rd check by short-circuiting `prev.length >= 2`.
   - `data-testid="selection-count"` reads "{N} of 2 selected".
   - `data-testid="compare-button"` disabled until `selected.length === 2`.
   - Each row checkbox has `data-testid="run-checkbox-{run_id}"` plus a `<label htmlFor>` linking to it.

2. `web/app/sentence_hover_test/two_run_picker/page.tsx` (NEW, 53 LOC, `"use client"`):
   - 4 STUB_RUNS, supplies `onCompare` callback that updates a `last` state.
   - `data-testid="last-compared-pair"` displays the joined-id string.

3. `web/tests/e2e/two_run_picker.spec.ts` (NEW, 50 LOC, 4 specs):
   - `picks exactly 2 runs and emits compare event` — `.check()` r1 + r2, assert count "2 of 2", click compare, assert pair "r1,r2".
   - `compare button disabled until exactly 2 selected`.
   - `cannot select more than 2` — `.check()` first 2; `.click()` (NOT `.check()`) the 3rd; assert third `not.toBeChecked()` and count still "2 of 2".
   - `unchecking a row removes it from selection`.

## Test results (local chromium)

```
$ npx playwright test --project=chromium tests/e2e/two_run_picker.spec.ts --reporter=line
4 passed (2.4s)
```

## Risks for Codex Red-Team

1. **Client-boundary correctness.** Both component + fixture page are `"use client"`; no server→client function-prop crossing.
2. **Native checkbox semantics.** `<input type="checkbox">` ensures `getByRole("checkbox")` and `.check()`/`.uncheck()` work. The 3rd-selection refusal preserves the unchecked state, which is why spec 3 uses `.click()` then asserts `not.toBeChecked()`.
3. **§9.4 hygiene.** The literal `2` is the explicit business rule; type signature `[string, string]` and `.length === 2` checks pin it. No magic-number tunable.
4. **CHARTER §3 LOC cap.** 185 net (under 200).

## Acceptance criteria — forced enumeration

1. ✅ `web/app/generation/components/two_run_picker.tsx` (`"use client"`) with `TwoRunPicker` rendering native checkbox controls + compare button.
2. ✅ `/sentence_hover_test/two_run_picker` fixture page hosts STUB_RUNS + onCompare callback.
3. ✅ Playwright spec at `web/tests/e2e/two_run_picker.spec.ts` with 4 specs exercising checkbox semantics + exactly-2 rule.
4. ✅ CHARTER §3 LOC cap (185 ≤ 200).

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Diff (appended below)
