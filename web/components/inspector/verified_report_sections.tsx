// I-cd-013a (GH#609) — VerifiedReport.sections renderer.
// I-ui-014 (#734) — Proof Replay: click a verified sentence to resolve its
// provenance token(s) into the EXACT source span (full_text[start:end]) from
// the evidence pool. No synthetic proof — every span is sliced from a typed
// evidence-pool field, or shown honestly as unavailable.
"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  VerifiedReportSectionShape,
  VerifiedReportShape,
  VerifiedSentenceShape,
} from "@/lib/inspector_bundle_loader";
import { parseProvenanceToken } from "@/lib/provenance_tokens";

interface EvidenceSource {
  source_id: string;
  full_text?: string;
  snippet?: string;
  title?: string;
  url?: string;
  tier?: string | number;
}

interface ResolvedSpan {
  raw: string;
  sourceId: string;
  source: EvidenceSource | undefined;
  start: number;
  end: number;
  quote: string | null;
}

function buildSourceIndex(evidencePool: unknown): Map<string, EvidenceSource> {
  const index = new Map<string, EvidenceSource>();
  const sources = (evidencePool as { sources?: unknown } | null)?.sources;
  if (Array.isArray(sources)) {
    for (const s of sources) {
      if (
        s &&
        typeof s === "object" &&
        typeof (s as EvidenceSource).source_id === "string"
      ) {
        index.set((s as EvidenceSource).source_id, s as EvidenceSource);
      }
    }
  }
  return index;
}

function resolveToken(
  token: string,
  index: Map<string, EvidenceSource>,
): ResolvedSpan | null {
  const parsed = parseProvenanceToken(token);
  if (!parsed) return null;
  const source = index.get(parsed.source_id);
  const body = source?.full_text ?? source?.snippet ?? null;
  const quote =
    body != null && parsed.start >= 0 && parsed.end <= body.length
      ? body.slice(parsed.start, parsed.end)
      : null;
  return {
    raw: token,
    sourceId: parsed.source_id,
    source,
    start: parsed.start,
    end: parsed.end,
    quote,
  };
}

interface VerifiedReportSectionsProps {
  verifiedReport: VerifiedReportShape;
  evidencePool: unknown;
}

export function VerifiedReportSections({
  verifiedReport,
  evidencePool,
}: VerifiedReportSectionsProps) {
  const sourceIndex = buildSourceIndex(evidencePool);
  return (
    <Card data-testid="verified-report-sections">
      <CardHeader>
        <CardTitle>
          Verified report ({verifiedReport.sections.length} sections,{" "}
          {(verifiedReport.overall_verify_pass_rate * 100).toFixed(0)}%
          verified)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <VerdictBadge verdict={verifiedReport.pipeline_verdict} />
        <p className="text-muted-foreground text-xs">
          Click any sentence to see the exact source passage it is verified
          against.
        </p>
        {verifiedReport.sections.length === 0 ? (
          <p className="border-border text-muted-foreground rounded-md border border-dashed p-4 text-center">
            No verified sections (pipeline verdict:{" "}
            <code className="font-mono">{verifiedReport.pipeline_verdict}</code>
            ).
          </p>
        ) : (
          verifiedReport.sections.map((s) => (
            <SectionPanel
              key={s.section_id}
              section={s}
              sourceIndex={sourceIndex}
            />
          ))
        )}
      </CardContent>
    </Card>
  );
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const isSuccess = verdict === "success";
  return (
    <p
      data-testid="pipeline-verdict-badge"
      data-state={isSuccess ? "success" : "abort"}
      className={
        isSuccess
          ? "inline-flex items-center rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
          : "inline-flex items-center rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200"
      }
    >
      Verdict: {verdict}
    </p>
  );
}

function SectionPanel({
  section,
  sourceIndex,
}: {
  section: VerifiedReportSectionShape;
  sourceIndex: Map<string, EvidenceSource>;
}) {
  return (
    <div
      className="border-border rounded-md border p-4"
      data-testid="verified-report-section"
      data-section-id={section.section_id}
    >
      <div className="mb-2 flex items-center justify-between gap-3">
        <h3 className="font-medium">{section.section_id}</h3>
        <span className="text-muted-foreground font-mono text-xs">
          pass rate {(section.section_verify_pass_rate * 100).toFixed(0)}%
        </span>
      </div>
      <ul className="space-y-2">
        {section.verified_sentences.map((sentence, idx) => (
          <SentenceItem
            key={`${section.section_id}-${idx}`}
            sentence={sentence}
            sourceIndex={sourceIndex}
          />
        ))}
      </ul>
    </div>
  );
}

function SentenceItem({
  sentence,
  sourceIndex,
}: {
  sentence: VerifiedSentenceShape;
  sourceIndex: Map<string, EvidenceSource>;
}) {
  const [open, setOpen] = useState(false);
  const resolved = sentence.provenance_tokens
    .map((t) => resolveToken(t, sourceIndex))
    .filter((r): r is ResolvedSpan => r !== null);
  const hasProof = resolved.length > 0;

  return (
    <li
      className="border-border/60 rounded-sm border p-2"
      data-testid="verified-sentence"
      data-verifier-pass={sentence.verifier_pass}
    >
      <button
        type="button"
        disabled={!hasProof}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="focus-visible:ring-ring enabled:hover:bg-muted/60 -m-2 flex w-full items-start gap-2 rounded-sm p-2 text-left transition-colors focus-visible:ring-2 focus-visible:outline-none disabled:cursor-default"
        data-testid="toggle-provenance-tokens"
      >
        <span
          aria-hidden
          className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${
            sentence.verifier_pass ? "bg-primary" : "bg-muted-foreground/40"
          }`}
        />
        <span className="flex-1 text-sm">{sentence.sentence_text}</span>
        {hasProof && (
          <span className="text-muted-foreground shrink-0 text-xs">
            {open ? "hide source" : "show source"}
          </span>
        )}
      </button>
      {open && (
        <div className="mt-2 space-y-2" data-testid="proof-replay-spans">
          {resolved.map((r) => (
            <ProofSpan key={r.raw} span={r} />
          ))}
        </div>
      )}
    </li>
  );
}

function ProofSpan({ span }: { span: ResolvedSpan }) {
  const label = span.source?.title ?? span.sourceId;
  return (
    <div
      className="border-primary/30 bg-primary/5 rounded-sm border-l-2 p-3"
      data-testid="proof-source-span"
      data-source-id={span.sourceId}
    >
      <div className="text-muted-foreground mb-1 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-foreground font-medium">{label}</span>
        {span.source?.tier != null && (
          <span>· tier {String(span.source.tier)}</span>
        )}
        <span className="font-mono">
          [{span.sourceId}:{span.start}-{span.end}]
        </span>
      </div>
      {span.quote != null ? (
        <blockquote className="text-foreground border-border border-l-2 pl-3 text-sm italic">
          “{span.quote}”
        </blockquote>
      ) : (
        <p className="text-muted-foreground text-sm">
          Source body not in this bundle — span not renderable here (verify via
          the signed bundle).
        </p>
      )}
      {span.source?.url && (
        <a
          href={span.source.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-primary mt-1 inline-block text-xs underline-offset-2 hover:underline"
        >
          {span.source.url}
        </a>
      )}
    </div>
  );
}
