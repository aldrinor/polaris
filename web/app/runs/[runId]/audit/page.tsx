// I-p2-020 (#759) — Audit / export: the "take the proof with you" surface.
//
// Distinct from /inspector/[runId] (the evidence EXPLORER: per-claim proof
// replay, evidence, reasoning). This is the COMPLIANCE/EXPORT artifact: the
// signed-package integrity manifest (file hashes), the pipeline gate ledger,
// the two-family provenance, and the download. Server component — every field
// comes from the proven `loadBundle` path (same loader the inspector + the
// /api/inspector_bundle/[runId] route use); no client JS needed (download is a
// plain <a download> to that route).
//
// Honesty (LAW II): the canonical bundle ships WITHOUT manifest.yaml.asc (the
// GPG seal was deliberately deferred — operator "skip the seal, build the real
// proof"). So `signaturePresent` is false and the page says exactly that:
// integrity manifest present, GPG signature pending sovereign signing. It never
// claims a signature that isn't on disk.
//
// The richer per-gate audit log (corpus adequacy / approval / evaluator
// rule-checks from AuditIrRun via GET /api/inspector/runs/{id}) is a documented
// follow-up — that endpoint is used by no frontend yet, so building on it would
// violate LAW II until it's verified live against the backend.

import Link from "next/link";

import { BundlePendingCta } from "@/components/inspector/bundle_pending_cta";
import { Button } from "@/components/ui/button";
import {
  loadBundle,
  type LoadedBundle,
  type VerifiedReportShape,
} from "@/lib/inspector_bundle_loader";
import type { FileEntry } from "@/lib/signed_bundle";

interface AuditPageProps {
  params: Promise<{ runId: string }>;
}

const CONTENT_TYPE_LABEL: Record<string, string> = {
  scope_decision: "Scope decision",
  evidence_pool: "Evidence pool",
  verified_report: "Verified report",
  source_snapshot: "Source snapshot",
  metadata: "Metadata",
  reasoning_trace: "Reasoning trace",
};

function pct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function shortHash(sha256: string): string {
  return sha256.length > 16 ? `${sha256.slice(0, 16)}…` : sha256;
}

// I-p2-020 Codex iter-2 P1: `verified_sentences` carries BOTH passed AND
// dropped sentences (audit completeness), so `.length` overstates coverage.
// Count `verifier_pass === true` for the genuinely span-verified total.
function passedSentences(section: {
  verified_sentences: { verifier_pass: boolean }[];
}): number {
  return section.verified_sentences.filter((s) => s.verifier_pass).length;
}

function totalPassedSentences(report: VerifiedReportShape): number {
  return report.sections.reduce(
    (sum, section) => sum + passedSentences(section),
    0,
  );
}

function totalAttemptedSentences(report: VerifiedReportShape): number {
  return report.sections.reduce(
    (sum, section) => sum + section.verified_sentences.length,
    0,
  );
}

interface GateRow {
  gate: string;
  pass: boolean;
  detail: string;
}

// The pipeline gate ledger, composed ONLY from fields that exist in the proven
// signed-bundle verified_report. No fabricated gate fields.
function buildGateLedger(report: VerifiedReportShape): GateRow[] {
  const rows: GateRow[] = [
    {
      gate: "Pipeline verdict",
      pass: report.pipeline_verdict === "success",
      detail: report.pipeline_verdict,
    },
    {
      gate: "Strict-verify (overall)",
      pass: report.overall_verify_pass_rate >= report.verifier_pass_threshold,
      detail: `${pct(report.overall_verify_pass_rate)} of sentences span-verified · threshold ${pct(report.verifier_pass_threshold)}`,
    },
    {
      gate: "Two-family segregation",
      pass: report.family_segregation_passed,
      // I-p2-020 Codex P2: don't hardcode "≠" when the gate failed (a
      // same-lineage bundle would show a contradictory detail beside Fail).
      detail: report.family_segregation_passed
        ? `Distinct lineages — ${report.generator_model} (generator) ≠ ${report.evaluator_model} (evaluator)`
        : `Same lineage — ${report.generator_model} (generator), ${report.evaluator_model} (evaluator)`,
    },
  ];
  for (const section of report.sections) {
    rows.push({
      gate: `Section: ${section.section_id}`,
      pass: section.section_verify_pass_rate >= report.verifier_pass_threshold,
      detail: `${pct(section.section_verify_pass_rate)} span-verified · ${passedSentences(section)}/${section.verified_sentences.length} sentences passed`,
    });
  }
  return rows;
}

function StatusPill({ pass }: { pass: boolean }) {
  return (
    <span
      className={
        pass
          ? "border-verified bg-verified/10 text-verified inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase"
          : "border-refusal bg-refusal/10 text-refusal inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase"
      }
    >
      {pass ? "Pass" : "Fail"}
    </span>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-muted-foreground text-[10px] font-medium tracking-widest uppercase">
        {label}
      </span>
      <span className="text-foreground text-sm break-words">{value}</span>
    </div>
  );
}

