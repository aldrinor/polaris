#!/bin/bash
set -e

REPO="aldrinor/polaris"

create_issue() {
  local title="$1"
  local body="$2"
  local label="${3:-type-bug}"
  gh issue create --repo "$REPO" --title "$title" --label "bug" --body "$body"
}

# Outstanding follow-ups (open and keep open)
create_issue "I-bug-093 — Warn-mode demo run on entailment judge" \
  "Run a demo sweep with PG_PROVENANCE_ENTAILMENT_MODE=warn to confirm entailment-judge behavior is observable and metrics flow before production enforcement. Acceptance: outputs/I-bug-093_warn/ shows judge metrics, no aborts, recovery rate logged."

create_issue "I-bug-099 — Extract entailment-judge helpers to shared module" \
  "Currently entailment-judge logic is split between strict_verify.py and provenance_generator.py. Extract shared LLM-prompt + parse helpers into src/polaris_graph/generator/entailment_judge.py. Acceptance: single import path, unit tests, no behavior change."

create_issue "I-bug-100 — Route entailment-judge calls through OpenRouterClient for cost tracking" \
  "Currently entailment judge uses raw httpx; bypasses cost-ledger and family-segregation guards. Route through openrouter_client. Acceptance: cost tracked in pg_cost_ledger.jsonl, family-segregation enforced, unit tests."

create_issue "I-bug-101 — Distributional false-positive audit on entailment judge" \
  "Run entailment judge on 200 known-good sentences (already strict_verify-passing) to measure false-NULL_DROP rate. Acceptance: outputs/I-bug-101_audit/distribution.json with per-sentence verdict + false-positive rate. If FPR > 5%, escalate as urgent."

create_issue "I-bug-102 — Off-mode should skip generator2 import" \
  "When PG_PROVENANCE_ENTAILMENT_MODE=off, generator2 module is still imported (top-level imports load entailment helpers). Refactor to lazy-import. Acceptance: off-mode has zero entailment-judge code-path execution, unit test asserts."

create_issue "I-bug-103 — Retrieval expansion experiment (FAILED — document for archive)" \
  "Hypothesis: expanding retrieval from K=20 to K=60 would improve coverage. Empirical result: full sweep showed no recovery improvement; wasted sweep budget. Acceptance: capture the negative result in docs/experiments/i_bug_103_failed.md and close with no code change."

create_issue "I-bug-104 — Prompt rewrite experiment (FAILED — document for archive)" \
  "Hypothesis: 100-line prompt rewrite emphasizing per-decimal extraction would improve verified-rate. Empirical result: catastrophic regression (verified-rate dropped 15pp). Reverted. Acceptance: capture in docs/experiments/i_bug_104_failed.md and close."

create_issue "I-bug-106 — Synthesis subheadings should be ### not ##" \
  "Analyst Synthesis section emits ## subheadings which conflict with main section headers. Should be ### per markdown hierarchy. Acceptance: synthesis prompt updated, regression test asserts no ## in synthesis output."

create_issue "I-bug-107 — Multi-run BEAT-BOTH average instead of single-run" \
  "Single BEAT-BOTH run has high variance (sweep-to-sweep recovery rates differ ±5pp). Average 3 runs and report mean ± stddev. Acceptance: scripts/run_beat_both.py supports --n-runs, manifest aggregates."

create_issue "I-bug-109 — Synthesis [N] hallucination root-cause investigation" \
  "Synthesis LLM emitted [18] [19] when bibliography size = 17. Runtime scrub guardrail (PR #351) handles symptom; root cause unknown. Investigate: prompt format, bibliography rendering, LLM tokenizer. Acceptance: docs/investigation/i_bug_109_root_cause.md with finding + fix recommendation."

create_issue "I-bug-110 — Synthesis [N] scrub telemetry counters" \
  "Add metrics.synthesis_n_scrub_count and metrics.synthesis_n_scrub_per_run to track scrub frequency. Acceptance: counter in manifest, regression test."

create_issue "I-bug-111 — Alert if synthesis [N] scrub count > 5 in single run" \
  "If synthesis hallucinates >5 [N] markers in a single run, log WARNING and tag manifest. Indicates synthesis prompt/bibliography degeneration. Acceptance: WARN log, manifest.synthesis_n_scrub_alert flag."

create_issue "I-tests-001 — 10 pre-existing failing tests triage" \
  "tests/polaris_graph/ has 10 pre-existing failing tests (predate this session). Triage: real bugs vs stale tests vs flaky. Acceptance: docs/tests/i_tests_001_triage.md with per-test classification + per-class fix plan."

create_issue "I-bakeoff-A-001 — Path A bakeoff (Qwen 3.5 Plus / Opus 4.7 / GPT-5)" \
  "Codex strategic review path A: bake off generator candidates against current DeepSeek V3.2-Exp on the 5-question Carney goldset. Score by line-by-line audit (PRISMA 2020, AMSTAR-2, GRADE per claim — NOT metadata). Acceptance: outputs/bakeoff_A/{model}/audit.md with per-claim verdicts, recommendation."

create_issue "I-decompose-001 — Path G multi-question decomposition" \
  "Codex strategic review path G: decompose Carney complex questions into N sub-questions, run each through pipeline, synthesize cross-question. Acceptance: src/polaris_graph/decomposer.py + integration test on 'tirzepatide vs semaglutide T2DM' (decomposes to efficacy / safety / cost / availability)."

# Retroactive issues for shipped PRs this session (§3.0 hygiene)
create_issue "I-bug-092 — Entailment judge (6th strict_verify check) [SHIPPED]" \
  "Closed by PR #343. Add LLM-as-judge entailment as the 6th strict_verify check. Two-family judge (Gemma 4 31B), confidence threshold, NULL_DROP fallback."

create_issue "I-bug-094 — Live OpenRouter canary on entailment judge [SHIPPED]" \
  "Closed by PR #347. 4/4 PASS canary against live OpenRouter to confirm entailment judge behavior end-to-end."

create_issue "I-bug-095 — Default PG_PROVENANCE_ENTAILMENT_MODE flipped to enforce [SHIPPED]" \
  "Closed by PR #348. After warn-mode soak, default flipped from warn to enforce for production protection."

create_issue "I-bug-096 — Entailment-judge telemetry counters [SHIPPED]" \
  "Closed by PR #346. Counters: entailment_judge_invocations, entailment_judge_drops, entailment_judge_pass."

create_issue "I-bug-097 — Entailment-judge skip on typo warning [SHIPPED]" \
  "Closed by PR #345. When sentence has typo warning from upstream, skip entailment to avoid false NULL_DROP."

create_issue "I-bug-098 — Production verifier wired with entailment judge [SHIPPED]" \
  "Closed by PR #349. Production generator/provenance_generator.py was NOT wired with entailment until this fix. Latent gap caught by user pushback."

create_issue "I-bug-105 — Two-layer report contract (verified core + analyst synthesis) [SHIPPED]" \
  "Closed by PR #350. Verified core with [#ev:...] tokens + analyst synthesis with [N] markers, hedged. Per Codex strategic review path D."

create_issue "I-bug-108 — Sentence repair loop + synthesis [N] scrub [SHIPPED]" \
  "Closed by PR #351. Verifier-driven sentence repair loop (35.3% recovery rate) + runtime scrub guardrail for invalid synthesis [N] markers. Codex iter-2 APPROVE."

create_issue "I-cj-008 — Crown Jewel binding test [SHIPPED]" \
  "Closed by PR #344. End-to-end binding test: scope discovery to BPEI to retrieval to adequacy gate to generator to strict_verify to bundle export." \
  "type-bug"

echo "Done creating issues"
