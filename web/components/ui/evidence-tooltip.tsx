"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import * as React from "react";

interface EvidenceTooltipProps {
  evidenceId: string;
  sourceUrl?: string;
  spanText?: string;
  sourceTier?: "T1" | "T2" | "T3";
  onClickToInspect?: () => void;
  children: React.ReactNode;
}

/**
 * F6 citation overlay (Phase 2B Task 2B.1) — hover-card preview of the
 * source span behind a provenance token. Click still triggers the right-
 * pane Inspector view; hover shows a quick preview.
 */
export function EvidenceTooltip({
  evidenceId,
  sourceUrl,
  spanText,
  sourceTier,
  onClickToInspect,
  children,
}: EvidenceTooltipProps) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        render={
          <button
            type="button"
            onClick={onClickToInspect}
            className="text-foreground bg-muted hover:bg-foreground hover:text-background mx-0.5 cursor-pointer rounded px-1 font-mono text-xs transition"
          />
        }
      >
        {children}
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={6} side="top">
          <Tooltip.Popup className="border-border bg-background text-foreground z-50 max-w-md rounded-md border p-3 shadow-md">
            <p className="text-muted-foreground font-mono text-[11px]">
              {evidenceId}
              {sourceTier && ` · tier ${sourceTier}`}
            </p>
            {sourceUrl && (
              <p className="text-muted-foreground mt-1 truncate text-[11px]">
                {sourceUrl}
              </p>
            )}
            {spanText && (
              <p className="text-foreground mt-2 text-xs leading-snug">
                &ldquo;
                {spanText.length > 240
                  ? spanText.slice(0, 240) + "…"
                  : spanText}
                &rdquo;
              </p>
            )}
            <p className="text-muted-foreground mt-2 text-[11px] italic">
              Click to pin in Evidence pane
            </p>
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}

export const EvidenceTooltipProvider = Tooltip.Provider;
