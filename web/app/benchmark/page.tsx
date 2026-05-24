import { BenchmarkBoard } from "./components/benchmark_board";

export const metadata = {
  title: "BEAT-BOTH benchmark — POLARIS Canada",
  description:
    "Head-to-head comparison of POLARIS vs ChatGPT Deep Research vs Gemini DR across 7 dimensions. Demoable scoreboard for the gift to PM Carney's office.",
};

// I-cd-027 (#617): /benchmark rebuild — G1/G6 fix. Page no longer renders
// its own <header>, <footer>, or <main>. AppShell (via AppShellGate from
// I-cd-022) is the single landmark provider. G2 fix: removed
// "POLARIS Canada — Slice 005" + "POLARIS v6.2 — Slice 005 (BEAT-BOTH
// benchmark)" dev-language strings via header/footer removal.
export default function BenchmarkPage() {
  return (
    <section
      data-testid="benchmark-page"
      className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-6 py-10"
    >
      <div className="flex flex-col gap-2">
        <h1 className="text-foreground text-2xl font-semibold tracking-tight sm:text-3xl">
          BEAT-BOTH benchmark
        </h1>
        <p className="text-muted-foreground max-w-3xl text-sm sm:text-base">
          Head-to-head comparison of POLARIS vs commercial deep-research
          products on 7 dimensions: sourcing tier mix, numeric grounding,
          provenance density, refusal correctness, coverage completeness,
          latency, and auditability. Refusal correctness and auditability are
          dimensions no commercial deep-research product reports against —
          POLARIS is built to be graded on them. Every score below comes from
          the published scoreboard, not this page.
        </p>
      </div>

      <BenchmarkBoard />

      <div
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
          runs against the same inputs produce identical scores. Carney&rsquo;s
          office can re-run the benchmark and compare bytewise.
        </p>
      </div>
    </section>
  );
}
