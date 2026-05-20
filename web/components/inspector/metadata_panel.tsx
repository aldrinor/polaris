// I-cd-021 (#631): metadata panel — Codex iter-1 P1.2 finding was that
// `LoadedBundle.metadata` was parsed but never rendered. Adds explicit
// surfacing for both /inspector/[runId] and /inspector/offline.

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BundleMetadata } from "@/lib/signed_bundle";

interface MetadataPanelProps {
  metadata: BundleMetadata;
}

export function MetadataPanel({ metadata }: MetadataPanelProps) {
  return (
    <Card data-testid="metadata-panel">
      <CardHeader>
        <CardTitle className="text-base">Bundle metadata</CardTitle>
      </CardHeader>
      <CardContent className="text-sm">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-[max-content,1fr]">
          <dt className="text-muted-foreground">POLARIS version</dt>
          <dd
            className="text-foreground font-mono"
            data-testid="metadata-polaris-version"
          >
            {metadata.polaris_version}
          </dd>
          <dt className="text-muted-foreground">Generator model</dt>
          <dd
            className="text-foreground font-mono"
            data-testid="metadata-generator-model"
          >
            {metadata.generator_model}
          </dd>
          <dt className="text-muted-foreground">Evaluator model</dt>
          <dd
            className="text-foreground font-mono"
            data-testid="metadata-evaluator-model"
          >
            {metadata.evaluator_model}
          </dd>
          <dt className="text-muted-foreground">Bundle created at (UTC)</dt>
          <dd
            className="text-foreground font-mono"
            data-testid="metadata-created-at"
          >
            {metadata.bundle_created_at_utc}
          </dd>
          <dt className="text-muted-foreground">Schema version</dt>
          <dd
            className="text-foreground font-mono"
            data-testid="metadata-schema-version"
          >
            {metadata.schema_version}
          </dd>
        </dl>
      </CardContent>
    </Card>
  );
}
