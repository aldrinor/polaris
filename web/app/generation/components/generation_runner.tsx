"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  AuditBundleError,
  downloadAuditBundle,
  GenerationBadRequestError,
  IntakeBadRequestError,
  RetrievalBadRequestError,
  runGeneration,
  runIntake,
  runRetrieval,
  type EvidencePool,
  type IntakeScopeDecision,
  type VerifiedReport,
} from "@/lib/api";

import { VerifiedReportView } from "./verified_report_view";

type RunnerStage = "scope" | "retrieval" | "generation";

type RunnerState =
  | { kind: "idle" }
  | { kind: "loading"; stage: RunnerStage }
  | { kind: "scope_unsuitable"; decision: IntakeScopeDecision; reason: string }
  | {
      kind: "failed";
      stage: RunnerStage;
      code: string;
      message: string;
    }
  | {
      kind: "ok";
      decision: IntakeScopeDecision;
      pool: EvidencePool;
      report: VerifiedReport;
    };

export function GenerationRunner() {
  const [question, setQuestion] = useState("");
  const [show_dropped, setShowDropped] = useState(false);
  const [state, setState] = useState<RunnerState>({ kind: "idle" });

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 3) {
      setState({
        kind: "failed",
        stage: "scope",
        code: "too_short",
        message: "Question is too short.",
      });
      return;
    }

    setState({ kind: "loading", stage: "scope" });
    let decision: IntakeScopeDecision;
    try {
      const intake = await runIntake(trimmed);
      decision = intake.decision;
    } catch (err) {
      const code =
        err instanceof IntakeBadRequestError ? err.code : "unknown";
      const msg = err instanceof Error ? err.message : "Intake failed.";
      setState({ kind: "failed", stage: "scope", code, message: msg });
      return;
    }

    if (decision.status !== "in_scope") {
      setState({
        kind: "scope_unsuitable",
        decision,
        reason: scope_reason_for(decision),
      });
      return;
    }

    setState({ kind: "loading", stage: "retrieval" });
    let pool: EvidencePool;
    try {
      const retrieval = await runRetrieval(decision);
      pool = retrieval.pool;
    } catch (err) {
      const code =
        err instanceof RetrievalBadRequestError ? err.code : "unknown";
      const msg = err instanceof Error ? err.message : "Retrieval failed.";
      setState({ kind: "failed", stage: "retrieval", code, message: msg });
      return;
    }

    if (!pool.adequacy.is_adequate) {
      setState({
        kind: "failed",
        stage: "retrieval",
        code: "inadequate_pool",
        message:
          pool.adequacy.failure_reason ?? "Corpus not adequate for generation.",
      });
      return;
    }

    setState({ kind: "loading", stage: "generation" });
    try {
      const generation = await runGeneration(pool, decision.scope_class);
      setState({ kind: "ok", decision, pool, report: generation.report });
    } catch (err) {
      const code =
        err instanceof GenerationBadRequestError ? err.code : "unknown";
      const msg = err instanceof Error ? err.message : "Generation failed.";
      setState({ kind: "failed", stage: "generation", code, message: msg });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">
            One-click clinical research
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={submit}
            className="flex flex-col gap-3"
            data-testid="generation-form"
          >
            <label
              htmlFor="generation-question"
              className="text-foreground text-sm font-medium"
            >
              Clinical research question
            </label>
            <input
              id="generation-question"
              data-testid="generation-question-input"
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Is aspirin effective for headache in adults?"
              maxLength={2000}
              autoComplete="off"
              disabled={state.kind === "loading"}
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 h-9 w-full rounded-lg border bg-transparent px-3 py-1 text-sm outline-none transition-colors focus-visible:ring-3 disabled:opacity-50"
            />
            <p className="text-muted-foreground text-xs">
              POLARIS chains intake → retrieval → generation in one click.
              Each stage's failure short-circuits the next; UI surfaces the
              specific stage that failed (LAW II — never silently degrade).
            </p>
            <Button
              type="submit"
              variant="default"
              data-testid="generation-submit"
              disabled={state.kind === "loading"}
            >
              {state.kind === "loading"
                ? `Running ${stage_label(state.stage)}…`
                : "Run end-to-end"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {state.kind === "scope_unsuitable" ? (
        <Card
          data-testid="scope-unsuitable"
          className="border-amber-500/40 bg-amber-500/5"
        >
          <CardContent className="text-amber-700 dark:text-amber-300">
            {state.reason}
          </CardContent>
        </Card>
      ) : null}

      {state.kind === "failed" ? (
        <Card
          data-testid="generation-error"
          className="border-rose-500/40 bg-rose-500/5"
        >
          <CardContent className="text-rose-700 dark:text-rose-300">
            <strong className="block">
              {stage_label(state.stage)} failed ({state.code})
            </strong>
            {state.message}
          </CardContent>
        </Card>
      ) : null}

      {state.kind === "ok" ? (
        <>
          <div className="flex items-center justify-end gap-2">
            <DownloadAuditBundleButton
              decision={state.decision}
              pool={state.pool}
              report={state.report}
            />
            <button
              type="button"
              onClick={() => setShowDropped(!show_dropped)}
              data-testid="toggle-dropped"
              className="text-muted-foreground hover:text-foreground border-border rounded-full border px-3 py-1 text-xs transition-colors"
            >
              {show_dropped ? "Hide" : "Show"} dropped sentences
            </button>
          </div>
          <VerifiedReportView
            report={state.report}
            show_dropped={show_dropped}
          />
        </>
      ) : null}
    </div>
  );
}

