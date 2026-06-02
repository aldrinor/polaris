import { Suspense } from "react";

import { IntakeForm } from "./components/intake_form";
import { PdfDropBanner } from "./components/pdf_drop_banner";

// I-ux-001c sub-PR 3 (GH #884): v6 intake page chrome.
//
// Visual evolution only — the backend flow (scope check → scope_decision_view
// render-in-place → "Review sources →" handoff to /source_review) is
// PRESERVED in intake_form.tsx. The previous "Clinical scope discovery"
// muted eyebrow + "Ask a clinical research question" H1 + "how it works"
// 3-step grid are replaced by a brand-red eyebrow + display H1 + tightened
// subtitle. The STEPS grid is dropped — the v6 home's proof-as-CTA
// messaging already carries that explanation.

export const metadata = {
  title: "Ask a research question — POLARIS Canada",
  description:
    "Ask a clinical research question. POLARIS confirms it's answerable from clinical evidence and flags anything ambiguous or out of scope before running any search.",
};

// I-cd-023 (#613): /intake renders inside AppShell (single landmark
// provider). AppShellGate keeps /intake in the authed shell — NOT
// chromeless like the v6 home `/`.
export default function IntakePage() {
  return (
    <section
      data-testid="intake-page"
      className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-6 py-10 sm:py-12"
    >
      <div className="flex flex-col gap-3">
        <span
          data-testid="intake-eyebrow"
          className="text-primary text-[10px] font-medium tracking-[0.14em] uppercase"
        >
          ASK · POLARIS CLINICAL RESEARCH
        </span>
        <h1
          data-testid="intake-h1"
          className="text-foreground text-3xl leading-[1.1] font-bold tracking-tight text-balance sm:text-4xl"
        >
          Ask the research question.
        </h1>
        <p
          data-testid="intake-subtitle"
          className="text-muted-foreground max-w-2xl text-sm leading-relaxed sm:text-base"
        >
          POLARIS confirms your question is answerable from clinical evidence
          and flags anything ambiguous or out of scope before running a single
          search — so no run is wasted.
        </p>
      </div>

      <PdfDropBanner />

      <Suspense fallback={null}>
        <IntakeForm />
      </Suspense>
    </section>
  );
}
