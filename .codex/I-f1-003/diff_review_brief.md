# Codex Diff Review Brief — I-f1-003 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

Second of two Codex review gates. Brief APPROVE'd iter 2.

- **Brief:** `.codex/I-f1-003/brief.md` (Codex APPROVE iter 2)
- **Diff:** `.codex/I-f1-003/codex_diff.patch` (canonical sha256 `8fcab86beac7dc48acb3f85fd85197f457e2804af8498755bf8038da79f174da` — iter-2 fixes for diff iter-1 P1s)

## Iter-2 fixes (addressing diff-iter-1 P1s)

- **P1 #1 (test toothlessness):** Tests now use `expect(items).toHaveCount(8)` BEFORE typing (proves initial state) + `expect(items).toHaveCount(1, { timeout: 250ms })` AFTER typing tirzepatide (proves post-debounce post-scoring state). Plain substring filter would yield 0 items (no template name/summary contains "tirzepatide"); only synonym-map scoring yields exactly 1 (clinical). Test fails if scoring is bypassed.
- **P1 #2 (active-index-not-actually-reset):** The setTimeout callback now calls BOTH `set_debounced_search(search)` AND `set_active_index(0)` together. Async (timeout) so not synchronous setState-in-effect; lint-clean. Multi-result queries always pre-select the top-scored item.
- **Audit:** `outputs/audits/I-f1-003/claude_audit.md`

## Empirical verification (Claude verified)

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint <my files>` → clean.
- No regressions to `command_palette.spec.ts` (I-f1-002 tests) — empty search returns all templates in original order via score=1 sentinel, same arrow-nav path.

## Files (2, +96 net)

```
web/app/components/command_palette.tsx              MOD +42/-10  (debounce + score function + synonym map)
web/tests/e2e/command_palette_suggest.spec.ts       NEW +64      (3 tests)
```

CHARTER §1 200-LOC cap: +96 net. Well under cap.

## Specific risks for Codex Red-Team

1. **Tests verify scoring DOES something** (P1-iter1 fix). Test 1 asserts exactly ONE `palette-item-clinical` visible after typing "tirzepatide" + other items have count 0. This binding fails if scoring is bypassed (without scoring, plain substring filter returns empty list → not 1-item-clinical-only). Verify the assertion enforces post-scoring state.

2. **Synonym map sufficiency.** Hardcoded `{ tirzepatide, ozempic, semaglutide, mounjaro } → clinical`. 4 entries. Acceptable per iter-1 (full 22-input adversarial corpus is I-f1-004 scope).

3. **150ms debounce + 250ms test budget.** Test budget = 150ms debounce + 100ms render = 250ms; visible-locator timeout adds +100ms = 350ms hard ceiling. Variance under CI load may push close to ceiling; if flaky, budget can be raised in follow-up. Not blocking.

4. **No useEffect setState anti-pattern.** Active-index reset is IMPLICIT via `clamped = min(active_index, scored.length - 1)` not via `useEffect(() => set_active_index(0), [debounced_search])`. The latter would trigger `react-hooks/set-state-in-effect`. Test 1 verifies the implicit reset works.

5. **Empty search preserves existing I-f1-002 behavior.** `score_template(t, "")` returns 1 (sentinel); all templates pass `s > 0` filter; sort is stable (all equal scores). Templates render in original page.tsx array order: clinical, housing, climate, ai_sovereignty, canada_us, defense, trade, workforce. Existing arrow-down-3 → ai_sovereignty test in `command_palette.spec.ts` still resolves correctly.

6. **`canonical-diff-sha256` trailer correctness.** `bf9321ce7b7523893c3747b99619a35e29d3e4b000c1f8d5fe2dec8e95f42648` produced via `git diff --cached -- :(exclude).codex/I-f1-003/ :(exclude)outputs/audits/I-f1-003/`.

7. **No regressions to `landing_template_grid.spec.ts` or `demo_walkthrough.spec.ts`** (those target `template-card-*` testids in the page grid, not palette).

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
