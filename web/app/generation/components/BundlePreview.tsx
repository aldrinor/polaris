"use client";

import { useEffect, useState } from "react";

import {
  AuditBundleError,
  type BundlePreviewResponse,
  type EvidencePool,
  type IntakeScopeDecision,
  type VerifiedReport,
  previewAuditBundle,
} from "@/lib/api";

type State =
  | { kind: "loading" }
  | { kind: "ok"; preview: BundlePreviewResponse }
  | { kind: "error"; code: string; message: string };

const ROWS: ReadonlyArray<readonly [string, string]> = [
  ["scope_decision", "Scope decision"],
  ["evidence_pool", "Evidence pool"],
  ["verified_report", "Verified report"],
  ["source_snapshot", "Source snapshots"],
  ["metadata", "Metadata"],
];

const fmt = (n: number) =>
  n < 1024
    ? `${n} B`
    : n < 1048576
      ? `${(n / 1024).toFixed(1)} KB`
      : `${(n / 1048576).toFixed(2)} MB`;

export function BundlePreview({
  decision,
  pool,
  report,
}: {
  decision: IntakeScopeDecision;
  pool: EvidencePool;
  report: VerifiedReport;
}) {
  const [s, set_s] = useState<State>({ kind: "loading" });
  useEffect(() => {
    let cancel = false;
    previewAuditBundle(decision, pool, report)
      .then((preview) => {
        if (!cancel) set_s({ kind: "ok", preview });
      })
      .catch((err: unknown) => {
        if (cancel) return;
        if (err instanceof AuditBundleError) {
          set_s({ kind: "error", code: err.code, message: err.message });
        } else {
          const message = err instanceof Error ? err.message : "Unknown error.";
          set_s({ kind: "error", code: "unknown", message });
        }
      });
    return () => {
      cancel = true;
    };
  }, [decision, pool, report]);

  if (s.kind === "loading")
    return (
      <section
        data-testid="bundle-preview-loading"
        className="text-muted-foreground border-border rounded-md border p-3 text-xs"
      >
        Computing bundle preview…
      </section>
    );
  if (s.kind === "error")
    return (
      <section
        data-testid="bundle-preview-error"
        className="border-border rounded-md border p-3 text-xs text-rose-700 dark:text-rose-300"
        title={s.message}
      >
        Bundle preview failed:{" "}
        <span data-testid="bundle-preview-error-code">{s.code}</span>
      </section>
    );
  const p = s.preview;
  return (
    <section
      data-testid="bundle-preview"
      className="border-border bg-muted/30 rounded-md border p-3 text-xs"
    >
      <header className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
        <span data-testid="bundle-preview-id">
          Preview ID: {p.preview_bundle_id.slice(0, 8)}…
        </span>
        <span>Generator: {p.generator_model}</span>
        <span>POLARIS: {p.polaris_version}</span>
        <span data-testid="bundle-preview-file-count">
          {p.file_count} file{p.file_count === 1 ? "" : "s"}
        </span>
        <span data-testid="bundle-preview-total-bytes">
          {fmt(p.total_bytes)}
        </span>
      </header>
      <table className="w-full">
        <tbody>
          {ROWS.map(([ct, label]) => {
            const r = p.content_type_breakdown[ct] ?? { count: 0, bytes: 0 };
            return (
              <tr
                key={ct}
                data-testid={`bundle-preview-row-${ct}`}
                className="border-border/50 border-t"
              >
                <td className="py-1">{label}</td>
                <td className="py-1 text-right">{r.count}</td>
                <td className="py-1 text-right tabular-nums">{fmt(r.bytes)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
