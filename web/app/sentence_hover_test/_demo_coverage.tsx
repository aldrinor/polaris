"use client";

import { VerifiedReportView } from "@/app/generation/components/verified_report_view";
import type {
  EvidencePool,
  FrameGap,
  GapReason,
  RetrievalSource,
  VerifiedReport,
} from "@/lib/api";

const ISO = new Date().toISOString();
const FRESH_DATE = new Date(Date.now() - 30 * 24 * 3600 * 1000)
  .toISOString()
  .slice(0, 10);

// Cycle synthetic gaps through GapReason union literals (NOT a runtime enum
// per Codex iter-1 P2 — explicit typed array).
const GAP_REASONS: GapReason[] = [
  "paywalled",
  "no_oa",
  "source_tier_ineligible",
  "language_unavailable",
  "retracted_only",
  "jurisdiction_outside",
  "not_indexed",
  "embargoed",
  "other",
];

const SRC: RetrievalSource = {
  source_id: "src-cov-0",
  url: "https://www.cochrane.org/CD-cov-0",
  domain: "cochrane.org",
  tier: "T1",
  title: "Coverage harness source",
  publication_date: FRESH_DATE,
  authors: ["Smith J"],
  snippet: "Coverage demo source snippet text used by the harness.",
  full_text_available: true,
  full_text: "Coverage demo source snippet text used by the harness.",
  fetched_at_utc: ISO,
  provenance: {},
};

export function CoverageHarness({
  covered,
  gap_count,
}: {
  covered: number;
  gap_count: number;
}) {
  const total = covered + gap_count;
  const gaps: FrameGap[] = Array.from({ length: gap_count }, (_, i) => ({
    entity_name: `Entity ${i + 1}`,
    reason: GAP_REASONS[i % GAP_REASONS.length],
    reason_detail: `synthetic detail ${i + 1}`,
  }));
  const pool: EvidencePool = {
    pool_id: "p-cov",
    decision_id: "d-cov",
    sources: [SRC],
    adequacy: {
      is_adequate: true,
      sources_per_tier: { T1: 1, T2: 0, T3: 0 },
      min_required_per_tier: { T1: 1, T2: 0, T3: 0 },
      failure_reason: null,
    },
    queries_executed: ["coverage"],
    retrieval_started_at_utc: ISO,
    retrieval_finished_at_utc: ISO,
    latency_ms: 0,
    cost_usd: 0,
  };
  const report: VerifiedReport = {
    report_id: "r-cov",
    pool_id: "p-cov",
    decision_id: "d-cov",
    sections: [
      {
        section_id: "sec_cov",
        section_title: `Coverage harness (${covered}/${total})`,
        verified_sentences: [
          {
            section_id: "sec_cov",
            sentence_text: "Coverage harness sentinel sentence.",
            provenance_tokens: ["[#ev:src-cov-0:0-20]"],
            verifier_pass: true,
            drop_reason: null,
            evaluator_agrees: true,
          },
        ],
        section_verify_pass_rate: 1.0,
        section_status: "verified",
      },
    ],
    overall_verify_pass_rate: 1.0,
    pipeline_verdict: "success",
    generator_model: "test/cov",
    evaluator_model: "strict_verify_v1",
    family_segregation_passed: true,
    frame_coverage: {
      covered_entity_count: covered,
      total_entity_count: total,
      gaps,
    },
    verifier_pass_threshold: 0.4,
    started_at_utc: ISO,
    finished_at_utc: ISO,
    latency_ms: 0,
    cost_usd: 0,
  };
  return (
    <div
      data-testid={`coverage-harness-${covered}-${gap_count}`}
      className="mx-auto max-w-4xl p-6"
    >
      <VerifiedReportView report={report} pool={pool} />
    </div>
  );
}
