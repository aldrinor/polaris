"use client";

import { VerifiedReportView } from "@/app/generation/components/verified_report_view";
import type { EvidencePool, RetrievalSource, VerifiedReport } from "@/lib/api";

const ISO = new Date().toISOString();

// I-f5-007: keep the "normal" demo source ALWAYS fresh so the stale badge
// only renders for sources we explicitly mark stale. Pin to ~30 days ago.
const FRESH_DATE = new Date(Date.now() - 30 * 24 * 3600 * 1000)
  .toISOString()
  .slice(0, 10);
// Pin the stale demo source to 3 years ago — well past the 730-day cutoff.
const STALE_DATE = new Date(Date.now() - 3 * 365 * 24 * 3600 * 1000)
  .toISOString()
  .slice(0, 10);

const SOURCE_FULL_TEXT_5 =
  "The randomized trial enrolled 1247 adults with chronic migraines and demonstrated significant aspirin headache reduction at outcomes assessment.";

function _src(i: number): RetrievalSource {
  return {
    source_id: `src-${i}`,
    url: `https://www.cochrane.org/CD-${i}`,
    domain: "cochrane.org",
    tier: "T1",
    title: `Cochrane review ${i}`,
    publication_date: FRESH_DATE,
    authors: ["Smith J", "Doe R", "Patel K"],
    snippet: SOURCE_FULL_TEXT_5.slice(0, 80),
    full_text_available: true,
    full_text: SOURCE_FULL_TEXT_5,
    fetched_at_utc: ISO,
    provenance: {},
  };
}

const SRC_RETRACTED: RetrievalSource = {
  source_id: "src-retracted",
  url: "https://www.cochrane.org/CD-retracted",
  domain: "cochrane.org",
  tier: "T1",
  title: "Cochrane review (retracted)",
  publication_date: FRESH_DATE,
  authors: ["Doe R"],
  snippet: SOURCE_FULL_TEXT_5.slice(0, 80),
  full_text_available: true,
  full_text: SOURCE_FULL_TEXT_5,
  fetched_at_utc: ISO,
  provenance: {},
  retracted: true,
};

const SRC_PAYWALLED: RetrievalSource = {
  source_id: "src-paywalled",
  url: "https://nejm.org/paywalled/abc",
  domain: "nejm.org",
  tier: "T1",
  title: "Paywalled NEJM article",
  publication_date: FRESH_DATE,
  authors: ["Jones B"],
  snippet: "Abstract excerpt only — full text behind paywall.",
  full_text_available: false,
  full_text: null,
  fetched_at_utc: ISO,
  provenance: {},
};

const SRC_STALE: RetrievalSource = {
  source_id: "src-stale",
  url: "https://www.cochrane.org/CD-stale",
  domain: "cochrane.org",
  tier: "T1",
  title: "Cochrane review (3y old)",
  publication_date: STALE_DATE,
  authors: ["Patel K"],
  snippet: SOURCE_FULL_TEXT_5.slice(0, 80),
  full_text_available: true,
  full_text: SOURCE_FULL_TEXT_5,
  fetched_at_utc: ISO,
  provenance: {},
};

