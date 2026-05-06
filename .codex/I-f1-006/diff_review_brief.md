# Codex Diff Review Brief — I-f1-006 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 2 of 5.**

## Iter-1 fix
- **P1: async-leak stability window.** Added `await pageB.waitForTimeout(SUGGEST_BUDGET_MS)` (350ms) AFTER tab A's manipulation but BEFORE the tab B/C unchanged assertions. This window covers the I-f1-003 debounce (150ms) + render budget; any debounced cross-tab leak via BroadcastChannel / storage event / setTimeout-based sync has time to arrive before the assertions evaluate.

## NEW canonical hash (iter-2)
`21cfa18b9b02f15626a79a5c5d699ffb266cea047f31b82f1d0f0fde77b00738`
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE; do not bank.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

Second of two Codex review gates. Brief APPROVE'd iter 3.

- **Brief:** `.codex/I-f1-006/brief.md` (Codex APPROVE iter 3)
- **Diff:** `.codex/I-f1-006/codex_diff.patch` (canonical sha256 `21cfa18b9b02f15626a79a5c5d699ffb266cea047f31b82f1d0f0fde77b00738` — iter-2)
- **Audit:** `outputs/audits/I-f1-006/claude_audit.md`

## Empirical verification (Claude verified)

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint tests/e2e/f1_multi_tab.spec.ts` → clean.

## Files (1, +96 net)

```
web/tests/e2e/f1_multi_tab.spec.ts    NEW +96   (3 same-context tabs, active-index isolation)
```

CHARTER §1 200-LOC cap: +96 net. Under cap.

## Specific risks for Codex Red-Team

1. **One-context / three-pages architecture.** `browser.newContext()` × 1, `context.newPage()` × 3. Same-context tabs share storage but have independent React state. Verify the test does NOT use `browser.newContext()` × 3.

2. **Active-index multi-tab leak detection.** Tab B is forced to multi-result (cleared to 8 items, ArrowDown × 1 → housing active = index 1). Tab A is then made multi-result (cleared to 8 items, ArrowDown × 2 → climate active = index 2). After tab A's manipulation, tab B's `palette-item-housing` MUST still have `data-active="true"`. A leak from tab A would push tab B's clamped active to climate (index 2 in B's 8-item list), changing the asserted DOM. Verify the assertion enforces post-leak state, not just initial state.

3. **Tab C symmetric list-isolation.** Tab C remains single-result (`tariff` → `trade`). After all manipulations, tab C's `palette-item-trade` count = 1 with `data-active="true"`. Catches a hypothetical leak that converts tab C to multi-result.

4. **`Promise.all` hydration.** Three tabs' `goto`s race; per-tab `await expect(header-sign-in-link).toBeVisible()` ensures each is hydrated before its `Control+k`.

5. **`context.close()` cleanup.** Test body ends with `await context.close()`. Avoids resource leak.

6. **No regression to existing F1 specs.** New file is independent; doesn't touch `command_palette.tsx`, `home_keyboard_shell.tsx`, `page.tsx`, or any other test.

7. **`canonical-diff-sha256` correctness.** `1271556abbc89c5b0b4931d621be2232140f9b954f35070a12e70c7609a25ad0`.

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
