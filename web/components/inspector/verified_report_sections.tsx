// I-cd-013a (GH#609) — VerifiedReport.sections renderer.
// Real field names per verified_report.py:
//   sections[].section_verify_pass_rate
//   sections[].verified_sentences
//   verified_sentences[].provenance_tokens (token strings)
"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  VerifiedReportSectionShape,
  VerifiedReportShape,
  VerifiedSentenceShape,
} from "@/lib/inspector_bundle_loader";

interface VerifiedReportSectionsProps {
  verifiedReport: VerifiedReportShape;
}

export function VerifiedReportSections({
  verifiedReport,
}: VerifiedReportSectionsProps) {
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
        {verifiedReport.sections.length === 0 ? (
          <p className="border-border text-muted-foreground rounded-md border border-dashed p-4 text-center">
            No verified sections (pipeline verdict:{" "}
            <code className="font-mono">{verifiedReport.pipeline_verdict}</code>
            ).
          </p>
        ) : (
          verifiedReport.sections.map((s) => (
            <SectionPanel key={s.section_id} section={s} />
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

function SectionPanel({ section }: { section: VerifiedReportSectionShape }) {
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
          />
        ))}
      </ul>
    </div>
  );
}

function SentenceItem({ sentence }: { sentence: VerifiedSentenceShape }) {
  const [showTokens, setShowTokens] = useState(false);
  return (
    <li
      className="bg-muted/30 hover:bg-muted/60 rounded-sm border border-transparent p-2 transition-colors"
      data-testid="verified-sentence"
      data-verifier-pass={sentence.verifier_pass}
    >
      <p className="text-sm">{sentence.sentence_text}</p>
      {sentence.provenance_tokens.length > 0 && (
        <button
          type="button"
          className="text-muted-foreground focus-visible:ring-ring mt-1 inline-flex items-center gap-1 text-xs underline-offset-2 hover:underline focus-visible:ring-2 focus-visible:outline-none"
          onClick={() => setShowTokens((v) => !v)}
          data-testid="toggle-provenance-tokens"
        >
          {showTokens ? "Hide" : "Show"} {sentence.provenance_tokens.length}{" "}
          provenance token
          {sentence.provenance_tokens.length === 1 ? "" : "s"}
        </button>
      )}
      {showTokens && (
        <ul className="text-muted-foreground mt-1 ml-4 list-disc font-mono text-xs">
          {sentence.provenance_tokens.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
      )}
    </li>
  );
}
