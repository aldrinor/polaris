"use client";

import { useState } from "react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSentenceHover } from "@/lib/sentence_highlight";
import { cn } from "@/lib/utils";
import {
  keptSentences,
  type AssertionSurface,
  type ContradictionSignal,
  type DropReason,
  type EvaluatorDisagreement,
  type EvidencePool,
  type ReportVerifiedSentence,
  type VerifiedReport,
  type VerifiedReportSection,
} from "@/lib/api";

import { ContradictionPane } from "./contradiction_pane";
import { EvaluatorPane } from "./evaluator_pane";

const ASSERTION_SURFACES: AssertionSurface[] = [
  "prose",
  "table",
  "summary_bullet",
  "limitation",
  "caption",
  "heading",
];

const SURFACE_LABEL: Record<AssertionSurface, string> = {
  prose: "Prose",
  table: "Table",
  summary_bullet: "Summary bullet",
  limitation: "Limitation",
  caption: "Caption",
  heading: "Heading",
};

import { FrameCoveragePanel } from "./frame_coverage_panel";
import { SentenceInspector } from "./sentence_inspector";

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
  onSelect,
  onSelectContradiction,
  onSelectEvaluator,
  pool,
}: {
  sentence: ReportVerifiedSentence;
  show_dropped: boolean;
  sentence_id: string;
  hovered_id: string | null;
  onSelect: (id: string, sentence: ReportVerifiedSentence) => void;
  onSelectContradiction: (signal: ContradictionSignal) => void;
  onSelectEvaluator: (d: EvaluatorDisagreement) => void;
  pool: EvidencePool | null;
}) {
  const dropped = !sentence.verifier_pass;
  if (dropped && !show_dropped) return null;

  // I-f5-010: T1-conflict HEURISTIC — when ≥2 distinct T1 sources are cited
  // for one sentence, surface a "may conflict — review Inspector" caption.
  // Honest framing per CLAUDE.md §9.4: this is NOT a semantic conflict
  // detector; it's a flag prompting human review.
  const t1_conflict = (() => {
    if (!pool || dropped) return false;
    const cited_t1 = new Set<string>();
    for (const tok of sentence.provenance_tokens) {
      const m = tok.match(/^\[#ev:([a-zA-Z0-9_\-]+):/);
      if (!m) continue;
      const src = pool.sources.find((s) => s.source_id === m[1]);
      if (src && src.tier === "T1") cited_t1.add(m[1]);
    }
    return cited_t1.size >= 2;
  })();

  return (
    <li
      data-testid={dropped ? "dropped-sentence" : "kept-sentence"}
      data-sentence-id={sentence_id}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(sentence_id, sentence)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(sentence_id, sentence);
        }
      }}
      className={cn(
        "flex cursor-pointer flex-col gap-1 rounded-md border px-3 py-2 text-sm transition-colors focus:ring-2 focus:ring-blue-400 focus:outline-none",
        dropped
          ? "text-muted-foreground border-rose-500/30 bg-rose-500/5 line-through"
          : "border-border bg-background",
        hovered_id === sentence_id && "bg-yellow-100 dark:bg-yellow-900/40",
      )}
    >
      <div className="flex items-start gap-2">
        {(() => {
          const surface = sentence.assertion_surface ?? "prose";
          if (surface === "prose") return null;
          return (
            <span
              data-testid={`surface-badge-${surface}`}
              title={`Assertion surface: ${SURFACE_LABEL[surface]} (gated through Inspector)`}
              className="inline-flex shrink-0 items-center rounded-full border border-blue-500/40 bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium tracking-widest text-blue-700 uppercase dark:text-blue-300"
            >
              {SURFACE_LABEL[surface]}
            </span>
          );
        })()}
        <span className={cn(dropped ? "" : "text-foreground")}>
          {sentence.sentence_text}
        </span>
      </div>
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
      {!dropped && sentence.evaluator_agrees === false ? (
        <button
          type="button"
          data-testid={`evaluator-flag-${sentence_id}`}
          title="Two-family evaluator disagrees with generator's claim per CLAUDE.md §9.1 invariant 1."
          onClick={(e) => {
            e.stopPropagation();
            if (sentence.evaluator_disagreement)
              onSelectEvaluator(sentence.evaluator_disagreement);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.stopPropagation();
              e.preventDefault();
              if (sentence.evaluator_disagreement)
                onSelectEvaluator(sentence.evaluator_disagreement);
            }
          }}
          className="inline-flex min-h-6 w-fit cursor-pointer items-center gap-1 rounded px-2 py-1 text-[10px] font-medium tracking-widest text-rose-700 uppercase hover:bg-rose-500/10 focus:ring-2 focus:ring-rose-400 focus:outline-none dark:text-rose-300"
        >
          ⚠ Internal evaluator flagged this
        </button>
      ) : null}
      {!dropped && sentence.contradiction ? (
        <button
          type="button"
          data-testid={`inspector-contradiction-${sentence_id}`}
          title={sentence.contradiction.summary}
          onClick={(e) => {
            // Codex iter-1 P2: stop propagation so the parent row's
            // SentenceInspector doesn't ALSO open.
            e.stopPropagation();
            if (sentence.contradiction)
              onSelectContradiction(sentence.contradiction);
          }}
          onKeyDown={(e) => {
            // Codex iter-1 P1: keyboard activation must not bubble to the
            // parent row onKeyDown either, otherwise SentenceInspector opens.
            if (e.key === "Enter" || e.key === " ") {
              e.stopPropagation();
              e.preventDefault();
              if (sentence.contradiction)
                onSelectContradiction(sentence.contradiction);
            }
          }}
          className="inline-flex min-h-6 w-fit cursor-pointer items-center gap-1 rounded px-2 py-1 text-[10px] font-medium tracking-widest text-amber-700 uppercase hover:bg-amber-500/10 focus:ring-2 focus:ring-amber-400 focus:outline-none dark:text-amber-300"
        >
          {(() => {
            const kind = sentence.contradiction.kind ?? "multi_source";
            if (kind === "self_contradiction") {
              // Codex iter-1 P2: self-contradiction span count comes from
              // sides.length, NOT disagreeing_source_count (which is 1).
              const span_n = sentence.contradiction.sides?.length ?? 0;
              return `⚠ Source self-contradicts (${span_n} spans)`;
            }
            return `⚠ ${sentence.contradiction.disagreeing_source_count} sources disagree`;
          })()}
        </button>
      ) : null}
      {t1_conflict ? (
        <span
          data-testid="inspector-t1-conflict"
          title="Multiple T1 sources cited — they may conflict; review Inspector. Heuristic flag, not a semantic conflict detection."
          className="inline-flex items-center gap-1 text-[10px] tracking-widest text-amber-700 uppercase dark:text-amber-300"
        >
          ⚠ T1 sources may conflict — review Inspector
        </span>
      ) : null}
    </li>
  );
}

