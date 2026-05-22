// I-p2-004 (#743): reusable citation chip + hover/focus source card.
// Chip = inline provenance marker (tier dot + mono index/id). Hover OR focus OR
// tap → source card with the EXACT cited span (untruncated) via resolveSpan.
// No-synthetic-proof: shows the span only when resolved, else an honest note.
"use client";

import { Tooltip } from "@base-ui/react/tooltip";
import { useState } from "react";

import { resolveSpan } from "@/lib/evidence_span";

interface CitationChipProps {
  /** A provenance token `[#ev:<id>:<start>-<end>]`. */
  token: string;
  /** The run's evidence pool (EvidenceContract / bundle.evidencePool). */
  evidencePool: unknown;
  /** Optional display index (e.g. the nth citation in a sentence). */
  index?: number;
}

function tierDotClass(tier: string | number | null | undefined): string {
  const t = String(tier ?? "").toUpperCase();
  if (t === "T1" || t === "1") return "bg-tier-1"; // primary evidence (red)
  if (t === "T2" || t === "2") return "bg-tier-2";
  return "bg-tier-3";
}

export function CitationChip({
  token,
  evidencePool,
  index,
}: CitationChipProps) {
  const span = resolveSpan(token, evidencePool);
  const tier = span?.source?.tier ?? null;
  const label = span?.source?.title ?? span?.sourceId ?? token;
  // Controlled open so hover (mouse), focus (keyboard) AND tap (touch) all open
  // the source card — base-ui hover alone is mouse-only (Codex iter-1 P1).
  const [open, setOpen] = useState(false);

  return (
    <Tooltip.Root open={open} onOpenChange={setOpen}>
      <Tooltip.Trigger
        closeOnClick={false}
        render={
          <button
            type="button"
            data-testid="citation-chip"
            data-source-id={span?.sourceId}
            aria-label={`Source: ${label}`}
            onClick={() => setOpen((o) => !o)}
            onMouseEnter={() => setOpen(true)}
            onMouseLeave={() => setOpen(false)}
            onFocus={() => setOpen(true)}
            onBlur={() => setOpen(false)}
            className="border-border text-muted-foreground hover:bg-muted focus-visible:ring-ring/70 mx-0.5 inline-flex min-h-[24px] min-w-[24px] items-center justify-center gap-1 rounded border px-1.5 align-baseline font-mono text-[11px] leading-none transition-colors focus-visible:ring-2 focus-visible:outline-none"
          />
        }
      >
        <span
          aria-hidden
          className={`inline-block h-1.5 w-1.5 shrink-0 rounded-full ${tierDotClass(tier)}`}
        />
        {index != null ? index : (span?.sourceId ?? "ev")}
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={6}>
          <Tooltip.Popup
            data-testid="citation-source-card"
            className="border-border bg-background text-foreground z-50 max-w-md rounded-md border p-3 shadow-md"
          >
            <div className="text-muted-foreground mb-1 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="text-foreground font-medium">{label}</span>
              {tier != null && <span>· tier {String(tier)}</span>}
              <span className="font-mono">
                [{span?.sourceId ?? "?"}:{span?.start ?? "?"}-{span?.end ?? "?"}
                ]
              </span>
            </div>
            {span?.quote != null ? (
              <blockquote className="text-foreground border-border max-h-48 overflow-auto border-l-2 pl-3 text-xs leading-snug italic">
                &ldquo;{span.quote}&rdquo;
              </blockquote>
            ) : (
              <p className="text-muted-foreground text-xs">
                Source span not renderable from this bundle — verify via the
                signed bundle.
              </p>
            )}
            {span?.source?.url && (
              // Non-interactive provenance text: a tooltip popup must not hold
              // interactive elements (unreachable on mouseleave + ARIA
              // antipattern). The clickable "open source" lives in the full
              // source card (#745) / Proof Replay (#756).
              <p
                className="text-muted-foreground mt-1 max-w-full truncate text-[11px]"
                title={span.source.url}
              >
                {span.source.url}
              </p>
            )}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
