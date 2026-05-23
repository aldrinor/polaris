# Codex DESIGN+DIFF review — I-p2-020 (#759): audit / export page

HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `2ff6c1969bee6db719a94fcf7f138b3ca4beaa72f2741fda2206d7ffa552eb8d`. web/ only, 3 files. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## iter-1 → iter-2 delta (all 3 findings fixed)
- **P1 (overclaim — FIXED):** you flagged that the JSON download (`/api/inspector_bundle/<runId>` → `NextResponse.json(bundle)`, parsed objects not byte-preserving files) can't be re-hashed against the manifest SHA-256s, so the copy overclaimed offline verification. Reworded: integrity-manifest copy now says the hashes are the manifest-recorded ones (real) + the GPG signature (pending) seals the manifest; export copy now says the download is a convenience JSON snapshot and that byte-preserving verification (`.tar.gz` + `gpg --verify` + per-file SHA-256 re-hash) comes from the sovereign signer, NOT yet live. No promise the JSON re-hashes.
- **P2 (≠ hardcode — FIXED):** two-family detail is now conditional — `Distinct lineages — gen ≠ eval` when passed, `Same lineage — gen, eval` when failed.
- **P2 (gate wording — FIXED):** "Every gate this run cleared" → "Gate outcomes recorded for this run" (the loader serves aborted/failing bundles too).

## iter-2 → iter-3 delta (your iter-2 P1 fixed)
- **P1 (count — FIXED):** you flagged that `verified_sentences.length` includes BOTH passed AND dropped sentences (audit completeness), overstating coverage. Now I count `verifier_pass === true`: the subtitle reads "{passed} of {attempted} sentences span-verified" and each section row reads "{passed}/{attempted} sentences passed". For the all-pass canonical bundle this renders "8 of 8" / "2/2" — verified in the standalone harness. (`VerifiedSentenceShape.verifier_pass: boolean` confirmed in inspector_bundle_loader.ts.)

