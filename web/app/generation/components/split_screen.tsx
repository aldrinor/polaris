"use client";

// I-f12-002: split-screen view backed by react-resizable-panels
// (the engine behind shadcn/ui's <Resizable*> primitives). The library
// emits its own data-testid + role="separator" + aria-orientation so we
// expose stable testids only on outer wrappers and content divs; the
// divider itself is queried by role="separator".

import { Group, Panel, Separator } from "react-resizable-panels";
import { useId, type ReactNode } from "react";

const MIN_PCT = 20;
const MAX_PCT = 80;
// react-resizable-panels v4 treats Panel minSize/maxSize as pixels when
// numeric; pass percentage strings to enforce the 20%-80% bounds.
const MIN_PCT_STR = "20%";
const MAX_PCT_STR = "80%";

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
  const leftDefault = clamp(initialPercent);
  const rightDefault = 100 - leftDefault;
  const reactId = useId();
  const leftId = `${reactId}-left`;
  const rightId = `${reactId}-right`;
  return (
    <div data-testid="split-screen" className="h-full w-full">
      <Group
        orientation="horizontal"
        className="h-full w-full"
        defaultLayout={{ [leftId]: leftDefault, [rightId]: rightDefault }}
      >
        <Panel id={leftId} minSize={MIN_PCT_STR} maxSize={MAX_PCT_STR}>
          <div data-testid="split-left" className="h-full overflow-auto">
            {left}
          </div>
        </Panel>
        <Separator className="bg-border hover:bg-primary focus:bg-primary w-1 cursor-col-resize touch-none focus:outline-none" />
        <Panel id={rightId} minSize={MIN_PCT_STR} maxSize={MAX_PCT_STR}>
          <div data-testid="split-right" className="h-full overflow-auto">
            {right}
          </div>
        </Panel>
      </Group>
    </div>
  );
}
