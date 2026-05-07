"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  IntakeBadRequestError,
  RetrievalBadRequestError,
  runIntake,
  runRetrieval,
  type EvidencePool,
  type IntakeScopeDecision,
} from "@/lib/api";

import { CorpusBrief } from "./corpus_brief";

type RunnerState =
  | { kind: "idle" }
  | { kind: "scope_loading" }
  | { kind: "scope_failed"; message: string }
  | {
      kind: "scope_unsuitable";
      decision: IntakeScopeDecision;
      reason: string;
    }
  | {
      kind: "retrieval_loading";
      decision: IntakeScopeDecision;
    }
  | {
      kind: "retrieval_failed";
      decision: IntakeScopeDecision;
      code: string;
      message: string;
    }
  | {
      kind: "ok";
      decision: IntakeScopeDecision;
      pool: EvidencePool;
    };

export function RetrievalRunner() {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<RunnerState>({ kind: "idle" });

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 3) {
      setState({ kind: "scope_failed", message: "Question is too short." });
      return;
    }

    setState({ kind: "scope_loading" });
    let decision: IntakeScopeDecision;
    try {
      const intake = await runIntake(trimmed);
      decision = intake.decision;
    } catch (err) {
      const msg =
        err instanceof IntakeBadRequestError
          ? err.message
          : err instanceof Error
            ? err.message
            : "Intake failed.";
      setState({ kind: "scope_failed", message: msg });
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

    setState({ kind: "retrieval_loading", decision });
    try {
      const result = await runRetrieval(decision);
      setState({ kind: "ok", decision, pool: result.pool });
    } catch (err) {
      if (err instanceof RetrievalBadRequestError) {
        setState({
          kind: "retrieval_failed",
          decision,
          code: err.code,
          message: err.message,
        });
        return;
      }
      const msg = err instanceof Error ? err.message : "Retrieval failed.";
      setState({
        kind: "retrieval_failed",
        decision,
        code: "unknown",
        message: msg,
      });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">Retrieve clinical evidence</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={submit}
            className="flex flex-col gap-3"
            data-testid="retrieval-form"
          >
            <label
              htmlFor="retrieval-question"
              className="text-foreground text-sm font-medium"
            >
              Clinical research question
            </label>
            <input
              id="retrieval-question"
              data-testid="retrieval-question-input"
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="e.g. Is aspirin effective for headache in adults?"
              maxLength={2000}
              autoComplete="off"
              disabled={
                state.kind === "scope_loading" ||
                state.kind === "retrieval_loading"
              }
              className="border-input focus-visible:border-ring focus-visible:ring-ring/50 h-9 w-full rounded-lg border bg-transparent px-3 py-1 text-sm transition-colors outline-none focus-visible:ring-3 disabled:opacity-50"
            />
            <p className="text-muted-foreground text-xs">
              Slice 002 only retrieves for in-scope clinical questions. The
              intake gate runs first; ambiguous, out-of-scope, or refused
              questions short-circuit before any retrieval is attempted.
            </p>
            <Button
              type="submit"
              variant="default"
              data-testid="retrieval-submit"
              disabled={
                state.kind === "scope_loading" ||
                state.kind === "retrieval_loading"
              }
            >
              {state.kind === "scope_loading"
                ? "Checking scope…"
                : state.kind === "retrieval_loading"
                  ? "Retrieving sources…"
                  : "Run retrieval"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {state.kind === "scope_failed" ? (
        <Card
          data-testid="retrieval-error"
          className="border-rose-500/40 bg-rose-500/5"
        >
          <CardContent className="text-rose-700 dark:text-rose-300">
            Intake failed: {state.message}
          </CardContent>
        </Card>
      ) : null}

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

      {state.kind === "retrieval_failed" ? (
        <Card
          data-testid="retrieval-error"
          className="border-rose-500/40 bg-rose-500/5"
        >
          <CardContent className="text-rose-700 dark:text-rose-300">
            <strong className="block">Retrieval failed ({state.code})</strong>
            {state.message}
          </CardContent>
        </Card>
      ) : null}

      {state.kind === "ok" ? <CorpusBrief pool={state.pool} /> : null}
    </div>
  );
}

function scope_reason_for(decision: IntakeScopeDecision): string {
  switch (decision.status) {
    case "out_of_scope":
      return "This question is out of scope for POLARIS clinical research.";
    case "refused":
      return "POLARIS refused this question (instruction-override attempt detected).";
    case "ambiguous_needs_clarification":
      return "This question is ambiguous. Please go to /intake to clarify before running retrieval.";
    default:
      return `Cannot run retrieval for status='${decision.status}'.`;
  }
}
