# Codex Diff Review — I-f6-003 (ITER 1 of 5)

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
**Canonical-diff-sha256:** `0271f9f12f91fb611098c440240e7b49fbbf46ef5e1d432c64eb6c035f9c65af`
**LOC:** 128 net (under CHARTER §1 200-cap)

## Files

```
web/components/ui/evidence-tooltip.tsx        +95 -1 (fully-controlled Tooltip + touch handler + dual timer refs)
web/tests/e2e/evidence_tooltip_mobile.spec.ts NEW +33 (iPhone 12 device profile + tap + auto-close assertion)
```

## What changed

### Component (`web/components/ui/evidence-tooltip.tsx`)
- `Tooltip.Root` is now **fully controlled**: `open={open}`, `onOpenChange={handleOpenChange}` for the entire lifetime — no undefined↔boolean toggling, so Base UI's `useControlledProp` does not error.
- `Tooltip.Trigger` receives `closeOnClick={false}` to suppress Base UI's `useDismiss(referencePress)` close path that would otherwise cancel touch-open in the same event (per Codex iter-3 P1 finding).
- Refs: `hoverDebounceRef`, `touchAutoCloseRef`, `touchSessionRef`.
- Constants: `HOVER_DEBOUNCE_MS = 300`, `TOUCH_AUTO_CLOSE_MS = 3000`.
- Trigger button handlers (in addition to existing `onClick={onClickToInspect}`):
  - `onMouseEnter` → if `!touchSessionRef.current`, clear hover debounce timer and start fresh 300ms timer that calls `setOpen(true)`.
  - `onMouseLeave` → if `!touchSessionRef.current`, clear hover debounce and `setOpen(false)`.
  - `onFocus` / `onBlur` → if `!touchSessionRef.current`, `setOpen(true|false)`.
  - `onPointerDown` → if `e.pointerType === "touch"`, set `touchSessionRef = true`, clear both timers, `setOpen(true)`, start fresh 3000ms `touchAutoCloseRef` timer that runs `setOpen(false); touchSessionRef.current = false; touchAutoCloseRef.current = null`.
- `handleOpenChange(next)` → on `next === false` (Base UI Escape / outside-press), clear both timers + reset `touchSessionRef` + `setOpen(false)`. On `next === true`, just `setOpen(true)`.
- `useEffect` cleanup → clears both `hoverDebounceRef` and `touchAutoCloseRef` on unmount.

### Playwright spec (`web/tests/e2e/evidence_tooltip_mobile.spec.ts`)
- `import { devices, expect, test } from "@playwright/test"` and `test.use({ ...devices["iPhone 12"] })`.
- Navigates to `/sentence_hover_test/evidence_tooltip` (existing harness route from I-f6-001).
- Asserts popup absent before tap.
- Calls `page.tap('[data-testid="evidence-tooltip-trigger"]')`.
- Asserts popup visible within 500ms (touch path skips the 300ms hover debounce).
- Asserts content: `tier T1`, `Published: 2024-03-15`, `randomized trial enrolled 1247 adults`.
- Asserts auto-close at 3600ms (3000ms timer + 600ms slack).

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- No backend changes; existing `evidence_tooltip.spec.ts` (desktop hover) remains unchanged — the component's new internal hover handler replicates the Provider's prior 300ms debounce.

## Risks for Codex Red-Team

1. **Single source of truth (continuing P0 from iter-3 brief):** `Tooltip.Root` is fully-controlled for the entire lifetime. No undefined→boolean toggling.
2. **Base UI press-close suppression:** `closeOnClick={false}` on `Tooltip.Trigger` removes the referencePress dismiss that would close touch-opened popups in the same event.
3. **Touch session isolation:** while `touchSessionRef.current === true`, hover/focus/blur/mouseLeave handlers are no-ops. The 3000ms auto-close timer is the sole closer during a touch session.
4. **Existing desktop hover spec compatibility:** The `evidence_tooltip.spec.ts` Playwright spec asserts (a) popup absent immediately after hover, (b) popup visible within 500ms. The component now owns the 300ms hover debounce internally (via `onMouseEnter` → `setTimeout(setOpen(true), 300)`), preserving the prior user-visible behavior.
5. **Timer hygiene:** `useEffect` cleanup clears both timers on unmount; `handleOpenChange(false)` clears both timers when Base UI fires close (Escape / outside-press).
6. **§9.4 N/A frontend.**
7. **CHARTER §1 LOC cap:** 128 net. Under 200.
8. **No new package dep.**

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
