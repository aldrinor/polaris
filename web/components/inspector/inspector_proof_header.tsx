// I-p2-043 (#833) S-tier — the Inspector's bespoke proof-header band.
// I-ux-001c (#878) sub-PR 1: REBUILT to the v6 hero spec.
//
// v6 layout:
//   H1 (research question)
//   Two-band provenance strip:
//     · Faithfulness band : claim counts (verified / partial / unsupported)
//                            + independent-family check note
//     · Evidence strength band : per-certainty counts (high / moderate /
//                            low / very-low) + signed-bundle pill
//   Trust grid : FamilySegregationBadge + SignatureBadge + BundleHeader
//   (collapsed manifest disclosure)
//
// Abort verdicts are HUMANIZED inline (no abort_* tokens reach the UI per the
// zero-jargon banlist from I-ux-001d TRACK 2 Codex iter-1 P1-003).
//
// Two-judgment separation: faithfulness band uses verified-green; evidence-
// strength band uses slate-blue ordinal foregrounds (--certainty-*-fg). The
// two NEVER share a swatch (design_tokens_v2 §2.2; clinical-safety lethal
// failure mode prevention).
import {
  BundleHeader,
  SignatureBadge,
  type SignatureState,
} from "@/components/inspector/bundle_header";
import { FamilySegregationBadge } from "@/components/inspector/family_segregation_badge";
import { flattenToClaimList } from "@/lib/proof_replay_adapter";
import type { LoadedBundle } from "@/lib/inspector_bundle_loader";

interface InspectorProofHeaderProps {
  bundle: LoadedBundle;
  signatureState: SignatureState;
}

const VERDICT_LABELS: Record<string, string> = {
  abort_no_verified_sections: "No claim survived the faithfulness check",
  abort_corpus_inadequate: "Corpus was inadequate for the question",
  abort_corpus_approval_denied: "Corpus declined at the approval gate",
  abort_scope_rejected: "Scope rejected at the gate",
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
  signatureState,
}: InspectorProofHeaderProps) {
  const report = bundle.verifiedReport;
  const sectionCount = report.sections?.length ?? 0;
  const verified = sectionCount > 0;

  // Compute v6 two-band provenance counts from the adapter's per-claim view.
  // Faithfulness verdict tally: verified vs partial vs unsupported.
  // Evidence-strength tally: counts per certainty level.
  const claims = verified
    ? flattenToClaimList(report, bundle.evidencePool)
    : [];
  const f = { verified: 0, partial: 0, unsupported: 0 };
  const e = { high: 0, moderate: 0, low: 0, very_low: 0 };
  for (const c of claims) {
    if (c.faithfulness.verdict === "verified") f.verified += 1;
    else if (c.faithfulness.verdict === "partial") f.partial += 1;
    else f.unsupported += 1;
    if (c.evidence_strength.level === "high") e.high += 1;
    else if (c.evidence_strength.level === "moderate") e.moderate += 1;
    else if (c.evidence_strength.level === "low") e.low += 1;
    else e.very_low += 1;
  }
  const totalClaims = claims.length;

  return (
    <header className="flex flex-col gap-4">
      <h1
        data-testid="inspector-h1"
        className="font-heading text-foreground max-w-3xl text-2xl leading-tight font-bold tracking-tight text-balance sm:text-3xl"
      >
        {report.research_question ?? "Signed research bundle"}
      </h1>

      <div
        data-testid="inspector-proof-header"
        className="bg-card ring-foreground/10 shadow-card flex flex-col gap-3 rounded-xl p-4 ring-1 sm:p-5"
      >
        {verified ? (
          /* v6 two-band provenance strip */
          <div
            data-testid="provenance-strip"
            className="bg-muted/30 flex flex-col gap-1 rounded-md px-3 py-2 text-xs sm:text-[13px]"
          >
            {/* Faithfulness band */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-muted-foreground w-32 shrink-0 text-[10px] font-medium tracking-[0.08em] uppercase">
                Faithfulness
              </span>
              <span className="text-foreground tabular-nums">
                {totalClaims} claim{totalClaims === 1 ? "" : "s"}
              </span>
              <span aria-hidden className="text-border">
                ·
              </span>
              <span className="text-verified font-medium tabular-nums">
                {f.verified} verified
              </span>
              <span className="text-amber-700 tabular-nums">
                · {f.partial} partial
              </span>
              <span className="text-muted-foreground tabular-nums">
                · {f.unsupported} unsupported
              </span>
              <span aria-hidden className="text-border">
                ·
              </span>
              <span className="text-muted-foreground italic">
                independent-family check
              </span>
            </div>
            {/* Evidence-strength band — slate-blue ordinal; NEVER shares
                a swatch with faithfulness greens (design_tokens_v2 §2.2). */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-muted-foreground w-32 shrink-0 text-[10px] font-medium tracking-[0.08em] uppercase">
                Evidence strength
              </span>
              <span
                className="tabular-nums"
                style={{ color: "var(--certainty-high-fg, oklch(0.32 0.14 250))" }}
              >
                {e.high} high
              </span>
              <span
                className="tabular-nums"
                style={{ color: "var(--certainty-moderate-fg, oklch(0.40 0.10 250))" }}
              >
                · {e.moderate} moderate
              </span>
              <span
                className="tabular-nums"
                style={{ color: "var(--certainty-low-fg, oklch(0.45 0.06 250))" }}
              >
                · {e.low} low
              </span>
              <span
                className="tabular-nums"
                style={{ color: "var(--certainty-very-low-fg, oklch(0.50 0.04 250))" }}
              >
                · {e.very_low} very-low
              </span>
              <span aria-hidden className="text-border">
                ·
              </span>
              {/* Codex diff iter-1 P1-005 fix: the 'signed bundle' line is
                  tri-state aware. Only `gpg_verified` may render the green
                  'verifiable offline' affordance; other states render the
                  honest counter-state copy. */}
              {signatureState === "gpg_verified" && (
                <span className="text-verified text-[11px] font-medium">
                  ⬡ signed bundle (verifiable offline)
                </span>
              )}
              {signatureState === "present_unverified" && (
                <span className="text-amber-700 text-[11px] font-medium">
                  ⊟ signature attached — verify offline
                </span>
              )}
              {signatureState === "missing" && (
                <span className="text-contradiction-foreground text-[11px] font-medium">
                  ⊠ not signed — trust not established
                </span>
              )}
            </div>
          </div>
        ) : (
          /* Honest-fail header for abort states. Verdict is humanized; the
              raw abort_* token NEVER reaches the user-facing surface. */
          <div
            data-testid="inspector-proof-summary"
            className="flex flex-wrap items-center gap-x-2 gap-y-1 text-sm"
          >
            <span className="border-amber-700/40 bg-amber-100/40 text-amber-900 inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium">
              {humanizeVerdict(report.pipeline_verdict)}
            </span>
            <span className="text-muted-foreground">
              The pipeline ran honestly and signed the abort. See the Report
              tab for the full per-section state.
            </span>
          </div>
        )}

        {/* Trust grid — two trust chips grouped on top, then the
            bundle/model/date line + the manifest disclosure as one coherent
            block (so the expanded manifest never splits into floating
            islands). */}
        <div className="border-border/60 flex flex-col gap-2.5 border-t pt-3">
          <div className="flex flex-wrap items-center gap-2">
            <FamilySegregationBadge
              manifest={bundle.manifest}
              verifiedReport={report}
            />
            <SignatureBadge state={signatureState} />
          </div>
          <BundleHeader manifest={bundle.manifest} />
        </div>
      </div>
    </header>
  );
}
