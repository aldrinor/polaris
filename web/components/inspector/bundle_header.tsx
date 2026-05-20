// I-cd-013a (GH#609) — Bundle header (top-level manifest summary).
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { BundleManifest } from "@/lib/signed_bundle";

interface BundleHeaderProps {
  manifest: BundleManifest;
  signaturePresent: boolean;
}

export function BundleHeader({
  manifest,
  signaturePresent,
}: BundleHeaderProps) {
  const created = new Date(manifest.bundle_created_at_utc).toUTCString();
  return (
    <Card data-testid="bundle-header">
      <CardHeader>
        <CardTitle>Signed audit bundle</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
        <KeyValue label="Bundle ID" value={manifest.bundle_id} mono />
        <KeyValue
          label="Schema version"
          value={`v${manifest.bundle_version}`}
        />
        <KeyValue label="POLARIS version" value={manifest.polaris_version} />
        <KeyValue
          label="Generator model"
          value={manifest.generator_model}
          mono
        />
        <KeyValue label="Decision ID" value={manifest.decision_id} mono />
        <KeyValue label="Pool ID" value={manifest.pool_id} mono />
        <KeyValue label="Report ID" value={manifest.report_id} mono />
        <KeyValue label="Created (UTC)" value={created} />
        <div className="md:col-span-2">
          <SignatureBadge present={signaturePresent} />
        </div>
      </CardContent>
    </Card>
  );
}

function KeyValue({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <p className="text-muted-foreground text-xs tracking-wide uppercase">
        {label}
      </p>
      <p className={mono ? "font-mono text-sm" : "text-sm"}>{value}</p>
    </div>
  );
}

function SignatureBadge({ present }: { present: boolean }) {
  if (present) {
    return (
      <p
        className="inline-flex items-center gap-1 rounded-md border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
        data-testid="signature-badge"
        data-state="present"
      >
        Signature present
      </p>
    );
  }
  return (
    <p
      className="inline-flex items-center gap-1 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-900 dark:border-amber-700 dark:bg-amber-950 dark:text-amber-200"
      data-testid="signature-badge"
      data-state="missing"
    >
      Signature missing
    </p>
  );
}
