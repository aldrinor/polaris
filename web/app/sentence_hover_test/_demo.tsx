"use client";

import { VerifiedReportView } from "@/app/generation/components/verified_report_view";
import type { EvidencePool, RetrievalSource, VerifiedReport } from "@/lib/api";

const ISO = new Date().toISOString();

const SOURCE_FULL_TEXT_5 =
  "The randomized trial enrolled 1247 adults with chronic migraines and demonstrated significant aspirin headache reduction at outcomes assessment.";

function _src(i: number): RetrievalSource {
  return {
    source_id: `src-${i}`,
    url: `https://www.cochrane.org/CD-${i}`,
    domain: "cochrane.org",
    tier: "T1",
    title: `Cochrane review ${i}`,
    publication_date: "2024-03-15",
    authors: ["Smith J", "Doe R", "Patel K"],
    snippet: SOURCE_FULL_TEXT_5.slice(0, 80),
    full_text_available: true,
    full_text: SOURCE_FULL_TEXT_5,
    fetched_at_utc: ISO,
    provenance: {},
  };
}

const POOL: EvidencePool = {
  pool_id: "p-hover",
  decision_id: "d-hover",
  sources: Array.from({ length: 10 }, (_, i) => _src(i)),
  adequacy: {
    is_adequate: true,
    sources_per_tier: { T1: 10, T2: 0, T3: 0 },
    min_required_per_tier: { T1: 1, T2: 0, T3: 0 },
    failure_reason: null,
  },
  queries_executed: ["aspirin migraine"],
  retrieval_started_at_utc: ISO,
  retrieval_finished_at_utc: ISO,
  latency_ms: 0,
  cost_usd: 0,
};

const REPORT: VerifiedReport = {
  report_id: "r-hover-test",
  pool_id: "p-hover",
  decision_id: "d-hover",
  sections: [
    {
      section_id: "sec_x",
      section_title: "Test section",
      verified_sentences: Array.from({ length: 10 }, (_, i) => {
        // Sentence 5 has a valid token referencing src-5 with span 0-50.
        // Sentence 9 has a token referencing src-ghost (not in pool) for missing-source path.
        const token =
          i === 9
            ? `[#ev:src-ghost:0-3]`
            : `[#ev:src-${i}:0-${Math.min(50, SOURCE_FULL_TEXT_5.length)}]`;
        return {
          section_id: "sec_x",
          sentence_text: `Test sentence ${i} about aspirin.`,
          provenance_tokens: [token],
          verifier_pass: true,
          drop_reason: null,
        };
      }),
      section_verify_pass_rate: 1.0,
      section_status: "verified",
    },
  ],
  overall_verify_pass_rate: 1.0,
  pipeline_verdict: "success",
  generator_model: "test/model",
  verifier_pass_threshold: 0.4,
  started_at_utc: ISO,
  finished_at_utc: ISO,
  latency_ms: 0,
  cost_usd: 0,
};

export function SentenceHoverHarness() {
  return (
    <div className="mx-auto max-w-4xl p-6">
      <VerifiedReportView report={REPORT} pool={POOL} />
    </div>
  );
}
