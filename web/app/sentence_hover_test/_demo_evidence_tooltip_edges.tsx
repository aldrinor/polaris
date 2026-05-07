"use client";

import {
  EvidenceTooltip,
  EvidenceTooltipProvider,
} from "@/components/ui/evidence-tooltip";

/**
 * I-f6-002: edge-aware positioning harness. Three triggers placed near
 * top, bottom, and right viewport edges with deliberately-clipping side
 * requests so Base UI's flip+shift collision avoidance kicks in.
 */
export function EvidenceTooltipEdgesHarness() {
  return (
    <EvidenceTooltipProvider delay={0}>
      <div className="relative h-screen w-screen">
        {/* near-top: requests side="top" but trigger is at top → must flip down */}
        <div className="absolute left-1/2 top-2 -translate-x-1/2">
          <EvidenceTooltip
            evidenceId="src-top"
            spanText="Near-top trigger demonstration."
            side="top"
          >
            <span data-testid="evidence-tooltip-trigger-top">[#ev:top]</span>
          </EvidenceTooltip>
        </div>
        {/* near-bottom: requests side="bottom" but trigger is at bottom → flip up */}
        <div className="absolute bottom-2 left-1/2 -translate-x-1/2">
          <EvidenceTooltip
            evidenceId="src-bottom"
            spanText="Near-bottom trigger demonstration."
            side="bottom"
          >
            <span data-testid="evidence-tooltip-trigger-bottom">
              [#ev:bottom]
            </span>
          </EvidenceTooltip>
        </div>
        {/* near-right: requests side="right" but trigger is at right → flip left */}
        <div className="absolute right-2 top-1/2 -translate-y-1/2">
          <EvidenceTooltip
            evidenceId="src-right"
            spanText="Near-right trigger demonstration."
            side="right"
          >
            <span data-testid="evidence-tooltip-trigger-right">
              [#ev:right]
            </span>
          </EvidenceTooltip>
        </div>
      </div>
    </EvidenceTooltipProvider>
  );
}
