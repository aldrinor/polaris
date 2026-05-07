"use client";

import { VerifiedReportView } from "@/app/generation/components/verified_report_view";
import type {
  EvidencePool,
  RetrievalSource,
  VerifiedReport,
} from "@/lib/api";

const ISO = new Date().toISOString();
const FRESH_DATE = new Date(Date.now() - 30 * 24 * 3600 * 1000)
  .toISOString()
  .slice(0, 10);

const FULL_TEXT =
  "The randomized trial enrolled adults and demonstrated a significant outcome at endpoint assessment.";

const N = 12;

function _src(i: number): RetrievalSource {
  return {
    source_id: `src-${i}`,
    url: `https://www.cochrane.org/CD-edge-${i}`,
    domain: "cochrane.org",
    tier: "T1",
    title: `Edge source ${i}`,
    publication_date: FRESH_DATE,
    authors: ["Smith J"],
    snippet: FULL_TEXT.slice(0, 80),
    full_text_available: true,
    full_text: FULL_TEXT,
    fetched_at_utc: ISO,
    provenance: {},
  };
}

export function EvaluatorEdgeHarness({ mode }: { mode: "all" | "none" }) {
  const flagged = mode === "all";
  const pool: EvidencePool = {
    pool_id: `p-edge-${mode}`,
    decision_id: `d-edge-${mode}`,
    sources: Array.from({ length: N }, (_, i) => _src(i)),
    adequacy: {
      is_adequate: true,
      sources_per_tier: { T1: N, T2: 0, T3: 0 },
      min_required_per_tier: { T1: 1, T2: 0, T3: 0 },
      failure_reason: null,
    },
    queries_executed: ["edge"],
    retrieval_started_at_utc: ISO,
    retrieval_finished_at_utc: ISO,
    latency_ms: 0,
    cost_usd: 0,
  };

  const report: VerifiedReport = {
    report_id: `r-edge-${mode}`,
    pool_id: `p-edge-${mode}`,
    decision_id: `d-edge-${mode}`,
    sections: [
      {
        section_id: "sec_x",
        section_title: `Evaluator-edge harness (mode=${mode})`,
        verified_sentences: Array.from({ length: N }, (_, i) => ({
          section_id: "sec_x",
          sentence_text: `Edge sentence ${i} cites a source.`,
          provenance_tokens: [`[#ev:src-${i}:0-30]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: !flagged,
          ...(flagged
            ? {
                evaluator_disagreement: {
                  generator_reading: `Generator reading for sentence ${i}: claim X.`,
                  evaluator_reading: `Evaluator reading for sentence ${i}: confidence interval suggests Y.`,
                  cited_sources: [`src-${i}`],
                  evaluator_model: "qwen-3.5-plus",
                },
              }
            : {}),
        })),
        section_verify_pass_rate: 1.0,
        section_status: "verified",
      },
    ],
    overall_verify_pass_rate: 1.0,
    pipeline_verdict: "success",
    generator_model: "test/edge",
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
      data-testid={`evaluator-edge-${mode}`}
      className="mx-auto max-w-4xl p-6"
    >
      <VerifiedReportView report={report} pool={pool} />
    </div>
  );
}
