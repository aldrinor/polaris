// I-cd-013a (GH#609) — Inspector view (client component, Tabs structure).
// I-p2-043 (#833) S-tier: the page led with two stacked audit-metadata cards
// (BundleHeader + FamilySegregationBadge) ABOVE the Proof Replay centerpiece —
// "compliance tooling before the product" (Codex). Restructured so a bespoke
// proof-header band (question + verify-rate proof artifact + trust line) leads and
// Proof Replay is the default tab. See InspectorProofHeader.
"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EvidencePoolTable } from "@/components/inspector/evidence_pool_table";
import { HashChainPanel } from "@/components/inspector/hash_chain_panel";
import { InspectorProofHeader } from "@/components/inspector/inspector_proof_header";
import { MetadataPanel } from "@/components/inspector/metadata_panel";
import { ProofReplay } from "@/components/proof_replay/proof_replay";
import { ReasoningTraceTimeline } from "@/components/inspector/reasoning_trace_timeline";
import { ScopeDecisionCard } from "@/components/inspector/scope_decision_card";
import { SourcesPanel } from "@/components/inspector/sources_panel";
import { VerifiedReportSections } from "@/components/inspector/verified_report_sections";
import type { LoadedBundle } from "@/lib/inspector_bundle_loader";

interface InspectorViewProps {
  bundle: LoadedBundle;
  signaturePresent: boolean;
}

export function InspectorView({
  bundle,
  signaturePresent,
}: InspectorViewProps) {
  return (
    <main
      className="mx-auto flex max-w-6xl flex-col gap-6 p-6"
      data-testid="inspector-view"
      data-run-id={bundle.runId}
    >
      <InspectorProofHeader
        bundle={bundle}
        signaturePresent={signaturePresent}
      />
      <Tabs defaultValue="proof">
        {/* I-p2-043 (#833): the 8-tab rail overflowed the 375w viewport (Codex visual
            iter-2 P1). Contain it in a horizontal-scroll lane — desktop hugs content,
            mobile scrolls instead of bleeding off-screen. */}
        <div className="-mx-1 overflow-x-auto px-1 pb-1">
          <TabsList>
            <TabsTrigger value="proof">Proof Replay</TabsTrigger>
            <TabsTrigger value="report">Report</TabsTrigger>
            <TabsTrigger value="scope">Scope</TabsTrigger>
            <TabsTrigger value="evidence">Evidence</TabsTrigger>
            <TabsTrigger value="reasoning">Reasoning</TabsTrigger>
            <TabsTrigger value="sources">Sources</TabsTrigger>
            <TabsTrigger value="hashchain">Hash chain</TabsTrigger>
            <TabsTrigger value="metadata">Metadata</TabsTrigger>
          </TabsList>
        </div>
        {/* I-p2-017 (#756): the CENTERPIECE — Report = Proof Replay. The #746
            split-view (click a verified claim → see its exact cited source span)
            was built but wired into NO route; this surfaces it as the default
            inspector tab. */}
        <TabsContent value="proof" tabId="proof">
          <ProofReplay
            sections={bundle.verifiedReport.sections}
            evidencePool={bundle.evidencePool}
          />
        </TabsContent>
        <TabsContent value="report" tabId="report">
          <VerifiedReportSections verifiedReport={bundle.verifiedReport} />
        </TabsContent>
        <TabsContent value="scope" tabId="scope">
          <ScopeDecisionCard value={bundle.scopeDecision} />
        </TabsContent>
        <TabsContent value="evidence" tabId="evidence">
          <EvidencePoolTable value={bundle.evidencePool} />
        </TabsContent>
        <TabsContent value="reasoning" tabId="reasoning">
          <ReasoningTraceTimeline records={bundle.reasoningTrace} />
        </TabsContent>
        <TabsContent value="sources" tabId="sources">
          <SourcesPanel sources={bundle.sources} />
        </TabsContent>
        <TabsContent value="hashchain" tabId="hashchain">
          <HashChainPanel manifest={bundle.manifest} />
        </TabsContent>
        <TabsContent value="metadata" tabId="metadata">
          <MetadataPanel metadata={bundle.metadata} />
        </TabsContent>
      </Tabs>
    </main>
  );
}
