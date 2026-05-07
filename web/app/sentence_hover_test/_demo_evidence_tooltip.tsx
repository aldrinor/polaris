"use client";

import {
  EvidenceTooltip,
  EvidenceTooltipProvider,
} from "@/components/ui/evidence-tooltip";

/**
 * I-f6-001 harness: minimal page exercising EvidenceTooltip with a
 * `EvidenceTooltipProvider delay={300}` wrapper so the Playwright spec
 * can assert (a) popup absent before hover, (b) popup absent immediately
 * after hover (within ~50ms), (c) popup visible within 500ms.
 */
export function EvidenceTooltipHarness() {
  return (
    <EvidenceTooltipProvider delay={300}>
      <div
        data-testid="evidence-tooltip-harness"
        className="mx-auto max-w-xl p-8"
      >
        <p className="mb-4 text-sm">
          Hover the citation token below to see the evidence tooltip.
        </p>
        <p className="text-sm">
          Aspirin reduces headache pain in adults
          <EvidenceTooltip
            evidenceId="src-demo-1"
            sourceUrl="https://www.cochrane.org/CD-demo-1"
            sourceTier="T1"
            publishedDate="2024-03-15"
            spanText="The randomized trial enrolled 1247 adults with chronic migraines and demonstrated significant aspirin headache reduction."
          >
            <span data-testid="evidence-tooltip-trigger">[#ev:src-demo-1]</span>
          </EvidenceTooltip>
          .
        </p>
      </div>
    </EvidenceTooltipProvider>
  );
}
