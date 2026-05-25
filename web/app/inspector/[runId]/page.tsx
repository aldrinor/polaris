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
import { IntendedUseBanner } from "@/components/global/intended_use_banner";
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
    return (
      <>
        {/* I-ux-001c (#878) sub-PR 1: intended-use posture appears even on
            pending state — the page IS clinical context regardless of whether
            a bundle loaded. */}
        <IntendedUseBanner />
        <BundlePendingCta runId={runId} />
      </>
    );
  }

  // I-ux-001a: signature state lives on the LoadedBundle (tri-valued); the
  // server loader runs `gpg --verify` in an isolated keyring against the
  // shipped trust root + asserts the pinned canonical fingerprint.
  void filesByContentType; // re-exported helper available to consumers
  return (
    <>
      {/* I-ux-001c (#878) sub-PR 1: amber INTENDED USE band above the chrome
          per I-ux-001d TRACK 2 Codex iter-1 P1 fix and plan §6 intended-use
          posture. */}
      <IntendedUseBanner />
      <InspectorView bundle={bundle} />
    </>
  );
}
