# Codex DESIGN+DIFF review — I-p2-017 (#756): wire the Proof Replay centerpiece

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `8233e86153a65835a7e085a4018c1f0e951052e3a8827ca19174085b2eeb34e9`. web/ only, 1 file, 40-line diff. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Context — a real phantom-completion gap
#756 = "Report = Proof Replay (CENTERPIECE)". The `ProofReplay` split-view
(#746) — POLARIS's centerpiece (click a verified claim → see its EXACT cited
source span) — was built but **imported by NO route** (`grep -rln ProofReplay
web/` returned only build-cache refs). The inspector's "Report" tab rendered a
plain `VerifiedReportSections` list; there is no `/report` route. So the
centerpiece was invisible in the shipped product — classic code-exists-no-UI
phantom completion.

## Diff (1 file: web/app/inspector/[runId]/inspector_view.tsx)
- Import `ProofReplay` from `@/components/proof_replay/proof_replay`.
- Add a `"proof"` tab labelled "Proof Replay" as the FIRST `TabsTrigger` +
  `defaultValue="proof"` (the centerpiece is now the default inspector view).
- Its `TabsContent` renders `<ProofReplay sections={bundle.verifiedReport.sections}
  evidencePool={bundle.evidencePool} />`. The existing "Report" tab
  (VerifiedReportSections prose list) stays as the second tab.

## Why this is safe + faithful (no fabrication)
ProofReplay is the existing #746 composition (resolveSpan #743 + SourceCard #745
+ VerdictChip #744) with honest edge-case handling (no-tokens / unresolvable-token
/ source-not-in-bundle / span-not-renderable each show an honest note, never
synthetic proof). Props match: `LoadedBundle.verifiedReport.sections`
(VerifiedReportSectionShape[]) + `LoadedBundle.evidencePool`. No new logic — pure
wiring.

## Files I have ALSO checked and they're clean
- `proof_replay.tsx` read in full: flatten() reads section.verified_sentences[]
  (sentence_text/provenance_tokens/verifier_pass) + section.section_title (falls
  back to null) — all present on the canonical bundle's verified_report.
