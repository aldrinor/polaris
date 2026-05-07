"use client";

import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { FrameCoverage, FrameGap, GapReason } from "@/lib/api";

const UNBLOCK_ACTION: Record<GapReason, string> = {
  paywalled: "Search PMC OA mirror or Sci-Hub for ${entity_name}, or email author for postprint.",
  no_oa: "Email Cochrane corresponding author for OA preprint of ${entity_name}.",
  source_tier_ineligible: "Escalate to Tier-2 manual review for ${entity_name}; document tier override rationale.",
  language_unavailable: "Request translation of ${entity_name} via institutional library translation service.",
  retracted_only: "Search Retraction Watch for replacement source on ${entity_name}; do NOT cite retracted result.",
  jurisdiction_outside: "Note ${entity_name} is outside scope jurisdiction; flag for explicit jurisdictional caveat in report.",
  not_indexed: "Try Google Scholar + author homepages for ${entity_name}; check institutional preprint repositories.",
  embargoed: "Note embargo expiry date for ${entity_name}; schedule report regeneration after release.",
  other: "Manually triage ${entity_name}; document resolution in operator notes.",
};

const GAP_REASON_LABEL: Record<GapReason, string> = {
  paywalled: "Paywalled",
  no_oa: "No OA",
  source_tier_ineligible: "Source-tier ineligible",
  language_unavailable: "Language unavailable",
  retracted_only: "Only retracted sources",
  jurisdiction_outside: "Jurisdiction outside scope",
  not_indexed: "Not indexed",
  embargoed: "Embargoed",
  other: "Other",
};

export function FrameCoveragePanel({
  coverage,
}: {
  coverage: FrameCoverage | null | undefined;
}) {
  const [selected_gap_idx, set_selected_gap_idx] = useState<number | null>(
    null,
  );
  const [copied, set_copied] = useState(false);
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
                role="button"
                tabIndex={0}
                onClick={() => set_selected_gap_idx(idx)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    set_selected_gap_idx(idx);
                  }
                }}
                className="min-h-6 cursor-pointer rounded-md px-2 py-1 text-amber-800 hover:bg-amber-500/10 focus:ring-2 focus:ring-amber-400 focus:outline-none dark:text-amber-200"
              >
                <strong>{g.entity_name}</strong> — {GAP_REASON_LABEL[g.reason]}
                {g.reason_detail ? `: ${g.reason_detail}` : ""}
              </li>
            ))}
          </ul>
        ) : null}
      </CardContent>
      <FrameGapDetailSheet
        gap={selected_gap_idx !== null ? (gaps[selected_gap_idx] ?? null) : null}
        copied={copied}
        onClose={() => {
          set_selected_gap_idx(null);
          set_copied(false);
        }}
        onCopy={async (text) => {
          try {
            await navigator.clipboard.writeText(text);
            set_copied(true);
            setTimeout(() => set_copied(false), 2000);
          } catch {
            // clipboard write rejected (sandbox / no perm) — UI just doesn't flash.
          }
        }}
      />
    </Card>
  );
}

function FrameGapDetailSheet({
  gap,
  copied,
  onClose,
  onCopy,
}: {
  gap: FrameGap | null;
  copied: boolean;
  onClose: () => void;
  onCopy: (text: string) => void;
}) {
  const action = gap
    ? UNBLOCK_ACTION[gap.reason].replace(/\$\{entity_name\}/g, gap.entity_name)
    : "";
  return (
    <Sheet
      open={gap !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent
        data-testid="frame-gap-detail-sheet"
        side="right"
        className="data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none"
      >
        <SheetHeader>
          <SheetTitle data-testid="frame-gap-detail-title">
            {gap ? `${gap.entity_name} — ${GAP_REASON_LABEL[gap.reason]}` : ""}
          </SheetTitle>
          <SheetDescription>
            Documented unblock action for this frame coverage gap.
          </SheetDescription>
        </SheetHeader>
        {gap ? (
          <div className="flex flex-col gap-3 px-4 pb-4 text-sm">
            <p data-testid="frame-gap-detail-body" className="text-foreground">
              {gap.reason_detail ?? "No additional detail provided."}
            </p>
            <p
              data-testid="frame-gap-action"
              className="border-border rounded-md border bg-amber-500/5 p-2 text-sm"
            >
              <strong>Suggested action:</strong> {action}
            </p>
            <div className="flex items-center gap-2">
              <Button
                data-testid="frame-gap-copy-button"
                onClick={() => onCopy(action)}
                size="sm"
              >
                Copy action
              </Button>
              {copied ? (
                <span
                  data-testid="frame-gap-copy-confirm"
                  className="text-xs text-emerald-700 dark:text-emerald-300"
                >
                  Copied!
                </span>
              ) : null}
            </div>
          </div>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
