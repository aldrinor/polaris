"use client";

// I-ux-001c sub-PR 3 (GH #884): auto-detected research-domain chip.
//
// Heuristic keyword-anchored classifier — pure client-side, no backend call.
// Maps the user's question text to one of the 8 scope templates from
// `web/app/page.tsx` (the v6 home's CommandPalette corpus). HONEST FALLBACK
// (LAW II): when no domain crosses the confidence threshold (no anchors
// matched, or matches are split too evenly), returns `null` — the UI MUST
// omit the chip rather than render a fabricated "custom" guess.
//
// This is NOT a scope-validity check. The authoritative scope gate is the
// backend `runIntake` call (POST /api/v6/intake), which classifies far
// beyond keyword anchors. The chip is a lightweight "here's what this
// LOOKS like" affordance shown WHILE the user is typing, so they have an
// immediate read of which template will likely fire.
import { useMemo } from "react";
import {
  Briefcase,
  Building2,
  Cpu,
  FileText,
  Flag,
  Globe,
  Search,
  Stethoscope,
  type LucideIcon,
} from "lucide-react";

interface AutoDomainChipProps {
  question: string;
}

type Domain =
  | "clinical"
  | "policy"
  | "tech"
  | "ai_sovereignty"
  | "canada_us"
  | "due_diligence"
  | "workforce"
  | "custom";

interface DomainMeta {
  label: string;
  icon: LucideIcon;
  anchors: RegExp[];
}

// Keyword anchors — case-insensitive whole-word matches. Each domain has
// 4-8 strong anchors; a match contributes 1 point to that domain. The
// highest-scoring domain wins iff its score ≥ 2 AND > runner-up score.
const DOMAINS: Record<Exclude<Domain, "custom">, DomainMeta> = {
  clinical: {
    label: "Clinical research",
    icon: Stethoscope,
    anchors: [
      /\b(rct|trial|trials|cohort)\b/i,
      /\b(efficacy|safety|contraindication|adverse|dose|dosing)\b/i,
      /\b(patient|patients|diagnosis|prognosis|treatment)\b/i,
      /\b(drug|drugs|medication|therapy|placebo)\b/i,
      /\b(meta-?analysis|systematic review|cochrane|grade)\b/i,
    ],
  },
  policy: {
    label: "Public policy",
    icon: FileText,
    anchors: [
      /\b(nice|cadth|hta|reimburs|listing|formulary)\b/i,
      /\b(regulation|regulatory|guidance|recommendation)\b/i,
      /\b(public health|health policy|jurisdiction)\b/i,
      /\b(cost-effectiveness|cost effective)\b/i,
    ],
  },
  tech: {
    label: "Technology assessment",
    icon: Cpu,
    anchors: [
      /\b(transformer|llm|gpu|cuda|inference|fine-?tune)\b/i,
      /\b(benchmark|architecture|algorithm)\b/i,
      /\b(peer-?reviewed|conference|preprint|arxiv)\b/i,
      /\b(mixture of experts|moe|dense model)\b/i,
    ],
  },
  ai_sovereignty: {
    label: "AI sovereignty",
    icon: Flag,
    anchors: [
      /\b(sovereign|sovereignty|data residency)\b/i,
      /\b(canadian (ai|compute|cluster))\b/i,
      /\b(bill c-?27|aida|pipeda)\b/i,
      /\b(alignment|safety policy|frontier model)\b/i,
    ],
  },
  canada_us: {
    label: "Canada–US relations",
    icon: Globe,
    anchors: [
      /\b(cusma|usmca|nafta)\b/i,
      /\b(canada.{0,15}us|us.{0,15}canada|bilateral)\b/i,
      /\b(ira|inflation reduction act|tariff)\b/i,
      /\b(critical minerals|energy integration)\b/i,
    ],
  },
  due_diligence: {
    label: "Due diligence",
    icon: Search,
    anchors: [
      /\b(10-?k|10-?q|annual report|filing)\b/i,
      /\b(customer concentration|revenue recognition|disclosure)\b/i,
      /\b(m&a|merger|acquisition|investment thesis)\b/i,
      /\b(competitive landscape|market analysis)\b/i,
    ],
  },
  workforce: {
    label: "Workforce & productivity",
    icon: Briefcase,
    anchors: [
      /\b(labour productivity|labor productivity)\b/i,
      /\b(immigration|skills mismatch|federal-?provincial training)\b/i,
      /\b(unemployment|statcan|workforce)\b/i,
      /\b(demographic shift|aging population)\b/i,
    ],
  },
};

interface ScoredDomain {
  domain: Domain;
  label: string;
  icon: LucideIcon;
  score: number;
}

function classify(question: string): ScoredDomain | null {
  if (!question || question.trim().length < 6) return null;
  const scores: ScoredDomain[] = [];
  for (const [key, meta] of Object.entries(DOMAINS)) {
    let s = 0;
    for (const anchor of meta.anchors) {
      if (anchor.test(question)) s += 1;
    }
    if (s > 0) {
      scores.push({
        domain: key as Domain,
        label: meta.label,
        icon: meta.icon,
        score: s,
      });
    }
  }
  if (scores.length === 0) return null;
  scores.sort((a, b) => b.score - a.score);
  const top = scores[0];
  const runnerUp = scores[1];
  // Confidence threshold: ≥ 2 hits AND clear lead over runner-up
  if (top.score < 2) return null;
  if (runnerUp && runnerUp.score >= top.score) return null;
  return top;
}

export function AutoDomainChip({ question }: AutoDomainChipProps) {
  const detected = useMemo(() => classify(question), [question]);
  if (!detected) return null;
  const Icon = detected.icon;
  return (
    <div
      data-testid="auto-domain-chip"
      data-domain={detected.domain}
      className="text-muted-foreground border-border bg-muted/40 inline-flex items-center gap-1.5 self-start rounded-full border px-2.5 py-1 text-xs"
      title={`POLARIS will likely use the ${detected.label} template for this question.`}
    >
      <span
        aria-hidden
        className="text-muted-foreground inline-flex h-3.5 w-3.5 items-center justify-center"
      >
        <Icon aria-hidden className="h-3.5 w-3.5" />
      </span>
      <span className="text-foreground font-medium">{detected.label}</span>
      <Building2
        aria-hidden
        className="text-muted-foreground/60 ml-0.5 h-3 w-3"
      />
      <span className="text-muted-foreground text-[10px] tracking-wider uppercase">
        Auto-detected
      </span>
    </div>
  );
}
