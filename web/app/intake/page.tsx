import { Suspense } from "react";

import { IntakeForm } from "./components/intake_form";
import { PdfDropBanner } from "./components/pdf_drop_banner";

export const metadata = {
  title: "Intake — POLARIS Canada",
  description:
    "Submit a clinical research question. POLARIS classifies scope and detects PICO ambiguity before any retrieval is run.",
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
          Clinical scope discovery
        </h1>
        <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
          Type a clinical research question and POLARIS will run it through the
          scope + intake: refusal-bait detection, scope classification (efficacy
          / safety / diagnosis / prognosis), and PICO axis ambiguity detection.
          No retrieval is run yet — this is the gate that decides if a question
          is researchable as written.
        </p>
      </div>

      <PdfDropBanner />

      <Suspense fallback={null}>
        <IntakeForm />
      </Suspense>
    </section>
  );
}
