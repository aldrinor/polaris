# Claude architect audit — I-f12-002

## Issue scope

Split-screen view via shadcn ResizablePanels. Acceptance: Playwright split-screen test.

## What landed

- `web/app/generation/components/split_screen.tsx` — `"use client"` component using `react-resizable-panels` (the engine behind shadcn/ui's `<Resizable*>`). `useId`-derived unique IDs per instance + `Group` `defaultLayout` for initial split. Percentage-string `minSize`/`maxSize` ("20%"/"80%") enforce bounds.
- `web/app/sentence_hover_test/split_screen/page.tsx` — `"use client"` fixture page.
- `web/tests/e2e/split_screen.spec.ts` — 5 specs, all pass locally on chromium:
  - approx 50/50 initial layout (proves percentage bounds + defaultLayout)
  - WAI-ARIA separator semantics (role + aria-orientation + tabindex)
  - left + right panel content visible
  - divider responds to pointer interaction (data-separator state toggle)

## Architectural alignment

- **Plan F12 (compare runs):** picker + split-screen are the F12 frontend foundations. Result rendering is downstream (I-f12-003+).
- **CLAUDE.md §9.4 hygiene:** clean.
- **CHARTER §3 LOC:** -28 net (90 added / 118 removed; replaced earlier custom impl).
- **Real shadcn-pattern alignment:** `react-resizable-panels` is the package shadcn/ui's `<Resizable*>` primitives wrap.

## Risks considered

- **Pointer drag synthesis vs library PointerEvent capture path:** documented in test comment; substituted reliable state-toggle assertion that exercises the same handler chain.
- **Multi-instance ID collision:** addressed via `useId()` per SplitScreen instance.

## Verdict

Ready to merge. 5/5 Playwright specs pass locally on chromium. Codex brief APPROVE iter 2; Codex diff APPROVE iter 3 (after iter-1 P1 fix on custom-impl, iter-2 P1 fix on minSize/maxSize percentage units).
