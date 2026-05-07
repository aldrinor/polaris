"use client";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type {
  ContradictionCategory,
  ContradictionEvidenceType,
  ContradictionSignal,
} from "@/lib/api";

const EVIDENCE_TYPE_LABEL: Record<ContradictionEvidenceType, string> = {
  trial: "Trial",
  guideline: "Guideline",
  meta_analysis: "Meta-analysis",
  observational: "Observational",
  regulatory_label: "Regulatory label",
  expert_opinion: "Expert opinion",
  unspecified: "Unspecified",
};

const TIER_TONE: Record<"T1" | "T2" | "T3", string> = {
  T1: "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  T2: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  T3: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-300",
};

const CATEGORY_LABEL: Record<ContradictionCategory, string> = {
  numeric: "Numeric",
  categorical: "Categorical",
  regulatory: "Regulatory",
  temporal: "Temporal",
  jurisdictional: "Jurisdictional",
  other: "Other",
};

export function ContradictionPane({
  open,
  signal,
  onOpenChange,
}: {
  open: boolean;
  signal: ContradictionSignal | null;
  onOpenChange: (next: boolean) => void;
}) {
  // Codex iter-1 P2: tolerate signal.sides being absent at runtime.
  const sides = signal?.sides ?? [];
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent
        data-testid="contradiction-pane"
        side="right"
        className="data-[side=right]:w-full data-[side=right]:sm:w-2/5 data-[side=right]:sm:max-w-none"
      >
        <SheetHeader>
          <SheetTitle data-testid="contradiction-pane-title">
            {(() => {
              if (!signal) return "";
              const kind = signal.kind ?? "multi_source";
              if (kind === "self_contradiction") {
                return `Self-contradiction: source contradicts itself across ${sides.length} spans`;
              }
              return `Contradiction: ${signal.disagreeing_source_count} sources disagree`;
            })()}
          </SheetTitle>
          <SheetDescription>
            {signal?.summary ?? ""}
            {signal ? (
              <span
                data-testid="contradiction-category"
                className="ml-2 inline-flex items-center rounded-full border border-blue-500/40 bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium tracking-widest text-blue-700 uppercase dark:text-blue-300"
              >
                {CATEGORY_LABEL[signal.category ?? "other"]}
              </span>
            ) : null}
          </SheetDescription>
        </SheetHeader>
        <div className="flex flex-col gap-3 px-4 pb-4 text-sm">
          {sides.map((side, idx) => (
            <div
              key={idx}
              data-testid={`contradiction-side-${idx}`}
              className="border-border flex flex-col gap-1 rounded border p-2 text-xs"
            >
              <div className="flex items-center justify-between gap-2">
                <code data-testid={`contradiction-source-${idx}`}>
                  {side.source_id}
                </code>
                <div className="flex items-center gap-1">
                  {(() => {
                    // Codex iter-1 P2: coalesce undefined to "unspecified"
                    // and skip badge for that default.
                    const et = side.evidence_type ?? "unspecified";
                    if (et === "unspecified") return null;
                    return (
                      <span
                        data-testid={`contradiction-evidence-type-${idx}`}
                        className="rounded-full border border-violet-500/40 bg-violet-500/10 px-2 py-0.5 text-[10px] tracking-widest text-violet-700 uppercase dark:text-violet-300"
                      >
                        {EVIDENCE_TYPE_LABEL[et]}
                      </span>
                    );
                  })()}
                  <span
                    data-testid={`contradiction-tier-${idx}`}
                    className={`rounded-full border px-2 py-0.5 text-[10px] tracking-widest uppercase ${TIER_TONE[side.source_tier]}`}
                  >
                    {side.source_tier}
                  </span>
                </div>
              </div>
              <div className="text-muted-foreground flex flex-wrap gap-2 text-[10px]">
                {side.sample_size !== null &&
                side.sample_size !== undefined ? (
                  <span data-testid={`contradiction-sample-${idx}`}>
                    n = {side.sample_size}
                  </span>
                ) : null}
                <span data-testid={`contradiction-hedge-${idx}`}>
                  {side.hedge_language}
                </span>
                {side.pt08_flag ? (
                  <span data-testid={`contradiction-pt08-${idx}`}>
                    PT08: {side.pt08_flag}
                  </span>
                ) : null}
              </div>
              <blockquote
                data-testid={`contradiction-claim-${idx}`}
                className="border-l-2 border-amber-400 bg-amber-50 px-2 py-1 italic dark:bg-amber-900/20"
              >
                {side.claim_excerpt}
              </blockquote>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
