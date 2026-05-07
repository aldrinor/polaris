"use client";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import type { FrameCoverage } from "@/lib/api";

export function FrameCoveragePanel({
  coverage,
}: {
  coverage: FrameCoverage | null | undefined;
}) {
  if (!coverage) return null;
  const { covered_entity_count, total_entity_count, gaps } = coverage;
  // Codex iter-1 P2: degenerate empty 0/0/[] coverage is not informative;
  // render nothing rather than misleading amber gaps panel.
  if (total_entity_count === 0) return null;
  // total>0 from here, so progress_pct is well-defined.
  const progress_pct = Math.round(
    (covered_entity_count / total_entity_count) * 100,
  );
  const all_covered = gaps.length === 0;
  const has_gaps = gaps.length > 0;
  return (
    <Card
      data-testid={
        all_covered ? "frame-coverage-complete" : "frame-coverage-gaps"
      }
      className={cn(
        "border",
        all_covered
          ? "border-emerald-500/40 bg-emerald-500/5"
          : "border-amber-500/40 bg-amber-500/5",
      )}
    >
      <CardContent className="flex flex-col gap-2 py-3">
        <div className="flex items-center justify-between gap-3">
          <span
            className={cn(
              "text-sm font-medium",
              all_covered ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300",
            )}
          >
            {covered_entity_count}/{total_entity_count} entities covered
          </span>
          {has_gaps ? (
            <span
              data-testid="frame-coverage-gap-count"
              className="text-xs text-amber-700 dark:text-amber-300"
            >
              {gaps.length} gap{gaps.length > 1 ? "s" : ""}
            </span>
          ) : null}
        </div>
        <div
          data-testid="frame-coverage-progress"
          className="bg-muted h-2 w-full overflow-hidden rounded-full"
        >
          <div
            className={cn(
              "h-full transition-all",
              all_covered ? "bg-emerald-500" : "bg-amber-500",
            )}
            style={{ width: `${progress_pct}%` }}
          />
        </div>
        {has_gaps ? (
          <ul className="flex flex-col gap-1 text-xs">
            {gaps.map((g, idx) => (
              <li
                key={idx}
                data-testid={`frame-coverage-gap-${idx}`}
                className="text-amber-800 dark:text-amber-200"
              >
                <strong>{g.entity_name}</strong> — {g.reason}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}