const POOL: EvidencePool = {
  pool_id: "p-hover",
  decision_id: "d-hover",
  sources: [
    ...Array.from({ length: 10 }, (_, i) => _src(i)),
    SRC_RETRACTED,
    SRC_STALE,
    SRC_PAYWALLED,
  ],
  adequacy: {
    is_adequate: true,
    sources_per_tier: { T1: 13, T2: 0, T3: 0 },
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
        // sec_x:16 — retracted source (I-f5-007).
        {
          section_id: "sec_x",
          sentence_text: "Retracted-source demo sentence.",
          provenance_tokens: [`[#ev:src-retracted:0-30]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:17 — stale source >2y (I-f5-007).
        {
          section_id: "sec_x",
          sentence_text: "Stale-source demo sentence.",
          provenance_tokens: [`[#ev:src-stale:0-30]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:18..22 — non-prose assertion surfaces (I-f5-009).
        ...(
          [
            "table",
            "summary_bullet",
            "limitation",
            "caption",
            "heading",
          ] as const
        ).map((surface, k) => ({
          section_id: "sec_x",
          sentence_text: `${surface} assertion demo sentence.`,
          provenance_tokens: [`[#ev:src-${k}:0-20]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
          assertion_surface: surface,
        })),
        // sec_x:23 — paywalled source (I-f5-010 case 1).
        {
          section_id: "sec_x",
          sentence_text: "Paywalled-source demo sentence cites NEJM.",
          provenance_tokens: [`[#ev:src-paywalled:0-20]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:24 — multi-span with one out-of-range (I-f5-010 case 2).
        {
          section_id: "sec_x",
          sentence_text: "Multi-span with bad span demo sentence.",
          provenance_tokens: [
            `[#ev:src-0:0-30]`,
            `[#ev:src-0:5000-5050]`,
          ],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:25 — T1-vs-T1 conflict heuristic (I-f5-010 case 3).
        {
          section_id: "sec_x",
          sentence_text: "T1-conflict heuristic demo cites two T1 sources.",
          provenance_tokens: [`[#ev:src-0:0-20]`, `[#ev:src-1:0-20]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
        },
        // sec_x:26 — contradiction signal (I-f8-001/I-f8-002).
        {
          section_id: "sec_x",
          sentence_text: "Contradiction demo: ≥2 sources disagree on dose.",
          provenance_tokens: [
            `[#ev:src-0:0-20]`,
            `[#ev:src-1:0-20]`,
            `[#ev:src-2:0-20]`,
          ],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
          contradiction: {
            kind: "multi_source",
            disagreeing_source_count: 3,
            summary: "Three Cochrane reviews disagree on dose-response curve",
            sides: [
              {
                source_id: "src-0",
                source_tier: "T1",
                sample_size: 1247,
                hedge_language: "high confidence",
                pt08_flag: "PT04",
                claim_excerpt:
                  "Aspirin significantly reduces headache at 81mg dose.",
              },
              {
                source_id: "src-1",
                source_tier: "T2",
                sample_size: 432,
                hedge_language: "moderate confidence",
                pt08_flag: null,
                claim_excerpt:
                  "Aspirin shows mixed results below 162mg threshold.",
              },
              {
                source_id: "src-2",
                source_tier: "T1",
                sample_size: 2103,
                hedge_language: "high confidence",
                pt08_flag: "PT08",
                claim_excerpt:
                  "Aspirin demonstrates dose-response saturation above 325mg.",
              },
            ],
          },
        },
        // sec_x:27 — self-contradiction (I-f8-003).
        {
          section_id: "sec_x",
          sentence_text: "Self-contradiction demo: same source on both sides.",
          provenance_tokens: [`[#ev:src-0:0-20]`],
          verifier_pass: true,
          drop_reason: null,
          evaluator_agrees: true,
          contradiction: {
            kind: "self_contradiction",
            disagreeing_source_count: 1,
            summary: "Single source contradicts itself across two paragraphs",
            sides: [
              {
                source_id: "src-0",
                source_tier: "T1",
                sample_size: 1247,
                hedge_language: "high confidence",
                pt08_flag: null,
                claim_excerpt: "Aspirin is safe at chronic doses.",
              },
              {
                source_id: "src-0",
                source_tier: "T1",
                sample_size: 1247,
                hedge_language: "high confidence",
                pt08_flag: null,
                claim_excerpt:
                  "Aspirin is dangerous beyond 8 weeks of chronic use.",
              },
            ],
          },
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
  frame_coverage: {
    covered_entity_count: 14,
    total_entity_count: 15,
    gaps: [
      {
        entity_name: "Pediatric population",
        reason: "no_oa",
        reason_detail: "no open-access version of Cochrane review",
      },
    ],
  },
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
