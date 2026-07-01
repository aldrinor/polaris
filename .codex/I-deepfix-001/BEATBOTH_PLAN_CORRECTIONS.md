# BEAT-BOTH master plan — CORRECTIONS layer (Codex iter-1 REQUEST_CHANGES + operator decision)

This amends `BEATBOTH_MASTER_PLAN.md`. Where this file and the plan disagree, THIS file wins. Codex verdict: `root_cause_sound: true`, `s13_violations: []`, `faithfulness_engine_relaxed_by: []` — the strategy is sound; these are factual/wiring corrections.

## OPERATOR DECISION (2026-07-01, SUPERSEDED same day)
An earlier AskUserQuestion answer said "all-GLM (GLM-5.2 gen + judge, PERMIT=1)". The operator CORRECTED this same day: **the D8 terminal judge stays moonshotai/kimi-k2.6** — chosen deliberately for its high OpenRouter provider count (21 providers) which prevents the 429 trickle that caused the D8 false-negatives (per feedback_judge_model_provider_availability_render_blocker_2026_06_30). The precise posture is **all-GLM EVERYWHERE EXCEPT the D8 terminal judge**:
- Generator = GLM-5.2. Mirror + side-checkers (entailment / semantic_conflict / credibility / span-quality) = GLM-5.2 too, by the operator-locked §9.1.8 side-judge→mirror mapping. External evaluator `PG_EVALUATOR_MODEL` = GLM-5.2 (the all-GLM / sovereignty-dropped campaign choice).
- **D8 terminal faithfulness judge = moonshotai/kimi-k2.6 (DISTINCT family).** This IS the meaningful two-family self-bias safeguard: every VERIFIED / UNSUPPORTED verdict is decided by a model that did NOT write the text. `assert_four_role_families_distinct()` passes: `{generator: z-ai, mirror: z-ai, sentinel: minimax, judge: moonshotai}`.
- **`PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY` stays = 1** — NOT 0. Setting 0 would ABORT the run, because `check_family_segregation` compares the GLM generator against the GLM external evaluator / GLM side-checkers (same family, the intended disclosed all-GLM surface). PERMIT=1 governs only that disclosed same-family side surface; it does NOT weaken the D8 terminal judge, which is kimi (cross-family). (My earlier "set PERMIT=0" note here was wrong; the Wave-A fix agent caught it and left PERMIT=1, correctly.)
- The kimi default in `openrouter_role_transport.py:211` is CORRECT — do NOT force it to GLM. (The drb_72 re-smoke ran with a GLM D8 judge, which is why its D8 trickled/gave false-negatives; kimi fixes that.)

## CORRECTED WORKSTREAMS

### WS-1 (REVISED) — kimi-k2.6 D8 judge RELIABILITY (keep the kimi judge; do NOT swap to GLM).
Keep moonshotai/kimi-k2.6 as the judge (stable provider count). Two-family AT THE D8 TERMINAL JUDGE (gen=GLM, D8 judge=kimi = distinct family = the meaningful self-bias safeguard, genuinely ON — see the OPERATOR DECISION block above). Kill the residual trickle/false-negative class via the NON-model mechanisms:
- (a) enforce the verdict enum via OpenRouter `response_format`/`json_schema` (not the vLLM-only `structured_outputs.choice` at `judge_adapter.py:229-231`) so `JudgeEnumError` cannot fire off-vLLM;
- (b) bounded per-claim RETRY before the fail-closed degrade (`judge_adapter.py:284-298,311-325`) — a transient blank/429 re-asks, never convicts;
- (c) verdict IDEMPOTENCY cache keyed on `(normalized_claim, span-identity)` so a byte-twin inherits a clean sibling's verdict — this removes the 02-001/02-007 split (the 3 false-negatives);
- (d) raise the D8 seam wall for a slow GLM judge (per feedback_judge_model_provider) so the trickle does not tear the seam.
- Keep `PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1`. This governs ONLY the disclosed all-GLM SIDE surface (GLM generator vs the GLM external-evaluator + GLM side-checkers, per the §9.1.8 side-judge→mirror lock). It does NOT touch the D8 terminal judge, which is kimi (cross-family). Setting it to 0 would ABORT the run at `check_family_segregation`. Disclose the all-GLM side surface every run.
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
