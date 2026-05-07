"use client";

import { VerifiedReportView } from "@/app/generation/components/verified_report_view";
import type { EvidencePool, RetrievalSource, VerifiedReport } from "@/lib/api";

const ISO = new Date().toISOString();
const FRESH_DATE = new Date(Date.now() - 30 * 24 * 3600 * 1000)
  .toISOString()
  .slice(0, 10);

const FULL_TEXT =
  "The randomized trial enrolled adults and demonstrated a significant outcome at endpoint assessment.";

function _src(i: number): RetrievalSource {
  return {
    source_id: `src-${i}`,
    url: `https://www.cochrane.org/CD-stress-${i}`,
    domain: "cochrane.org",
    tier: "T1",
    title: `Stress source ${i}`,
    publication_date: FRESH_DATE,
    authors: ["Smith J"],
    snippet: FULL_TEXT.slice(0, 80),
    full_text_available: true,
    full_text: FULL_TEXT,
    fetched_at_utc: ISO,
    provenance: {},
  };
}

export function StressHarness({ n }: { n: number }) {
  const pool: EvidencePool = {
    pool_id: `p-stress-${n}`,
    decision_id: `d-stress-${n}`,
    sources: Array.from({ length: Math.min(n, 50) }, (_, i) => _src(i)),
    adequacy: {
      is_adequate: true,
      sources_per_tier: { T1: Math.min(n, 50), T2: 0, T3: 0 },
      min_required_per_tier: { T1: 1, T2: 0, T3: 0 },
      failure_reason: null,
    },
    queries_executed: ["stress"],
    retrieval_started_at_utc: ISO,
    retrieval_finished_at_utc: ISO,
    latency_ms: 0,
    cost_usd: 0,
  };

  const report: VerifiedReport = {
    report_id: `r-stress-${n}`,
    pool_id: `p-stress-${n}`,
    decision_id: `d-stress-${n}`,
    sections: [
      {
        section_id: "sec_stress",
        section_title: `Stress section (n=${n})`,
        verified_sentences: Array.from({ length: n }, (_, i) => ({
          section_id: "sec_stress",
          sentence_text: `Stress sentence ${i} cites a source.`,
          provenance_tokens: [
            `[#ev:src-${i % Math.min(n, 50)}:0-${Math.min(40, FULL_TEXT.length)}]`,
          ],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        })),
        section_verify_pass_rate: 1.0,
        section_status: "verified",
      },
    ],
    overall_verify_pass_rate: 1.0,
    pipeline_verdict: "success",
    generator_model: "test/stress",
    evaluator_model: "strict_verify_v1",
    family_segregation_passed: true,
    verifier_pass_threshold: 0.4,
    started_at_utc: ISO,
    finished_at_utc: ISO,
    latency_ms: 0,
    cost_usd: 0,
  };

  return (
    <div
      data-testid={`inspector-latency-${n}`}
      className="mx-auto max-w-4xl p-6"
    >
      <VerifiedReportView report={report} pool={pool} />
    </div>
  );
}
