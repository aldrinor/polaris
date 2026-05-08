"use client";

import { VerifiedReportView } from "@/app/generation/components/verified_report_view";
import type { VerifiedReport } from "@/lib/api";

const ISO = "2026-05-08T00:00:00Z";

const MEMORY_REPORT: VerifiedReport = {
  report_id: "r-memory-cite",
  pool_id: "p-memory",
  decision_id: "d-memory",
  sections: [
    {
      section_id: "sec_m",
      section_title: "Cited recall demo",
      verified_sentences: [
        {
          section_id: "sec_m",
          sentence_text:
            "Prior workspace research found tirzepatide outperforms semaglutide on weight reduction.",
          provenance_tokens: ["[#ev:ev_memory_abc123def456:0-90]"],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        {
          section_id: "sec_m",
          sentence_text:
            "A separate trial corroborated the cardiovascular outcome reduction.",
          provenance_tokens: ["[#ev:src-1:0-60]"],
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
  generator_model: "demo-generator",
  evaluator_model: "demo-evaluator",
  family_segregation_passed: true,
  verifier_pass_threshold: 0.4,
  started_at_utc: ISO,
  finished_at_utc: ISO,
  latency_ms: 0,
  cost_usd: 0,
};

export default function MemoryCitePage() {
  return (
    <main className="bg-background text-foreground mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        Cited recall fixture (I-f14-005)
      </h1>
      <div className="mt-4">
        <VerifiedReportView report={MEMORY_REPORT} />
      </div>
    </main>
  );
}
