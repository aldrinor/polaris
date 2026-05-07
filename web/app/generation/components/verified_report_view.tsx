"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSentenceHover } from "@/lib/sentence_highlight";
import { cn } from "@/lib/utils";
import {
  keptSentences,
  type DropReason,
  type ReportVerifiedSentence,
  type VerifiedReport,
  type VerifiedReportSection,
} from "@/lib/api";

const STATUS_TONE: Record<string, string> = {
  verified:
    "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  regenerated:
    "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
  dropped: "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
};

const DROP_REASON_LABEL: Record<DropReason, string> = {
  invalid_token: "Invalid token (source not in pool)",
  span_out_of_range: "Span out of range",
  numeric_mismatch: "Numeric mismatch (decimal not in cited span)",
  overlap_too_low: "Insufficient content overlap",
  no_provenance_token: "No provenance token",
};

function VerdictBadge({
  verdict,
}: {
  verdict: "success" | "abort_no_verified_sections";
}) {
  const ok = verdict === "success";
  return (
    <span
      data-testid="verdict-badge"
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        ok
          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
          : "border-rose-500/40 bg-rose-500/10 text-rose-700 dark:text-rose-300",
      )}
    >
      <span aria-hidden="true">{ok ? "●" : "◌"}</span>
      {ok ? "Success" : "Aborted (no verified sections)"}
    </span>
  );
}

function SentenceRow({
  sentence,
  show_dropped,
  sentence_id,
  hovered_id,
}: {
  sentence: ReportVerifiedSentence;
  show_dropped: boolean;
  sentence_id: string;
  hovered_id: string | null;
}) {
  const dropped = !sentence.verifier_pass;
  if (dropped && !show_dropped) return null;

  return (
    <li
      data-testid={dropped ? "dropped-sentence" : "kept-sentence"}
      data-sentence-id={sentence_id}
      className={cn(
        "flex flex-col gap-1 rounded-md border px-3 py-2 text-sm transition-colors",
        dropped
          ? "text-muted-foreground border-rose-500/30 bg-rose-500/5 line-through"
          : "border-border bg-background",
        hovered_id === sentence_id && "bg-yellow-100 dark:bg-yellow-900/40",
      )}
    >
      <span className={cn(dropped ? "" : "text-foreground")}>
        {sentence.sentence_text}
      </span>
      {sentence.provenance_tokens.length > 0 && !dropped ? (
        <span className="text-muted-foreground font-mono text-[10px]">
          {sentence.provenance_tokens.join(" ")}
        </span>
      ) : null}
      {dropped && sentence.drop_reason ? (
        <span className="text-[10px] tracking-widest text-rose-700 uppercase dark:text-rose-300">
          dropped — {DROP_REASON_LABEL[sentence.drop_reason as DropReason]}
        </span>
      ) : null}
    </li>
  );
}

function SectionCard({
  section,
  show_dropped,
  hovered_id,
}: {
  section: VerifiedReportSection;
  show_dropped: boolean;
  hovered_id: string | null;
}) {
  const kept = keptSentences(section);
  const dropped_count = section.verified_sentences.length - kept.length;
  return (
    <Card
      data-testid={`section-${section.section_id}`}
      className={cn(
        "border",
        section.section_status === "dropped" && "opacity-60",
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-3">
        <CardTitle className="text-base">{section.section_title}</CardTitle>
        <span
          className={cn(
            "rounded-full border px-2 py-0.5 text-[10px] tracking-widest uppercase",
            STATUS_TONE[section.section_status],
          )}
        >
          {section.section_status} ·{" "}
          {Math.round(section.section_verify_pass_rate * 100)}%
        </span>
      </CardHeader>
      <CardContent className="flex flex-col gap-2">
        {kept.length === 0 && !show_dropped ? (
          <p className="text-muted-foreground text-sm">
            No verified sentences in this section.
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {section.verified_sentences.map((s, idx) => (
              <SentenceRow
                key={idx}
                sentence={s}
                show_dropped={show_dropped}
                sentence_id={`${section.section_id}:${idx}`}
                hovered_id={hovered_id}
              />
            ))}
          </ul>
        )}
        {!show_dropped && dropped_count > 0 ? (
          <p className="text-muted-foreground text-xs italic">
            {dropped_count} sentence{dropped_count > 1 ? "s" : ""} dropped by
            strict-verify (toggle below to inspect).
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function VerifiedReportView({
  report,
  show_dropped = false,
}: {
  report: VerifiedReport;
  show_dropped?: boolean;
}) {
  const { hovered_id, root_ref } = useSentenceHover();
  return (
    <div
      ref={root_ref}
      data-testid="verified-report-view"
      className="flex flex-col gap-4"
    >
      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle className="text-lg">Verified report</CardTitle>
          <VerdictBadge verdict={report.pipeline_verdict} />
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <dt className="text-muted-foreground">Generator</dt>
            <dd className="text-foreground font-medium">
              {report.generator_model}
            </dd>
            <dt className="text-muted-foreground">Pass rate</dt>
            <dd className="text-foreground font-medium">
              {Math.round(report.overall_verify_pass_rate * 100)}%
            </dd>
            <dt className="text-muted-foreground">Sections</dt>
            <dd className="text-foreground font-medium">
              {
                report.sections.filter((s) => s.section_status !== "dropped")
                  .length
              }{" "}
              kept ·{" "}
              {
                report.sections.filter((s) => s.section_status === "dropped")
                  .length
              }{" "}
              dropped
            </dd>
            <dt className="text-muted-foreground">Latency</dt>
            <dd className="text-foreground font-medium">
              {report.latency_ms} ms
            </dd>
          </dl>
        </CardContent>
      </Card>

      {report.sections.map((section) => (
        <SectionCard
          key={section.section_id}
          section={section}
          show_dropped={show_dropped}
          hovered_id={hovered_id}
        />
      ))}
    </div>
  );
}
