# BEAT-BOTH master plan — CORRECTIONS layer (Codex iter-1 REQUEST_CHANGES + operator decision)

This amends `BEATBOTH_MASTER_PLAN.md`. Where this file and the plan disagree, THIS file wins. Codex verdict: `root_cause_sound: true`, `s13_violations: []`, `faithfulness_engine_relaxed_by: []` — the strategy is sound; these are factual/wiring corrections.

## OPERATOR DECISION (2026-07-01) — model-family policy
**STAY ALL-GLM.** Generator = judge = GLM-5.2; two-family self-bias safeguard OFF (`PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1`), DISCLOSED in the report + manifest (a §-1.3 disclosure, not a hidden relaxation). NOT kimi-k2.6, NOT two-family. Overrides the plan's WS-1 judge-swap.

## CORRECTED WORKSTREAMS

### WS-1 (REVISED) — GLM-5.2 D8 judge RELIABILITY (no model swap).
Keep GLM-5.2 as the judge. Kill the trickle/false-negative class via the NON-model mechanisms only:
- (a) enforce the verdict enum via OpenRouter `response_format`/`json_schema` (not the vLLM-only `structured_outputs.choice` at `judge_adapter.py:229-231`) so `JudgeEnumError` cannot fire off-vLLM;
- (b) bounded per-claim RETRY before the fail-closed degrade (`judge_adapter.py:284-298,311-325`) — a transient blank/429 re-asks, never convicts;
- (c) verdict IDEMPOTENCY cache keyed on `(normalized_claim, span-identity)` so a byte-twin inherits a clean sibling's verdict — this removes the 02-001/02-007 split (the 3 false-negatives);
- (d) raise the D8 seam wall for a slow GLM judge (per feedback_judge_model_provider) so the trickle does not tear the seam.
- Keep `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1` (all-GLM, operator-locked) and DISCLOSE the disabled two-family safeguard every run.
- Risk: still ADJACENT (touches the judge); safe-direction (a real UNSUPPORTED still holds; only transport-noise convictions removed). Depends hard on WS-0 (GPU un-degrade) since GLM tiering + judge share the trickle root.

### WS-2 (CORRECTED per Codex P1) — the slate does NOT contain all 4 winners.
`run_gate_b.py`'s `apply_full_capability_benchmark_slate()` sets/preflights `PG_CONSOLIDATION_NLI` + `PG_BREADTH_ENRICHMENT_ENABLED`, but **NOT `PG_CROSS_SOURCE_SYNTHESIS` and NOT `PG_DOCUMENT_TYPE_WEIGHT`** (confirmed: the re-smoke had to set `PG_CROSS_SOURCE_SYNTHESIS=1` by hand and M2 stayed OFF). WS-2 MUST: add `PG_CROSS_SOURCE_SYNTHESIS=1` to the slate + preflight-required-flags + a fail-loud firing assertion (`cross_source_analytical_units>0` when ≥2 same-anchor baskets exist); handle `PG_DOCUMENT_TYPE_WEIGHT` per WS-8 (ON only for the journal-only question class, via the scope template). The paid `run_honest_sweep_r3.py` path must apply the slate with a fail-loud "slate-OFF cannot launch" preflight.

### WS-10 (CLARIFIED per Codex P2) — Source-Necessity quarantine keeps sources.
The min-vertex-cover minimizes only the SCORED reference/citation list (the 12 cited). Non-necessary + zero-support sources STAY in the audit ledger (`corpus_credibility_disclosure`, explicitly typed as an audit ledger NOT a reference list) and the disclosed sidecar — never deleted (§-1.3). Point Uncited/Necessity at the 12-cited list, never the 88-corpus.

### WS-11 / WS-15 (HARDENED per Codex P2) — add abstain + cost bounds.
WS-11 debate router: explicit ABSTAIN/no-evidence behavior when only one span-grounded side exists (never fabricate a counter-side). WS-15 TTD-DR: hard bounded loop count + wall-clock + cost gate.

## CORRECTED BOARD FACTS (per Codex P2 + live-board checks)
- **B3 DeepScholar-Bench is NOT an open top slot** — the live leaderboard already lists OpenAI DeepResearch (guestrin-lab.github.io/deepscholar-leaderboard). Re-scope B3 to "beat the listed systems," refresh ranks before execution.
- **B5 DeepResearch-Bench v1** — the official evaluator switched to **GPT-5.5 (May 2026)**; Gemini-2.5-Pro RACE 48.88 is HISTORICAL. Refresh from github.com/Ayanami0730/deep_research_bench before targeting.
- **B2 DRB-II AI21-DeepResearch 64.38 #1 — CONFIRMED current** (agentresearchlab.com).
- **B1 DeepTRACE** — Salesforce AI Research (NOT Microsoft), ICLR 2026, v1 only; **NO public official scorer/leaderboard**.

## CORRECTED ACCEPTANCE (per Codex P1 — downgrade DeepTRACE proof)
DeepTRACE has no public scorer → our re-implementation ESTIMATES, it does not PROVE #1. Acceptance language for B1: "score ESTIMATED via our re-implemented scorer, CALIBRATED against the paper's published GPT-5-DR column, judge substitution DISCLOSED, human-validation Pearson published." Only B2 (`run_evaluation.py`, Gemini judge) is a true official-harness proof; B3/B4/B5 are submissions/subset-checks, not standalone #1 proofs — state this honestly.

## CORRECTED ROOT-CAUSE WORDING (per Codex P2)
"Winners MIXED partial-ON / GPU-degraded" — NOT "all winners OFF." In the drb_72 Gate-B smoke, `PG_CONSOLIDATION_NLI` + `PG_BREADTH_ENRICHMENT_ENABLED` WERE ON (via the Gate-B slate) but degraded under the GPU-OOM (consolidation→CPU-wall under-merge, W2→lexical, tiering→rules-floor); `PG_CROSS_SOURCE_SYNTHESIS` was ON only because set by hand; `PG_DOCUMENT_TYPE_WEIGHT` (M2) was OFF. The degrade, not a blanket OFF, is the root.

## HOUSEKEEPING (WS-16) — also fix BENCHMARKS_STUDY.md line 14 (Salesforce not Microsoft) + line 20 (Uncited = uncited/listed, lower-better).
