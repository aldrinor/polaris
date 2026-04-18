# Open-Source Models: April 2026 Follow-up

**Date:** 2026-04-17
**Scope:** Verify whether any model released or benchmarked between 2026-03-20 and 2026-04-17 changes the POLARIS Phase 5 generator+evaluator pair.

---

## 1. Vectara HHEM Leaderboard — April 2026 Updates

**Verdict: NO update after 2026-03-20.** The most recent commit on the main branch is PR #181 "lb-update-3-20-2026" (merged 2026-03-20). No later commits between 2026-03-20 and 2026-04-17. Source: [vectara/hallucination-leaderboard/commits/main](https://github.com/vectara/hallucination-leaderboard/commits/main).

**HHEM-3 status:** Not released as of 2026-04-17. HHEM-2.3 remains the current detector (primary: [Vectara docs](https://docs.vectara.com/docs/hallucination-and-evaluation/hallucination-evaluation)).

Primary-source Vectara rates (README of leaderboard, dated 2026-03-20) for models in question:

| Model | Hallucination Rate | Position |
|---|---|---|
| antgroup/finix_s1_32b | 1.8% | 1 |
| microsoft/Phi-4 | 3.7% | 4 |
| google/gemma-3-12b-it | 4.4% | 7 |
| mistralai/mistral-large-2411 | 4.5% | 8 |
| **qwen/qwen3-8b** | **4.8%** | **9** |
| qwen/qwen3-14b | 5.4% | 16 |
| qwen/qwen3-32b | 5.9% | 23 |
| deepseek-ai/DeepSeek-V3.2-Exp | 5.3% | 15 |
| meta-llama/Llama-4-Scout-17B-16E-Instruct | 7.7% | 34 |
| meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8 | 8.2% | 36 |
| GLM-4.6 | 9.5% | 49 |
| **GLM-5** | **10.1%** | **57** |
| kimi-K2.5 | 14.2% | 77 |

**Not on leaderboard:** Qwen3.5-397B-A17B, Gemma 4 (31B or any variant), GLM-5.1, Mistral Large 3, DeepSeek V3.3/V4.

---

## 2. Other April 2026 Benchmarks

**AA-Omniscience (Artificial Analysis):** Methodologically different from Vectara — measures parametric knowledge + abstention, NOT retrieval-grounded summarization. GLM-5 scores -1 (top open-weight) and Kimi K2.5 scores -11, but both do so largely by **abstaining more** rather than improving grounded accuracy ([AA GLM-5 analysis](https://artificialanalysis.ai/articles/glm-5-everything-you-need-to-know), 2026-02-11). **Phase 5 uses retrieved evidence — AA-Omniscience is the WRONG axis.** GLM-5's rank-57 on Vectara (which IS the right axis) is the more relevant datapoint.

**FACTS Grounding v2 (Kaggle + DeepMind), released early 2026:** Gemini 3 Pro tops at 68.8% overall; no evaluated model exceeds 70% ([InfoQ 2026-01](https://www.infoq.com/news/2026/01/facts-benchmark-suite/)). Open-weight specific scores not broken out in accessible sources; could not verify Qwen3.5 or Gemma 4 numbers on FACTS v2.

**LettuceDetect v0.2:** Could not verify a release by that version. Only v1-series artifacts (lettucedetect-large-v1) on the GitHub releases page as of 2026-04-17 ([KRLabsOrg/LettuceDetect/releases](https://github.com/KRLabsOrg/LettuceDetect/releases)).

**SourceCheckup:** Could not verify. No primary-source hit in April 2026 searches.

**HalluHard, PlaceboBench, RAGTruth:** Continue to exist; no April-2026 revisions affecting open-weight rankings.

---

## 3. April 2026 Releases Reconsidered

**Gemma 4 31B (released 2026-04-02, Apache 2.0):** Strong capability benchmarks (85.2% MMLU Pro, 89.2% AIME 2026, Arena ELO 1452). **Factuality on retrieved evidence: NO Vectara HHEM data.** Gemma-3-12b scored 4.4% on Vectara — Gemma 4 MAY inherit that grounding quality but is unverified. Secondary sources rank it #30/106 on "multimodal and grounded tasks" ([benchlm.ai/models/gemma-4-31b](https://benchlm.ai/models/gemma-4-31b)) — not authoritative for summarization faithfulness.

**GLM-5.1 (released 2026-04-07, MIT, 744B total / 40B active):** Targets agentic engineering (SWE-Bench Pro 58.4, BrowseComp 68.0). Internal claims of improved factuality but **no Vectara number**. GLM-5 (older sibling) scored 10.1% on Vectara — not encouraging for grounded work. [AA model page](https://artificialanalysis.ai/models/glm-5-1) shows pricing: blended $2.15/M tokens — expensive vs. Qwen3-8B and DeepSeek V3.2.

**Qwen 3.5 397B-A17B (released 2026-02-16):** AA-Omniscience hallucination rate 88% (actual fabrication; accuracy gains come from being correct more, not hallucinating less) — [VentureBeat](https://venturebeat.com/technology/alibabas-qwen-3-5-397b-a17-beats-its-larger-trillion-parameter-model-at-a), [AA](https://artificialanalysis.ai/articles/qwen3-5-397b-a17b-everything-you-need-to-know). No Vectara HHEM entry. Proxy signal is poor.

**Mistral Large 3 (Dec 2025):** SimpleQA ~23.8% — hallucinates confidently. Disqualified regardless of Vectara status.

**Llama 4 Maverick/Scout:** ON Vectara (7.7% Scout, 8.2% Maverick) — markedly worse than Qwen3-8B's 4.8%. Not a pair upgrade.

**DeepSeek V4:** NOT released as of 2026-04-17. API still maps deepseek-chat to V3.2. Reuters/Information reports "next few weeks" ([technode.com 2026-04-08](https://technode.com/2026/04/08/deepseek-v4-may-launch-this-month-test-interface-suggests-vision-and-expert-modes/)). V3.3 does not exist as a public version.

---

## 4. Revised Pair Recommendation

**The 2026-03-20 pair HOLDS.** No April-2026 release has verified grounded-generation factuality data that beats the existing recommendation. Critically: GLM-5 and GLM-5.1's "record low hallucination" narrative comes from AA-Omniscience (abstention-driven), NOT from retrieval-grounded summarization (Vectara), where GLM-5 sits at position 57 of 77+ models.

**Recommended pair, confirmed:**
- **Generator: DeepSeek V3.2-Exp** — Vectara 5.3% hallucination, $0.27/$0.41 per M tokens on OpenRouter ([openrouter.ai/deepseek/deepseek-v3.2-exp](https://openrouter.ai/deepseek/deepseek-v3.2-exp)). Fits $0.15–$0.50/report budget.
- **Evaluator: Qwen3-8B** — Vectara 4.8% (rank #9 open-weight), $0.05/$0.40 per M tokens on OpenRouter ([openrouter.ai/qwen/qwen3-8b](https://openrouter.ai/qwen/qwen3-8b)). Cheap enough for hundreds of evaluator calls.

**Tempting but unverified alternatives to NOT adopt yet:**
- Gemma 4 31B (Apache 2.0 attractive, but no HHEM data — revisit when Vectara updates)
- GLM-5.1 (pricing too high + GLM-5 Vectara signal is negative)

**Re-evaluation trigger:** next Vectara leaderboard update (watch PR #182+) OR FACTS Grounding v2 with broken-out open-weight numbers.

---

## 5. Gaps / Could Not Verify

- HHEM-3 release: not confirmed; HHEM-2.3 still current
- LettuceDetect v0.2: no release under that name found
- SourceCheckup April 2026 update: no primary source
- Gemma 4 / GLM-5.1 factuality on grounded-summarization tasks: zero data — will need independent run or await HHEM refresh
- FACTSGrounding v2 open-weight model-by-model rankings not extractable from accessible content
- DeepSeek V3.3: does not appear to exist; V4 not yet released

**Bottom line:** In the 28-day window from 2026-03-20 to 2026-04-17, no benchmark with primary-source open-weight numbers on grounded-generation factuality has changed the pair. Hold DeepSeek V3.2-Exp + Qwen3-8B until Vectara refreshes or a new grounded-factuality benchmark posts verified numbers for the April releases.
