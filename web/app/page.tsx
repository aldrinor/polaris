import Link from "next/link";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type Template = {
  id: string;
  name: string;
  summary: string;
  sample_question: string;
  out_of_scope: string;
  active: boolean;
};

const templates: Template[] = [
  {
    id: "clinical",
    name: "Clinical drug audit",
    summary:
      "Drug safety signals, labelling deltas, and post-market surveillance evidence across Health Canada, FDA, EMA, and clinical trials.",
    sample_question:
      "What did the SELECT trial show on cardiovascular outcomes for semaglutide?",
    out_of_scope: "Should I take ozempic for my diabetes?",
    active: true,
  },
  {
    id: "housing",
    name: "Housing & productivity",
    summary:
      "Canadian housing supply, affordability, productivity links, Indigenous housing gaps, and federal-provincial housing policy.",
    sample_question:
      "What did Q3 2025 CMHC housing-starts data show vs StatCan series 34-10-0143-01?",
    out_of_scope: "Should I buy a condo in Toronto?",
    active: true,
  },
  {
    id: "climate",
    name: "Climate & critical minerals",
    summary:
      "Canadian climate policy, oil-sands transition, critical minerals strategy, carbon pricing, methane regulation, Indigenous consent.",
    sample_question:
      "How did oil-sands emissions intensity per barrel change from 2010 to 2023 according to ECCC?",
    out_of_scope: "Should I buy a heat pump for my house?",
    active: true,
  },
  {
    id: "ai_sovereignty",
    name: "AI sovereignty",
    summary:
      "Canadian AI policy, sovereign compute, talent retention, IP and data residency, alignment posture, Bill C-27 / AIDA, federal AI strategy.",
    sample_question:
      "What sovereign compute capacity does Canada have for training frontier models as of 2025?",
    out_of_scope:
      "Should I take a job at a Canadian AI startup or move to San Francisco?",
    active: false,
  },
  {
    id: "canada_us",
    name: "Canada–US relations",
    summary:
      "Bilateral relationship, CUSMA / USMCA renegotiation, IRA spillover, energy + critical minerals integration, defense interoperability.",
    sample_question:
      "What are the 2026 CUSMA review triggers and what does Canada's pre-position look like?",
    out_of_scope: "Should I move to the US for tax reasons?",
    active: false,
  },
  {
    id: "defense",
    name: "Defense & Arctic",
    summary:
      "Canadian defense policy, NORAD modernization, Arctic sovereignty, AUKUS-adjacent posture, NATO 2% commitment.",
    sample_question:
      "What is Canada's defense spending as a percentage of GDP relative to the NATO 2% target in 2025?",
    out_of_scope: "How do I join the Canadian Armed Forces?",
    active: false,
  },
  {
    id: "trade",
    name: "Trade & tariff",
    summary:
      "Canadian trade policy, USMCA/CUSMA disputes, Section 232/301 tariff exposure, supply-chain resilience, and bilateral trade flows.",
    sample_question:
      "What is the status of US Section 232 steel tariffs on Canadian exports as of 2025?",
    out_of_scope: "Should I move my supply chain to Mexico?",
    active: false,
  },
  {
    id: "workforce",
    name: "Workforce & productivity",
    summary:
      "Canadian labour productivity, immigration + skills mismatch, regional unemployment, federal-provincial training, demographic shifts.",
    sample_question:
      "What does StatCan's 2024 productivity series show for Canada vs US over the last decade?",
    out_of_scope: "How do I apply for permanent residency?",
    active: false,
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
          aria-labelledby="template_grid_heading"
          className="flex flex-col gap-5"
          data-testid="template-grid"
        >
          <div className="flex items-baseline justify-between">
            <h2
              id="template_grid_heading"
              className="text-foreground text-xl font-semibold tracking-tight"
            >
              Research templates
            </h2>
            <span className="text-muted-foreground text-xs tracking-widest uppercase">
              3 active · 5 to-build
            </span>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {templates.map((tpl) => (
              <Card
                key={tpl.id}
                aria-disabled={tpl.active ? undefined : true}
                className={
                  tpl.active
                    ? "flex flex-col"
                    : "bg-muted/40 text-muted-foreground flex flex-col"
                }
                data-testid={`template-card-${tpl.id}`}
              >
                <CardHeader>
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-lg">{tpl.name}</CardTitle>
                    {!tpl.active ? (
                      <span
                        aria-hidden="true"
                        className="bg-background text-muted-foreground border-border rounded-full border px-2 py-0.5 text-[10px] font-medium tracking-widest uppercase"
                      >
                        Coming soon
                      </span>
                    ) : null}
                  </div>
                  <CardDescription className="text-sm">
                    {tpl.summary}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col justify-between gap-4">
                  <div className="flex flex-col gap-2 text-sm">
                    <p>
                      <span className="text-foreground font-medium">
                        In scope:
                      </span>{" "}
                      {tpl.sample_question}
                    </p>
                    <p>
                      <span className="text-foreground font-medium">
                        Out of scope:
                      </span>{" "}
                      {tpl.out_of_scope}
                    </p>
                  </div>
                  {tpl.active ? (
                    <Button
                      variant="outline"
                      nativeButton={false}
                      render={
                        <Link
                          data-testid={`template-card-${tpl.id}-link`}
                          href={`/intake?template=${tpl.id}`}
                        />
                      }
                    >
                      Open {tpl.name}
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      disabled
                      tabIndex={-1}
                      aria-disabled="true"
                    >
                      Coming soon
                    </Button>
                  )}
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
