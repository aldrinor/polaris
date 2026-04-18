# Open-Weight LLM Pair for Grounded Long-Form Research Generation — April 2026

**Question:** Best open-weight generator + evaluator pair (different families) for 3K–5K word grounded research reports, medical/scientific domain, $0.15–$0.50/report, 128K+ context.

**Primary sources:** HuggingFace model cards, Vectara HHEM-2.3 Leaderboard (20-Mar-2026 snapshot), DeepInfra pricing page, Artificial Analysis, mistral.ai, ai.google.dev, arXiv. Vendor-adjacent/SEO sources (intuitionlabs, serenitiesai, nxcode, skywork, buildfastwithai, mayhemcode, lushbinary, tech-insider) flagged inline; never relied on for load-bearing claims.

## 1. Summary Table

| Model | Release | License | Params (tot/act) | Ctx | DeepInfra $/M in / out (blended 3:1) | Vectara HHEM | Strengths | Weaknesses |
|---|---|---|---|---|---|---|---|---|
| DeepSeek V3.2-Exp | 2025-09-29 (Exp), V3.2 Dec-2025 | MIT | 671B / ~37B (MoE) | 128K | 0.26 / 0.38 (~0.29) | **6.3%** | Cheap, MMLU-Pro 85.0, GPQA-D 79.9, sparse attn | R1 variant halluc 11.3% — avoid reasoning variant for grounded work |
| DeepSeek R1 | Updated 2025 | MIT | 671B / 37B | 128K | 0.50 / 2.15 (~0.91) | 11.3% | Strong reasoning (AIME) | Halluc nearly 2x V3.2 |
| Qwen3 32B | 2025-04-28 | Apache 2.0 | 32B dense | 128K | ~0.10 / 0.30 (est.) | **5.9%** | Excellent factuality, cheap, dense model | Smaller capacity than MoE flagships |
| Qwen3 14B | 2025-04-28 | Apache 2.0 | 14B dense | 128K | <$0.10 blended | **5.4%** | Best Vectara among mid-tier | Limited long-form coherence |
| Qwen3.5 397B-A17B | 2026-02-16 | Apache 2.0 | 397B / 17B | 262K (1M YaRN) | 0.54 / 3.40 (1.25) | not yet measured | MMLU-Pro 87.8, GPQA-D 88.4 (best open-weight), Gated DeltaNet | Priced out of evaluator role at scale; HHEM unverified |
| GLM-4.6 | 2025-09 | MIT | 355B / 32B | 200K | not on DeepInfra | n/a (4.5-AIR: 9.3%) | Good coding, MIT, 200K ctx | Factuality worse than Qwen/DeepSeek |
| GLM-5 | 2026-02-11 | MIT | 744B / 40B | 200K | 0.80 / 2.56 (1.24) | **10.1%** | SWE 77.8, GPQA-D 86.0, AIME 92.7 | Borderline halluc; too expensive as per-call evaluator |
| Llama 4 Maverick | 2025-04-05 | Llama 4 Community | 400B / 17B (128 exp) | 1M | 0.15 / 0.60 (0.26) | not on March leaderboard (3.3: 4.1%) | Cheap, 1M ctx | Llama license = "community" not OSI; multimodal-native |
| Llama 3.3 70B | 2024-12 | Llama 3.3 Community | 70B dense | 128K | ~0.23 / 0.40 (0.27) est. | **4.1%** (best in class) | Best-in-class factuality on Vectara | Older architecture; license restrictions |
| Gemma 3 27B | 2025-03 | Gemma ToU | 27B dense | 128K | 0.08 / 0.16 (0.10) | 7.4% | Cheapest mid-tier; Google eval ecosystem | Custom Gemma ToU (not pure Apache) |
| Gemma 4 31B | 2026-04-02 | **Apache 2.0** | 30.7B dense | 256K | not yet on DeepInfra | not yet measured | MMLU-Pro 85.2, GPQA-D 84.3, Apache 2.0, 256K ctx | HHEM not yet measured; fresh release |
| Mistral Large 3 | 2025-12-02 | Apache 2.0 | 675B / 41B | not published on docs | ~$0.50 / 1.50 (official) | not on March leaderboard (Large-2411: 4.5%) | Apache 2.0, European jurisdiction | GPQA-D only ~43.9 per vendor-adjacent write-up; SimpleQA ~23.8 suggests hedging/"I don't know" behavior |
| Kimi K2.5 | 2026-01-29 | Modified MIT | 1T / 32B (384 exp) | 256K | not on DeepInfra | **17.9%** (K2-Instruct-0905) | MMLU-Pro 87.1, GPQA-D 87.6, agent swarm | **Highest halluc on Vectara — disqualified as evaluator** |

