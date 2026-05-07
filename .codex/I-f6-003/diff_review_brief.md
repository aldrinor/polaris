# Codex Diff Review — I-f6-003 (ITER 2 of 5)

## Iter 2 changes vs iter 1

The PR diff now also includes **5 mechanical lint fixes** to satisfy the required `lint + format + typecheck + build` CI check that turned out to fail on PR #288 with **pre-existing** `react/no-unescaped-entities` errors (4 sites) and one `no-state-update-in-effect` error in files unrelated to I-f6-003 substance. None of those files is on the I-f6-003 substance scope.

The CI required check on `polaris` evidently tightened OR the prior I-f9-002 / I-f5-008 PRs landed before lint became a hard gate. Either way, the merge is blocked until lint is clean. Per `feedback_route_policy_questions_to_codex.md` this is a CI-gate question: rather than route to user (option enumeration anti-pattern) or block on a separate cleanup PR (queue-fatigue), I bundled the trivial fixes into this PR.

Lint fixes — diff summary:
- `web/app/benchmark/components/benchmark_board.tsx:107` `server's` → `server&rsquo;s`
- `web/app/benchmark/page.tsx:77` `Carney's` → `Carney&rsquo;s`
- `web/app/generation/components/evaluator_pane.tsx:34` `generator's` → `generator&rsquo;s`
- `web/app/generation/page.tsx:83` `POLARIS's` → `POLARIS&rsquo;s`
- `web/app/intake/components/pdf_drop_banner.tsx:35` `setReady(true)` (sync inside useEffect) → `queueMicrotask(() => setReady(true))` (defer one microtask out of effect body)

`npx eslint app/**/*.{ts,tsx} components/**/*.{ts,tsx}` exits 0 locally.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f6-003 — Mobile tap-to-show fallback
**Brief:** APPROVED iter 4
**Canonical-diff-sha256:** `8365e5feeab943432fca5202c3697fba4bc5a6946d87b9a40cf4fb20b6d17e5d`
**LOC:** ~133 net (under CHARTER §1 200-cap)

## Files

```
web/components/ui/evidence-tooltip.tsx        +95 -1 (I-f6-003 substance: fully-controlled Tooltip + touch handler + dual timer refs)
web/tests/e2e/evidence_tooltip_mobile.spec.ts NEW +33 (iPhone 12 device profile + tap + auto-close)
web/app/benchmark/components/benchmark_board.tsx +1 -1 (lint fix: &rsquo;)
web/app/benchmark/page.tsx                       +1 -1 (lint fix: &rsquo;)
web/app/generation/components/evaluator_pane.tsx +1 -1 (lint fix: &rsquo;)
web/app/generation/page.tsx                      +1 -1 (lint fix: &rsquo;)
web/app/intake/components/pdf_drop_banner.tsx    +1 -1 (lint fix: queueMicrotask)
```

## What changed (I-f6-003 substance, unchanged from iter 1)

### Component (`web/components/ui/evidence-tooltip.tsx`)
- `Tooltip.Root` is now **fully controlled**: `open={open}`, `onOpenChange={handleOpenChange}` for the entire lifetime — no undefined↔boolean toggling, so Base UI's `useControlledProp` does not error.
- `Tooltip.Trigger` receives `closeOnClick={false}` to suppress Base UI's `useDismiss(referencePress)` close path that would otherwise cancel touch-open in the same event (per Codex iter-3 brief P1 finding).
- Refs: `hoverDebounceRef`, `touchAutoCloseRef`, `touchSessionRef`.
- Trigger button handlers: `onMouseEnter` / `onMouseLeave` / `onFocus` / `onBlur` (all suppressed when `touchSessionRef.current === true`); `onPointerDown` with `pointerType === "touch"` opens + starts 3000ms auto-close.
- `useEffect` cleanup clears both timers on unmount.
- `handleOpenChange(false)` clears both timers and resets `touchSessionRef`.

### Playwright spec (`web/tests/e2e/evidence_tooltip_mobile.spec.ts`)
- `devices['iPhone 12']` mobile profile, taps trigger, asserts popup visible within 500ms with content, asserts auto-close by 3600ms.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} components/**/*.{ts,tsx}` (web/): exit 0.

## Risks for Codex Red-Team

1. **I-f6-003 substance unchanged from iter-1 APPROVE:** the substance diff (`evidence-tooltip.tsx` + `evidence_tooltip_mobile.spec.ts`) is byte-identical to iter 1 (which Codex APPROVE'd 0 P0 / 0 P1).
2. **Lint fixes are mechanical:** each is a single character/line change with no semantic effect on user-visible behavior.
3. **`queueMicrotask` semantics:** defers `setReady(true)` one microtask out of the effect body. Tests that check `data-ready="1"` may transiently see "0" before the microtask flushes; `pdf_drop_ready.spec.ts` is the only consumer — please verify the test is tolerant (it should be, as both before-and-after the change `ready` is set in a render after mount).
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** ~133 net. Under 200.

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
