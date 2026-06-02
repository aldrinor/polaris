# Codex gate — final 4-role open-weight OpenRouter selection: numbers real, picks sound?

ADVERSARIAL §-1.1 auditor. A workflow produced the per-role model selection below (full doc
outputs/I-meta-002/role_selection_final.md — READ IT). It claims live-verified benchmarks + prices and a Mirror
RE-PICK (Cohere→GLM-5.1). Re-verify via WebFetch — sub-agents may have erred (one already had a wrong Gemma
calibration number). Rule whether the picks are merit-correct, the numbers real, and the proxy-caveat honest. iter 1.

```yaml
verdict: SOUND | NEEDS_CORRECTION
price_or_availability_errors: [...]
benchmark_errors: [...]              # esp. proxy/sibling numbers presented as the model's own
wrong_picks: [...]
family_distinct_valid: <true|false>  # deepseek / z-ai(glm) / ibm-granite / qwen all distinct + open-weight?
license_errors: [...]                # GLM-5.1 MIT? Qwen3.6-35b-a3b Apache? granite-guardian Apache? deepseek-v4-pro MIT?
sentinel_gap_honest: <true|false>    # is "self-host Granite 0.841 vs ~0.73-0.775 OR-general = +6.5-11 BAcc" fair?
the_one_correction: "<or none>"
honest_one_line: "<for the operator>"
```

## The selection to verify
- WRITER (keep): deepseek/deepseek-v4-pro, MIT, $0.435/$0.87. GDPval-AA 1558 Elo #1 open-weight, +23 over GLM-5.1.
- MIRROR (RE-PICK Cohere→GLM-5.1): z-ai/glm-5.1, MIT, $0.98/$3.08. AA-Omniscience 29.4% hallucination = best calibration
  in eligible OpenRouter pool; −9.9pts vs Kimi K2.6 (39.3%). (Cohere command-a-plus NOT on OpenRouter → hard-gate fail.)
- SENTINEL (keep, self-host): ibm-granite/granite-guardian-4.1-8b (NOT on OpenRouter), Apache 2.0. RAGTruth BAcc
  0.841 think / 0.834 non-think; best OR general LLM ~0.73-0.775 → gap +6.5-11 BAcc pts → self-host justified.
- JUDGE (keep): qwen/qwen3.6-35b-a3b, Apache 2.0, $0.14/$1.00. BFCL V4: Qwen owns all 9 board slots; 35B-A3B = 0.673.
- Families: deepseek / z-ai / ibm-granite / qwen = 4 distinct. Per-run API ≈ $0.12, golden-5 ≈ $0.62.
- HONEST GAP the workflow flagged: GLM-5.1 / Qwen3.6 / DeepSeek-V4 not independently benchmarked AS faithfulness
  judges; some Judge/Mirror numbers rest on same-family SIBLING proxies (Qwen3.5-35B-A3B BFCL 0.673; GLM-5 base for
  Vectara). VERIFY whether any headline number is a proxy presented as the model's own, and flag it.

## The decisive checks
1. Live prices + OpenRouter availability for z-ai/glm-5.1, qwen/qwen3.6-35b-a3b, deepseek/deepseek-v4-pro.
2. LICENSES: GLM-5.1 actually MIT? (Z.ai GLM models have varied licenses — verify.) granite-guardian-4.1-8b Apache?
3. Is GLM-5.1's 29.4% AA-Omniscience a REAL GLM-5.1 number or a GLM-5-base proxy? Is Qwen 0.673 BFCL the actual
   qwen3.6-35b-a3b or a qwen3.5 sibling? Flag any proxy.
4. Is the Sentinel +6.5-11 BAcc gap defensible, and is self-hosting the real specialist the right call for the lethal role?
5. Family-distinctness + open-weight + commercial-self-host all hold?
6. Is the Mirror re-pick to GLM-5.1 merit-correct, or is there a better-calibrated eligible open-weight OpenRouter model?

## Your ruling
SOUND or NEEDS_CORRECTION. Re-verify each load-bearing number/price/license live. Flag proxy numbers. The single
most important correction. Honest one-liner. (Mirror final pick is operator-locked — verify facts, don't decide it.)
