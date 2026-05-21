import Link from "next/link";

import { HomeHero } from "@/app/components/home_hero";
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
        <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-14 px-6 pb-16 sm:gap-20">
          <HomeHero />

          <section
            aria-labelledby="template_grid_heading"
            className="flex flex-col gap-5"
            data-testid="template-grid"
          >
            <div className="flex items-baseline justify-between">
              <h2
                id="template_grid_heading"
                className="text-foreground text-sm font-semibold tracking-[0.15em] uppercase"
              >
                Research templates
              </h2>
              <span className="text-muted-foreground text-xs">
                1 active · 7 in development
              </span>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {templates.map((tpl) => (
                <Card
                  key={tpl.id}
                  aria-disabled={tpl.active ? undefined : true}
                  className={
                    tpl.active
                      ? "ring-border hover:ring-primary/40 hover:shadow-primary/5 group bg-card flex flex-col gap-2 rounded-xl p-4 ring-1 transition-all hover:-translate-y-0.5 hover:shadow-lg"
                      : "ring-border bg-muted/30 text-muted-foreground flex flex-col gap-2 rounded-xl p-4 opacity-70 ring-1"
                  }
                  data-testid={`template-card-${tpl.id}`}
                >
                  <CardHeader className="p-0 pb-1">
                    <div className="flex items-start justify-between gap-2">
                      <CardTitle className="text-foreground text-base font-semibold tracking-tight">
                        {tpl.name}
                      </CardTitle>
                      {!tpl.active ? (
                        <span
                          aria-hidden="true"
                          className="border-border text-muted-foreground rounded-full border px-2 py-0.5 text-[9px] font-medium tracking-widest uppercase"
                        >
                          Soon
                        </span>
                      ) : (
                        <span
                          aria-hidden="true"
                          className="bg-primary/10 text-primary rounded-full px-2 py-0.5 text-[9px] font-medium tracking-widest uppercase"
                        >
                          Live
                        </span>
                      )}
                    </div>
                    <CardDescription className="text-muted-foreground line-clamp-3 text-xs leading-relaxed">
                      {tpl.summary}
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-1 flex-col justify-end p-0">
                    {tpl.active ? (
                      <Button
                        className="group-hover:bg-primary group-hover:text-primary-foreground w-full justify-between"
                        nativeButton={false}
                        render={
                          <Link
                            data-testid={`template-card-${tpl.id}-link`}
                            href={`/intake?template=${tpl.id}`}
                          />
                        }
                        variant="outline"
                      >
                        Open <span aria-hidden="true">→</span>
                      </Button>
                    ) : (
                      <Button
                        aria-disabled="true"
                        className="w-full"
                        disabled
                        tabIndex={-1}
                        variant="ghost"
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
          <div className="text-muted-foreground mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4 text-xs">
            <span>POLARIS · Sovereign Canadian deep research</span>
            <span>
              <Link
                className="hover:text-foreground underline-offset-4 hover:underline"
                href="/transparency"
              >
                Transparency
              </Link>
            </span>
          </div>
        </footer>
      </HomeKeyboardShell>
    </div>
  );
}
