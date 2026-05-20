import Link from "next/link";

import { Button } from "@/components/ui/button";

import { BenchmarkBoard } from "./components/benchmark_board";

export const metadata = {
  title: "BEAT-BOTH benchmark — POLARIS Canada",
  description:
    "Head-to-head comparison of POLARIS vs ChatGPT Deep Research vs Gemini DR across 7 dimensions. Demoable scoreboard for the gift to PM Carney's office.",
};

export default function BenchmarkPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada — Slice 005
            </span>
            <span className="text-foreground text-base font-semibold">
              BEAT-BOTH benchmark
            </span>
          </div>
          <div className="flex gap-2">
            {/* I-cd-015 (GH#611): /generation is a dev-only harness route;
                the prod middleware 404s it. Removed the dead link button. */}
            <Button
              variant="outline"
              nativeButton={false}
              render={<Link href="/" />}
            >
              Home
            </Button>
          </div>
        </div>
      </header>

      <main
        data-testid="benchmark-page"
        className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-6 py-10"
      >
        <section className="flex flex-col gap-2">
          <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
            BEAT-BOTH benchmark
          </h1>
          <p className="text-muted-foreground max-w-3xl text-sm sm:text-base">
            Head-to-head comparison of POLARIS vs commercial deep-research
            products on 7 dimensions: sourcing tier mix, numeric grounding,
            provenance density, refusal correctness, coverage completeness,
            latency, and auditability. POLARIS uniquely scores 1.0 on refusal
            correctness and auditability — these are features no commercial
            system attempts.
          </p>
        </section>

        <BenchmarkBoard />

        <section
          aria-label="What this proves"
          className="border-border text-muted-foreground rounded-lg border p-4 text-xs"
        >
          <p>
            <strong className="text-foreground">Reproducible.</strong> Each
            scoreboard is produced by{" "}
            <code className="bg-muted rounded px-1 py-0.5 text-xs">
              scripts/run_benchmark.py
            </code>
            . The scoreboard.json artifact is canonical (sort_keys=True), so two
            runs against the same inputs produce identical scores.
            Carney&rsquo;s office can re-run the benchmark and compare bytewise.
          </p>
        </section>
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — Slice 005 (BEAT-BOTH benchmark)</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