type DownloadState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok" }
  | { kind: "error"; code: string; message: string };

function DownloadAuditBundleButton({
  decision,
  pool,
  report,
}: {
  decision: IntakeScopeDecision;
  pool: EvidencePool;
  report: VerifiedReport;
}) {
  const [dl_state, setDlState] = useState<DownloadState>({ kind: "idle" });

  async function handle_click() {
    setDlState({ kind: "loading" });
    try {
      const blob = await downloadAuditBundle(decision, pool, report);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `audit_${report.report_id}.tar.gz`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setDlState({ kind: "ok" });
    } catch (err) {
      if (err instanceof AuditBundleError) {
        setDlState({ kind: "error", code: err.code, message: err.message });
      } else {
        const msg = err instanceof Error ? err.message : "Unknown error.";
        setDlState({ kind: "error", code: "unknown", message: msg });
      }
    }
  }

  if (dl_state.kind === "error") {
    return (
      <span
        data-testid="audit-bundle-error"
        className="text-rose-700 dark:text-rose-300 text-xs"
        title={dl_state.message}
      >
        Bundle failed: {dl_state.code}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={handle_click}
      disabled={dl_state.kind === "loading"}
      data-testid="download-audit-bundle"
      className="text-foreground border-border bg-background hover:bg-muted rounded-full border px-3 py-1 text-xs transition-colors disabled:opacity-50"
    >
      {dl_state.kind === "loading"
        ? "Building bundle…"
        : dl_state.kind === "ok"
          ? "✓ Downloaded"
          : "Download audit bundle"}
    </button>
  );
}

function stage_label(stage: RunnerStage): string {
  switch (stage) {
    case "scope":
      return "Scope check";
    case "retrieval":
      return "Retrieval";
    case "generation":
      return "Generation";
  }
}

function scope_reason_for(decision: IntakeScopeDecision): string {
  switch (decision.status) {
    case "out_of_scope":
      return "This question is out of scope for POLARIS clinical research.";
    case "refused":
      return "POLARIS refused this question (instruction-override attempt detected).";
    case "ambiguous_needs_clarification":
      return "This question is ambiguous. Clarify on the /intake page first.";
    default:
      return `Cannot generate for status='${decision.status}'.`;
  }
}
