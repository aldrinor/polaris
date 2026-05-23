"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { ErrorState } from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  IntakeBadRequestError,
  runDisambiguation,
  runIntake,
  type DisambiguationCluster,
  type IntakeScopeDecision,
} from "@/lib/api";

import { AmbiguityModal } from "./ambiguity_modal";
import { DisambiguationModal } from "./disambiguation_modal";
import { ScopeDecisionView } from "./scope_decision_view";

type IntakeState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; decision: IntakeScopeDecision }
  | { kind: "error"; message: string };

const SAMPLE_QUESTIONS = [
  "Does aspirin reduce headaches in adults?",
  "What are the safety risks of metformin in older adults?",
  "Is physical therapy effective for chronic back pain in adults?",
];

const FRENCH_STOPWORD_RE =
  /\b(le|la|les|de|des|du|que|qui|et|est|un|une|sont|pour|avec|sans|dans)\b/gi;
const FRENCH_ACCENTED_RE = /[éèêëàâäçîïôöùûüÿñ]/i;

function looksNonEnglish(s: string): boolean {
  if (FRENCH_ACCENTED_RE.test(s)) return true;
  const matches = s.match(FRENCH_STOPWORD_RE);
  return (matches?.length ?? 0) >= 3;
}

export function IntakeForm() {
  // I-cd-ui-001 (#704): prefill from the home hero search (/intake?q=...).
  // useSearchParams requires a Suspense boundary — the intake page wraps
  // this component in <Suspense> (mirroring web/app/sign-in/page.tsx).
  const searchParams = useSearchParams();
  const [question, setQuestion] = useState(searchParams.get("q") ?? "");
  const [state, setState] = useState<IntakeState>({ kind: "idle" });
  const [modalOpen, setModalOpen] = useState(false);
  const [disambigClusters, setDisambigClusters] = useState<
    DisambiguationCluster[]
  >([]);
  const [disambigOpen, setDisambigOpen] = useState(false);
  const [pickedClusterLabel, setPickedClusterLabel] = useState<string | null>(
    null,
  );

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 3) {
      setState({
        kind: "error",
        message: "Please enter a question with at least 3 characters.",
      });
      return;
    }
    if (looksNonEnglish(trimmed)) {
      setState({
        kind: "error",
        message: "POLARIS currently supports English questions only.",
      });
      return;
    }

    setState({ kind: "loading" });
    try {
      const result = await runIntake(trimmed);
      setState({ kind: "ok", decision: result.decision });
      if (result.decision.status === "ambiguous_needs_clarification") {
        setModalOpen(true);
      }
      if (
        result.decision.needs_disambiguation &&
        result.decision.candidate_snippets &&
        result.decision.candidate_snippets.length > 0
      ) {
        const dis = await runDisambiguation(result.decision.candidate_snippets);
        if (dis.is_ambiguous && dis.clusters.length > 1) {
          setDisambigClusters(dis.clusters);
          setDisambigOpen(true);
        }
      }
    } catch (err) {
      if (err instanceof IntakeBadRequestError) {
        setState({ kind: "error", message: err.message });
        return;
      }
      const message = err instanceof Error ? err.message : "Unknown error.";
      setState({ kind: "error", message });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-xl">
            Ask POLARIS a clinical research question
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form
            onSubmit={submit}
            className="flex flex-col gap-3"
            data-testid="intake-form"
          >
            <label
              htmlFor="intake-question"
              className="text-foreground text-sm font-medium"
            >
              Your question
            </label>
            <Input
              id="intake-question"
              data-testid="intake-question-input"
              placeholder="e.g. Does aspirin reduce headaches in adults?"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              maxLength={2000}
              disabled={state.kind === "loading"}
              autoComplete="off"
            />
            <p className="text-muted-foreground text-xs">
              POLARIS only researches clinical evidence questions (efficacy,
              safety, diagnosis, prognosis). Other domains will be marked out of
              scope.
            </p>

            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="submit"
                variant="default"
                disabled={state.kind === "loading"}
                data-testid="intake-submit"
              >
                {state.kind === "loading" ? "Checking…" : "Check scope"}
              </Button>
              <span className="text-muted-foreground text-xs">or try:</span>
              {SAMPLE_QUESTIONS.map((sample) => (
                <button
                  key={sample}
                  type="button"
                  onClick={() => setQuestion(sample)}
                  className="text-muted-foreground hover:text-foreground border-border rounded-full border px-2 py-1 text-xs transition-colors"
                >
                  {sample}
                </button>
              ))}
            </div>
          </form>
        </CardContent>
      </Card>

      {state.kind === "error" ? (
        <div data-testid="intake-error">
          {/* I-p2-014 (#753): #750 ErrorState (design-system tokens + role=alert)
              replaces the hardcoded-rose card. */}
          <ErrorState title="Scope check failed" message={state.message} />
        </div>
      ) : null}

      {state.kind === "ok" ? (
        <>
          <ScopeDecisionView decision={state.decision} />
          {/* I-p2-015 (#754): in-scope questions hand off to the plan-review
              page, which is the run-start surface. */}
          {state.decision.status === "in_scope" ? (
            <div className="flex justify-end">
              {/* I-p2-031 (#770): route through source-review (see the source
                  set + adequacy bar) before the plan/run-start surface. */}
              <Button
                nativeButton={false}
                data-testid="intake-continue-to-plan"
                render={
                  <Link
                    href={`/source_review?q=${encodeURIComponent(question.trim())}`}
                  >
                    Review sources →
                  </Link>
                }
              />
            </div>
          ) : null}
        </>
      ) : null}

      <AmbiguityModal
        open={modalOpen}
        decision={state.kind === "ok" ? state.decision : null}
        onContinue={() => setModalOpen(false)}
        onCancel={() => setModalOpen(false)}
      />

      <DisambiguationModal
        open={disambigOpen}
        clusters={disambigClusters}
        onSelectCluster={(cid) => {
          const found = disambigClusters.find((c) => c.cluster_id === cid);
          setPickedClusterLabel(found?.label ?? null);
          setDisambigOpen(false);
        }}
        onCancel={() => setDisambigOpen(false)}
      />

      <output data-testid="disambig-picked-label" className="sr-only">
        {pickedClusterLabel ?? ""}
      </output>
    </div>
  );
}
