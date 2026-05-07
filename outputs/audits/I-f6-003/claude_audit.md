# Claude architect audit — I-f6-003

**Issue:** Mobile tap-to-show fallback
**Branch:** bot/I-f6-003
**Canonical-diff-sha256:** 0271f9f12f91fb611098c440240e7b49fbbf46ef5e1d432c64eb6c035f9c65af
**Brief verdict:** APPROVE iter 4 (controlled/uncontrolled toggle and Base UI referencePress concerns resolved across iters 1-4)
**Diff verdict:** APPROVE iter 1 (0/0/0/2 — both P2, accept_remaining)

## Substrate honesty
- Production code change: `EvidenceTooltip` is now fully-controlled (`Tooltip.Root` open prop is a stable boolean for component lifetime; `useControlledProp` cannot error from controlled↔uncontrolled toggle).
- `Tooltip.Trigger closeOnClick={false}` removes Base UI's `useDismiss(referencePress)` close path so the touch `onPointerDown` setOpen(true) is not cancelled by Base UI's same-event close.
- Touch-session isolation: while `touchSessionRef.current === true`, custom hover/focus/blur/mouseLeave handlers are no-ops; the 3000ms `touchAutoCloseRef` timer is the sole closer during touch.
- Hover/focus desktop path replicates the prior Provider 300ms debounce inside the component (own `setTimeout` in `onMouseEnter`); existing harness Provider stays in place (harmless).
- Two timer refs cleared on unmount via `useEffect` cleanup AND on Base UI close (Escape / outside-press) via `handleOpenChange(false)`.

## §9.4 N/A frontend.

## CHARTER §1 LOC cap
- 128 net. Under 200.

## Verdict
APPROVE.
