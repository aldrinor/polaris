import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type DemoSlice = {
  id: string;
  step: string;
  title: string;
  href: string;
  description: string;
};

const demo_slices: DemoSlice[] = [
  {
    id: "intake",
    step: "Step 1",
    title: "Scope discovery + ambiguity",
    href: "/intake",
    description:
      "Submit a clinical research question. POLARIS detects ambiguity, prompts for PICO clarification, and emits a scope decision.",
  },
  {
    id: "retrieval",
    step: "Step 2",
    title: "Tiered retrieval",
    href: "/retrieval",
    description:
      "Live retrieval against Cochrane / PubMed / regulator domains via Serper + Semantic Scholar, with corpus-adequacy gating.",
  },
  {
    id: "generation",
    step: "Step 3",
    title: "Generator + strict-verify",
    href: "/generation",
    description:
      "Multi-section generation with provenance tokens and per-sentence numeric + content-overlap verification.",
  },
  {
    id: "benchmark",
    step: "Step 4",
    title: "BEAT-BOTH benchmark",
    href: "/benchmark",
    description:
      "Head-to-head scoreboard vs ChatGPT-DR / Gemini-DR across 7 dimensions: tier mix, numeric grounding, provenance density, refusal correctness, coverage, latency, auditability.",
  },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border bg-background border-b">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <div className="flex flex-col">
            <span className="text-muted-foreground text-xs font-medium tracking-widest uppercase">
              POLARIS Canada
            </span>
            <span className="text-foreground text-base font-semibold">
              Sovereign Deep Research
            </span>
          </div>
          <Button
            variant="default"
            nativeButton={false}
            render={<Link href="/sign-in" />}
          >
            Sign in
          </Button>
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-10 px-6 py-12">
        <section className="flex flex-col gap-3">
          <h1 className="text-foreground text-3xl font-semibold tracking-tight sm:text-4xl">
            POLARIS Canada — Sovereign Deep Research
          </h1>
          <p className="text-muted-foreground max-w-3xl text-base sm:text-lg">
            Two-family verified evidence pipelines for Government of Canada
            policy work. Every claim carries a provenance token tied to a
            primary source.
          </p>
        </section>

        <section
          aria-labelledby="demo_walkthrough_heading"
          className="flex flex-col gap-5"
          data-testid="demo-walkthrough"
        >
          <div className="flex items-baseline justify-between">
            <h2
              id="demo_walkthrough_heading"
              className="text-foreground text-xl font-semibold tracking-tight"
            >
              Tracer demo walkthrough
            </h2>
            <span className="text-muted-foreground text-xs tracking-widest uppercase">
              Slices 1 → 5
            </span>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {demo_slices.map((slice) => (
              <Card
                key={slice.id}
                className="flex flex-col"
                data-testid={`demo-slice-${slice.id}`}
              >
                <CardHeader>
                  <CardDescription className="text-xs tracking-widest uppercase">
                    {slice.step}
                  </CardDescription>
                  <CardTitle className="text-lg">{slice.title}</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col justify-between gap-4">
                  <p className="text-muted-foreground text-sm">
                    {slice.description}
                  </p>
                  <Button
                    variant="outline"
                    nativeButton={false}
                    render={<Link href={slice.href} />}
                  >
                    Open {slice.title}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-border bg-background border-t">
        <div className="text-muted-foreground mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4 text-xs">
          <span>POLARIS v6.2 — slices 1-5 shipped</span>
          <span>Sovereign Canadian deep research</span>
        </div>
      </footer>
    </div>
  );
}
