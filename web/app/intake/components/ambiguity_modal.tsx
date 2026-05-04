"use client";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { IntakeScopeDecision } from "@/lib/api";

type AmbiguityModalProps = {
  open: boolean;
  decision: IntakeScopeDecision | null;
  onContinue: () => void;
  onCancel: () => void;
};

export function AmbiguityModal({
  open,
  decision,
  onContinue,
  onCancel,
}: AmbiguityModalProps) {
  const ambiguous_axes =
    decision?.ambiguity_axes.filter((axis) => axis.needs_clarification) ?? [];

  return (
    <DialogPrimitive.Root
      open={open}
      onOpenChange={(next_open) => {
        if (!next_open) onCancel();
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop
          className={cn(
            "fixed inset-0 z-50 bg-black/20 transition-opacity duration-150",
            "data-ending-style:opacity-0 data-starting-style:opacity-0",
            "supports-backdrop-filter:backdrop-blur-xs",
          )}
        />
        <DialogPrimitive.Popup
          data-slot="ambiguity-modal"
          className={cn(
            "bg-popover text-popover-foreground fixed top-1/2 left-1/2 z-50",
            "w-full max-w-lg -translate-x-1/2 -translate-y-1/2",
            "flex flex-col gap-4 rounded-xl border p-6 shadow-lg",
            "transition duration-200 ease-in-out",
            "data-ending-style:opacity-0 data-starting-style:opacity-0",
            "data-ending-style:scale-95 data-starting-style:scale-95",
          )}
        >
          <div className="flex flex-col gap-1">
            <DialogPrimitive.Title className="text-foreground text-lg font-semibold">
              Your question needs clarification
            </DialogPrimitive.Title>
            <DialogPrimitive.Description className="text-muted-foreground text-sm">
              POLARIS detected ambiguity along the PICO axes below. Pick a
              specific interpretation to get a focused answer, or continue with
              the broad question and accept lower confidence.
            </DialogPrimitive.Description>
          </div>

          <ul className="flex flex-col gap-3">
            {ambiguous_axes.map((axis) => (
              <li
                key={axis.axis}
                className="border-border bg-muted/30 flex flex-col gap-2 rounded-lg border p-3"
              >
                <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
                  {axis.axis}
                </span>
                <ul className="text-foreground flex flex-wrap gap-2 text-sm">
                  {axis.plausible_interpretations.map((interp) => (
                    <li
                      key={interp}
                      className="border-border bg-background rounded-md border px-2 py-1 text-xs"
                    >
                      {interp}
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ul>

          {decision?.clarifications_needed.length ? (
            <ul className="text-muted-foreground list-disc pl-5 text-sm">
              {decision.clarifications_needed.map((c, idx) => (
                <li key={idx}>{c}</li>
              ))}
            </ul>
          ) : null}

          <div className="flex justify-end gap-2 pt-2">
            <DialogPrimitive.Close
              render={
                <Button variant="outline" onClick={onCancel}>
                  Refine my question
                </Button>
              }
            />
            <Button variant="default" onClick={onContinue}>
              Continue anyway
            </Button>
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
