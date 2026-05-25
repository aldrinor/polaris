// I-ux-001c (#878) sub-PR 2: v6 marketing-auth hero.
//
// Replaces the previous home (search bar + templates grid + ProofShowcase +
// RecentRunsStrip + pillars) with the brief-iter-4-APPROVE'd v6 hero:
//   - Tiny brand-red eyebrow
//   - One H1 (display 56/68 Geist Bold equivalent): "Every sentence proves itself."
//   - One subtitle paragraph, honest sovereignty wording
//   - Proof-as-CTA card (REAL verified claim + numeric stamp + sig pill)
//   - One primary CTA: "Try a verified brief →" → /intake
//
// Page is wrapped in HomePaletteShell (Ctrl+K + sign-in-link focus restore).
// AppShellGate keeps `/` chromeless; this page is its own marketing surface.
//
// Honest sovereignty wording (Codex iter-1 P1-001 fix on the iter-2 brief):
// "Canadian-hosted clinical research system, built toward sovereign Canadian
// deployment" — NEVER present-tense "sovereign" overclaim (LLM inference is
// routed via OpenRouter-US, disclosed in /transparency).
import { ArrowRight } from "lucide-react";
import Link from "next/link";

import { HomePaletteShell } from "@/components/home/home_palette_shell";
import { ProofAsCta } from "@/components/home/proof_as_cta";
import { MapleLeafSignatureLazy } from "@/components/signature/maple_leaf_signature_lazy";
import { SiteFooter } from "@/components/site_footer";
import { loadHomeBrief } from "@/lib/home_brief_loader";

// Template list passed to the CommandPalette (Ctrl+K). Shape preserved from
// the legacy HomeKeyboardShell so the existing 3 command_palette*.spec.ts
// suites pass unchanged.
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

export default async function HomePage() {
  const brief = await loadHomeBrief();
  return (
    <div className="relative flex min-h-screen flex-col">
      <HomePaletteShell templates={templates} signInHref="/sign-in">
        <main
          data-testid="home-hero"
          className="mx-auto flex w-full max-w-5xl flex-1 flex-col items-center gap-5 px-6 py-8 text-center sm:gap-6 sm:py-12"
        >
          {/* Decorative Braille maple-leaf signature (I-p2-028 #767) */}
          <MapleLeafSignatureLazy />

          {/* Eyebrow — brand-red, small caps */}
          <span
            data-testid="home-eyebrow"
            className="text-primary text-[10px] font-medium tracking-[0.14em] uppercase"
          >
            POLARIS · Canadian-hosted clinical research
          </span>

          {/* H1 — display weight, balanced wrap. Codex visual iter-3 P1:
              tightened from text-6xl→text-5xl on md+ to bring the primary
              CTA into the 900px desktop viewport. */}
          <h1
            data-testid="home-h1"
            className="text-foreground max-w-3xl text-4xl leading-[1.05] font-bold tracking-tight text-balance sm:text-5xl"
          >
            Every sentence proves itself.
          </h1>

          {/* Subtitle — honest sovereignty wording. Codex visual iter-3
              P1: trimmed to one sentence to recover above-fold real estate
              for the primary CTA. (The proof card + footer carry the
              "signed bundle / audit offline / OpenRouter US disclosure"
              detail, so the subtitle doesn't need to.) */}
          <p
            data-testid="home-subtitle"
            className="text-muted-foreground max-w-2xl text-base leading-relaxed text-pretty sm:text-lg"
          >
            POLARIS is a Canadian-hosted clinical research system, built toward
            sovereign Canadian deployment. Every claim is verified against its
            cited source by an independent model family — no verifier, no claim.
          </p>

          {/* Proof-as-CTA card — the HERO climax */}
          <ProofAsCta brief={brief} />

          {/* Primary CTA — one button only */}
          <Link
            href="/intake"
            data-testid="home-primary-cta"
            className="bg-primary text-primary-foreground ring-primary/40 hover:bg-primary/90 focus-visible:ring-ring/70 ease-standard inline-flex h-12 items-center justify-center gap-2 rounded-lg px-7 text-base font-semibold ring-1 transition-colors duration-150 focus-visible:ring-2 focus-visible:outline-none"
          >
            Try a verified brief
            <ArrowRight aria-hidden className="h-4 w-4" />
          </Link>
        </main>

        <SiteFooter />
      </HomePaletteShell>
    </div>
  );
}
