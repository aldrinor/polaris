"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import * as React from "react";

interface EvidenceTooltipProps {
  evidenceId: string;
  sourceUrl?: string;
  spanText?: string;
  sourceTier?: "T1" | "T2" | "T3";
  /**
   * I-f6-001: optional publication-date string surfaced in the popup
   * as `Published: <date>`. When undefined/null, the line is omitted.
   */
  publishedDate?: string | null;
  /**
   * I-f6-002: requested popup side. Default "top" (back-compat). Base UI
   * Positioner applies flip+shift collision avoidance automatically when
   * the requested side would clip the viewport.
   */
  side?: "top" | "right" | "bottom" | "left";
  onClickToInspect?: () => void;
  children: React.ReactNode;
}

const HOVER_DEBOUNCE_MS = 300;
const TOUCH_AUTO_CLOSE_MS = 3000;

/**
 * F6 citation overlay (Phase 2B Task 2B.1) — hover-card preview of the
 * source span behind a provenance token. Click still triggers the right-
 * pane Inspector view; hover shows a quick preview.
 *
 * I-f6-003: fully-controlled Tooltip with explicit hover/focus/touch open
 * semantics. Touch tap opens the popup with a 3-second auto-close timer
 * (Base UI's `closeOnClick={false}` prevents the referencePress dismiss
 * from cancelling our touch-open in the same event).
 */
export function EvidenceTooltip({
  evidenceId,
  sourceUrl,
  spanText,
  sourceTier,
  publishedDate,
  side = "top",
  onClickToInspect,
  children,
}: EvidenceTooltipProps) {
  const [open, setOpen] = React.useState(false);
  const hoverDebounceRef = React.useRef<number | null>(null);
  const touchAutoCloseRef = React.useRef<number | null>(null);
  const touchSessionRef = React.useRef(false);

  const clearHoverDebounce = React.useCallback(() => {
    if (hoverDebounceRef.current !== null) {
      window.clearTimeout(hoverDebounceRef.current);
      hoverDebounceRef.current = null;
    }
  }, []);

  const clearTouchAutoClose = React.useCallback(() => {
    if (touchAutoCloseRef.current !== null) {
      window.clearTimeout(touchAutoCloseRef.current);
      touchAutoCloseRef.current = null;
    }
  }, []);

  const handleOpenChange = React.useCallback(
    (next: boolean) => {
      if (!next) {
        clearHoverDebounce();
        clearTouchAutoClose();
        touchSessionRef.current = false;
      }
      setOpen(next);
    },
    [clearHoverDebounce, clearTouchAutoClose],
  );

  React.useEffect(
    () => () => {
      clearHoverDebounce();
      clearTouchAutoClose();
    },
    [clearHoverDebounce, clearTouchAutoClose],
  );

  const handleMouseEnter = React.useCallback(() => {
    if (touchSessionRef.current) return;
    clearHoverDebounce();
    hoverDebounceRef.current = window.setTimeout(() => {
      hoverDebounceRef.current = null;
      setOpen(true);
    }, HOVER_DEBOUNCE_MS);
  }, [clearHoverDebounce]);

  const handleMouseLeave = React.useCallback(() => {
    if (touchSessionRef.current) return;
    clearHoverDebounce();
    setOpen(false);
  }, [clearHoverDebounce]);

  const handleFocus = React.useCallback(() => {
    if (touchSessionRef.current) return;
    setOpen(true);
  }, []);

  const handleBlur = React.useCallback(() => {
    if (touchSessionRef.current) return;
    setOpen(false);
  }, []);

  const handlePointerDown = React.useCallback(
    (event: React.PointerEvent<HTMLButtonElement>) => {
      if (event.pointerType !== "touch") return;
      touchSessionRef.current = true;
      clearHoverDebounce();
      clearTouchAutoClose();
      setOpen(true);
      touchAutoCloseRef.current = window.setTimeout(() => {
        touchAutoCloseRef.current = null;
        touchSessionRef.current = false;
        setOpen(false);
      }, TOUCH_AUTO_CLOSE_MS);
    },
    [clearHoverDebounce, clearTouchAutoClose],
  );

  return (
    <Tooltip.Root open={open} onOpenChange={handleOpenChange}>
      <Tooltip.Trigger
        closeOnClick={false}
        render={
          <button
            type="button"
            onClick={onClickToInspect}
            onMouseEnter={handleMouseEnter}
            onMouseLeave={handleMouseLeave}
            onFocus={handleFocus}
            onBlur={handleBlur}
            onPointerDown={handlePointerDown}
            className="text-foreground bg-muted hover:bg-foreground hover:text-background mx-0.5 inline-flex min-h-[24px] cursor-pointer items-center rounded px-1.5 py-0.5 font-mono text-xs transition"
          />
        }
      >
        {children}
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={6} side={side}>
          <Tooltip.Popup
            data-testid="evidence-tooltip-popup"
            className="border-border bg-background text-foreground z-50 max-w-md rounded-md border p-3 shadow-md"
          >
            <p className="text-muted-foreground font-mono text-[11px]">
              {evidenceId}
              {sourceTier && ` · tier ${sourceTier}`}
            </p>
            {sourceUrl && (
              <p className="text-muted-foreground mt-1 truncate text-[11px]">
                {sourceUrl}
              </p>
            )}
            {publishedDate && (
              <p
                data-testid="evidence-tooltip-published"
                className="text-muted-foreground mt-1 text-[11px]"
              >
                Published: {publishedDate}
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
