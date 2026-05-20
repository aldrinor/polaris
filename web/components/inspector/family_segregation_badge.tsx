// I-cd-013a (GH#609) — Two-family invariant badge.
// Source of truth: verified_report.evaluator_model + verified_report.family_segregation_passed
// (NOT metadata.json — corrected at brief iter 1 P1).
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
    <div
      data-testid="family-segregation-badge"
      data-state={passed ? "pass" : "fail"}
      className="border-border bg-card flex flex-col gap-2 rounded-md border p-4 text-sm"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="font-medium">Two-family invariant</p>
        <span
          className={
            passed
              ? "inline-flex items-center rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
              : "inline-flex items-center rounded-md bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-900 dark:bg-rose-950 dark:text-rose-200"
          }
        >
          {passed ? "Pass" : "Fail"}
        </span>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <p className="text-muted-foreground text-xs tracking-wide uppercase">
            Generator
          </p>
          <p className="font-mono text-sm">{manifest.generator_model}</p>
        </div>
        <div>
          <p className="text-muted-foreground text-xs tracking-wide uppercase">
            Evaluator
          </p>
          <p className="font-mono text-sm">{verifiedReport.evaluator_model}</p>
        </div>
      </div>
    </div>
  );
}
