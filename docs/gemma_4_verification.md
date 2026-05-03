# POLARIS v6.2 — Gemma 4 31B Dense Verification

**Last updated:** 2026-05-01
**Owning task:** Phase 0 Task 0.8
**Plan reference:** `docs/carney_delivery_plan_v6_2.md`

This document verifies Gemma 4 31B Dense as POLARIS's Global Verifier model, fixes the license scan (with material correction vs v6.2 plan), and locks the vLLM serving recipe.

---

## 1. Material correction vs v6.2 plan

**v6.2 plan stated:** "Gemma 4 31B Dense (Apache 2.0)"

**ACTUAL** (verified at https://ai.google.dev/gemma/docs/gemma_4_license on 2026-05-01):
- Apache 2.0 license text (clean Apache 2.0 body)
- **PLUS three layered Google policies**:
  1. Gemma Prohibited Use Policy (`/gemma/prohibited_use_policy`)
  2. Gemma Intended Use Statement (`/gemma/intended_use_statement`)
  3. Gemma Terms of Use (`/gemma/terms`)

This is **not** "vanilla open-source" — it is "Apache 2.0 + Google use restrictions". The substrate audit and v6.2 plan understated the constraint.

**Severity assessment for Carney delivery:** LOW.

The Prohibited Use Policy excludes:
1. IP infringement
2. Illegal/dangerous activities (CSAM, terrorism, illegal substances)
3. Unlicensed professional practice (legal, medical, accounting, financial)
4. Service disruption (spam, fraud)
5. Safety filter circumvention
6. Harmful content (hate, harassment, violence, self-harm)
7. **Misinformation: "Generate and distribute content intended to misinform, misrepresent or mislead"**
8. Sexual / pornographic content

**No prohibition on:**
- Government / sovereign deployment
- Gift to a head of state
- Weight redistribution (running on OVH Canada sovereign cluster is permitted)
- Derivative model creation

**Action items from policy:**
- A. Misinformation clause aligns with POLARIS sycophancy + refusal CI suite (Phase 1 Task 1.7) — POLARIS already explicitly tests against generating misleading content. **No new work.**
- B. Unlicensed-professional-practice clause: POLARIS clinical template generates evidence-graded synthesis (research output, not diagnosis/treatment). Phase 1/2 legal review (already in `docs/blockers.md` §5) must add an opinion: "is research synthesis 'practice of medicine'?" — likely no, but document the opinion.
- C. Add a footer disclosure to Carney handover package (Phase 5 task 5.3) noting Gemma 4 use policy attached.

---

## 2. Model verification

| Field | Verified value | Source |
|---|---|---|
| Total parameters | 30.7B | https://huggingface.co/google/gemma-4-31B |
| Architecture | Dense (not MoE) | HF model card |
| Layers | 60 | HF model card |
| Vocabulary | 262K | HF model card |
| Context length | 256K tokens | HF model card |
| Multimodal | Text + Image (not audio on 31B) | HF model card |
| Vision encoder | ~550M params | HF model card |
| Sliding window | 1024 tokens | HF model card |
| Pre-trained variant | `google/gemma-4-31B` | HF |
| Instruction-tuned | `google/gemma-4-31B-it` | HF |
| NVIDIA NVFP4 quantized | `nvidia/Gemma-4-31B-IT-NVFP4` | HF |

---

## 3. vLLM serving recipe (verified)

Per official [vLLM Gemma 4 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html):

### 3.1 Build-phase (Vast.ai US 4× H100, FP16)

```bash
vllm serve google/gemma-4-31B-it \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90
```

Memory footprint: ~62GB FP16 weights + KV cache headroom on 2× H100 = workable. Use 2 of 4 H100s for verifier; remaining 2 for DeepSeek V4 Flash generator (per Path C default).

### 3.2 Phase 4 sovereign (OVH Canada BHS H200, NVFP4 quantized)

```bash
vllm serve nvidia/Gemma-4-31B-IT-NVFP4 \
  --tensor-parallel-size 2 \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.85
```

NVFP4 reduces weights to ~16GB; doubles effective context-window headroom on H200.

### 3.3 Two-family segregation invariant cross-check

Per CLAUDE.md §9.1 invariant 1: generator and evaluator MUST be from different lineages. `openrouter_client.check_family_segregation` raises `RuntimeError` at construction if violated.

| Slot | Model | Lineage | Lineage hash |
|---|---|---|---|
| Generator | DeepSeek V4 Pro / Flash | DeepSeek | `lineage_deepseek_v4` |
| Global Verifier | Gemma 4 31B Dense | Google | `lineage_google_gemma_4` |

These are distinct lineages → segregation invariant **PASSES**.

---

## 4. Performance baseline (Phase 0 Task 0.7 will measure)

Expected from public benchmarks on similar 30B-class models:
- Throughput: ~80-120 tokens/sec at 32K context, batch 1, 2× H100 FP16
- Latency-to-first-token: <500ms
- KV cache: 4-bit-quantized cache for 256K context fits in H100 with quantized KV (vLLM `--kv-cache-dtype fp8`)

Phase 0 Task 0.7 (SGLang vs vLLM bakeoff) will measure actual numbers and freeze the engine choice.

### 4.1 Benchmark table excerpt (Google official, instruction-tuned 31B Dense)

Per Google's Gemma 4 model card (https://ai.google.dev/gemma/docs/core/model_card_4) — values quoted directly from the official table for the 31B Dense instruction-tuned variant:

| Benchmark | Gemma 4 31B-it (Google reported) | Source |
|---|---|---|
| **GPQA Diamond** (graduate-level reasoning) | **84.3%** | Google model card |
| **AIME 2026 no tools** (math olympiad) | **89.2%** | Google model card |
| **MMLU Pro** | **85.2%** | Google model card |
| **LiveCodeBench v6** | **80.0%** | Google model card |
| **BigBench Extra Hard** | **74.4%** | Google model card |
| **Codeforces ELO** | **2150** | Google model card |
| **Tau2** (avg over 3) | **76.9%** | Google model card |
| **HLE no tools** | **19.5%** | Google model card |
| **HLE with search** | **26.5%** | Google model card |

Note: Google labels the AIME benchmark "AIME 2026 no tools" on the card. Whether this is a forward-looking notation or a documentation-date issue is Google's call; values are quoted verbatim. The model card does NOT report a traditional "HumanEval" metric (Google's coding measure for Gemma 4 is LiveCodeBench v6 + Codeforces ELO instead).

