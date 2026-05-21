"use client";

import { useEffect, useState } from "react";

import type { RunStatusResponse, StreamEvent } from "@/lib/api";

// I-ui-002 (#707): Perplexity-style 4-stage progress for the live run.
// Consumes the #706 SSE sub-task events already accumulated by the parent
// page. Pure rendering of (events, status) — no fetching here.

type StageKey = "scope" | "retrieval" | "generation" | "verification";
type StageState = "pending" | "active" | "done" | "skipped" | "degraded";

const STAGES: { key: StageKey; label: string }[] = [
  { key: "scope", label: "Scope" },
  { key: "retrieval", label: "Retrieval" },
  { key: "generation", label: "Generation" },
  { key: "verification", label: "Verification" },
];

const LIFECYCLE_TERMINAL = ["completed", "failed", "cancelled"];

function asNumber(value: unknown): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function parseMs(value: string | null | undefined): number | null {
  if (!value) return null;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? null : t;
}

function formatElapsed(seconds: number | null): string {
  if (seconds === null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

interface RunProgressProps {
  events: StreamEvent[];
  status: RunStatusResponse | null;
}

export function RunProgress({ events, status }: RunProgressProps) {
  // --- parse events into per-stage data -----------------------------------
  const scope = events.find((e) => e.event === "scope_decision")?.data ?? null;
  const retrievalProgress =
    events.find((e) => e.event === "retrieval_progress")?.data ?? null;

  const sources: { id: string; url: string }[] = [];
  const seenIds = new Set<string>();
  for (const e of events) {
    if (e.event !== "evidence_id") continue;
    const id = asString(e.data.id ?? e.data.evidence_id);
    if (!id || seenIds.has(id)) continue; // defensive: skip blank/dup
    seenIds.add(id);
    sources.push({ id, url: asString(e.data.url ?? e.data.source_url) });
  }

  const sections = events
    .filter((e) => e.event === "section_complete")
    .map((e) => ({
      section: asString(e.data.section),
      verified: asNumber(e.data.verified ?? e.data.verified_sentences),
      dropped: asNumber(e.data.dropped),
    }));

  const verifications = events
    .filter((e) => e.event === "verifier_verdict")
    .map((e) => ({
      section: asString(e.data.section),
      local: Boolean(e.data.local ?? e.data.local_pass),
      global: Boolean(e.data.global ?? e.data.global_pass),
    }));

  const runCompleteEvent = events.find((e) => e.event === "run_complete");
  const terminalFromEvent = runCompleteEvent
    ? asString(runCompleteEvent.data.status) || "unknown"
    : null;
  const terminalFromStatus =
    status && LIFECYCLE_TERMINAL.includes(status.status) ? status.status : null;
  // I-ui-bug-001 (#725, Codex diff iter-1 P1): a COMPLETED run has no live SSE
  // to replay, so #706's STREAM_LOST_GRACE emits a SYNTHETIC
  // run_complete{stream_lost}. That synthetic artifact must NOT drive the UI —
  // but neither can lifecycle 'completed' alone, because mark_aborted() also
  // stores lifecycle_status='completed' (an aborted run would wrongly show as
  // success). The authoritative verdict for a completed run is the run_store
  // PIPELINE status (success / abort_* / partial_* / error_*).
  const syntheticLoss =
    terminalFromEvent === "stream_lost" ||
    terminalFromEvent === "stream_unavailable";
  // A REAL run_complete event (genuine pipeline verdict, live-finished run) wins.
  const realEventStatus =
    terminalFromEvent && !syntheticLoss ? terminalFromEvent : null;
  const lifecycleCompleted = status?.status === "completed";
  const pipelineStatus = status?.pipeline_status ?? null;
  const terminalStatus =
    realEventStatus ??
    (lifecycleCompleted
      ? (pipelineStatus ?? "success")
      : (terminalFromStatus ?? ""));
  // terminal if: a real verdict event, a completed/failed/cancelled lifecycle,
  // OR a genuinely-running run whose stream dropped (stream-loss degraded).
  const isTerminal =
    realEventStatus !== null ||
    lifecycleCompleted ||
    terminalFromStatus !== null ||
    syntheticLoss;
  const isSuccess =
    terminalStatus === "success" ||
    terminalStatus === "completed" ||
    terminalStatus.startsWith("partial_");
  // Stream-loss is a REAL degradation only for a run that is NOT lifecycle-
  // completed (i.e. genuinely still running and the live stream dropped).
  const isStreamLost = syntheticLoss && !lifecycleCompleted;

  const observed: Record<StageKey, boolean> = {
    scope: scope !== null,
    retrieval: retrievalProgress !== null || sources.length > 0,
    generation: sections.length > 0,
    verification: verifications.length > 0,
  };

  // --- stage state (ONE rule, per the Codex-APPROVE'd brief) --------------
  function stageState(key: StageKey, idx: number): StageState {
    if (isTerminal) {
      if (isSuccess) return "done"; // success proves the full pipeline ran
      if (observed[key]) return "done";
      return isStreamLost ? "degraded" : "skipped"; // never green-check unobserved
    }
    // non-terminal: active = most-recent observed stage; earlier observed = done
    const lastObserved = STAGES.reduce(
      (acc, s, i) => (observed[s.key] ? i : acc),
      -1,
    );
    if (!observed[key]) return "pending";
    return idx < lastObserved ? "done" : "active";
  }

  // --- elapsed (tick + freeze on terminal) --------------------------------
  // `nowMs` ticks every 1s ONLY while the run is live; when it goes terminal
  // the effect stops the interval, so nowMs freezes at the last tick (≤1s of
  // the terminal moment). status.finished_at stays null after run_complete
  // (iter-1 P1), so we never depend on it.
  // `tickedWhileLive` is set from the interval CALLBACK (async — not a
  // synchronous setState in the effect body, so lint-clean). It is the
  // honest signal that we actually watched the run progress live: only then
  // is now−start a trustworthy elapsed. A run that was ALREADY terminal when
  // this page opened (status loads terminal after mount, finished_at null)
  // never ticks → elapsed shows "—" instead of a bogus page-open duration.
  // (Codex diff iter-1 P2: replaces the mount-time isTerminal capture, which
  // was always false because status is null at first render.)
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [tickedWhileLive, setTickedWhileLive] = useState(false);
  useEffect(() => {
    if (isTerminal) return; // frozen — stop ticking
    const id = setInterval(() => {
      setNowMs(Date.now());
      setTickedWhileLive(true);
    }, 1000);
    return () => clearInterval(id);
  }, [isTerminal]);

  const startMs = parseMs(status?.started_at) ?? parseMs(status?.queued_at);
  const elapsedSec =
    startMs === null || (isTerminal && !tickedWhileLive)
      ? null
      : Math.max(0, Math.floor((nowMs - startMs) / 1000));

  const sourcesRead =
    sources.length > 0
      ? sources.length
      : retrievalProgress
        ? asNumber(retrievalProgress.sources_found)
        : null;
  const sentencesVerified = sections.length
    ? sections.reduce((acc, s) => acc + s.verified, 0)
    : null;

  return (
    <section className="flex flex-col gap-4" data-testid="run-progress">
      {/* counters */}
      <div className="grid grid-cols-3 gap-3">
        <Counter label="Elapsed" value={formatElapsed(elapsedSec)} />
        <Counter
          label="Sources read"
          value={sourcesRead === null ? "—" : String(sourcesRead)}
        />
        <Counter
          label="Sentences verified"
          value={sentencesVerified === null ? "—" : String(sentencesVerified)}
        />
      </div>

      {isStreamLost && (
        <p
          role="status"
          className="border-border text-muted-foreground rounded-md border border-dashed p-3 text-sm"
        >
          Live connection lost — the run may still be progressing on the server.
          Reload to reconnect.
        </p>
      )}

      {/* stages */}
      <ol className="flex flex-col gap-3">
        {STAGES.map((stage, idx) => {
          const state = stageState(stage.key, idx);
          return (
            <li
              key={stage.key}
              data-testid={`stage-${stage.key}`}
              data-state={state}
              className="border-border bg-card flex flex-col gap-2 rounded-lg border p-4"
            >
              <div className="flex items-center gap-2">
                <StageChip state={state} />
                <h3 className="text-foreground text-sm font-semibold">
                  {stage.label}
                </h3>
              </div>
              <StageBody
                stageKey={stage.key}
                state={state}
                scope={scope}
                sources={sources}
                sections={sections}
                verifications={verifications}
              />
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Counter({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-border bg-card flex flex-col gap-1 rounded-lg border px-3 py-2">
      <span className="text-muted-foreground text-[10px] font-medium tracking-widest uppercase">
        {label}
      </span>
      <span className="text-foreground font-mono text-lg">{value}</span>
    </div>
  );
}

function StageChip({ state }: { state: StageState }) {
  if (state === "active") {
    return (
      <span
        aria-label="in progress"
        className="border-primary size-4 animate-spin rounded-full border-2 border-t-transparent"
      />
    );
  }
  if (state === "done") {
    return (
      <span
        aria-label="done"
        className="bg-primary text-primary-foreground flex size-4 items-center justify-center rounded-full text-[10px]"
      >
        ✓
      </span>
    );
  }
  if (state === "degraded") {
    return (
      <span
        aria-label="connection lost"
        className="border-muted-foreground text-muted-foreground flex size-4 items-center justify-center rounded-full border text-[10px]"
      >
        ?
      </span>
    );
  }
  // pending / skipped
  return (
    <span
      aria-label={state === "skipped" ? "did not run" : "pending"}
      className="bg-muted-foreground/30 size-4 rounded-full"
    />
  );
}

function StageBody({
  stageKey,
  state,
  scope,
  sources,
  sections,
  verifications,
}: {
  stageKey: StageKey;
  state: StageState;
  scope: Record<string, unknown> | null;
  sources: { id: string; url: string }[];
  sections: { section: string; verified: number; dropped: number }[];
  verifications: { section: string; local: boolean; global: boolean }[];
}) {
  // Codex diff iter-1 P2: a stage that did not run / was not observed at a
  // terminal must NOT show active-sounding placeholder copy ("Drafting…").
  if (state === "skipped") {
    return <p className="text-muted-foreground text-xs">Did not run.</p>;
  }
  if (state === "degraded") {
    return (
      <p className="text-muted-foreground text-xs">
        Not observed (stream lost).
      </p>
    );
  }
  // I-ui-bug-001 (#725): a stage resolved `done` but with no replayed event
  // data — the common case when opening an ALREADY-completed run (no live SSE
  // to replay) — must NOT show active-sounding placeholders ("Gathering
  // evidence…"). Show "Completed." Live runs that finish while watching keep
  // their real per-stage feed (data is present → falls through below).
  if (state === "done") {
    const hasData =
      (stageKey === "scope" && scope) ||
      (stageKey === "retrieval" && sources.length > 0) ||
      (stageKey === "generation" && sections.length > 0) ||
      (stageKey === "verification" && verifications.length > 0);
    if (!hasData)
      return <p className="text-muted-foreground text-xs">Completed.</p>;
  }
  if (stageKey === "scope") {
    if (!scope)
      return (
        <p className="text-muted-foreground text-xs">Awaiting scope gate…</p>
      );
    return (
      <p className="text-muted-foreground text-xs">
        <span className="text-foreground font-medium">
          {asString(scope.verdict) || "decided"}
        </span>
        {asString(scope.reason) ? ` — ${asString(scope.reason)}` : ""}
      </p>
    );
  }
  if (stageKey === "retrieval") {
    if (sources.length === 0)
      return (
        <p className="text-muted-foreground text-xs">Gathering evidence…</p>
      );
    return (
      <ul className="flex flex-col gap-1">
        {sources.slice(0, 12).map((s) => (
          <li
            key={s.id}
            className="text-muted-foreground truncate text-xs"
            title={s.url || s.id}
          >
            <span className="text-primary">✓</span> {s.url || s.id}
          </li>
        ))}
        {sources.length > 12 && (
          <li className="text-muted-foreground text-xs">
            + {sources.length - 12} more
          </li>
        )}
      </ul>
    );
  }
  if (stageKey === "generation") {
    if (sections.length === 0)
      return (
        <p className="text-muted-foreground text-xs">Drafting sections…</p>
      );
    return (
      <ul className="flex flex-col gap-1">
        {sections.map((s, i) => (
          <li
            key={`${s.section}-${i}`}
            className="text-muted-foreground text-xs"
          >
            <span className="text-foreground font-medium">
              {s.section || "section"}
            </span>{" "}
            — {s.verified} verified, {s.dropped} dropped
          </li>
        ))}
      </ul>
    );
  }
  // verification
  if (verifications.length === 0)
    return <p className="text-muted-foreground text-xs">Verifying claims…</p>;
  return (
    <ul className="flex flex-col gap-1">
      {verifications.map((v, i) => (
        <li key={`${v.section}-${i}`} className="text-muted-foreground text-xs">
          <span className="text-foreground font-medium">
            {v.section || "section"}
          </span>{" "}
          — local {v.local ? "✓" : "✗"} · global {v.global ? "✓" : "✗"}
        </li>
      ))}
    </ul>
  );
}
