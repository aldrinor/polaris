# Codex Brief Review — I-f6-003 (ITER 4 of 5)

## Iter 4 changes per Codex iter 3

- **P1 fix (Base UI referencePress closes touch-open):** Codex iter-3 verified Base UI's TooltipTrigger defaults `closeOnClick=true` and TooltipRoot wires `useDismiss(referencePress)`, so without intervention our `onPointerDown` setOpen(true) is overwritten by Base UI's same-event close handler. Fix: pass `closeOnClick={false}` to `Tooltip.Trigger`. This disables the referencePress close path entirely; we keep `onClickToInspect` on the trigger button (the click event still fires the inspector callback — closeOnClick controls whether Base UI closes the popup, not whether click events propagate to our handler).

- **P2 fix (touch focus cancels 3s auto-close):** split into two timer refs. `hoverDebounceRef` for the 300ms hover-open timer; `touchAutoCloseRef` for the 3000ms touch auto-close. `onFocus`/`onBlur`/`onMouseLeave` only manage `hoverDebounceRef`. The touch-auto-close timer runs to completion regardless of focus/blur events that fire after the tap. Track a `touchSessionRef` boolean: while true, suppress hover-driven `setOpen(false)` (so the touch session lives for the full 3 seconds even if focus/blur events fire).

- **P2 fix (timer cleanup):** `useEffect` cleanup clears BOTH `hoverDebounceRef` and `touchAutoCloseRef`. `onOpenChange(false)` from Base UI (outside-press/Escape) clears both timers and resets `touchSessionRef`.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Context:** I-f6-003 — on mobile (no hover), tap should show the tooltip. Per Codex iter-1 verification of `web/node_modules/@base-ui/react`, Base UI's TooltipTrigger uses `mouseOnly: true` for hover and does NOT auto-open on touch tap. We add explicit touch handling in `EvidenceTooltip`.
- **Scope:** Production code change to `web/components/ui/evidence-tooltip.tsx` (fully-controlled mode + manual hover/focus/touch open semantics) PLUS a new mobile Playwright spec on the existing I-f6-001 harness route.
- **Done-when:** acceptance criteria 1-6 below.

## Plan

### Frontend
1. `web/components/ui/evidence-tooltip.tsx` — convert to fully-controlled Tooltip with explicit Base-UI-press suppression:
   - State: `const [open, setOpen] = useState(false)`.
   - Refs: `hoverDebounceRef`, `touchAutoCloseRef`, `touchSessionRef` (boolean).
   - Render `<Tooltip.Root open={open} onOpenChange={handleOpenChange}>` — controlled for the entire lifetime (no undefined→true toggle, so Base UI's `useControlledProp` does not error).
   - Render `<Tooltip.Trigger closeOnClick={false} ...>` — disables Base UI's `useDismiss(referencePress)` close path so our touch onPointerDown can win the race. Click still propagates to our handler (closeOnClick controls Base UI's popup-close behavior, not our onClick).
   - `handleOpenChange(next: boolean)`:
     - If `next === false`: clear both timers, reset `touchSessionRef.current = false`, then `setOpen(false)`.
     - Else: `setOpen(true)`.
   - Trigger button handlers (in addition to existing click→`onClickToInspect`):
     - `onMouseEnter`: if `!touchSessionRef.current`, clear `hoverDebounceRef` and start fresh 300ms timer that calls `setOpen(true)`.
     - `onMouseLeave`: if `!touchSessionRef.current`, clear `hoverDebounceRef` and `setOpen(false)`. (Suppressed during touch session so the 3s auto-close runs to completion.)
     - `onFocus`: if `!touchSessionRef.current`, `setOpen(true)`. (Suppressed during touch session — focus events that fire as a side-effect of the tap must not interfere with the auto-close timer.)
     - `onBlur`: if `!touchSessionRef.current`, `setOpen(false)`.
     - `onPointerDown(e)`: if `e.pointerType === "touch"`:
       1. Set `touchSessionRef.current = true`.
       2. Clear `hoverDebounceRef` and `touchAutoCloseRef`.
       3. `setOpen(true)`.
       4. Start fresh 3000ms `touchAutoCloseRef` timer that runs: `setOpen(false); touchSessionRef.current = false; touchAutoCloseRef.current = null;`.
   - `useEffect` cleanup (unmount): clear both `hoverDebounceRef` and `touchAutoCloseRef`.

   **Single source of truth:** `open` is always a boolean from React state. Tooltip.Root sees a stable controlled prop. Hover/focus/touch all funnel into the same `setOpen` setter. No controlled↔uncontrolled toggle.

   **Why closeOnClick={false} is correct here:** Base UI's referencePress close is a UX assumption ("user clicked the trigger again, so close"). Our trigger doubles as both hover-target AND inspector-launch button. Click→inspect navigates away, so the popup-close-on-click behavior is moot for desktop. For touch, we explicitly want tap-to-open with timer-driven auto-close. Disabling closeOnClick removes Base UI's interference with both flows.

   **Note on hover delay:** the I-f6-001 harness wraps in `<EvidenceTooltipProvider delay={300}>`. With Tooltip.Root now fully controlled, the Provider's delay no longer governs open timing — we replicate the 300ms hover debounce in the component's `onMouseEnter` handler. The Provider stays in place (harmless) so existing call sites compile unchanged.

