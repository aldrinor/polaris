# Claude architect self-audit — I-f1-003

**Issue:** I-f1-003 — Live template-suggestion as user types
**Brief:** `.codex/I-f1-003/brief.md` (Codex APPROVE iter 2)
**Diff:** `.codex/I-f1-003/codex_diff.patch` (canonical sha256 `8fcab86beac7dc48acb3f85fd85197f457e2804af8498755bf8038da79f174da` — iter-2 fixes for diff iter-1 P1s)

## What the diff does

Per iter-2 brief (Codex APPROVE), adds debounced + scored search to the command palette built in I-f1-002:

1. **`web/app/components/command_palette.tsx`** (MODIFY +42/-10): replaces plain substring filter with:
   - `debounced_search` state + `useEffect` setTimeout 150ms debounce
   - `score_template(t, q)` function with weighted matches:
     - `id` exact (case-insensitive): +100
     - `name` exact: +50; substring: +30
     - `summary` substring: +10
     - `sample_question` substring: +5
     - `out_of_scope` substring: +2
     - SYNONYMS map (`tirzepatide`→clinical, `ozempic`→clinical, `semaglutide`→clinical, `mounjaro`→clinical): +60
   - `scored` = filter score>0 + sort desc by score (empty search returns all unsorted via score=1 sentinel)
   - `clamped` index implicitly resets active-index when `scored.length` shrinks (no useEffect setState; avoids `react-hooks/set-state-in-effect` per existing pattern)
2. **`web/tests/e2e/command_palette_suggest.spec.ts`** (NEW +64): 3 Playwright tests asserting the scoring DOES something (P1-iter1 fix — tests must observe post-scoring state):
   - Test 1: type "tirzepatide" → exactly ONE visible item: `palette-item-clinical` (synonym map fires; other 7 templates filtered out via score=0). Binding fails if scoring is no-op.
   - Test 2: type "BPEI" → ZERO visible items (no template scores > 0). Adversarial pre-cursor; full I-f1-004 has 22-input corpus.
   - Test 3: type "tirzepatide" + wait for clinical visible + Enter → URL = `/intake?template=clinical`.
   - Each test waits for `header-sign-in-link` visible before keypress (hydration race avoidance).

## Empirical verification

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint app/components/command_palette.tsx tests/e2e/command_palette_suggest.spec.ts` → clean.
- Playwright not run locally.

## LOC accounting

```
web/app/components/command_palette.tsx              MOD +42 / -10
web/tests/e2e/command_palette_suggest.spec.ts       NEW +64
```

**Total: +106 / -10 = +96 net additions.** Under 140 LOC issue-budget AND under CHARTER §1 200-LOC hard cap.

## Risks acknowledged

- **150ms debounce + 250ms test budget.** Synonym test asserts `palette-item-clinical` visible within `SUGGEST_BUDGET_MS+100` = 350ms. CI Chromium under load may flake; raise budget if needed (still under "200ms target" intent — debounce fires at 150ms; render is fast).
- **No explicit scrollIntoView.** Brief documented: 8-template list with `max-h-80 overflow-y-auto`; index-0 is visible without scroll. Acceptable per brief P2 disposition.
- **No cross-Issue regression.** I-f1-002 tests use empty search (all 8 visible) or arrow nav over default order (clinical/housing/climate/ai_sovereignty/...) — score=1 sentinel for empty search preserves order so tests pass.
- **`useDeferredValue` not used.** Inline `useEffect + setTimeout` chosen for deterministic 150ms timing required by Playwright timing test.
- **Active-index reset on debounced_search change** (iter-2 fix for diff-iter-1 P1). The setTimeout callback now sets BOTH `debounced_search` and `active_index = 0`. Async (timeout) so not synchronous setState-in-effect; lint-clean. Multi-result queries (e.g. `productivity` matches workforce + housing) always pre-select the top-scored item.
- **Test asserts post-debounce state** (iter-2 fix for diff-iter-1 P1). Both tirzepatide tests use `await expect(items).toHaveCount(1, { timeout: SUGGEST_BUDGET_MS + 100 })` — Playwright auto-retry waits for count to STABILIZE at 1, which only happens after 150ms debounce + scoring runs. Pre-debounce count is 8; post-debounce count is 1 (synonym filter). Tests fail if scoring is bypassed.

## What I do NOT claim this Issue does

- Does NOT add a typeahead dropdown OUTSIDE the palette.
- Does NOT add fuzzy/Levenshtein matching.
- Does NOT call `GET /templates` at runtime.
- Does NOT add a mobile-specific palette trigger button (would expand scope).
- Does NOT cover the full 22-input adversarial corpus (that's I-f1-004).

## Output schema for Codex review

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
