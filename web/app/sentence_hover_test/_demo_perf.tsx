"use client";

import * as React from "react";

import {
  EvidenceTooltip,
  EvidenceTooltipProvider,
} from "@/components/ui/evidence-tooltip";

const POPUP_SELECTOR = '[data-testid="evidence-tooltip-popup"]';
const TOTAL_ITERS = 100;
const UNMOUNT_POLL_LIMIT = 50;
const STUCK_POPUP_SENTINEL = -1;

function findPopup(node: Node): boolean {
  if (node.nodeType !== Node.ELEMENT_NODE) return false;
  const el = node as Element;
  return el.matches?.(POPUP_SELECTOR) || !!el.querySelector?.(POPUP_SELECTOR);
}

function waitForPopupAdded(): Promise<void> {
  return new Promise((resolve) => {
    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const node of Array.from(m.addedNodes)) {
          if (findPopup(node)) {
            observer.disconnect();
            resolve();
            return;
          }
        }
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });
  });
}

function nextFrame(): Promise<void> {
  return new Promise((r) => requestAnimationFrame(() => r()));
}

async function waitForPopupRemoved(): Promise<boolean> {
  for (let i = 0; i < UNMOUNT_POLL_LIMIT; i++) {
    if (!document.querySelector(POPUP_SELECTOR)) return true;
    await nextFrame();
  }
  return false;
}

export function PerfHarness() {
  const [openOverride, setOpenOverride] = React.useState<boolean | undefined>(
    undefined,
  );
  const [iter, setIter] = React.useState(0);
  const [timings, setTimings] = React.useState<number[]>([]);
  const [running, setRunning] = React.useState(false);
  const timings_ref = React.useRef<number[]>([]);
  const open_ref = React.useRef<boolean | undefined>(undefined);

  React.useEffect(() => {
    open_ref.current = openOverride;
  }, [openOverride]);

  const run = React.useCallback(async () => {
    setRunning(true);
    timings_ref.current = [];
    setTimings([]);
    setIter(0);
    for (let i = 0; i < TOTAL_ITERS; i++) {
      const popup_added = waitForPopupAdded();
      const t_start = performance.now();
      setOpenOverride(true);
      await popup_added;
      const t_end = performance.now();
      timings_ref.current.push(t_end - t_start);

      setOpenOverride(false);
      const removed = await waitForPopupRemoved();
      if (!removed) {
        timings_ref.current[timings_ref.current.length - 1] =
          STUCK_POPUP_SENTINEL;
        break;
      }
      if ((i + 1) % 5 === 0) setIter(i + 1);
    }
    setTimings([...timings_ref.current]);
    setIter(TOTAL_ITERS);
    setRunning(false);
  }, []);

  return (
    <EvidenceTooltipProvider delay={300}>
      <div className="flex flex-col gap-4 p-6">
        <h1 className="text-foreground text-lg font-semibold">
          F6 perf — 100x hover render
        </h1>
        <p className="text-muted-foreground text-sm">
          Click the button to run 100 controlled tooltip-mount cycles via{" "}
          <code>openOverride</code>. Each timing measures from{" "}
          <code>setOpenOverride(true)</code> to MutationObserver popup-added
          callback (React commit + DOM insert).
        </p>
        <div>
          <EvidenceTooltip
            evidenceId="ev-perf-001"
            sourceUrl="https://example.org/perf"
            spanText="Perf-test span; identical across all 100 cycles."
            sourceTier="T1"
            publishedDate="2026-01-01"
            openOverride={openOverride}
            onClickToInspect={() => {}}
          >
            <span data-testid="perf-trigger">[#ev:ev-perf-001:0-50]</span>
          </EvidenceTooltip>
        </div>
        <button
          type="button"
          data-testid="run-perf"
          disabled={running}
          onClick={run}
          className="border-border w-fit rounded border px-4 py-2 text-sm hover:bg-blue-500/10 disabled:opacity-50"
        >
          {running ? `Running… (${iter}/${TOTAL_ITERS})` : "Run 100x perf"}
        </button>
        <div
          data-testid="perf-results"
          data-iter={String(iter)}
          data-timings={JSON.stringify(timings)}
        />
      </div>
    </EvidenceTooltipProvider>
  );
}
