# Codex Brief Review — I-f1-006 (ITER 3 of 5)

## Iter-1 fix (architecture)
- 3× `browser.newContext()` → **ONE `browser.newContext()` + 3× `context.newPage()`**. Same-context tabs share storage (the real-tab model).

## Iter-2 fix (active-index test had false negative)
- **P1: B/C single-result tabs cannot prove active-index isolation** because clamping forces them to index 0 anyway. **Iter-3 fix:** make tab B multi-result. Tab B initially types `housing` (single result), then BEFORE the active-index check, clear tab B's input → tab B shows all 8 → press ArrowDown ONCE → tab B's active is on `palette-item-housing` (index 1). Then move tab A: type empty → all 8 → ArrowDown twice → tab A active on `palette-item-climate` (index 2). Assert tab B still on index 1 (`palette-item-housing` `data-active="true"`). A leaked `active_index=2` from tab A would push tab B's active to climate — observable DOM change. Tab C remains single-result for the symmetric list-isolation assertion.
- **P2 sessionStorage claim** — removed from rationale. Same-context tabs share cookies + localStorage; sessionStorage is per-tab. Test no longer claims to catch sessionStorage sharing.
- **P2 stale "browser.newContext() × 3" risk text** — removed from Risks section.

**HARD ITERATION CAP: 5 per document. This is iter 3 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f1-006 — F1 multi-tab safety test (3 tabs, no state pollution)
**Phase:** 1 / **Feature:** F1 (closes F1)
**LOC budget:** 80 net per `state/polaris_restart/issue_breakdown.md`. **CHARTER §1 hard cap: 200.**

## Mission

Add a Playwright parallel-context test that proves opening the F1 command palette in 3 separate tabs/contexts simultaneously does NOT leak state between them. Each tab types a different query; each must see only its own filtered/scored results, its own active-index, its own debounced search.

Per Carney plan §F1: "open in 3 tabs, type different queries, no state pollution."

## Substrate (HONEST)

- I-f1-002 + I-f1-003 + I-f1-005 merged the palette + scoring + a11y. State (`palette_open`, `search`, `debounced_search`, `active_index`, `signInLinkRef`) is React-component-local — no `localStorage`, no `sessionStorage`, no `window.*` shared mutable state. So multi-tab pollution would only happen if (a) future code introduces a shared singleton, or (b) the global keydown listener on `window` somehow cross-talks (it can't — each tab has its own `window`).
- This Issue's value: regression-prevention. If a future PR introduces a shared `localStorage` cache or a `BroadcastChannel` for syncing palette state, this test catches the introduced state pollution.
- Playwright supports parallel browser **contexts** (separate cookie jars / storage / windows). Each `browser.newContext()` is isolated by default — true browser-level isolation.

## Acceptance criteria (binding)

1. **`web/tests/e2e/f1_multi_tab.spec.ts`** (NEW) — One test that:
   - Spawns ONE `browser.newContext()` → 3× `context.newPage()` (sibling tabs sharing storage).
   - Each page: `goto("/")`, wait `header-sign-in-link` visible (hydration guard), `Control+k` to open palette, fill input with a distinct query.
     - Tab A: `tirzepatide` → expects `palette-item-clinical` only (synonym fires).
     - Tab B: `housing` → expects `palette-item-housing` only.
     - Tab C: `tariff` → expects `palette-item-trade` only.
   - After all 3 tabs settle on their respective scored result, assert each tab STILL shows only its own expected single item — no cross-tab pollution.
   - **Active-index regression check (revised iter-3):**
     1. Clear tab B's input → tab B shows all 8 items → press ArrowDown ONCE → tab B's `[data-active="true"]` lands on `palette-item-housing` (index 1, alphabetical-ish-by-active-array-order).
     2. Clear tab A's input → tab A shows all 8 items → press ArrowDown TWICE → tab A's `[data-active="true"]` lands on `palette-item-climate` (index 2).
     3. Assert tab B's active is STILL on `palette-item-housing`. Active-index leak from tab A → would force tab B to climate; this assertion catches it.
     4. Assert tab C (still single-result `tariff`) is STILL on `palette-item-trade`.
   - Symmetric-isolation: clearing tab A doesn't change tab B's or tab C's rendered list.

2. **No production code change.** Test-only.

3. **Single `browser.newContext()` + 3× `context.newPage()` within one test body.** Same-context tabs share storage (localStorage/sessionStorage/cookies) — this matches real-user "open new tab" behavior and surfaces shared-state regressions that separate contexts would mask.

## Planned diff shape

```
web/tests/e2e/f1_multi_tab.spec.ts            NEW +75
```

LOC: +75 net. Under 80 budget AND CHARTER §1 200-cap.

## Out of scope

- Cross-Issue F2 disambiguation modal multi-tab → I-f2-006.
- localStorage / sessionStorage cleanup helpers (no cookies/storage written by F1 today).

## Non-acceptance / explicit exclusions

- Does NOT modify production components.
- Does NOT add a third-party state-sync library (BroadcastChannel et al.).
- Does NOT write storage (each context starts empty by default).

## Risks for Codex Red-Team

1. **Three contexts in one test.** `browser.newContext()` × 3 → 3 `page` instances. Acceptable per Playwright API. Resource: each context is a fresh browser session; ~3× memory of one tab. Test budget: 1 test × ~2 sec per context init + ~500ms per palette flow = ~6-8 sec total. Acceptable.

2. **Hydration race × 3.** Each page must wait `header-sign-in-link` visible BEFORE `Control+k`. If one tab is slow to hydrate, sequencing matters. Use `Promise.all` to await all 3 hydrations before any keypress.

3. **Cross-tab pollution invariant.** After all 3 tabs typed and settled, each tab is in its own DOM with its own React state. The test asserts:
   - `pageA.getByTestId("palette-item-clinical").count() === 1` AND other tab IDs hidden in pageA.
   - `pageB.getByTestId("palette-item-housing").count() === 1`.
   - `pageC.getByTestId("palette-item-trade").count() === 1`.
   
   THEN: clear pageA's input → wait → assert pageB and pageC are UNCHANGED (still showing their respective single items).

4. **Synonym-fired test inputs already exist** in I-f1-003 + I-f1-004. Test reuses them without adding new corpus. Stays under LOC budget.

5. **`browser.newContext()` cleanup.** Test must `context.close()` for each in `afterAll` or via `test.use({ ... })`. Playwright auto-cleanup of unclosed contexts at test-end works but is not explicit; better to close in test body. ~3 LOC overhead.

6. **localStorage assertion REMOVED iter-2.** Same-context tabs intentionally SHARE localStorage (per browser spec), so a localStorage assertion would incorrectly flag legitimate cross-tab sync. The test focuses on what matters: React component-local state (palette_open, search, debounced_search, active_index) being per-tab via React's render isolation, not shared via storage.

7. **Test-flakiness budget.** Multi-context tests with timing assertions can be flaky on slow CI. Use `await expect(...).toHaveCount(N, { timeout: 350 })` like I-f1-003+004 spec. Each tab waits for its own scored state before moving on.

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
