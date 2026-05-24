"use client";

import { Check, GitCompareArrows, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  compareRuns,
  listCompletedRuns,
  type ReportComparison,
  type RunStatusResponse,
} from "@/lib/api";

// I-ui-004 (#543): two-run compare. Pick two completed runs → GET
// /runs/{l}/compare/{r}. Distinct from /benchmark (POLARIS-vs-external).

const FIELD_CLASS =
  "border-input bg-transparent focus-visible:border-ring focus-visible:ring-ring/70 w-full rounded-lg border px-2.5 py-2 text-sm transition-colors outline-none focus-visible:ring-3";

function shortDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-CA", { month: "short", day: "numeric" });
}

// Lead with the unique run id + completion date so two runs that share a
// template/question are still distinguishable (the id never truncates off the
// end of the select); the question follows for context (Codex visual iter-1 P1).
function optionLabel(run: RunStatusResponse): string {
  const q =
    run.question.length > 44 ? `${run.question.slice(0, 44)}…` : run.question;
  return `${run.run_id} · ${shortDate(run.finished_at ?? run.queued_at)} · ${run.template} · ${q}`;
}

function compareErrorMessage(err: unknown): string {
  const status = (err as { status?: number })?.status;
  if (status === 400) return "Pick two distinct runs.";
  if (status === 404) return "One of the runs was not found.";
  if (status === 422)
    return "One of the runs has no shippable evidence (aborted or release-blocked).";
  return "Couldn't compare those runs right now. Please retry shortly.";
}

