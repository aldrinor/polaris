"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export type ChartDatumSource = {
  evidence_id: string;
  url: string;
  tier: "T1" | "T2" | "T3";
  excerpt: string;
};

const TIER_TONE: Record<ChartDatumSource["tier"], string> = {
  T1: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  T2: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  T3: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

export function ChartSourceInspector({
  open,
  onOpenChange,
  source,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  source: ChartDatumSource | null;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="chart-source-pane"
        side="right"
        className="data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none"
      >
        <SheetHeader>
          <SheetTitle>Chart datum source</SheetTitle>
          <SheetDescription>
            Source span derived from the clicked Vega datum.
          </SheetDescription>
        </SheetHeader>
        {source ? (
          <div className="flex flex-col gap-3 px-4 pb-4 text-sm">
            <div className="flex items-center justify-between gap-2">
              <code
                data-testid="chart-source-pane-evidence-id"
                className="bg-muted/40 rounded px-1 text-xs"
              >
                {source.evidence_id}
              </code>
              <span
                data-testid="chart-source-pane-tier"
                className={`rounded-full border px-2 py-0.5 text-[10px] tracking-widest uppercase ${TIER_TONE[source.tier]}`}
              >
                {source.tier}
              </span>
            </div>
            <a
              data-testid="chart-source-pane-url"
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="truncate text-xs text-blue-700 underline dark:text-blue-300"
            >
              {source.url}
            </a>
            <blockquote
              data-testid="chart-source-pane-excerpt"
              className="border-l-2 border-yellow-400 bg-yellow-50 px-2 py-1 text-xs italic dark:bg-yellow-900/20"
            >
              {source.excerpt.length > 240
                ? source.excerpt.slice(0, 240) + "…"
                : source.excerpt}
            </blockquote>
          </div>
        ) : (
          <p
            data-testid="chart-source-pane-empty"
            className="text-muted-foreground px-4 pb-4 text-sm italic"
          >
            No datum selected.
          </p>
        )}
      </SheetContent>
    </Sheet>
  );
}