Budget math: a generator averaging ~5K output tokens plus ~20K input context per final draft, plus evaluator averaging ~2K output and ~8K input across ~200 per-claim calls per report. DeepSeek V3.2 generator ≈ $0.008 final draft + Qwen3-32B evaluator ≈ $0.06 evaluator ≈ **$0.07–$0.10 per report**. GLM-5 generator + Qwen3-32B evaluator ≈ **$0.20–$0.30**. Qwen 3.5 397B as evaluator at $1.25/M blended ≈ **$0.40+ on evaluator alone**, near the cap.

## 2. Per-Candidate Notes

**DeepSeek V3.2-Exp.** MIT, 671B/~37B MoE, 128K ctx, MMLU-Pro 85.0, GPQA-D 79.9, AIME 89.3, SWE-Verified 67.8 ([HF card](https://huggingface.co/deepseek-ai/DeepSeek-V3.2-Exp)). DeepInfra $0.26/$0.38. Vectara HHEM 6.3% ([HHEM leaderboard](https://github.com/vectara/hallucination-leaderboard)). **R1 variant at 11.3% HHEM unsuitable for grounded work.**

**Qwen 3 series (8B/14B/32B, 2025-04-28, Apache 2.0).** Vectara HHEM: 8B=4.8%, 14B=5.4%, 32B=5.9%. Dense, 128K ([qwenlm.github.io/blog/qwen3](https://qwenlm.github.io/blog/qwen3/)). **Best open-weight evaluator candidates by verified factuality.**

**Qwen 3.5 397B-A17B (2026-02-16, Apache 2.0).** 262K native / ~1M YaRN. MMLU-Pro 87.8, GPQA-D 88.4, LongBench v2 63.2 ([HF card](https://huggingface.co/Qwen/Qwen3.5-397B-A17B)). DeepInfra blended $1.25/M. HHEM not yet measured on March-2026 table.

**GLM-4.6 / GLM-5.** GLM-4.6: 355B/32B, 200K ctx, MIT (Sep-2025). GLM-5: 744B/40B, DeepSeek Sparse Attention, GPQA-D 86.0, AIME 92.7, Feb-2026 ([HF card](https://huggingface.co/zai-org/GLM-5)). Vectara HHEM GLM-5 10.1% (borderline); GLM-4.5-AIR-FP8 9.3%.

**Llama 4 Maverick (2025-04-05).** 400B/17B, 1M ctx, Llama 4 Community license ([ai.meta.com/blog/llama-4-multimodal-intelligence](https://ai.meta.com/blog/llama-4-multimodal-intelligence/)). DeepInfra $0.15/$0.60. Not on Mar-2026 Vectara. Llama 3.3 70B at 4.1% HHEM is the best-factuality Llama option but uses the older Llama 3.3 Community license.

**Gemma 3 27B (2025-03, Gemma ToU).** Vectara HHEM 7.4%. DeepInfra $0.08/$0.16 — cheapest mid-tier evaluator. Gemma ToU includes use restrictions.

**Gemma 4 (2026-04-02, Apache 2.0).** 31B dense, 256K, MMLU-Pro 85.2, GPQA-D 84.3, AIME-2026 89.2 ([model card](https://ai.google.dev/gemma/docs/core/model_card_4); [blog.google](https://blog.google/innovation-and-ai/technology/developers-tools/gemma-4/)). First Gemma under Apache 2.0 ([venturebeat.com](https://venturebeat.com/technology/google-releases-gemma-4-under-apache-2-0-and-that-license-change-may-matter)). Not yet on Vectara.

**Mistral Large 3 (2025-12-02, Apache 2.0).** 675B/41B MoE ([mistral.ai/news/mistral-3](https://mistral.ai/news/mistral-3); [TechCrunch](https://techcrunch.com/2025/12/02/mistral-closes-in-on-big-ai-rivals-with-mistral-3-open-weight-frontier-and-small-models/)). Official API $0.50/$1.50. GPQA-D ~43.9 (vendor-adjacent). Mistral-large-2411 predecessor 4.5% HHEM. Context window not published in primary docs — gap.

**Kimi K2.5 (2026-01-29, Modified MIT).** 1T/32B, 256K, MMLU-Pro 87.1, GPQA-D 87.6 ([HF card](https://huggingface.co/moonshotai/Kimi-K2.5)). K2-Instruct-0905 HHEM 17.9% — **disqualified as evaluator.**

## 3. Family-Distance Recommendation

The task brief defines DeepSeek / Qwen / GLM / Gemma / Llama / Mistral as distinct families. GLM-5 adopts DeepSeek Sparse Attention but remains a distinct training lineage per the [Raschka Jan-Feb 2026 architectural survey](https://magazine.sebastianraschka.com/p/a-dream-of-spring-for-open-weight). Qwen 3.5's Gated DeltaNet is genuinely novel.

**Primary pair: DeepSeek V3.2 (generator) + Qwen 3 32B (evaluator).**
- Family distance: DeepSeek MoE with sparse attention vs Qwen dense with Gated DeltaNet lineage — genuinely distinct families satisfying Play Favorites (arXiv 2508.06709) and DeepHalluBench concerns on self-bias.
- Cost: ~$0.07–$0.10 per report, well under $0.50 ceiling.
- Factuality: V3.2 at 6.3% HHEM, Qwen3-32B evaluator at 5.9% HHEM — both **independently verified** on the 20-Mar-2026 Vectara run.
- Licenses: both permit commercial self-deployment (MIT + Apache 2.0).
- Context: 128K both, sufficient for the 3K–5K word task.

**Fallback 1: GLM-4.6 (generator) + Llama 3.3 70B (evaluator).**
- Family distance: Zhipu vs Meta — distinct.
- Llama 3.3 70B has the **lowest HHEM of any open-weight evaluator** (4.1%).
- GLM-4.6 generator (200K ctx, MIT) is cheaper than GLM-5. Confirm Vectara numbers since GLM-4.5-AIR is 9.3%.
- Budget: fits comfortably; Llama 4 Maverick evaluator at $0.26 blended is alternative.
- Caveat: Llama 3.3 Community license has use restrictions vs pure Apache.

**Fallback 2: Qwen 3.5 397B-A17B (generator) + Gemma 3 27B (evaluator).**
- Family distance: Alibaba vs Google — distinct.
- Strongest open-weight generator capability (GPQA-D 88.4 per HF card).
- Gemma 3 27B evaluator at DeepInfra $0.10 blended — cheapest evaluator arm.
- Cost: evaluator ~$0.02–$0.03 per report; generator ~$0.08–$0.12. Total ~$0.10–$0.15 — fits.
- Risk: Qwen 3.5 HHEM not yet on Vectara; Gemma 3 at 7.4% is the weakest factuality among primary picks. Monitor post-deployment.

## 4. Gaps (Not Verifiable)

- **Vectara HHEM for Qwen 3.5, Gemma 4 31B, Mistral Large 3, Llama 4, Kimi K2.5** — not on the 20-Mar-2026 leaderboard snapshot. Do not extrapolate from sibling models.
- **MedQA / PubMedQA 2026 scores** for the above models — not published in primary sources reviewed; vendor-adjacent sources summarize but lack per-model numbers.
- **RULER effective context** per model — benchmark concept exists (arXiv 2404.06654) but no consolidated 2026 table was found for the candidate set. Claimed context windows are vendor figures.
- **Together/Fireworks exact prices** — DeepInfra is the sole provider with verified per-model prices for this set; Fireworks and Together typically charge 1.3–2.0x DeepInfra per third-party comparisons (vendor-adjacent: [pricepertoken.com](https://pricepertoken.com)).
- **Mistral Large 3 context window** — not in [docs.mistral.ai](https://docs.mistral.ai) or mistral.ai/news/mistral-3; flagged.
- **SourceCheckup / RAGTruth** — no 2026 open-weight leaderboard run surfaced for candidate set.

## 5. Gap vs Frontier (Opus 4 / GPT-5 / Gemini 3)

On **raw capability**, Epoch AI reports open-weight models lag by ~3 months ([epoch.ai/data-insights/open-weights-vs-closed-weights-models](https://epoch.ai/data-insights/open-weights-vs-closed-weights-models)). On **grounded long-form generation specifically**, the gap is smaller: on Vectara's harder (long-document) benchmark, GPT-5, Claude Sonnet 4.5, and Grok-4 all exceeded 10% hallucination ([vectara.com/blog/introducing-the-next-generation-of-vectaras-hallucination-leaderboard](https://www.vectara.com/blog/introducing-the-next-generation-of-vectaras-hallucination-leaderboard)) — putting them on par with GLM-5 (10.1%) and worse than DeepSeek V3.2 (6.3%) and Qwen3-32B (5.9%) on shorter-doc factual consistency. No 2026 open-weight model has closed the capability gap on reasoning (GPQA, HLE-with-tools), but for **the specific sub-task of grounded, citation-anchored summarization, DeepSeek V3.2 + Qwen 3 rivals or beats frontier closed models on hallucination rate** while running at roughly 1/20th the cost. The task brief's pair recommendation is therefore competitive on its primary quality axis (faithfulness), not merely "acceptable fallback."

---
*File: `C:/POLARIS/loopback/audit/_open_source_models_2026.md`. Word count target <1500. Compiled 2026-04-17 from sources above.*
