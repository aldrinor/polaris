import Link from "next/link";

import { Button } from "@/components/ui/button";

import { IntakeForm } from "./components/intake_form";
import { PdfDropBanner } from "./components/pdf_drop_banner";

export const metadata = {
  title: "Intake — POLARIS Canada",
  description:
    "Submit a clinical research question. POLARIS classifies scope and detects PICO ambiguity before any retrieval is run.",
};

export default function IntakePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada — Slice 001
            </span>
            <span className="text-foreground text-base font-semibold">
              Clinical scope discovery
            </span>
          </div>
          <Button
            variant="outline"
            nativeButton={false}
            render={<Link href="/" />}
          >
            Home
          </Button>
        </div>
      </header>

      <main
        data-testid="intake-page"
        className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 px-6 py-10"
      >
        <section className="flex flex-col gap-2">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            Clinical scope discovery
          </h1>
          <p className="text-muted-foreground max-w-2xl text-sm sm:text-base">
            Type a clinical research question and POLARIS will run it through
            the scope + intake: refusal-bait detection, scope classification
            (efficacy / safety / diagnosis / prognosis), and PICO axis ambiguity
            detection. No retrieval is run yet — this is the gate that decides
            if a question is researchable as written.
          </p>
        </section>

        <PdfDropBanner />

        <IntakeForm />
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — Slice 001 (scope + intake)</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
