// I-p2-022 (#761): Dashboard — MONITORING ONLY (not a run-start). Run-start now
// lives at /intake → /plan (I-p2-015 #754). This page lists recent verified runs
// (real GET /api/v6/runs data) with their pipeline verdict + a link to each run's
// report, plus a clear "Start new research" CTA to intake. Replaces the prior
// 668-line run-start workflow (relocated, not lost).
"use client";

import { ArrowRight, FileSearch, Plus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import { listCompletedRuns, type RunStatusResponse } from "@/lib/api";

type LoadState =
  | { kind: "loading" }
  | { kind: "ok"; runs: RunStatusResponse[] }
  | { kind: "error"; message: string };

function formatWhen(value: string | null | undefined): string | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// Honest verdict label: lifecycle `status` cannot distinguish a success from an
// abort (mark_aborted stores status=completed) — pipeline_status is the truth.
function verdictOf(run: RunStatusResponse): { label: string; cls: string } {
  const v = run.pipeline_status ?? run.status;
  if (v === "success") {
    return {
      label: "Verified",
      cls: "text-verified border-verified/30 bg-verified/10",
    };
  }
  if (typeof v === "string" && v.startsWith("abort_")) {
    return {
      label: "Declined",
      cls: "text-refusal-foreground border-refusal/30 bg-refusal/10",
    };
  }
  if (typeof v === "string" && v.startsWith("error_")) {
    return {
      label: "Error",
      cls: "text-destructive border-destructive/30 bg-destructive/10",
    };
  }
  return {
    label: v ?? "Unknown",
    cls: "text-muted-foreground border-border bg-muted/30",
  };
}

export default function DashboardPage() {
  const [state, setState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const runs = await listCompletedRuns(50);
        if (!cancelled) setState({ kind: "ok", runs });
      } catch (err) {
        if (!cancelled) {
          setState({
            kind: "error",
            message:
              err instanceof Error
                ? err.message
                : "Could not load runs from the backend.",
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      data-testid="dashboard-page"
      className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-10"
    >
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            Runs
          </h1>
          <p className="text-muted-foreground text-sm">
            Recent completed research runs. Open one to replay its proof, claim
            by claim.
          </p>
        </div>
        <Button
          nativeButton={false}
          className="h-10"
          render={
            <Link href="/intake" data-testid="dashboard-start-run">
              <Plus aria-hidden className="mr-1.5 h-4 w-4" />
              Start new research
            </Link>
          }
        />
      </div>

      {state.kind === "loading" ? (
        <LoadingState label="Loading runs…" rows={5} />
      ) : null}

      {state.kind === "error" ? (
        <ErrorState title="Couldn't load runs" message={state.message} />
      ) : null}

      {state.kind === "ok" && state.runs.length === 0 ? (
        <EmptyState
          icon={FileSearch}
          title="No runs yet"
          description="Once you run a research question, every verified brief shows up here for monitoring and replay."
          action={
            <Button
              nativeButton={false}
              variant="outline"
              render={<Link href="/intake">Start your first research</Link>}
            />
          }
        />
      ) : null}

      {state.kind === "ok" && state.runs.length > 0 ? (
        <ul
          className="border-border divide-border divide-y rounded-xl border"
          data-testid="runs-list"
        >
          {state.runs.map((run) => {
            const verdict = verdictOf(run);
            const when = formatWhen(run.finished_at ?? run.queued_at);
            return (
              <li key={run.run_id}>
                <Link
                  href={`/runs/${run.run_id}`}
                  data-testid={`run-row-${run.run_id}`}
                  className="hover:bg-muted/40 focus-visible:ring-ring/70 flex items-center justify-between gap-4 px-4 py-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <span className="text-foreground line-clamp-1 text-sm font-medium">
                      {run.question || run.run_id}
                    </span>
                    <span className="text-muted-foreground text-xs">
                      <span className="text-primary font-medium tracking-wide uppercase">
                        {run.template}
                      </span>
                      {when ? <span> · {when}</span> : null}
                    </span>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <span
                      className={`rounded-full border px-2 py-0.5 text-xs font-medium ${verdict.cls}`}
                    >
                      {verdict.label}
                    </span>
                    <ArrowRight
                      aria-hidden
                      className="text-muted-foreground h-4 w-4"
                    />
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
