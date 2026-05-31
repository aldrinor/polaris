# Codex selection task — THE best open-weight OpenRouter model per POLARIS role (quantitative)

You are the SELECTION ANALYST + §-1.1 verifier. The operator demands a SERIOUS, benchmark-grounded CLEAR CHOICE of
THE single best model for each POLARIS role, with QUANTITATIVE evidence. A Claude workflow gathered live evidence but
hit a weekly limit before synthesizing — the captured fetched data is in `.codex/I-meta-002-roleselect/captured_evidence.md`
(READ IT) and the prior SOTA rationale is in `docs/archive/2026_05_28_pre_4role_lock/polaris_per_role_sota_2026_05_27.md`.
You have live web — VERIFY/refresh every number and price yourself (OpenRouter catalog + leaderboards). Produce the
final selection. This is the §8.3.1 cycle; emit the result, no iteration games.

## THE MANDATE
The 4-role architecture lock is OPEN for re-selection. For EACH role pick THE single best model by MERIT on the
benchmark that measures THAT role's function — not legacy, not default.

## HARD GATES (every pick must satisfy all)
1. OPEN-WEIGHT (downloadable; proof must self-host the IDENTICAL model sovereignly later).
2. AVAILABLE ON OPENROUTER NOW (verify slug + live price). EXCEPTION: Sentinel — if no OpenRouter model does
   RAG-faithfulness adequately, the honest pick may be "self-host the real specialist," but PROVE it with the benchmark gap.
3. SELF-HOSTABLE-LATER under a COMMERCIAL license (Apache-2.0 / MIT / Llama-community-OK). CC-BY-NC DISQUALIFIES.
4. NO closed-source families (openai/anthropic/google-closed).
5. Final 4 roles = 4 DISTINCT model families.

## ROLES + relevant benchmark
- WRITER: recall-heavy clinical synthesis, long ctx. Current deepseek/deepseek-v4-pro (MIT, OpenRouter). Confirm or beat.
- MIRROR: calibration auditor + citation grounding + entailment. Bench: calibration (AA-Omniscience/ECE), Vectara HHEM
  hallucination %, LLM-AggreFact BAcc, attribution. Current cohere/command-a-plus NOT on OpenRouter → must re-pick.
- SENTINEL (LETHAL): RAG-faithfulness detection. Bench: RAGTruth BAcc (bar = Granite Guardian 4.1 8B 0.834/0.841),
  LLM-AggreFact/MiniCheck, HaluEval, FELM, clinical MedHallu/MedNLI/BioNLI. Current granite-guardian NOT on OpenRouter.
- JUDGE: structured 5-enum arbiter. Bench: BFCL (function-calling), IFEval, JSON-schema adherence, MedHallu F1.
  Current qwen/qwen3.6-35b-a3b (Apache, OpenRouter). Confirm or beat.

## OUTPUT (emit in this order)
```yaml
verdict: SELECTION_COMPLETE
writer:   {model, slug, family, license, price_in_out, key_benchmark_number+source, vs_runner_up}
mirror:   {model, slug, family, license, price_in_out, key_benchmark_number+source, margin_over_runner_up}
sentinel: {decision: openrouter_model | self_host_specialist, model, slug_or_host, family, license, benchmark_BAcc+source, gap_vs_best_alternative}
judge:    {model, slug, family, license, price_in_out, key_benchmark_number+source, margin_over_runner_up}
four_families_distinct: <true|false + the 4 families>
family_clash_resolution: "<if best-per-role collide, which role took 2nd-best + the point cost>"
total_cost_per_run_usd: <number, ~330 claims, Mirror 2-pass + Sentinel 1x + Judge 1x>
changes_vs_current_lock: ["..."]
```
Then a 6-line plain-English summary for a BLIND operator: the 4 picks by name, the ONE benchmark number per pick,
the Sentinel call, the cost, and whether this lineup is a fair preview of the sovereign system.

## RULES
Every model/score/price/license cites a live URL (verify, don't trust the captured fragments blindly — they may be
partial). Open-weight only. Pick by merit on the role-relevant benchmark. If a captured number is unverifiable live,
flag it and use your own verified number. The Sentinel false-negative is lethal — be most rigorous there.
