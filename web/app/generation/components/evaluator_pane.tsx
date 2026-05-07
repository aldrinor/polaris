"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { EvaluatorDisagreement } from "@/lib/api";

export function EvaluatorPane({
  open,
  disagreement,
  onOpenChange,
}: {
  open: boolean;
  disagreement: EvaluatorDisagreement | null;
  onOpenChange: (next: boolean) => void;
}) {
  // Codex iter-1 P2: clear fallback when disagreement payload is absent.
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="evaluator-pane"
        side="right"
        className="data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none"
      >
        <SheetHeader>
          <SheetTitle data-testid="evaluator-pane-title">
            Generator vs Evaluator readings
          </SheetTitle>
          <SheetDescription>
            Two-family evaluator disagrees with generator&rsquo;s claim. Compare both
            readings against the same cited evidence.
          </SheetDescription>
        </SheetHeader>
        {disagreement ? (
          <div className="flex flex-col gap-3 px-4 pb-4 text-sm">
            <div
              data-testid="evaluator-pane-generator-reading"
              className="border-border rounded border bg-blue-500/5 p-2 text-xs"
            >
              <strong className="text-blue-700 dark:text-blue-300">
                Generator:
              </strong>{" "}
              {disagreement.generator_reading}
            </div>
            <div
              data-testid="evaluator-pane-evaluator-reading"
              className="border-border rounded border bg-rose-500/5 p-2 text-xs"
            >
              <strong className="text-rose-700 dark:text-rose-300">
                Evaluator:
              </strong>{" "}
              {disagreement.evaluator_reading}
            </div>
            <div className="text-muted-foreground text-xs">
              <strong>Both reviewed:</strong>{" "}
              <span className="flex flex-wrap gap-1">
                {disagreement.cited_sources.map((src, i) => (
                  <code
                    key={i}
                    data-testid={`evaluator-pane-source-${i}`}
                    className="bg-muted/40 rounded px-1"
                  >
                    {src}
                  </code>
                ))}
              </span>
            </div>
            <div className="text-muted-foreground text-xs">
              <strong>Evaluator model:</strong>{" "}
              <span data-testid="evaluator-pane-model">
                {disagreement.evaluator_model}
              </span>
            </div>
          </div>
        ) : (
          <p
            data-testid="evaluator-pane-empty"
            className="text-muted-foreground px-4 pb-4 text-sm italic"
          >
            No evaluator disagreement detail available.
          </p>
        )}
      </SheetContent>
    </Sheet>
  );
}