- `resolveSpan` already works with the canonical bundle (the home proof-showcase
  #794 uses it on the same bundle).
- No other consumer of the inspector Report tab; VerifiedReportSections retained.

## Claude visual audit (standalone @1366, real canonical bundle v1-canonical-success)
Inspector renders; "Proof Replay" is the default tab. Split-view: LEFT = 8
verified claims (role=list); selecting the treatment-difference claim shows RIGHT
= the claim text + a VERIFIED chip + the SourceCard (NEJM tirzepatide-vs-
semaglutide) + the exact cited source span blockquote. Faithful claim→span
mapping (the span is the real NEJM SURPASS-2 content carrying the cited numbers).

## Review focus (8-dim rubric + diff)
1. Is "Report = Proof Replay" satisfied by surfacing ProofReplay as the default
   tab (centerpiece now viewable)? Any a11y regression (tab order, the new
   default tab's role=list/listitem)?
2. Faithfulness: the split-view shows ONLY real bundle data; honest notes on
   missing/unresolvable provenance; no synthetic proof.
3. Any P0/P1.

(Note: #756 acceptance also lists "operator sign-off" — that final close stays
with the operator per their deferral; this PR fixes the build gap so the
centerpiece is actually viewable for that sign-off.)

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```

===== DIFF (codex_diff.patch) =====
```diff
diff --git a/web/app/inspector/[runId]/inspector_view.tsx b/web/app/inspector/[runId]/inspector_view.tsx
index 0d950bf3..d5459872 100644
--- a/web/app/inspector/[runId]/inspector_view.tsx
+++ b/web/app/inspector/[runId]/inspector_view.tsx
@@ -7,6 +7,7 @@ import { EvidencePoolTable } from "@/components/inspector/evidence_pool_table";
 import { FamilySegregationBadge } from "@/components/inspector/family_segregation_badge";
 import { HashChainPanel } from "@/components/inspector/hash_chain_panel";
 import { MetadataPanel } from "@/components/inspector/metadata_panel";
+import { ProofReplay } from "@/components/proof_replay/proof_replay";
 import { ReasoningTraceTimeline } from "@/components/inspector/reasoning_trace_timeline";
 import { ScopeDecisionCard } from "@/components/inspector/scope_decision_card";
 import { SourcesPanel } from "@/components/inspector/sources_panel";
@@ -36,8 +37,9 @@ export function InspectorView({
         manifest={bundle.manifest}
         verifiedReport={bundle.verifiedReport}
       />
-      <Tabs defaultValue="report">
+      <Tabs defaultValue="proof">
         <TabsList>
+          <TabsTrigger value="proof">Proof Replay</TabsTrigger>
           <TabsTrigger value="report">Report</TabsTrigger>
           <TabsTrigger value="scope">Scope</TabsTrigger>
           <TabsTrigger value="evidence">Evidence</TabsTrigger>
@@ -46,6 +48,16 @@ export function InspectorView({
           <TabsTrigger value="hashchain">Hash chain</TabsTrigger>
           <TabsTrigger value="metadata">Metadata</TabsTrigger>
         </TabsList>
+        {/* I-p2-017 (#756): the CENTERPIECE — Report = Proof Replay. The #746
+            split-view (click a verified claim → see its exact cited source span)
+            was built but wired into NO route; this surfaces it as the default
+            inspector tab. */}
+        <TabsContent value="proof" tabId="proof">
+          <ProofReplay
+            sections={bundle.verifiedReport.sections}
+            evidencePool={bundle.evidencePool}
+          />
+        </TabsContent>
         <TabsContent value="report" tabId="report">
           <VerifiedReportSections verifiedReport={bundle.verifiedReport} />
         </TabsContent>

# canonical-diff-sha256: 8233e86153a65835a7e085a4018c1f0e951052e3a8827ca19174085b2eeb34e9
```

===== ProofReplay component (full, for faithfulness review) =====
```tsx
// I-p2-007 (#746): Proof Replay split-view — POLARIS's centerpiece. Click a
// verified claim (left) → see the EXACT cited source span (right). Composes the
// shared resolveSpan (#743) + SourceCard (#745) + VerdictChip (#744). Honest:
// malformed/missing/empty provenance never crashes — it shows an honest note,
// never synthetic proof.
"use client";

import { useMemo, useState } from "react";

import {
  SourceCard,
  type SourceCardSource,
} from "@/components/source/source_card";
import { VerdictChip } from "@/components/verdict/verdict_chip";
import { resolveSpan } from "@/lib/evidence_span";
import type { VerifiedReportSectionShape } from "@/lib/inspector_bundle_loader";

interface ProofReplayProps {
  sections: VerifiedReportSectionShape[];
  evidencePool: unknown;
}

interface FlatClaim {
  key: string;
  sectionId: string;
  sectionTitle: string | null;
  text: string;
  tokens: string[];
  verified: boolean;
}

function flatten(sections: VerifiedReportSectionShape[]): FlatClaim[] {
  const out: FlatClaim[] = [];
  sections.forEach((section, si) => {
    const title =
      (typeof section.section_title === "string" && section.section_title) ||
      null;
    section.verified_sentences?.forEach((s, i) => {
      out.push({
        key: `${si}:${i}`,
        sectionId: section.section_id,
        sectionTitle: title,
        text: s.sentence_text,
        tokens: Array.isArray(s.provenance_tokens)
          ? s.provenance_tokens.filter(
              (t): t is string => typeof t === "string",
            )
          : [],
        verified: s.verifier_pass === true,
      });
    });
  });
  return out;
}

function UnverifiedBadge() {
  return (
    <span className="bg-muted text-foreground border-border inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium">
      Unverified
    </span>
  );
}

function ProofPane({
  claim,
  evidencePool,
}: {
  claim: FlatClaim;
  evidencePool: unknown;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-foreground text-sm leading-snug">{claim.text}</p>
        {claim.verified ? (
          <VerdictChip verdict="VERIFIED" />
        ) : (
          <UnverifiedBadge />
        )}
      </div>

      {claim.tokens.length === 0 ? (
        <p className="text-muted-foreground text-xs">
          No provenance tokens recorded for this claim.
        </p>
      ) : (
        <div className="flex flex-col gap-3">
          {claim.tokens.map((token, i) => {
            const span = resolveSpan(token, evidencePool);
            if (span === null) {
              return (
                <p
                  key={`${token}-${i}`}
                  className="text-muted-foreground text-xs"
                >
                  Unresolvable provenance token:{" "}
                  <span className="font-mono">{token}</span>
                </p>
              );
            }
            if (span.source === null) {
              return (
                <p
                  key={`${token}-${i}`}
                  className="text-muted-foreground text-xs"
                >
                  Source <span className="font-mono">{span.sourceId}</span> not
                  in this bundle — verify via the signed bundle.
                </p>
              );
            }
            const cardSource: SourceCardSource = {
              source_id: span.source.source_id,
              title: span.source.title,
              url: span.source.url,
              tier: span.source.tier,
            };
            return (
              <div key={`${token}-${i}`} className="flex flex-col gap-1">
                <SourceCard source={cardSource} />
                {span.quote != null ? (
                  <blockquote className="border-primary text-foreground max-h-48 overflow-auto border-l-2 pl-3 text-xs leading-snug italic">
                    &ldquo;{span.quote}&rdquo;
                  </blockquote>
                ) : (
                  <p className="text-muted-foreground text-xs">
                    Span not renderable from this bundle.
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function ProofReplay({ sections, evidencePool }: ProofReplayProps) {
  const claims = useMemo(() => flatten(sections), [sections]);
  const [selectedKey, setSelectedKey] = useState<string | null>(
    claims[0]?.key ?? null,
  );
  // Fall back to the first claim if the selected key is stale (e.g. sections
  // changed after mount), so the proof pane keeps its default-first behavior.
  const selected =
    claims.find((c) => c.key === selectedKey) ?? claims[0] ?? null;

  if (claims.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No verified claims in this report.
      </p>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div
        role="list"
        aria-label="Claims"
        className="border-border flex max-h-[32rem] flex-col gap-1 overflow-auto rounded-md border p-2"
      >
        {claims.map((claim, i) => {
          const isSelected = claim.key === selectedKey;
          const showHeading =
            i === 0 || claims[i - 1].sectionId !== claim.sectionId;
          return (
            <div key={claim.key} role="listitem">
              {showHeading && claim.sectionTitle && (
                <p className="text-muted-foreground mt-2 mb-1 px-2 text-[11px] font-medium tracking-wide uppercase">
                  {claim.sectionTitle}
                </p>
              )}
              <button
                type="button"
                aria-current={isSelected ? "true" : undefined}
                aria-label={`${claim.verified ? "Verified" : "Unverified"} claim: ${claim.text}`}
                onClick={() => setSelectedKey(claim.key)}
                className={`focus-visible:ring-ring/70 flex w-full items-start gap-2 rounded px-2 py-1.5 text-left text-xs leading-snug transition-colors focus-visible:ring-2 focus-visible:outline-none ${
                  isSelected
                    ? "bg-primary/10 text-foreground border-primary border-l-2"
                    : "text-muted-foreground hover:bg-muted border-l-2 border-transparent"
                }`}
              >
                <span
                  aria-hidden
                  className={`mt-1 inline-block h-1.5 w-1.5 shrink-0 rounded-full ${
                    claim.verified ? "bg-verified" : "bg-muted-foreground"
                  }`}
                />
                <span className="line-clamp-2">{claim.text}</span>
              </button>
            </div>
          );
        })}
      </div>

      <div
        aria-live="polite"
        aria-label="Proof for the selected claim"
        className="border-border rounded-md border p-4"
      >
        {selected ? (
          <ProofPane claim={selected} evidencePool={evidencePool} />
        ) : (
          <p className="text-muted-foreground text-sm">
            Select a claim to see its proof.
          </p>
        )}
      </div>
    </div>
  );
}
```
