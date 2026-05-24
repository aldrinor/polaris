// I-cd-013a (GH#609) — Bundle header.
// I-p2-043 (#833) S-tier: the full 8-field audit Card dominated ABOVE the Proof
// Replay centerpiece. Compacted to a slim metadata line + a subordinate "Full manifest"
// disclosure carrying all 8 fields (ZERO loss — report_id and bundle_version live ONLY
// here). Visual-gate iter 2: the signature chip moved OUT to the proof-header's chip row
// (grouped with the two-family chip) so the expanded manifest stays one coherent block
// instead of splitting trust state into two islands. SignatureBadge is exported for that.
import { Fragment } from "react";

import { ChevronRight, ShieldAlert, ShieldCheck } from "lucide-react";

import type { BundleManifest } from "@/lib/signed_bundle";

interface BundleHeaderProps {
  manifest: BundleManifest;
}

export function BundleHeader({ manifest }: BundleHeaderProps) {
  const created = new Date(manifest.bundle_created_at_utc).toUTCString();
  const fields: Array<{ label: string; value: string; mono?: boolean }> = [
    { label: "Bundle ID", value: manifest.bundle_id, mono: true },
    {
      label: "Schema version",
      value: `v${manifest.bundle_version}`,
      mono: true,
    },
    { label: "POLARIS version", value: manifest.polaris_version, mono: true },
    { label: "Generator model", value: manifest.generator_model, mono: true },
    { label: "Decision ID", value: manifest.decision_id, mono: true },
    { label: "Pool ID", value: manifest.pool_id, mono: true },
    { label: "Report ID", value: manifest.report_id, mono: true },
    { label: "Created (UTC)", value: created },
  ];
  return (
    <div data-testid="bundle-header" className="flex flex-col gap-1.5">
      <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
        <span className="font-mono">{manifest.bundle_id}</span>
        <span aria-hidden className="text-muted-foreground/40">
          ·
        </span>
        <span className="font-mono">{manifest.generator_model}</span>
        <span aria-hidden className="text-muted-foreground/40">
          ·
        </span>
        <span>{created}</span>
      </div>
      <details className="group/manifest text-xs">
        <summary className="text-muted-foreground hover:text-foreground ease-standard inline-flex w-fit cursor-pointer list-none items-center gap-1 rounded-md py-0.5 transition-colors duration-150 [&::-webkit-details-marker]:hidden">
          <ChevronRight
            aria-hidden
            className="ease-standard h-3 w-3 transition-transform duration-150 group-open/manifest:rotate-90"
          />
          Full manifest
        </summary>
        <dl className="border-border/60 bg-muted/40 mt-1.5 grid max-w-md grid-cols-[max-content_1fr] gap-x-4 gap-y-1 rounded-md border-l p-2.5">
          {fields.map((f) => (
            <Fragment key={f.label}>
              <dt className="text-muted-foreground">{f.label}</dt>
              <dd
                className={
                  f.mono
                    ? "text-foreground font-mono break-all"
                    : "text-foreground"
                }
              >
                {f.value}
              </dd>
            </Fragment>
          ))}
        </dl>
      </details>
    </div>
  );
}

export function SignatureBadge({ present }: { present: boolean }) {
  if (present) {
    return (
      <span
        className="border-verified/30 bg-verified/10 text-verified inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium"
        data-testid="signature-badge"
        data-state="present"
      >
        <ShieldCheck aria-hidden className="h-3.5 w-3.5" />
        Signed bundle
      </span>
    );
  }
  return (
    <span
      className="border-contradiction/40 bg-contradiction/15 text-contradiction-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium"
      data-testid="signature-badge"
      data-state="missing"
    >
      <ShieldAlert aria-hidden className="h-3.5 w-3.5" />
      Signature missing
    </span>
  );
}