### Playwright
2. `web/tests/e2e/evidence_tooltip_mobile.spec.ts` (new):
   - Import `devices` from `@playwright/test`.
   - Use `test.use({ ...devices['iPhone 12'] })`.
   - Navigate to `/sentence_hover_test/evidence_tooltip`.
   - Tap the trigger via `page.tap('[data-testid="evidence-tooltip-trigger"]')`.
   - Assert `[data-testid="evidence-tooltip-popup"]` visible within 500ms (after the touch path, no 300ms hover debounce applies — popup should appear immediately).
   - Assert content (tier T1, Published date, quote excerpt) is rendered same as desktop.
   - Optional: wait 3500ms and assert popup auto-closes (validates the 3-second timer).

## Risks for Codex Red-Team
1. **Playwright device profile:** `devices['iPhone 12']` is a stable Playwright export. Verify import path: `import { devices } from "@playwright/test"`.
2. **Single source of truth:** `Tooltip.Root` is fully controlled for the entire component lifetime. No undefined→true→undefined toggling, so `useControlledProp` does not error.
3. **Base UI press-close suppression:** `Tooltip.Trigger closeOnClick={false}` removes the referencePress dismiss path that would otherwise cancel touch-open in the same event.
4. **Touch session isolation:** while `touchSessionRef.current === true`, hover/focus/blur handlers are no-ops, so synthetic focus events from the tap cannot cancel the 3-second auto-close timer.
5. **Existing hover behavior:** moving the 300ms debounce from Provider to component preserves user-visible behavior. The existing `performance_hover.spec.ts` tolerates the 300ms hover delay (per I-f6-001 iter-2 baseline).
6. **Timer hygiene:** two timer refs (`hoverDebounceRef`, `touchAutoCloseRef`) cleared on unmount via `useEffect` cleanup AND on Base UI's `onOpenChange(false)`. No leak across remounts.
7. **§9.4 N/A frontend.**
8. **CHARTER §1 LOC cap:** estimated ~100 LOC component change + ~40 LOC spec = ~140 net. Under 200.

## Acceptance criteria

1. `EvidenceTooltip` is fully-controlled: `<Tooltip.Root open={open} onOpenChange={handleOpenChange}>` — no undefined↔boolean toggling.
2. `Tooltip.Trigger` receives `closeOnClick={false}` to suppress Base UI's referencePress close path.
3. Touch handler (`onPointerDown` with `pointerType === "touch"`) sets `touchSessionRef`, opens the tooltip, and starts a 3000ms auto-close timer.
4. While `touchSessionRef === true`, hover/focus/blur/mouseLeave handlers are suppressed; the auto-close timer is the sole closer.
5. Hover (300ms debounce) + focus open path replicated in component handlers; existing call sites compile unchanged.
6. New Playwright spec uses `devices['iPhone 12']` mobile profile, taps the trigger, asserts popup visible within 500ms with tier + published date + quote content.
7. Click→inspect path (`onClickToInspect`) preserved.
8. Both timers cleared on unmount (`useEffect` cleanup) and on Base UI `onOpenChange(false)`.
9. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-9.

**Completeness check:** list files actually read.

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

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
