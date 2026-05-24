// I-cd-013a (GH#609) — Two-family invariant badge.
// Source of truth: verified_report.evaluator_model + verified_report.family_segregation_passed
// (NOT metadata.json — corrected at brief iter 1 P1).
// I-p2-043 (#833) S-tier: tokenized (was hardcoded emerald/rose) — pass=--verified,
// FAIL=--destructive (an invariant violation, not a soft warning — Codex P2). Compacted
// from a full p-4 card to an inline trust chip so it rides in the hero's secondary row
// instead of stacking above the Proof Replay centerpiece. Generator/evaluator models stay
// in the title + are surfaced in MetadataPanel and the bundle-header manifest disclosure
// (zero data loss). Keeps data-testid + data-state for the e2e contract.
import { ShieldCheck, ShieldX } from "lucide-react";

import type { VerifiedReportShape } from "@/lib/inspector_bundle_loader";
import type { BundleManifest } from "@/lib/signed_bundle";

interface FamilySegregationBadgeProps {
  manifest: BundleManifest;
  verifiedReport: VerifiedReportShape;
}

export function FamilySegregationBadge({
  manifest,
  verifiedReport,
}: FamilySegregationBadgeProps) {
  const passed = verifiedReport.family_segregation_passed;
  return (
    <span
      data-testid="family-segregation-badge"
      data-state={passed ? "pass" : "fail"}
      title={`Generator: ${manifest.generator_model} · Evaluator: ${verifiedReport.evaluator_model}`}
      className={
        passed
          ? "border-verified/30 bg-verified/10 text-verified inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
          : "border-destructive/40 bg-destructive/10 text-destructive inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      }
    >
      {passed ? (
        <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
      ) : (
        <ShieldX aria-hidden className="h-3.5 w-3.5" />
      )}
      Two-family invariant {passed ? "verified" : "violated"}
    </span>
  );
}
