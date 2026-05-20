// I-cd-013a (GH#609) — gold route: /inspector/[runId].
//
// Server component that loads a signed audit bundle (v1.0 schema per
// src/polaris_graph/audit_bundle/bundle_schema.py) and renders it via
// `InspectorView`. Unknown runIds get the bundle-pending CTA (the page
// does NOT attempt to render an unrelated fixture — see iter-1 P1).
//
// Real-bundle backend wiring lands at I-B-08 (Seq 20); offline fallback
// at I-B-09 (Seq 21). For now `loadBundle` returns the canonical fixtures
// for runId "v1-canonical" and "v1-canonical-success".

import { BundlePendingCta } from "@/components/inspector/bundle_pending_cta";
import { loadBundle } from "@/lib/inspector_bundle_loader";
import { filesByContentType } from "@/lib/signed_bundle";

import { InspectorView } from "./inspector_view";

interface InspectorPageProps {
  params: Promise<{ runId: string }>;
}

export default async function InspectorPage({ params }: InspectorPageProps) {
  const { runId } = await params;
  const bundle = await loadBundle(runId);

  if (bundle === null) {
    return <BundlePendingCta runId={runId} />;
  }

  // Signature presence: the loader only resolves bundles that contain
  // manifest.yaml.asc per the v1.0 conformance check. This boolean is
  // surfaced for transparency; cryptographic verification belongs to
  // operator-side `gpg --verify` tooling, NOT this UI.
  const signaturePresent = true;
  // (kept as a const so the prop wiring is explicit at the call site —
  // the offline fallback at I-B-09 may flip this to false when rendering
  // a tampered/test bundle.)

  void filesByContentType; // re-exported helper available to consumers
  return <InspectorView bundle={bundle} signaturePresent={signaturePresent} />;
}
