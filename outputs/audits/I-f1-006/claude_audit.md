# Claude architect self-audit — I-f1-006

**Issue:** I-f1-006 — F1 multi-tab safety (3 same-context tabs, no state pollution)
**Brief:** `.codex/I-f1-006/brief.md` (Codex APPROVE iter 3)
**Diff:** `.codex/I-f1-006/codex_diff.patch` (canonical sha256 `21cfa18b9b02f15626a79a5c5d699ffb266cea047f31b82f1d0f0fde77b00738` — iter-2 fix for async-leak stability window)

## What the diff does

**`web/tests/e2e/f1_multi_tab.spec.ts`** (NEW +96): single Playwright test using ONE `browser.newContext()` + 3× `context.newPage()` (real "Ctrl+T new tab" model — sibling tabs share storage, each has independent React state). Steps:

1. Open palette in all 3 tabs (parallel `Promise.all`).
2. Tab A types `tirzepatide` → only `clinical` visible. Tab B types `housing` → only `housing`. Tab C types `tariff` → only `trade`. Each tab's `[data-testid^="palette-item-"]` count = 1.
3. Active-index isolation (the test that catches real cross-tab leaks):
   - Clear tab B → 8 items → ArrowDown × 1 → tab B `data-active="true"` on `palette-item-housing`.
   - Clear tab A → 8 items → ArrowDown × 2 → tab A `data-active="true"` on `palette-item-climate`.
   - Tab B STILL on `palette-item-housing`. Tab A's leaked active_index would push tab B to climate; assertion catches it.
4. Symmetric list-isolation: tab C single-result still on `trade`.
5. `context.close()` cleanup.

## Empirical verification

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint tests/e2e/f1_multi_tab.spec.ts` → clean.
- Playwright not run locally.

## LOC

```
web/tests/e2e/f1_multi_tab.spec.ts    NEW +96
```

**Total: +96 net.** Over 80 issue-budget but under CHARTER §1 200-cap. The +16 overrun came from the iter-3 active-index revision (multi-result tab B setup). Acceptable per CHARTER 200-cap binding ceiling.

## Iter trajectory

- Brief iter 1: 1 P1 (separate `browser.newContext()` instances isolate by design — can't catch shared-state regressions) + 1 P2 (active-index masked).
- Brief iter 2: 1 P1 (active-index test still toothless because B/C clamp to index 0) + 2 P2 (stale rationale text).
- Brief iter 3: APPROVE (zero P0/P1; 2 stale-text P2 non-blocking).

Codex's empirical Playwright API knowledge caught a real architecture flaw twice: separate-contexts vs same-context, then the active-index-clamping false-negative. Both fixes locked in iter-3.

## Risks acknowledged

- **3 sibling tabs in 1 context** — real-user model. Same context = shared cookies/localStorage; per-tab sessionStorage; per-tab React state. Test asserts React state isolation (the F1 invariant).
- **`Promise.all` for hydration parallelism** — three `goto`s race; each test's `expect(header-sign-in-link).toBeVisible()` waits per-tab.
- **Test-flakiness budget** — multi-context + multi-keypress can be flaky under CI load. Used `{ timeout: SUGGEST_BUDGET_MS }` (350ms) for visibility waits matching I-f1-003+004 pattern.
- **No CI integration** — `web_ci.yml` runs only inspector/accessibility/performance per existing policy.
- **Stale "browser.newContext() × 3" text** in brief Risks section (P2-iter3 non-blocking) — preserved as historical context; binding acceptance criteria are explicit.

## What this Issue does NOT do

- Does NOT add storage-state inspection (would falsely flag legitimate localStorage sharing).
- Does NOT modify production components.
- Does NOT add a fourth tab or vary the corpus beyond I-f1-003+004.
- Does NOT close F2 multi-tab (that's I-f2-006).

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
