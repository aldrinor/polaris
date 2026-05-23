"use client";

import { useState } from "react";

import { ErrorState } from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import { askFollowup, type FollowUpAnswer } from "@/lib/api";

// I-ui-003 (#542): report-scoped follow-up. Shown only for completed runs by
// the parent page. Submits POST /runs/{id}/followup and renders the
// FollowUpAnswer (all four statuses) with provenance.

const MAX_QUESTION = 2000;
const MIN_QUESTION = 4;

type PanelState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "answered"; answer: FollowUpAnswer }
  | { kind: "error"; message: string };

function errorMessage(err: unknown): string {
  const status = (err as { status?: number })?.status;
  const body = (err as { body?: unknown })?.body;
  if (status === 404) return "This run was not found.";
  if (status === 422) {
    // FastAPI request-validation errors carry a list under `detail`; a
    // run/artifact 422 from load_evidence_contract_for_run does not.
    const detail = (body as { detail?: unknown })?.detail;
    if (Array.isArray(detail)) {
      return `Your question must be ${MIN_QUESTION}–${MAX_QUESTION} characters.`;
    }
    return "This run has no shippable evidence to follow up on (it was aborted or release-blocked).";
  }
  return "Couldn't get a follow-up answer right now. Please retry shortly.";
}

const STATUS_LABEL: Record<FollowUpAnswer["status"], string> = {
  answered: "Answered",
  out_of_scope: "Out of scope",
  needs_new_run: "Needs a new run",
  evidence_insufficient: "Evidence insufficient",
};

export function FollowupPanel({ runId }: { runId: string }) {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<PanelState>({ kind: "idle" });

  const trimmed = question.trim();
  const canSubmit =
    trimmed.length >= MIN_QUESTION && state.kind !== "submitting";

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    setState({ kind: "submitting" });
    try {
      const answer = await askFollowup(runId, trimmed);
      setState({ kind: "answered", answer });
    } catch (err) {
      setState({ kind: "error", message: errorMessage(err) });
    }
  }

  return (
    <section
      data-testid="followup-panel"
      className="border-border bg-card flex flex-col gap-3 rounded-lg border p-4"
    >
      <h2 className="text-foreground text-sm font-semibold">Ask a follow-up</h2>
      <p className="text-muted-foreground text-xs">
        Scoped to this run&apos;s verified evidence — no new retrieval is run.
      </p>
      <form onSubmit={onSubmit} className="flex flex-col gap-2">
        <textarea
          data-testid="followup-question"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={MAX_QUESTION}
          rows={3}
          aria-label="Follow-up question"
          placeholder="e.g. What did the trial show for the subgroup over 65?"
          className="border-input focus-visible:border-ring focus-visible:ring-ring w-full rounded-lg border bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2"
        />
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground text-[10px]">
            {trimmed.length}/{MAX_QUESTION}
          </span>
          <Button type="submit" disabled={!canSubmit}>
            {state.kind === "submitting" ? "Asking…" : "Ask"}
          </Button>
        </div>
      </form>

      {/* I-p2-018 (#757): #750 ErrorState (design tokens + role=alert) for
          consistency with every other page. */}
      {state.kind === "error" && (
        <ErrorState title="Follow-up failed" message={state.message} />
      )}

      {state.kind === "answered" && <AnswerView answer={state.answer} />}
    </section>
  );
}

function AnswerView({ answer }: { answer: FollowUpAnswer }) {
  return (
    <div
      data-testid="followup-answer"
      data-status={answer.status}
      className="border-border flex flex-col gap-3 rounded-md border p-3"
    >
      <span className="text-primary text-[10px] font-semibold tracking-widest uppercase">
        {STATUS_LABEL[answer.status]}
      </span>

      {answer.status === "answered" && answer.answer_text && (
        <p className="text-foreground text-sm whitespace-pre-wrap">
          {answer.answer_text}
        </p>
      )}

      {/* rationale is always present and explains the status / evidence use */}
      <p className="text-muted-foreground text-xs">{answer.rationale}</p>

      {answer.status === "needs_new_run" && (
        <p className="text-muted-foreground text-xs">
          This question needs fresh retrieval — start a new run from{" "}
          <a className="text-primary underline" href="/intake">
            Intake
          </a>
          .
        </p>
      )}

      {(answer.used_evidence_ids.length > 0 ||
        answer.provenance_tokens.length > 0) && (
        <div className="flex flex-col gap-1">
          <span className="text-muted-foreground text-[10px] font-medium tracking-widest uppercase">
            Provenance
          </span>
          <div className="flex flex-wrap gap-1">
            {answer.used_evidence_ids.map((id) => (
              <span
                key={id}
                className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono text-[10px]"
              >
                {id}
              </span>
            ))}
            {answer.provenance_tokens.map((tok, i) => (
              <span
                key={`${tok}-${i}`}
                className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 font-mono text-[10px]"
              >
                {tok}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
