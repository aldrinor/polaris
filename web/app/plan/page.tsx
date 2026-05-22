// I-p2-015 (#754): Plan review — the run-start surface (relocated off the
// dashboard so #761 can become monitoring-only). "Confirm + start": the
// question is DISPLAY-ONLY here (single source of preflight truth = intake);
// editing routes back to /intake. On mount it re-runs the FULL intake gate
// (runIntake — the clinical + PICO classifier, NOT the lenient /scope/check) so
// direct navigation to /plan?q=… is gated identically. "Start research run" is
// enabled ONLY for an in_scope, disambiguation-resolved question. Question-only
// run-start (no uploads here — document grounding keeps its /upload home until a
// follow-up wires it into this flow).
"use client";

import {
  ArrowLeft,
  BadgeCheck,
  FileSearch,
  Layers,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { DisambiguationModal } from "@/app/intake/components/disambiguation_modal";
import { ErrorState } from "@/components/states/state_kit";
import { Button } from "@/components/ui/button";
import {
  ConcurrentRunError,
  createRun,
  runDisambiguation,
  runIntake,
  type DisambiguationCluster,
  type IntakeScopeDecision,
  type TemplateId,
} from "@/lib/api";

const TEMPLATE_IDS: readonly TemplateId[] = [
  "clinical",
  "policy",
  "tech",
  "ai_sovereignty",
  "canada_us",
  "due_diligence",
  "custom",
  "workforce",
];

function asTemplate(value: string | null): TemplateId {
  return value && (TEMPLATE_IDS as readonly string[]).includes(value)
    ? (value as TemplateId)
    : "clinical";
}

const PLAN_STEPS = [
  {
    icon: FileSearch,
    title: "Retrieve primary sources",
    body: "POLARIS searches via logged Canadian egress and snapshots each source it draws from.",
  },
  {
    icon: ShieldCheck,
    title: "Corpus-adequacy + approval gate",
    body: "The source set must meet per-tier adequacy and pass the approval gate before any brief is generated.",
  },
  {
    icon: Layers,
    title: "Generate, then verify every claim",
    body: "Each sentence is generated section by section, then span-verified against its primary source by an independent evaluator family.",
  },
  {
    icon: BadgeCheck,
    title: "Produce an auditable bundle",
    body: "You get a brief where every claim links to the exact source passage behind it.",
  },
] as const;

type State =
  | { kind: "loading" }
  | { kind: "ready"; decision: IntakeScopeDecision }
  | { kind: "error"; message: string };

function PlanContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const question = (searchParams.get("q") ?? "").trim();
  const template = asTemplate(searchParams.get("template"));

  const [state, setState] = useState<State>({ kind: "loading" });
  const [disambigClusters, setDisambigClusters] = useState<
    DisambiguationCluster[]
  >([]);
  const [disambigOpen, setDisambigOpen] = useState(false);
  const [disambigResolved, setDisambigResolved] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [concurrent, setConcurrent] = useState<{
    runId: string;
    message: string;
  } | null>(null);

  // On mount: re-run the FULL intake gate over the (immutable) question. This
  // is the same clinical + PICO classifier intake uses, so /plan is safe even
  // when reached by direct URL.
  useEffect(() => {
    if (!question) {
      setState({ kind: "error", message: "no-question" });
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const result = await runIntake(question);
        if (cancelled) return;
        setState({ kind: "ready", decision: result.decision });
        if (
          result.decision.needs_disambiguation &&
          result.decision.candidate_snippets &&
          result.decision.candidate_snippets.length > 0
        ) {
          const dis = await runDisambiguation(
            result.decision.candidate_snippets,
          );
          if (cancelled) return;
          if (dis.is_ambiguous && dis.clusters.length > 1) {
            setDisambigClusters(dis.clusters);
            setDisambigOpen(true);
          } else {
            setDisambigResolved(true); // nothing to disambiguate
          }
        } else {
          setDisambigResolved(true);
        }
      } catch (err) {
        if (cancelled) return;
        setState({
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Could not check this question.",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [question]);

  if (
    !question ||
    (state.kind === "error" && state.message === "no-question")
  ) {
    return (
      <section
        data-testid="plan-page"
        className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-6 py-16 text-center"
      >
        <h1 className="text-foreground text-2xl font-semibold tracking-tight">
          Nothing to plan yet
        </h1>
        <p className="text-muted-foreground text-sm">
          Start from a research question and POLARIS will lay out the plan
          before running it.
        </p>
        <div>
          <Button
            nativeButton={false}
            render={<Link href="/intake">Ask a question</Link>}
          />
        </div>
      </section>
    );
  }

  const decision = state.kind === "ready" ? state.decision : null;
  const inScope = decision?.status === "in_scope";
  const canStart = inScope && disambigResolved && !starting;

  async function onStart() {
    setStartError(null);
    setConcurrent(null);
    setStarting(true);
    try {
      const run = await createRun({ template, question, document_ids: [] });
      router.push(`/runs/${run.run_id}`);
    } catch (err) {
      if (err instanceof ConcurrentRunError) {
        setConcurrent({ runId: err.activeRunId, message: err.message });
        setStarting(false);
        return;
      }
      setStartError(
        err instanceof Error ? err.message : "Could not start the run.",
      );
      setStarting(false);
    }
  }

  function notInScopeMessage(d: IntakeScopeDecision): string {
    switch (d.status) {
      case "out_of_scope":
        return "This question is outside POLARIS's clinical research scope.";
      case "refused":
        return "POLARIS declined this question (refusal-bait or unsafe request).";
      case "ambiguous_needs_clarification":
        return "This question needs clarification before it can be researched.";
      default:
        return "This question can't be started as written.";
    }
  }

  return (
    <section
      data-testid="plan-page"
      className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-6 py-10"
    >
      <div className="flex flex-col gap-1">
        <Link
          href="/intake"
          className="text-muted-foreground hover:text-foreground inline-flex w-fit items-center gap-1 text-xs"
        >
          <ArrowLeft aria-hidden className="h-3.5 w-3.5" />
          Edit question
        </Link>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
          Review the plan
        </h1>
        <p className="text-muted-foreground text-sm">
          Confirm what POLARIS will research before the run starts.
        </p>
      </div>

      {/* The vetted question (display-only) */}
      <div className="border-border bg-card flex flex-col gap-2 rounded-xl border p-5">
        <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
          Your question
        </span>
        <p className="text-foreground text-lg leading-relaxed font-medium">
          {question}
        </p>
        <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
          <span className="border-border rounded-full border px-2 py-0.5">
            Template: <span className="text-foreground">{template}</span>
          </span>
          {state.kind === "loading" ? (
            <span>Checking scope…</span>
          ) : decision?.scope_class ? (
            <span className="border-border rounded-full border px-2 py-0.5">
              Scope:{" "}
              <span className="text-foreground">{decision.scope_class}</span>
            </span>
          ) : null}
        </div>
      </div>

      {/* What POLARIS will do */}
      <div className="flex flex-col gap-4">
        <h2 className="text-foreground text-sm font-semibold">
          What POLARIS will do
        </h2>
        <ol className="grid gap-4 sm:grid-cols-2">
          {PLAN_STEPS.map((step, i) => (
            <li
              key={step.title}
              className="border-border bg-card flex flex-col gap-1.5 rounded-lg border p-4"
            >
              <div className="text-primary flex items-center gap-2">
                <step.icon aria-hidden className="h-4 w-4 shrink-0" />
                <span className="text-foreground text-sm font-medium">
                  {i + 1}. {step.title}
                </span>
              </div>
              <p className="text-muted-foreground text-xs leading-relaxed">
                {step.body}
              </p>
            </li>
          ))}
        </ol>
      </div>

      {/* Not-in-scope guard */}
      {decision && !inScope ? (
        <div
          role="alert"
          data-testid="plan-blocked"
          className="border-refusal/30 bg-refusal/10 flex flex-col gap-1 rounded-lg border p-4"
        >
          <p className="text-foreground text-sm font-medium">
            Can't start this run
          </p>
          <p className="text-muted-foreground text-xs">
            {notInScopeMessage(decision)} Edit the question to continue.
          </p>
        </div>
      ) : null}

      {startError ? (
        <ErrorState title="Couldn't start the run" message={startError} />
      ) : null}

      {concurrent ? (
        <div
          role="alert"
          data-testid="plan-concurrent"
          className="border-contradiction/30 bg-contradiction/10 flex flex-col gap-1 rounded-lg border p-4"
        >
          <p className="text-foreground text-sm font-medium">
            A run is already in progress
          </p>
          <p className="text-muted-foreground text-xs">{concurrent.message}</p>
          <Link
            href={`/runs/${concurrent.runId}`}
            className="text-primary text-xs underline-offset-2 hover:underline"
          >
            View the active run →
          </Link>
        </div>
      ) : null}

      {/* Start */}
      <div className="flex items-center gap-3">
        <Button
          type="button"
          data-testid="plan-start-run"
          className="h-11 px-7"
          disabled={!canStart}
          onClick={onStart}
        >
          {starting ? "Starting…" : "Start research run"}
        </Button>
        <Button
          variant="ghost"
          nativeButton={false}
          render={<Link href="/intake">Cancel</Link>}
        />
      </div>

      <DisambiguationModal
        open={disambigOpen}
        clusters={disambigClusters}
        onSelectCluster={() => {
          setDisambigResolved(true);
          setDisambigOpen(false);
        }}
        onCancel={() => setDisambigOpen(false)}
      />
    </section>
  );
}

export default function PlanPage() {
  return (
    <Suspense fallback={null}>
      <PlanContent />
    </Suspense>
  );
}