These figures are strong for an open-weights 31B model and are more than sufficient for the Global Verifier role per Plan v13 §F architecture: the verifier detects grounding failures, hedging gaps, and family-disagreement. Gemma 4 31B is selected for verifier specifically because it is a *different lineage* from DeepSeek V4 (preserves the two-family segregation invariant) — quality at this level is a bonus, not the selection criterion.

### 4.2 Named fallback: Llama 4 Scout 109B (MoE)

If Gemma 4 31B verification fails (e.g. discovered behavioral pathology, license-policy reinterpretation, or Phase 4 NVFP4 serving issues): **Llama 4 Scout 109B-MoE** is the canonical fallback per `docs/task_acceptance_matrix.yaml task_0_8.green_criteria`.

| Property | Llama 4 Scout 109B | Source |
|---|---|---|
| Architecture | 109B parameters Mixture-of-Experts | Meta model card |
| Active parameters | ~17B (MoE routing) | Meta model card |
| License | Llama 4 Community License | Meta |
| Lineage | Meta (distinct from DeepSeek + Google) | preserves two-family invariant |
| Serving | vLLM + SGLang both support Llama 4 MoE | published recipes |

Triggering the fallback requires user-signed canonical reconciliation per Plan v13 §F (no SILENT fallback). The fallback path is documented here so that, if invoked, the substitute model has been pre-vetted at the same proof-level as Gemma 4 (license, benchmarks, lineage segregation).

### 4.3 vLLM/SGLang serving-recipe verification — Phase-4-deferred (explicit)

**Per `docs/blockers.md §3` API-first sequencing user-signed canonical reconciliation 2026-05-02:** physical bare-metal verification of the vLLM/SGLang serving recipe (§3.1 + §3.2 above) is **deferred to Phase 4 entry (~2026-08-10)** when the OVH BHS H200 cluster goes live. The recipe is documented here for traceability + planning, NOT executed in Phase 0.

Phase 0–3 POLARIS validation runs against API endpoints (OpenRouter/DeepSeek API). The recipe is exercised only when the sovereign cluster is operational. This is **NOT a silent fallback** — it is the canonical API-first sequencing per blockers.md §3.

---

## 5. Acceptance criteria for Task 0.8 GREEN

Per `docs/task_acceptance_matrix.yaml` task_0_8:

- [x] Model card verified (30.7B params, Dense, 256K ctx, multimodal text+image)
- [x] License scan completed with material correction surfaced (Apache 2.0 + Gemma policies)
- [x] Use-policy compatibility assessed: LOW severity for Carney delivery
- [x] Two-family segregation cross-check: PASSES (Google vs DeepSeek lineages)
- [x] vLLM serving recipe locked for build-phase (FP16) + sovereign (NVFP4)
- [ ] Smoke test on Vast.ai cluster (deferred to Task 0.3 + 0.7 once cluster live)
- [ ] Legal opinion added to docs/blockers.md §5 re: research synthesis ≠ practice of medicine

**Codex review brief:** `.codex/task_0_8_review_brief.md` (next step)

**Plan amendment required:** Update `docs/carney_delivery_plan_v6_2.md` to replace "Apache 2.0" Gemma 4 references with "Apache 2.0 + Gemma Use Policy (LOW severity for our scope)".

## Sources

- [Gemma 4 model card (Google AI)](https://ai.google.dev/gemma/docs/core/model_card_4)
- [Gemma 4 31B HuggingFace](https://huggingface.co/google/gemma-4-31B)
- [Gemma 4 license](https://ai.google.dev/gemma/docs/gemma_4_license)
- [Gemma Prohibited Use Policy](https://ai.google.dev/gemma/prohibited_use_policy)
- [vLLM Gemma 4 recipe](https://docs.vllm.ai/projects/recipes/en/latest/Google/Gemma4.html)
- [NVIDIA Gemma-4-31B-IT-NVFP4 quantized weights](https://huggingface.co/nvidia/Gemma-4-31B-IT-NVFP4)
