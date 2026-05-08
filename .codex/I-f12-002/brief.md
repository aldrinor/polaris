# Codex Brief Review — I-f12-002 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 (TEST-GAP-RESIZE-001):** Spec 5 added that performs an actual pointer drag on the divider (`page.mouse.down()`/`move()`/`up()` over `getByTestId("split-divider")`) and asserts both that `aria-valuenow` changed AND that the left panel's bounding width is wider than its initial 50% width.
- **P2 (initialPercent clamp):** `initialPercent` clamped via `Math.min(80, Math.max(20, initialPercent))` in component setup so external callers can't render outside the WAI-ARIA min/max bounds.
- **P2 (keyboard resize):** added `onKeyDown` for ArrowLeft / ArrowRight on the divider button — each step adjusts `pct` by 5%, also clamped to [20, 80].
- **P2 (module docstring MVP swap):** documented in the file header.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f12-002 — Split-screen view with shadcn ResizablePanels. Acceptance: Playwright split-screen test. LOC estimate 130.
- **Substrate today:** I-f12-001 ships the picker. No resizable-panels dependency or component exists in `web/components/ui/`.
- **Honest framing per CLAUDE.md §9.4:** ship a self-contained CSS-driven resizable container with pointer + keyboard support. Documented as MVP substrate; real shadcn `<ResizablePanelGroup>` is a post-MVP polish swap-in (drop-in replacement at the call site).

## Plan

### `web/app/generation/components/split_screen.tsx` (NEW, ~95 LOC, `"use client"`)

```tsx
"use client";
import { useCallback, useEffect, useRef, useState } from "react";

const MIN_PCT = 20;
const MAX_PCT = 80;
const STEP_PCT = 5;

function clamp(v: number) {
  return Math.min(MAX_PCT, Math.max(MIN_PCT, v));
}

export function SplitScreen({
  left, right, initialPercent = 50,
}: {
  left: React.ReactNode;
  right: React.ReactNode;
  initialPercent?: number;
}) {
  const [pct, setPct] = useState(clamp(initialPercent));
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const onPointerMove = useCallback((e: PointerEvent) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setPct(clamp(((e.clientX - rect.left) / rect.width) * 100));
  }, []);
  const onPointerUp = useCallback(() => { dragging.current = false; }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [onPointerMove, onPointerUp]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowLeft") setPct((p) => clamp(p - STEP_PCT));
    if (e.key === "ArrowRight") setPct((p) => clamp(p + STEP_PCT));
  }

  return (
    <div ref={containerRef} className="flex h-full w-full" data-testid="split-screen">
      <section data-testid="split-left" style={{ width: `${pct}%` }}>{left}</section>
      <button
        type="button" role="separator" data-testid="split-divider"
        aria-label="Resize divider" aria-valuenow={Math.round(pct)}
        aria-valuemin={MIN_PCT} aria-valuemax={MAX_PCT}
        onPointerDown={(e) => { dragging.current = true; e.preventDefault(); }}
        onKeyDown={onKeyDown}
        className="..."
      />
      <section data-testid="split-right" style={{ width: `${100 - pct}%` }}>{right}</section>
    </div>
  );
}
```

### `web/app/sentence_hover_test/split_screen/page.tsx` (NEW, ~25 LOC, `"use client"`)

Hosts `<SplitScreen left={<div>LEFT-CONTENT</div>} right={<div>RIGHT-CONTENT</div>} />` for Playwright.

### Tests `web/tests/e2e/split_screen.spec.ts` (NEW, ~50 LOC, 5 specs)

1. `renders both panels with initial 50/50 split` — `getByRole("separator")` exists with `aria-valuenow="50"`.
2. `divider has resize semantics` — `aria-valuemin="20"`, `aria-valuemax="80"`.
3. `left panel content visible`.
4. `right panel content visible`.
5. **(P1 fix)** `pointer drag changes panel widths` — capture initial `bounding box` of `split-left`; perform `page.mouse.down()`, move 100px right, `page.mouse.up()`; assert new `aria-valuenow` differs from 50 AND the left bounding-box `width` is greater than initial.

## Risks for Codex Red-Team

1. **Custom (not shadcn) implementation** — explicitly framed as MVP substrate. Module docstring records this.
2. **Pointer drag in Playwright headless chromium** — the test exercises the public DOM event surface; `page.mouse.down()/move()/up()` triggers the React `onPointerDown` handler.
3. **WAI-ARIA Window Splitter pattern** — `role="separator"` + `aria-valuenow/min/max` + ArrowLeft/ArrowRight keyboard support.
4. **§9.4 hygiene.** `MIN_PCT/MAX_PCT/STEP_PCT` are module-level named constants (not magic numbers).
5. **CHARTER §3 LOC cap.** ~170 LOC net (95+25+50). Under 200.

## Acceptance criteria

1. New `web/app/generation/components/split_screen.tsx` (`"use client"`) with `SplitScreen`, pointer drag + keyboard resize + clamped initialPercent.
2. Standalone fixture page at `/sentence_hover_test/split_screen`.
3. Playwright spec at `web/tests/e2e/split_screen.spec.ts` with 5 specs, including the pointer-drag assertion.
4. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-4.
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
