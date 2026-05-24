"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";

import { ErrorState } from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import {
  cancelRun,
  downloadBundleAsJson,
  getBundle,
  getRun,
  subscribeToRun,
  type RunStatusResponse,
  type StreamEvent,
} from "@/lib/api";

import { FollowupPanel } from "./components/followup_panel";
import { RunProgress } from "./components/run_progress";

interface RunPageProps {
  params: Promise<{ runId: string }>;
}

// I-rdy-011 (#507): lifecycle states from which a run can no longer be
// cancelled — the Cancel button is disabled for these.
const TERMINAL_STATUSES = ["completed", "failed", "cancelled"];

export default function RunDetailPage({ params }: RunPageProps) {
  const { runId } = use(params);
  const [status, setStatus] = useState<RunStatusResponse | null>(null);
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getRun(runId)
      .then((value) => {
        if (!cancelled) setStatus(value);
      })
      .catch((err) => {
        if (!cancelled) {
          // G4 (Codex iter-1 P0): map raw API errors to friendly copy.
          const raw = err instanceof Error ? err.message : String(err);
          const friendly = raw.toLowerCase().includes("404")
            ? "This run was not found. Check the URL or start a new run."
            : "We couldn't load this run right now. Please retry shortly.";
          setError(friendly);
        }
      });

    const source = subscribeToRun(
      runId,
      (event) => {
        setEvents((prev) => [...prev, event]);
        // I-ui-003 (#542) Codex diff P1: getRun() only populates `status`
        // once on mount; the SSE stream otherwise just appends events. When a
        // run watched live reaches `run_complete`, re-fetch the lifecycle
        // status so completed-only UI (the follow-up panel, the status line,
        // the cancel button) updates without a manual reload.
        if (event.event === "run_complete") {
          getRun(runId)
            .then((value) => {
              if (!cancelled) setStatus(value);
            })
            .catch(() => {});
        }
      },
      () => {
        // SSE error: backend may have closed the stream after run_complete.
        source.close();
      },
    );

    return () => {
      cancelled = true;
      source.close();
    };
  }, [runId]);

  // I-rdy-011 (#507): a queued run cancels instantly; an in-progress run
  // aborts cooperatively at the next pipeline stage boundary. The button is
  // disabled once the run is terminal (or its status is not yet loaded).
  const isTerminal =
    status !== null && TERMINAL_STATUSES.includes(status.status);
  const cancelRequested = status?.cancel_requested ?? false;

  // A genuinely verified, followable result. Per §9.1, the lifecycle `status`
  // is NOT authoritative — mark_aborted() persists lifecycle 'completed' for
  // abort_* runs too, so an abort_no_verified_sections run is lifecycle
  // 'completed' but has NO verified result. The run-store PIPELINE status is
  // the verdict: treat 'completed' as verified UNLESS pipeline_status is an
  // abort_*/error_* (a completed run with null pipeline_status predates the
  // field → trusted as success, matching RunProgress's own fallback). This
  // gates both the "verified result" copy and the follow-up panel so neither
  // overclaims on an aborted run.
  const pipelineStatus = status?.pipeline_status ?? null;
  const isAbortedOrError =
    pipelineStatus !== null &&
    (pipelineStatus.startsWith("abort_") ||
      pipelineStatus.startsWith("error_"));
  const hasVerifiedResult = status?.status === "completed" && !isAbortedOrError;

  const onCancel = async () => {
    setCancelling(true);
    setError(null);
    try {
      const updated = await cancelRun(runId);
      setStatus(updated);
    } catch (err) {
      setError(
        err instanceof Error
          ? `Cancel failed: ${err.message}`
          : "Cancel failed",
      );
    } finally {
      setCancelling(false);
    }
  };

  // I-cd-025 (#615): /runs/[runId] rebuild — G1/G6 fix. Page no longer
  // renders its own <header>, <footer>, or <main>. AppShell (via
  // AppShellGate, I-cd-022) is the single landmark provider on this
  // route. G2 fix: removed "POLARIS v6.2 — Phase 0 scaffold" footer
  // dev-language. The header's Export-bundle + New-run buttons move
  // into a page-level action row inside the <section>.
  return (
    <section
      data-testid="runs-runid-page"
      className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-6 py-12"
    >
      <div className="flex items-center justify-end gap-2">
        <Button
          variant="outline"
          onClick={async () => {
            try {
              const bundle = await getBundle(runId);
              downloadBundleAsJson(bundle);
            } catch (err) {
              setError(
                err instanceof Error
                  ? `Bundle export failed: ${err.message}`
                  : "Bundle export failed",
              );
            }
          }}
        >
          Export bundle
        </Button>
        <Button
          variant="default"
          nativeButton={false}
          render={<Link href="/intake" />}
        >
          New run
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-muted-foreground text-xs tracking-widest uppercase">
          Run {runId}
        </span>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
          {/* I-p2-016 (#755): don't show "Loading…" once an error has fired. */}
          {status?.question ?? (error ? "Couldn't load this run" : "Loading…")}
        </h1>
        {status && (
          <p className="text-muted-foreground text-sm">
            Template: <span className="text-foreground">{status.template}</span>
            {" · "}
            Status:{" "}
            <span className="text-foreground font-mono">{status.status}</span>
            {" · "}
            Queued at <time>{status.queued_at}</time>
          </p>
        )}
        {/* I-p2-016 (#755): #750 ErrorState (design tokens + role=alert) instead
            of the hand-rolled banner — consistent with every other page. */}
        {error && <ErrorState title="Couldn't load this run" message={error} />}
      </div>

      <div className="border-border bg-card shadow-card flex flex-col gap-2 rounded-xl border p-4">
        <h2 className="text-foreground text-sm font-semibold">
          {isTerminal ? "This run" : "While this run works"}
        </h2>
        <p className="text-muted-foreground text-xs">
          {/* hasVerifiedResult is pipeline-verdict-based (see above): an
              aborted/failed/cancelled run must not claim a "verified result". */}
          {!isTerminal
            ? "Actions you can take while POLARIS works:"
            : hasVerifiedResult
              ? "Open, export, or follow up on the verified result:"
              : "Open or export what this run produced:"}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            nativeButton={false}
            render={<Link href={`/inspector/${runId}`} />}
          >
            Open Inspector
          </Button>
          {/* I-p2-020 (#759): audit / export drill-down. */}
          <Button
            type="button"
            variant="outline"
            nativeButton={false}
            render={<Link href={`/runs/${runId}/audit`} />}
          >
            Audit &amp; export
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={async () => {
              try {
                const bundle = await getBundle(runId);
                downloadBundleAsJson(bundle);
              } catch (err) {
                setError(
                  err instanceof Error
                    ? `Bundle export failed: ${err.message}`
                    : "Bundle export failed",
                );
              }
            }}
          >
            Export current bundle
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={status === null || isTerminal || cancelling}
            title={
              cancelRequested
                ? "Cancellation requested — the run is winding down"
                : "Cancel this queued or in-progress run"
            }
            onClick={onCancel}
          >
            {cancelRequested
              ? "Cancelling…"
              : cancelling
                ? "Requesting…"
                : "Cancel run"}
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled
            title="Pin this run for later replay (coming soon)"
          >
            Pin for replay
          </Button>
        </div>
      </div>

      <RunProgress events={events} status={status} />

      {/* I-ui-003 (#542): follow-up is meaningful only for a run with a
          verified report. Per §9.1, gate on the PIPELINE verdict, not lifecycle
          'completed' — an abort_* run is lifecycle 'completed' but has no
          verified result to follow up on (I-p2-057 Codex diff iter-3 P2).
          Failed/cancelled/in-progress runs don't render it either. */}
      {hasVerifiedResult && <FollowupPanel runId={runId} />}
    </section>
  );
}
