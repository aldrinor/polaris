import { Suspense } from "react";

import { IntakeForm } from "./components/intake_form";
import { PdfDropBanner } from "./components/pdf_drop_banner";

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
    </section>
  );
}
