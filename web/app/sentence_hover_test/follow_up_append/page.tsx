"use client";

import { FollowUpAppendView } from "@/app/generation/components/follow_up_append_view";
import type { VerifiedReport } from "@/lib/api";

const ISO = "2026-05-08T00:00:00Z";

function _report(report_id: string, sentence_text: string): VerifiedReport {
  return {
    report_id,
    pool_id: `p-${report_id}`,
    decision_id: `d-${report_id}`,
    sections: [
      {
        section_id: "sec_a",
        section_title: "Demo section",
        verified_sentences: [
          {
            section_id: "sec_a",
            sentence_text,
            provenance_tokens: ["[#ev:src-1:0-30]"],
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
}

const ORIGINAL = _report("r-original", "Original report sentence about CMHC.");
const APPENDED = _report(
  "r-appended",
  "Follow-up sentence elaborating on Q4 housing-starts.",
);

export default function FollowUpAppendPage() {
  return (
    <main className="bg-background text-foreground mx-auto max-w-3xl px-6 py-8">
      <h1 className="text-2xl font-semibold tracking-tight">
        Follow-up append fixture (I-f11-002)
      </h1>
      <div className="mt-4">
        <FollowUpAppendView original={ORIGINAL} appended={APPENDED} />
      </div>
    </main>
  );
}
