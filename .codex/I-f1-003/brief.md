# Codex Brief Review — I-f1-003 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f1-003 — Live template-suggestion as user types
**Phase:** 1 / **Feature:** F1
**LOC budget:** 140 net per `state/polaris_restart/issue_breakdown.md` §I-f1-003. **CHARTER §1 hard cap: 200 net additions per PR.**

## Mission

Inside the command palette (added by I-f1-002 at `web/app/components/command_palette.tsx`), as the user types in the search input, the **first matching template** receives a "suggested" highlight + scroll-into-view within **200ms** of the last keystroke (debounced). Goal: zero-click "tirzepatide" → "Clinical drug audit" template moves to top, ready for Enter.

Per Carney plan §F1: "live template-suggestion as user types."

## Substrate (HONEST)

- I-f1-002 just merged at `2c5ec511`; `command_palette.tsx` already has substring-filtering `templates.filter((t) => t.name.toLowerCase().includes(q) || ...)`. Iter-1 builds on this.
- Filter currently sorts NOTHING — order is the array order from page.tsx (clinical, housing, climate, ai_sovereignty, ...). The brief: replace ordering with relevance score so the matched template surfaces first.
- Active-index tracking already exists (`active_index` state + `clamped` derivation). After scoring, `filtered[0]` is the top suggestion; `clamped = 0` puts focus there by default — no separate "suggested" state needed.
- Mobile: the input already has tap-to-focus by default (HTML behavior). No extra code needed for "tap-to-show."

## Acceptance criteria (binding)

1. **`web/app/components/command_palette.tsx`** (MODIFY): replace plain `templates.filter(...)` with a debounced, scored search.
   - Add `const [debounced_search, set_debounced_search] = useState("")`.
   - `useEffect(() => { const t = setTimeout(() => set_debounced_search(search), 150); return () => clearTimeout(t); }, [search])` — debounce 150ms (well under 200ms target with 50ms render budget).
   - Replace `filtered = templates.filter(...)` with `scored = score_templates(templates, debounced_search)`. Score function (uses the existing `Template` type fields `id`, `name`, `summary`, `sample_question`, `out_of_scope` — P2-iter1 field-naming fix):
     - Match on `id` exact (case-insensitive): +100
     - Match on `name` exact (case-insensitive): +50
     - Match on `name` substring: +30
     - Match on `summary` substring: +10
     - Match on `sample_question` substring: +5
     - Match on `out_of_scope` substring: +2
     - Special case: hardcoded brand→template synonym map: `{ "tirzepatide": "clinical", "ozempic": "clinical", "semaglutide": "clinical", "mounjaro": "clinical" }` adds +60 if matched.
   - **Filter out scores of 0** when debounced_search non-empty (empty search → show all unsorted). Sort descending by score.
   - Pass `scored` instead of `filtered` to the rest of the rendering / arrow-nav logic.
2. **Active-index reset to 0 on new debounced search.** When `debounced_search` changes, set `set_active_index(0)` so the highest-scored item is auto-selected.
3. **Mobile tap-to-show.** Input already focuses on tap (default `<input>` behavior); no JS needed. Verify via existing focus styles + a Playwright touch test.
4. **Playwright tests in `web/tests/e2e/command_palette_suggest.spec.ts`** (NEW). Tests must verify that scoring/synonym DOES something — they fail if scoring is no-op (P1-iter1 fix: assert post-scoring state, NOT initial-order state):
   - Test 1 (synonym DOES filter): type "tirzepatide" (no template name contains this string; only the synonym map matches `clinical`). After 200ms+ wait, **assert exactly ONE `palette-item-*` visible — `palette-item-clinical`** — and `palette-item-housing`/`-climate`/etc. have count 0. This binding fails if scoring is bypassed (without scoring, ALL 8 items would render since plain substring filter has no match → empty list, NOT 1-item-clinical-only). The "exactly 1 visible item = clinical" state ONLY exists when scoring runs AND synonym fires AND zero-score templates are filtered out.
   - Test 2 (BPEI no false-positive): type "BPEI". After 200ms+, assert ALL `palette-item-*` count = 0 (empty list — no template scores > 0). Adversarial pre-cursor; full I-f1-004 has the corpus-wide assertion.
   - Test 3 (synonym → Enter → navigate): type "tirzepatide" + wait for `palette-item-clinical` to be the only visible item + Enter → URL = `/intake?template=clinical`. The wait-for-only-clinical step ensures we Enter on the scored result, not the initial-order result.
   - Each test starts with `await expect(page.getByTestId("header-sign-in-link")).toBeVisible()` after `goto('/', { waitUntil: 'networkidle' })` (hydration race avoidance per existing pattern).

