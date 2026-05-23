"use client";

import { useEffect, useState } from "react";

import { ErrorState } from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import {
  compareRuns,
  listCompletedRuns,
  type ReportComparison,
  type RunStatusResponse,
} from "@/lib/api";

// I-ui-004 (#543): two-run compare. Pick two completed runs → GET
// /runs/{l}/compare/{r}. Distinct from /benchmark (POLARIS-vs-external).

function optionLabel(run: RunStatusResponse): string {
  const q =
    run.question.length > 60 ? `${run.question.slice(0, 60)}…` : run.question;
  return `${run.template} · ${q} · ${run.run_id.slice(0, 8)}`;
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

      {runs !== null && runs.length === 0 && (
        <p className="text-muted-foreground text-sm">
          No completed runs to compare yet.{" "}
          <a className="text-primary underline" href="/intake">
            Start a run
          </a>
          .
        </p>
      )}

      {runs !== null && runs.length > 0 && (
        <div className="flex flex-col gap-3">
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
            {left !== "" && right !== "" && left === right && (
              <span className="text-muted-foreground text-xs">
                Pick two distinct runs.
              </span>
            )}
          </div>
        </div>
      )}

      {/* I-p2-018 (#757): #750 ErrorState for design-system consistency. */}
      {error && (
        <ErrorState title="Couldn't compare those runs" message={error} />
      )}

      {result && <ComparisonView result={result} />}
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
    <label className="flex flex-col gap-1">
      <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
        {label}
      </span>
      <select
        data-testid={testid}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="border-input focus-visible:border-ring focus-visible:ring-ring rounded-lg border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2"
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

function Flag({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className="text-muted-foreground flex items-center gap-1 text-xs">
      <span className={ok ? "text-primary" : "text-muted-foreground"}>
        {ok ? "✓" : "✗"}
      </span>
      {label}
    </span>
  );
}

function EvidenceColumn({ title, ids }: { title: string; ids: string[] }) {
  return (
    <div className="border-border bg-card flex flex-col gap-1 rounded-lg border p-3">
      <span className="text-foreground text-xs font-semibold">
        {title} ({ids.length})
      </span>
      <div className="flex flex-wrap gap-1">
        {ids.slice(0, 20).map((id) => (
          <span
            key={id}
            className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono text-[10px]"
          >
            {id}
          </span>
        ))}
        {ids.length > 20 && (
          <span className="text-muted-foreground text-[10px]">
            + {ids.length - 20} more
          </span>
        )}
        {ids.length === 0 && (
          <span className="text-muted-foreground text-[10px]">—</span>
        )}
      </div>
    </div>
  );
}

function ComparisonView({ result }: { result: ReportComparison }) {
  const pct = Math.round((result.shared_evidence_pct ?? 0) * 100);
  return (
    <div data-testid="comparison-result" className="flex flex-col gap-5">
      <div className="border-border bg-card flex flex-wrap items-center gap-4 rounded-lg border p-4">
        <span className="text-foreground text-sm font-semibold">
          {pct}% shared evidence
        </span>
        <Flag label="Same template" ok={result.same_template} />
        <Flag label="Same question" ok={result.same_question} />
        <Flag label="Pipeline status match" ok={result.pipeline_status_match} />
        <Flag
          label="Two-family segregation (both)"
          ok={result.family_segregation_both_pass}
        />
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="text-foreground text-sm font-semibold">Evidence</h2>
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
      </div>

      <div className="flex flex-col gap-2">
        <h2 className="text-foreground text-sm font-semibold">
          Frame coverage
        </h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <EvidenceColumn title="Overlap" ids={result.frame_coverage_overlap} />
          <EvidenceColumn title="Only left" ids={result.only_left_frames} />
          <EvidenceColumn title="Only right" ids={result.only_right_frames} />
        </div>
      </div>

      <div className="border-border flex gap-6 rounded-lg border p-4 text-sm">
        <span className="text-muted-foreground">
          Left contradictions:{" "}
          <span className="text-foreground font-mono">
            {result.left_contradictions}
          </span>
        </span>
        <span className="text-muted-foreground">
          Right contradictions:{" "}
          <span className="text-foreground font-mono">
            {result.right_contradictions}
          </span>
        </span>
      </div>
    </div>
  );
}
