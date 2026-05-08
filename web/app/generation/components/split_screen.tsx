"use client";

// I-f12-002: split-screen view for two-run compare. MVP substrate using
// pointer + keyboard with WAI-ARIA Window Splitter pattern. Real shadcn
// <ResizablePanelGroup> from `react-resizable-panels` is a post-MVP
// drop-in replacement at the call site (ditto Tailwind container styles).

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

const MIN_PCT = 20;
const MAX_PCT = 80;
const STEP_PCT = 5;

function clamp(v: number): number {
  return Math.min(MAX_PCT, Math.max(MIN_PCT, v));
}

export function SplitScreen({
  left,
  right,
  initialPercent = 50,
}: {
  left: ReactNode;
  right: ReactNode;
  initialPercent?: number;
}) {
  const [pct, setPct] = useState<number>(clamp(initialPercent));
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef<boolean>(false);

  const onPointerMove = useCallback((e: PointerEvent) => {
    if (!dragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    setPct(clamp(((e.clientX - rect.left) / rect.width) * 100));
  }, []);

  const onPointerUp = useCallback(() => {
    dragging.current = false;
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [onPointerMove, onPointerUp]);

  function onKeyDown(e: React.KeyboardEvent<HTMLButtonElement>) {
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      setPct((p) => clamp(p - STEP_PCT));
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      setPct((p) => clamp(p + STEP_PCT));
    }
  }

  return (
    <div
      ref={containerRef}
      data-testid="split-screen"
      className="flex h-full w-full"
    >
      <section
        data-testid="split-left"
        style={{ width: `${pct}%` }}
        className="overflow-auto"
      >
        {left}
      </section>
      <button
        type="button"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize divider"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={MIN_PCT}
        aria-valuemax={MAX_PCT}
        data-testid="split-divider"
        onPointerDown={(e) => {
          dragging.current = true;
          e.preventDefault();
        }}
        onKeyDown={onKeyDown}
        className="bg-border hover:bg-primary focus:bg-primary w-1 cursor-col-resize touch-none focus:outline-none"
      />
      <section
        data-testid="split-right"
        style={{ width: `${100 - pct}%` }}
        className="overflow-auto"
      >
        {right}
      </section>
    </div>
  );
}