## Planned diff shape

```
web/app/components/command_palette.tsx                MOD +35 / -8   (debounced state + scored function + active-index reset)
web/tests/e2e/command_palette_suggest.spec.ts         NEW +60        (3 tests: timing, no-false-positive, synonym-Enter)
```

LOC: +95 / -8 = +87 net. Under 140 budget AND under CHARTER §1 200-cap.

## Out of scope (deferred per breakdown)

- Adversarial 22-input corpus → I-f1-004 (full BPEI false-positive coverage)
- WCAG-AA broader tests → I-f1-005
- Multi-tab safety → I-f1-006

## Non-acceptance / explicit exclusions

- Does NOT add a typeahead dropdown OUTSIDE the palette (suggestion is INSIDE the palette only).
- Does NOT call `GET /templates` at runtime.
- Does NOT add fuzzy/Levenshtein matching (substring + synonym map is sufficient for the 8-template corpus).
- Does NOT change the existing 3 I-f1-002 tests (no regression).

## Risks for Codex Red-Team

1. **150ms debounce + Playwright `wait` margin.** Test 1 asserts < 250ms. Variance: CI Chromium under load may add 30-50ms. If flaky, raise to 300ms — still under "200ms target" intent because the debounce-fire happens at 150ms; render is fast. Codex: confirm 250ms ceiling is sufficient OR escalate.

2. **Synonym map expansion (`tirzepatide` → clinical).** Hardcoded JSON object inside `command_palette.tsx`. ~5 entries. Future Issue can move to a JSON file if it grows. Acceptable as inline.

3. **Score-of-0 filter.** Empty search → show all. Non-empty + zero matches → empty list. Test 2 verifies the BPEI case doesn't crash; in current logic `templates.filter(s => s.score > 0)` returns empty; arrow-nav over empty list with `clamped = 0` is safe (Enter on empty does nothing).

4. **Active-index reset side effect.** After debounced search changes, `set_active_index(0)`. Risk: if user manually arrowed to item #3 then typed one more letter → resets to 0. UX trade-off accepted: the suggestion top-1 is the live experience the F1 spec asks for. Manual arrow-nav still works after the reset.

5. **`useEffect` for debounce vs `useDeferredValue`** — React 19 has `useDeferredValue` which gives debounced-like behavior without timeout. We use `useEffect + setTimeout` because we need DETERMINISTIC 150ms (Playwright timing test asserts < 250ms). `useDeferredValue` is heuristic; could be 0ms or 100ms. Inline timeout is required for the binding timing test.

6. **`scored` vs `filtered` rename.** Replace local var name to make scoring explicit. ArrowUp/Down/Enter handlers already reference `filtered[clamped_active]`; rename to `scored[clamped]`. Mechanical change.

7. **Mobile tap-to-show.** Default `<input>` accepts tap focus on iOS/Android Chrome. The visible Sign in link click area surfaces the palette via Ctrl+K which most mobile users won't have — they'd need a visible "Open palette" button. **Honest disclosure:** mobile UX is suboptimal in I-f1-002 design (no on-screen palette trigger). I-f1-003 doesn't add one (would expand scope). Carney plan §F1 mention of "mobile" is satisfied by the input being tappable; full mobile-first palette trigger could be a follow-up Issue.

8. **Scroll-into-view (P2-iter1-#2).** Reordering puts the suggested template at index 0 of the visible list. With 8 templates total and `max-h-80 overflow-y-auto` on the `<ul>` (a tall list element), all matching items render visible at standard viewports without scroll. **Decision: reorder-to-index-0 is sufficient; no explicit `scrollIntoView` call.** Future Issue with N>20 templates can add scroll. Documented as accepted limitation.

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
