"use client";

import { VerifiedReportView } from "@/app/generation/components/verified_report_view";
import type { VerifiedReport } from "@/lib/api";

const ISO = new Date().toISOString();

const REPORT: VerifiedReport = {
  report_id: "r-hover-test",
  pool_id: "p-hover",
  decision_id: "d-hover",
  sections: [
    {
      section_id: "sec_x",
      section_title: "Test section",
      verified_sentences: Array.from({ length: 10 }, (_, i) => ({
        section_id: "sec_x",
        sentence_text: `Test sentence ${i} about aspirin.`,
        provenance_tokens: [`[#ev:src-${i}:0-3]`],
        verifier_pass: true,
        drop_reason: null,
      })),
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
      <VerifiedReportView report={REPORT} />
    </div>
  );
}