export default function ComparePage() {
  const [runs, setRuns] = useState<RunStatusResponse[] | null>(null);
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<ReportComparison | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listCompletedRuns(50)
      .then((value) => {
        if (!cancelled) setRuns(value);
      })
      .catch(() => {
        if (!cancelled) setRuns([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const distinct = left !== "" && right !== "" && left !== right;

  async function onCompare() {
    if (!distinct) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      setResult(await compareRuns(left, right));
    } catch (err) {
      setError(compareErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section
      data-testid="compare-page"
      className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10"
    >
      <div className="flex flex-col gap-2">
        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
          Compare two runs
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
          Pick two completed runs to see shared vs unique evidence, frame
          coverage overlap, and contradiction counts. This is run-vs-run — for
          POLARIS-vs-external, use Benchmark.
        </p>
      </div>

      {runs === null ? (
        <LoadingState label="Loading completed runs…" rows={3} />
      ) : null}

      {runs !== null && runs.length === 0 ? (
        <EmptyState
          icon={GitCompareArrows}
          title="No completed runs to compare yet"
          description="Once two research runs have finished, pick any two here to diff their evidence, frame coverage, and contradictions."
          action={
            <Button
              nativeButton={false}
              variant="outline"
              render={<Link href="/intake">Start a run</Link>}
            />
          }
        />
      ) : null}

      {runs !== null && runs.length > 0 ? (
        <Card>
          <CardContent className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <RunPicker
                label="Left run"
                testid="compare-left"
                runs={runs}
                value={left}
                onChange={setLeft}
              />
              <RunPicker
                label="Right run"
                testid="compare-right"
                runs={runs}
                value={right}
                onChange={setRight}
              />
            </div>
            <div className="flex items-center gap-3">
              <Button
                type="button"
                onClick={onCompare}
                disabled={!distinct || submitting}
              >
                {submitting ? "Comparing…" : "Compare"}
              </Button>
              {left !== "" && right !== "" && left === right ? (
                <span className="text-muted-foreground text-xs">
                  Pick two distinct runs.
                </span>
              ) : null}
            </div>
          </CardContent>
        </Card>
      ) : null}

      {/* I-p2-018 (#757): #750 ErrorState for design-system consistency. */}
      {error ? (
        <ErrorState title="Couldn't compare those runs" message={error} />
      ) : null}

      {result ? <ComparisonView result={result} /> : null}
    </section>
  );
}

function RunPicker({
  label,
  testid,
  runs,
  value,
  onChange,
}: {
  label: string;
  testid: string;
  runs: RunStatusResponse[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
        {label}
      </span>
      <select
        data-testid={testid}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={FIELD_CLASS}
      >
        <option value="">Select a run…</option>
        {runs.map((run) => (
          <option key={run.run_id} value={run.run_id}>
            {optionLabel(run)}
          </option>
        ))}
      </select>
    </label>
  );
}

// A boolean run-property flag. A pass reads as verified-green; a mismatch is
// neutral (two runs differing on template/question is informational, not an
// error) — so it's muted, never the alarm/destructive token.
function Flag({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-xs">
      {ok ? (
        <Check aria-hidden className="text-verified h-3.5 w-3.5" />
      ) : (
        <X aria-hidden className="text-muted-foreground h-3.5 w-3.5" />
      )}
      {/* The Check/X is decorative (aria-hidden); carry the pass/fail status to
          assistive tech in text so the flag isn't colour/icon-only. */}
      <span className="sr-only">{ok ? "match: " : "mismatch: "}</span>
      <span className={ok ? "text-foreground" : "text-muted-foreground"}>
        {label}
      </span>
    </span>
  );
}

function EvidenceColumn({ title, ids }: { title: string; ids: string[] }) {
  return (
    <div className="border-border bg-muted/20 flex flex-col gap-1.5 rounded-lg border p-3">
      <span className="text-foreground text-xs font-semibold">
        {title}{" "}
        <span className="text-muted-foreground tabular-nums">
          ({ids.length})
        </span>
      </span>
      <div className="flex flex-wrap gap-1">
        {ids.slice(0, 20).map((id) => (
          <span
            key={id}
            className="bg-card text-muted-foreground border-border/60 rounded border px-1.5 py-0.5 font-mono text-[10px]"
          >
            {id}
          </span>
        ))}
        {ids.length > 20 ? (
          <span className="text-muted-foreground text-[10px]">
            + {ids.length - 20} more
          </span>
        ) : null}
        {ids.length === 0 ? (
          <span className="text-muted-foreground text-[10px]">—</span>
        ) : null}
      </div>
    </div>
  );
}

function ComparisonView({ result }: { result: ReportComparison }) {
  const pct = Math.round((result.shared_evidence_pct ?? 0) * 100);
  return (
    <div data-testid="comparison-result" className="flex flex-col gap-4">
      {/* Headline: which two runs, shared-evidence overlap, run-property flags. */}
      <Card>
        <CardContent className="flex flex-col gap-4">
          <div className="text-muted-foreground flex flex-wrap items-center gap-2 font-mono text-xs">
            <span className="text-foreground">{result.left_run_id}</span>
            <span aria-hidden>↔</span>
            <span className="text-foreground">{result.right_run_id}</span>
          </div>
          <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:gap-2">
            <span className="text-foreground text-4xl font-semibold tabular-nums">
              {pct}%
            </span>
            <span className="text-muted-foreground text-sm">
              shared evidence between the two runs
            </span>
          </div>
          <div className="flex flex-wrap gap-x-5 gap-y-2">
            <Flag label="Same template" ok={result.same_template} />
            <Flag label="Same question" ok={result.same_question} />
            <Flag
              label="Pipeline status match"
              ok={result.pipeline_status_match}
            />
            <Flag
              label="Two-family segregation (both)"
              ok={result.family_segregation_both_pass}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Evidence</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <EvidenceColumn title="Shared" ids={result.shared_evidence_ids} />
            <EvidenceColumn
              title="Only left"
              ids={result.only_left_evidence_ids}
            />
            <EvidenceColumn
              title="Only right"
              ids={result.only_right_evidence_ids}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Frame coverage</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <EvidenceColumn
              title="Overlap"
              ids={result.frame_coverage_overlap}
            />
            <EvidenceColumn title="Only left" ids={result.only_left_frames} />
            <EvidenceColumn title="Only right" ids={result.only_right_frames} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
          <span className="text-muted-foreground">
            Left contradictions{" "}
            <span className="text-foreground font-mono tabular-nums">
              {result.left_contradictions}
            </span>
          </span>
          <span className="text-muted-foreground">
            Right contradictions{" "}
            <span className="text-foreground font-mono tabular-nums">
              {result.right_contradictions}
            </span>
          </span>
        </CardContent>
      </Card>
    </div>
  );
}
