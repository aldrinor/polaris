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
      verified_sentences: [
        ...Array.from({ length: 10 }, (_, i) => {
          // Sentence 5: src-5 token span 0-50; sentence 9: src-ghost (missing-source path).
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
            evaluator_agrees: true,
          };
        }),
        // sec_x:10 — agree state (explicit for I-f5-004).
        {
          section_id: "sec_x",
          sentence_text: "Agreement-true demo sentence.",
          provenance_tokens: [`[#ev:src-0:0-3]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:11 — disagree (verifier_pass=true, LLM judge disagreed).
        {
          section_id: "sec_x",
          sentence_text: "Disagreement demo sentence.",
          provenance_tokens: [`[#ev:src-1:0-3]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: false,
        },
        // sec_x:12 — pending (no LLM judge pass yet).
        {
          section_id: "sec_x",
          sentence_text: "Pending demo sentence.",
          provenance_tokens: [`[#ev:src-2:0-3]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: null,
        },
        // sec_x:13 — multi-span same-source (I-f5-005). Two spans of src-0.
        {
          section_id: "sec_x",
          sentence_text: "Multi-span same-source demo sentence.",
          provenance_tokens: [`[#ev:src-0:0-30]`, `[#ev:src-0:60-90]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:14 — multi-source (I-f5-005). One span of src-1 + one of src-2.
        {
          section_id: "sec_x",
          sentence_text: "Multi-source demo sentence.",
          provenance_tokens: [`[#ev:src-1:0-20]`, `[#ev:src-2:30-50]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:15 — synthesis claim (I-f5-006). No tokens; flagged as synthesis.
        {
          section_id: "sec_x",
          sentence_text: "These trials together suggest a moderate effect.",
          provenance_tokens: [],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
          is_synthesis_claim: true,
        },
      ],
      section_verify_pass_rate: 1.0,
      section_status: "verified",
    },
  ],
  overall_verify_pass_rate: 1.0,
  pipeline_verdict: "success",
  generator_model: "test/model",
  evaluator_model: "strict_verify_v1",
  family_segregation_passed: true,
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
