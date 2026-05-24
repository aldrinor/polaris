import { Suspense } from "react";

import { BadgeCheck, MessageSquareText, ShieldCheck } from "lucide-react";

import { IntakeForm } from "./components/intake_form";
import { PdfDropBanner } from "./components/pdf_drop_banner";

// I-p2-045 (#837): a factual "how it works" strip — describes the real
// ask → scope-check → span-verified-brief flow (no fabricated metrics) — so the
// page reads intentional instead of a small card floating in empty space.
const STEPS = [
  {
    icon: MessageSquareText,
    title: "Ask your question",
    body: "Any clinical question — efficacy, safety, diagnosis, or prognosis.",
  },
  {
    icon: ShieldCheck,
    title: "Scope-checked first",
    body: "POLARIS confirms it's answerable from clinical evidence and flags ambiguity, so no run is wasted.",
  },
  {
    icon: BadgeCheck,
    title: "Get a verified brief",
    body: "Every sentence is span-checked against a primary source by an independent two-family evaluator.",
  },
] as const;

export const metadata = {
  title: "Ask a research question — POLARIS Canada",
  description:
    "Ask a clinical research question. POLARIS confirms it's answerable from clinical evidence and flags anything ambiguous or out of scope before running any search.",
};

// I-cd-023 (#613): /intake rebuild — G1/G6 fix. Page no longer renders
// its own <header> or <main>; AppShell (via AppShellGate, I-cd-022) is
// the single landmark provider for this route. G2 fix: removed
// "POLARIS Canada — Slice 001" + "POLARIS v6.2 — Slice 001 (scope + intake)"
// dev-language strings.
export default function IntakePage() {
  return (
    <section
      data-testid="intake-page"
      className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-6 py-10"
    >
      <div className="flex flex-col gap-2">
        <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
          Clinical scope discovery
        </span>
        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
          Ask a clinical research question
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
          POLARIS first confirms your question can be answered from clinical
          evidence — and flags anything ambiguous or out of scope — before it
          runs a single search. You&apos;ll see exactly how it&apos;s
          interpreted, so no run is wasted on a question that can&apos;t be
          answered as written.
        </p>
      </div>

      <PdfDropBanner />

      <Suspense fallback={null}>
        <IntakeForm />
      </Suspense>

      {/* How it works — sibling band (no nested card / no extra landmark) */}
      <div className="border-border/60 grid gap-x-6 gap-y-5 border-t pt-8 sm:grid-cols-3">
        {STEPS.map((step, i) => (
          <div key={step.title} className="flex flex-col gap-1.5">
            <div className="text-muted-foreground flex items-center gap-2">
              <span className="bg-muted text-foreground inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold tabular-nums">
                {i + 1}
              </span>
              <step.icon aria-hidden className="text-primary h-4 w-4" />
            </div>
            <h2 className="text-foreground text-sm font-semibold">
              {step.title}
            </h2>
            <p className="text-muted-foreground text-sm leading-relaxed">
              {step.body}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