function SectionCard({
  section,
  show_dropped,
  hovered_id,
  onSelect,
  onSelectContradiction,
  onSelectEvaluator,
  pool,
}: {
  section: VerifiedReportSection;
  show_dropped: boolean;
  hovered_id: string | null;
  onSelect: (id: string, sentence: ReportVerifiedSentence) => void;
  onSelectContradiction: (signal: ContradictionSignal) => void;
  onSelectEvaluator: (d: EvaluatorDisagreement) => void;
  pool: EvidencePool | null;
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
                onSelect={onSelect}
                onSelectContradiction={onSelectContradiction}
                onSelectEvaluator={onSelectEvaluator}
                pool={pool}
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
  pool = null,
}: {
  report: VerifiedReport;
  show_dropped?: boolean;
  pool?: EvidencePool | null;
}) {
  const { hovered_id, root_ref } = useSentenceHover();
  const [inspector, setInspector] = useState<{
    id: string;
    sentence: ReportVerifiedSentence;
  } | null>(null);
  const [contradiction_open, set_contradiction_open] = useState<
    ContradictionSignal | null
  >(null);
  const [evaluator_open, set_evaluator_open] =
    useState<EvaluatorDisagreement | null>(null);
  return (
    <div
      ref={root_ref}
      data-testid="verified-report-view"
      className="flex flex-col gap-4"
    >
      <FrameCoveragePanel coverage={report.frame_coverage ?? null} />
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
            <dt className="text-muted-foreground">Evaluator</dt>
            <dd
              className="text-foreground flex items-center gap-2 font-medium"
              data-testid="report-evaluator"
            >
              {report.evaluator_model}
              {report.family_segregation_passed ? (
                <span
                  data-testid="family-segregated"
                  title="Two-family segregation passed: evaluator and generator are from different training lineages."
                  className="inline-flex items-center rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium tracking-widest text-emerald-700 uppercase dark:text-emerald-300"
                >
                  ✓ Family segregated
                </span>
              ) : (
                <span
                  data-testid="family-not-segregated"
                  title="Two-family segregation FAILED: evaluator and generator share training lineage."
                  className="inline-flex items-center rounded-full border border-rose-500/40 bg-rose-500/10 px-2 py-0.5 text-[10px] font-medium tracking-widest text-rose-700 uppercase dark:text-rose-300"
                >
                  ✗ Same family
                </span>
              )}
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
          <p
            data-testid="assertion-surface-legend"
            className="text-muted-foreground mt-3 text-xs"
          >
            Gated assertion surfaces (all clickable through Inspector):{" "}
            {ASSERTION_SURFACES.map((s) => SURFACE_LABEL[s]).join(", ")}.
          </p>
        </CardContent>
      </Card>

      {report.sections.map((section) => (
        <SectionCard
          key={section.section_id}
          section={section}
          show_dropped={show_dropped}
          hovered_id={hovered_id}
          onSelect={(id, sentence) => setInspector({ id, sentence })}
          onSelectContradiction={(signal) => set_contradiction_open(signal)}
          onSelectEvaluator={(d) => set_evaluator_open(d)}
          pool={pool}
        />
      ))}
      <ContradictionPane
        open={contradiction_open !== null}
        signal={contradiction_open}
        onOpenChange={(open) => {
          if (!open) set_contradiction_open(null);
        }}
      />
      <EvaluatorPane
        open={evaluator_open !== null}
        disagreement={evaluator_open}
        onOpenChange={(open) => {
          if (!open) set_evaluator_open(null);
        }}
      />
      <SentenceInspector
        open={inspector !== null}
        onOpenChange={(open) => {
          if (!open) setInspector(null);
        }}
        sentence={inspector?.sentence ?? null}
        sentence_id={inspector?.id ?? null}
        pool={pool}
      />
    </div>
  );
}