## 200-LOC cap exemption (please validate)
Diff is ~378 patch lines / ~350 net additions — over the 200-LOC cap. **Exemption: one atomic new TIER-3 page.** ~340 lines are the single new file `web/app/runs/[runId]/audit/page.tsx` (a dense compliance surface with two tables + small render helpers); the other two files are a 6-line chromeless-pattern add + an 8-line deep-link button. Splitting the page would fragment a cohesive UI unit with no review benefit. Consistent with prior Phase-2 page builds (#761 dashboard was 668 lines). If you judge the size a real review risk, say so; otherwise the exemption stands.

## Context
#759 = "Page: Audit / export (signed package + manifest + audit log; dense-table gates)". This is the COMPLIANCE/EXPORT artifact — **distinct from `/inspector/[runId]`** (the evidence EXPLORER: per-claim proof replay, evidence, reasoning, sources). The inspector already has Hash-chain + Metadata + Scope tabs; this page is the focused "take the proof with you" surface: provenance + gate ledger + integrity manifest + download.

## Data source (LAW II — proven-live only)
Server component on `loadBundle(runId)` → `LoadedBundle` — the SAME proven loader the inspector page AND `/api/inspector_bundle/[runId]/route.ts` use. Every field is fully typed from `signed_bundle.ts` (BundleManifest, BundleMetadata, FileEntry) + `inspector_bundle_loader.ts` (VerifiedReportShape). NO fabricated fields.

**Deliberately NOT used:** `getAuditRun` → `AuditIrRun` (`GET /api/inspector/runs/{id}`) which has the richer per-gate log (adequacy/approval/evaluator rule-checks). That endpoint is referenced by ZERO frontend code today, so I can't prove it's live without running the heavy v6 backend (forbidden in autonomous loops per §8.4). Building the dense gate-table on an unverified endpoint would risk LAW II → captured as a documented follow-up instead. The gate ledger here is composed only from the proven `verified_report`.

## Honesty (LAW II + sovereignty)
The canonical bundle ships WITHOUT `manifest.yaml.asc` (the GPG seal was deliberately deferred — operator "skip the seal, build the real proof"). So `signaturePresent` is false and the page shows exactly that: **"Integrity manifest present · GPG signature pending"** (muted pill + tooltip explaining the sovereign signer is not yet live). It NEVER claims a signature that isn't on disk. The SHA-256 integrity manifest IS real and shown.

## Diff (3 files)
1. `web/app/runs/[runId]/audit/page.tsx` (NEW): the page. Chromeless (own header + `<main data-testid="audit-export-page">`). Sections: (a) Integrity & provenance card (bundle_id, schema, version, generator+evaluator models, created-at, honest signature pill); (b) Pipeline gate ledger dense table — pipeline verdict / strict-verify overall (rate vs threshold) / two-family segregation / per-section verify rates, each a Pass/Fail pill from `text-verified`/`text-refusal` tokens; (c) Integrity manifest dense table — every FileEntry (path/content_type/size/SHA-256, full hash on `title`); (d) Export — `<a download>` to `/api/inspector_bundle/<runId>` + "Open in Inspector". `null` bundle → `BundlePendingCta` inside the chromeless header.
2. `web/components/app_shell_gate.tsx`: added `/^\/runs\/[^/]+\/audit$/` to CHROMELESS_PATTERNS (same focused-drill-down pattern as `/graph`).
3. `web/app/runs/[runId]/page.tsx`: added an "Audit & export" deep-link button in the affordances row.

## Files I have ALSO checked and they're clean
- `loadBundle` / `LoadedBundle` / `VerifiedReportShape` / `BundleManifest` / `BundleMetadata` / `FileEntry` — all imported types verified present + field names exact (no fabrication).
- State tokens `text-verified`/`bg-verified/10`/`border-verified`/`text-refusal` confirmed in `globals.css` + used by dashboard/source_card.
- `Button` `nativeButton={false}` + `render={<a/Link>}` pattern matches the graph/runs pages.
- Chromeless regex anchored (`$`) — only `/runs/<id>/audit`, not nested paths.

## Claude visual audit (standalone harness @1366, real bundle v1-canonical-success)
Chromeless verified (0 global nav, 1 own header). Renders: provenance card (real deepseek generator + google/gemma evaluator, honest "GPG signature pending" pill), gate ledger (verdict success + strict-verify 100% + two-family + 4 section rows all PASS — real data), integrity manifest (scope_decision/evidence_pool/verified_report/metadata/reasoning_trace + source snapshots with real SHA-256), download + inspector buttons. On-brand Frontier-Minimal (white, red accent on the primary download CTA, hairline tables).

## Review focus (8-dim design rubric + diff)
1. Distinct from inspector (not a duplicate of Hash-chain/Metadata tabs)? Does the "compliance/export" framing hold?
2. Honesty: signature-pending disclosure correct + never overclaims a seal? Gate ledger only from real verified_report fields?
3. Design dims: hierarchy, density (two dense tables readable?), token use (state colors ≠ national red), a11y (table semantics, chromeless landmark single header/main), responsive (overflow-x on tables).
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```

===== FULL UPDATED FILE: web/app/runs/[runId]/audit/page.tsx =====
```tsx
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
  const { manifest, metadata, verifiedReport, signaturePresent, runId } =
    bundle;
  const gateLedger = buildGateLedger(verifiedReport);
  const files: FileEntry[] = manifest.files;
  const totalBytes = files.reduce((sum, f) => sum + f.size_bytes, 0);

  return (
    <div className="flex flex-col gap-8">
      {/* Integrity & provenance */}
      <section className="border-border bg-card flex flex-col gap-4 rounded-lg border p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <h2 className="text-foreground text-sm font-semibold">
            Integrity &amp; provenance
          </h2>
          {/* HONEST signature status — never claims a seal that isn't on disk. */}
          {signaturePresent ? (
            <span className="border-verified bg-verified/10 text-verified inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold">
              ⬡ GPG-signed (manifest.yaml.asc present)
            </span>
          ) : (
            <span
              className="border-border text-muted-foreground inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium"
              title="The bundle ships with a SHA-256 integrity manifest now; the detached GPG signature is added once the sovereign Canadian signer is live."
            >
              ◌ Integrity manifest present · GPG signature pending
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
        <div className="border-border overflow-x-auto rounded-lg border">
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
            detached GPG signature (pending sovereign signing) seals the
            manifest itself.
          </p>
        </div>
        <div className="border-border overflow-x-auto rounded-lg border">
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
        <p className="text-muted-foreground text-[10px]">
          {files.length} files · {totalBytes.toLocaleString()} bytes total
        </p>
      </section>

      {/* Export */}
      <section className="border-border bg-card flex flex-col gap-3 rounded-lg border p-5">
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
          SHA-256 re-hashing) is produced by the sovereign Canadian signer,
          which is not yet live.
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

      <main
        data-testid="audit-export-page"
        className="mx-auto w-full max-w-5xl flex-1 px-6 py-8"
      >
        {bundle === null ? (
          <BundlePendingCta runId={runId} />
        ) : (
          <AuditExportBody bundle={bundle} />
        )}
      </main>
    </div>
  );
}
```