function AuditExportBody({ bundle }: { bundle: LoadedBundle }) {
  const { manifest, metadata, verifiedReport, signatureState, signatureKeyFingerprint, runId } =
    bundle;
  const gateLedger = buildGateLedger(verifiedReport);
  const files: FileEntry[] = manifest.files;
  const totalBytes = files.reduce((sum, f) => sum + f.size_bytes, 0);

  return (
    <div className="flex flex-col gap-8">
      {/* Integrity & provenance */}
      <section className="border-border bg-card shadow-card flex flex-col gap-4 rounded-xl border p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="text-foreground text-sm font-semibold">
            Integrity &amp; provenance
          </h2>
          {/* I-ux-001a honest tri-valued signature status. Only gpg_verified
              may claim "Signed bundle." present_unverified states the file is
              attached but not yet cryptographically verified in this view;
              missing says trust is not established. The CI guard
              (scripts/check_signed_bundles.py) prevents the gpg_verified path
              from regressing — if the demo bundle ever ships without a
              valid signature, CI fails. */}
          {signatureState === "gpg_verified" ? (
            <span
              className="border-verified bg-verified/10 text-verified inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold"
              title={`Cryptographically verified against the published trust-root pubkey (signing key ${signatureKeyFingerprint ?? "—"}).`}
            >
              ⬡ Signed bundle · GPG verified
            </span>
          ) : signatureState === "present_unverified" ? (
            <span
              className="border-contradiction/40 bg-contradiction/10 text-contradiction-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold"
              title="A signature is attached but not verified in this view. Verify offline: gpg --verify manifest.yaml.asc manifest.yaml (after importing the published trust-root pubkey)."
            >
              ⬡ Signature attached · verify offline with gpg
            </span>
          ) : (
            <span
              className="border-border text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium"
              title="No signature file is present. Trust has not been established for this bundle."
            >
              ◌ Not signed · trust not established
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
          <MetaRow label="Bundle ID" value={manifest.bundle_id} />
          <MetaRow label="Schema" value={`v${metadata.schema_version}`} />
          <MetaRow label="POLARIS version" value={metadata.polaris_version} />
          <MetaRow label="Generator model" value={metadata.generator_model} />
          <MetaRow label="Evaluator model" value={metadata.evaluator_model} />
          <MetaRow
            label="Created (UTC)"
            value={metadata.bundle_created_at_utc}
          />
        </div>
      </section>

      {/* Pipeline gate ledger */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="text-foreground text-sm font-semibold">
            Pipeline gate ledger
          </h2>
          <p className="text-muted-foreground text-xs">
            {/* I-p2-020 Codex P2: neutral wording — the same loader serves
                aborted/failing bundles, not only cleared ones. */}
            Gate outcomes recorded for this run, composed from the verified
            report in the bundle — {totalPassedSentences(verifiedReport)} of{" "}
            {totalAttemptedSentences(verifiedReport)} sentences span-verified
            across {verifiedReport.sections.length} sections.
          </p>
        </div>
        <div className="border-border shadow-card hidden overflow-x-auto rounded-xl border sm:block">
          <table className="w-full text-left text-sm">
            <thead className="border-border text-muted-foreground border-b text-[10px] tracking-widest uppercase">
              <tr>
                <th className="px-4 py-2.5 font-medium">Gate</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Detail</th>
              </tr>
            </thead>
            <tbody>
              {gateLedger.map((row) => (
                <tr
                  key={row.gate}
                  className="border-border/60 border-b last:border-0"
                >
                  <td className="text-foreground px-4 py-2.5 font-medium">
                    {row.gate}
                  </td>
                  <td className="px-4 py-2.5">
                    <StatusPill pass={row.pass} />
                  </td>
                  <td className="text-muted-foreground px-4 py-2.5">
                    {row.detail}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Mobile: stacked gate cards — the detail (abort reason, threshold)
            must be fully readable on a compliance surface, not clipped by a
            horizontal-scroll table (Codex visual iter-1 P1). */}
        <div className="flex flex-col gap-2 sm:hidden">
          {gateLedger.map((row) => (
            <div
              key={row.gate}
              className="border-border bg-card shadow-card flex flex-col gap-1.5 rounded-xl border p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <span className="text-foreground text-xs font-medium">
                  {row.gate}
                </span>
                <StatusPill pass={row.pass} />
              </div>
              <p className="text-muted-foreground text-xs break-words">
                {row.detail}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Integrity manifest — the file hash chain */}
      <section className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <h2 className="text-foreground text-sm font-semibold">
            Integrity manifest
          </h2>
          <p className="text-muted-foreground text-xs">
            {/* I-p2-020 Codex P1: state what the hashes ARE (manifest-recorded,
                real) without promising the JSON export below re-hashes to them
                — only the byte-preserving signed package does. */}
            Every file the signed package contains, with the SHA-256 recorded in
            its manifest. Each file&apos;s content is fixed by its hash; the
            detached GPG signature seals the manifest itself — verify offline
            with{" "}
            <code className="font-mono text-[11px]">
              gpg --verify manifest.yaml.asc manifest.yaml
            </code>
            {" "}after importing the published trust-root pubkey.
          </p>
        </div>
        <div className="border-border shadow-card hidden overflow-x-auto rounded-xl border sm:block">
          <table className="w-full text-left text-sm">
            <thead className="border-border text-muted-foreground border-b text-[10px] tracking-widest uppercase">
              <tr>
                <th className="px-4 py-2.5 font-medium">File</th>
                <th className="px-4 py-2.5 font-medium">Type</th>
                <th className="px-4 py-2.5 text-right font-medium">Bytes</th>
                <th className="px-4 py-2.5 font-medium">SHA-256</th>
              </tr>
            </thead>
            <tbody>
              {files.map((f) => (
                <tr
                  key={f.path}
                  className="border-border/60 border-b last:border-0"
                >
                  <td className="text-foreground px-4 py-2.5 font-mono text-xs">
                    {f.path}
                  </td>
                  <td className="text-muted-foreground px-4 py-2.5 text-xs">
                    {CONTENT_TYPE_LABEL[f.content_type] ?? f.content_type}
                  </td>
                  <td className="text-muted-foreground px-4 py-2.5 text-right font-mono text-xs">
                    {f.size_bytes.toLocaleString()}
                  </td>
                  <td
                    className="text-muted-foreground px-4 py-2.5 font-mono text-xs"
                    title={f.sha256}
                  >
                    {shortHash(f.sha256)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {/* Mobile: stacked file cards — the full SHA-256 is the integrity proof,
            so it wraps in full here rather than scrolling off a table (Codex P2). */}
        <div className="flex flex-col gap-2 sm:hidden">
          {files.map((f) => (
            <div
              key={f.path}
              className="border-border bg-card shadow-card flex flex-col gap-1 rounded-xl border p-3"
            >
              <span className="text-foreground font-mono text-xs break-all">
                {f.path}
              </span>
              <div className="text-muted-foreground flex flex-wrap items-center gap-x-2 text-[10px]">
                <span>
                  {CONTENT_TYPE_LABEL[f.content_type] ?? f.content_type}
                </span>
                <span>· {f.size_bytes.toLocaleString()} bytes</span>
              </div>
              <span
                className="text-muted-foreground font-mono text-[10px] break-all"
                title={f.sha256}
              >
                {f.sha256}
              </span>
            </div>
          ))}
        </div>
        <p className="text-muted-foreground text-[10px]">
          {files.length} files · {totalBytes.toLocaleString()} bytes total
        </p>
      </section>

      {/* Export */}
      <section className="border-border bg-card shadow-card flex flex-col gap-3 rounded-xl border p-5">
        <h2 className="text-foreground text-sm font-semibold">
          Export the package
        </h2>
        <p className="text-muted-foreground text-xs">
          {/* I-p2-020 Codex P1: honest — this is a convenience JSON snapshot of
              the parsed bundle, NOT the byte-preserving signed package. Don't
              promise hash/gpg re-verification of this download. */}
          Download the bundle contents as a single JSON document — scope
          decision, evidence pool, verified report, source snapshots and
          reasoning trace. The byte-preserving signed package (a{" "}
          <code className="font-mono text-[11px]">.tar.gz</code> for{" "}
          <code className="font-mono text-[11px]">gpg --verify</code> + per-file
          SHA-256 re-hashing) is produced by the demo signing key (Ed25519,
          fingerprint pinned in{" "}
          <code className="font-mono text-[11px]">state/polaris_gpg_keyid.txt</code>
          ); see the Receipt view for the offline-verify flow.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            nativeButton={false}
            render={
              <a
                href={`/api/inspector_bundle/${encodeURIComponent(runId)}`}
                download={`polaris_audit_${runId}.json`}
              />
            }
          >
            Download audit package (JSON)
          </Button>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href={`/inspector/${runId}`} />}
          >
            Open in Inspector
          </Button>
        </div>
      </section>
    </div>
  );
}

export default async function AuditExportPage({ params }: AuditPageProps) {
  const { runId } = await params;
  const bundle = await loadBundle(runId);

  // Chromeless route (own header + <main>) — see app_shell_gate.tsx.
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              Audit &amp; export
            </span>
            <span className="text-foreground text-base font-semibold">
              Take the proof with you
            </span>
          </div>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href={`/inspector/${runId}`} />}
          >
            Back to Inspector
          </Button>
        </div>
      </header>

      {/* I-p2-020 Codex iter-3 P2: BundlePendingCta renders its OWN <main>, so
          the null path must NOT be wrapped in this page's <main> (single-main
          landmark contract). Only the loaded path provides the <main>. */}
      {bundle === null ? (
        <BundlePendingCta runId={runId} />
      ) : (
        <main
          data-testid="audit-export-page"
          className="mx-auto w-full max-w-5xl flex-1 px-6 py-8"
        >
          <AuditExportBody bundle={bundle} />
        </main>
      )}
    </div>
  );
}
