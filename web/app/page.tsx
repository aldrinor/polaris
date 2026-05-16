import Link from "next/link";

import { HomeKeyboardShell } from "@/app/components/home_keyboard_shell";
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
    id: "policy",
    name: "Public policy",
    summary:
      "Regulatory decisions, reimbursement and health-technology-assessment policy, public-health guidance, and cross-jurisdiction access comparisons.",
    sample_question:
      "What did NICE and CADTH conclude on the cost-effectiveness of CAR-T therapies?",
    out_of_scope: "Which political party has the better health platform?",
    active: false,
  },
  {
    id: "tech",
    name: "Technology assessment",
    summary:
      "Assessment of a technology, algorithm, or engineering approach — grounded in peer-reviewed conference and journal papers, standards, and attributed preprints.",
    sample_question:
      "What does the peer-reviewed evidence show on mixture-of-experts vs dense transformers as of 2025?",
    out_of_scope: "Which GPU should I buy for my gaming PC?",
    active: false,
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
    id: "due_diligence",
    name: "Due diligence",
    summary:
      "Company, product, market, and competitive-landscape research for investment, M&A, or partnership decisions — every claim carries named, dated provenance.",
    sample_question:
      "What did the most recent 10-K disclose on customer-concentration risk for this company?",
    out_of_scope: "Should I buy this stock?",
    active: false,
  },
  {
    id: "custom",
    name: "Custom research",
    summary:
      "Operator-defined catch-all for research questions that do not match the clinical, policy, tech, or due-diligence templates; accepts any classified source tier.",
    sample_question:
      "Summarize the documented positions on this question with provenance for each claim.",
    out_of_scope:
      "Requests for individualized legal, medical, or financial advice.",
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
      <HomeKeyboardShell templates={templates} signInHref="/sign-in">
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
                1 active · 7 to-build
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
      </HomeKeyboardShell>
    </div>
  );
}
