// I-p2-043 (#833) S-tier — the Inspector's bespoke proof-header band.
// Codex visual gate iter-1 P1: the prior thin chip rows read as "form metadata, not a
// premium proof artifact"; the abort shape lost its hero entirely. This consolidates the
// hero question + the proof artifact (verify rate is the headline number) + the trust line
// (two-family + signature + manifest disclosure) into ONE crafted band directly under the
// H1 — the signature move (proof as the page's visual operating system), applied to the
// header. Preserves the bundle-header / family-segregation-badge / signature-badge testids.
import {
  BundleHeader,
  SignatureBadge,
} from "@/components/inspector/bundle_header";
import { FamilySegregationBadge } from "@/components/inspector/family_segregation_badge";
import type { LoadedBundle } from "@/lib/inspector_bundle_loader";

interface InspectorProofHeaderProps {
  bundle: LoadedBundle;
  signaturePresent: boolean;
}

const VERDICT_LABELS: Record<string, string> = {
  abort_no_verified_sections: "No verified sections",
  abort_corpus_inadequate: "Corpus inadequate",
  abort_corpus_approval_denied: "Corpus approval denied",
  abort_scope_rejected: "Scope rejected",
};

function humanizeVerdict(verdict: string): string {
  return (
    VERDICT_LABELS[verdict] ??
    verdict
      .replace(/^abort_/, "")
      .replace(/_/g, " ")
      .trim()
  );
}

export function InspectorProofHeader({
  bundle,
  signaturePresent,
}: InspectorProofHeaderProps) {
  const report = bundle.verifiedReport;
  const sectionCount = report.sections?.length ?? 0;
  const verified = sectionCount > 0;
  const pct = Math.round(report.overall_verify_pass_rate * 100);

  return (
    <header className="flex flex-col gap-4">
      <h1 className="font-heading text-foreground max-w-3xl text-2xl leading-tight font-bold tracking-tight text-balance sm:text-3xl">
        {report.research_question ?? "Signed research bundle"}
      </h1>

      <div
        data-testid="inspector-proof-header"
        className="bg-card ring-foreground/10 shadow-card flex flex-col gap-3 rounded-xl p-4 ring-1 sm:p-5"
      >
        {/* primary proof artifact line — the verify rate is the headline number */}
        {verified ? (
          <div
            data-testid="inspector-proof-summary"
            className="flex flex-wrap items-baseline gap-x-3 gap-y-1"
          >
            <span className="text-verified text-3xl leading-none font-bold tabular-nums">
              {pct}%
            </span>
            <span className="text-foreground text-sm font-medium">
              of claims verified
            </span>
            <span aria-hidden className="text-border">
              •
            </span>
            <span className="text-muted-foreground text-sm">
              {sectionCount} verified section{sectionCount === 1 ? "" : "s"} ·
              every sentence traces to its cited source span
            </span>
          </div>
        ) : (
          <div
            data-testid="inspector-proof-summary"
            className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
          >
            <span className="border-contradiction/40 bg-contradiction/15 text-contradiction-foreground inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium">
              {humanizeVerdict(report.pipeline_verdict)}
            </span>
            <span className="text-muted-foreground">
              No verified sections — see the Report tab for the full pipeline
              verdict.
            </span>
          </div>
        )}

        {/* trust grid — one left-aligned column: the two trust chips grouped on top,
            then the bundle/model/date line + the manifest disclosure as one coherent
            block (so the expanded manifest never splits into floating islands). */}
        <div className="border-border/60 flex flex-col gap-2.5 border-t pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <FamilySegregationBadge
              manifest={bundle.manifest}
              verifiedReport={report}
            />
            <SignatureBadge present={signaturePresent} />
          </div>
          <BundleHeader manifest={bundle.manifest} />
        </div>
      </div>
    </header>
  );
}
