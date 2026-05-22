import { BadgeCheck, Network, ShieldCheck } from "lucide-react";

import { HomeKeyboardShell } from "@/app/components/home_keyboard_shell";
import { RecentRunsStrip } from "@/app/components/recent_runs_strip";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

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

const PILLARS = [
  {
    icon: BadgeCheck,
    title: "Provable",
    body: "Click any claim and see the exact source passage it came from. Frontier tools hallucinate 3–13% of their citations — every POLARIS claim is span-anchored to a primary source.",
  },
  {
    icon: ShieldCheck,
    title: "Sovereign",
    body: "Canadian AI processing, no external AI vendor. Public sources are fetched via logged Canadian egress, and every brief is integrity-hashed and auditable.",
  },
  {
    icon: Network,
    title: "Snowball",
    body: "Each run grows a connected knowledge graph of claims and sources you can explore, follow up on, and build the next question from.",
  },
] as const;

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      <HomeKeyboardShell templates={templates} signInHref="/sign-in">
        <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-20 px-6 py-24">
          {/* Hero — one primary action */}
          <section className="flex flex-col items-center gap-6 text-center">
            <span className="text-muted-foreground border-border inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs">
              ⬡ Sovereign Canadian deep research
            </span>
            <h1 className="text-foreground max-w-3xl text-4xl font-semibold tracking-tight text-balance sm:text-5xl">
              Deep research you can check, line by line.
            </h1>
            <p className="text-muted-foreground max-w-2xl text-base text-pretty sm:text-lg">
              Every sentence is tied to a primary source with a provenance token
              and checked by an independent two-family evidence pipeline. Ask a
              question — get a brief where you can click any claim and read the
              exact passage behind it.
            </p>
            <form
              action="/intake"
              method="get"
              data-testid="home-hero-search"
              className="mt-2 flex w-full max-w-2xl items-center gap-2"
            >
              <Input
                name="q"
                type="search"
                aria-label="Research question"
                placeholder="Ask a research question…"
                className="h-12 flex-1 text-base"
              />
              <Button type="submit" className="h-12 px-7">
                Verify
              </Button>
            </form>
          </section>

          {/* Differentiator pillars — replaces the templates grid */}
          <section
            aria-label="Why POLARIS"
            className="grid gap-8 sm:grid-cols-3"
          >
            {PILLARS.map((pillar) => (
              <div key={pillar.title} className="flex flex-col gap-2">
                <pillar.icon
                  aria-hidden
                  className="text-primary h-5 w-5 shrink-0"
                />
                <h2 className="text-foreground text-sm font-semibold">
                  {pillar.title}
                </h2>
                <p className="text-muted-foreground text-sm leading-relaxed">
                  {pillar.body}
                </p>
              </div>
            ))}
          </section>

          {/* Real recent verified briefs */}
          <RecentRunsStrip />
        </main>

        <footer className="border-border bg-background border-t">
          <div className="text-muted-foreground mx-auto flex w-full max-w-4xl items-center justify-between px-6 py-4 text-xs">
            <span>POLARIS · Sovereign Canadian deep research</span>
            <span>Two-family verified evidence</span>
          </div>
        </footer>
      </HomeKeyboardShell>
    </div>
  );
}
