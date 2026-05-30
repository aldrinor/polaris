# Claude deep research — gold-standard DR-tool evaluation (2026-05-27)

Parallel to Codex's research (`codex_dr_research.txt`). Synthesis → harness plan.

## 1. The recognized gold-standard DR-agent benchmark: DeepResearch Bench (RACE + FACT)

- **DeepResearch Bench** (arXiv 2506.11763, Jun 2025; site deepresearch-bench.github.io; GitHub Ayanami0730/deep_research_bench; HuggingFace leaderboard). 100 PhD-level tasks (50 EN / 50 ZH), 22 fields, distilled from 96,147 real user queries.
- **RACE** = Reference-based Adaptive Criteria-driven Evaluation w/ Dynamic Weighting → report QUALITY. Dynamically generates task-specific criteria; reference-based scoring; strong human alignment. (= analytic rubric, the judge-method best practice.)
- **FACT** = Framework for Factual Abundance and Citation Trustworthiness → retrieval/citation: effective citation count + **citation accuracy**.
- **Current standings (the targets)**:
  - RACE overall: **Gemini-2.5-Pro DR = 48.88** (leads); OpenAI/Claude/Kimi within ~4 pts.
  - FACT: Gemini = 111.21 avg effective citations (most); **Perplexity DR = 90.24% citation accuracy (highest)** ← the faithfulness bar POLARIS must beat.
  - OpenAI DR = 49.27 instruction-following (highest).
- Note: a SEPARATE "Deep Research Bench" exists at futuresearch.ai (agent leaderboard) — don't conflate. The academic RACE+FACT one is the methodological gold standard.

## 2. Adjacent recognized benchmarks
- **BrowseComp** (OpenAI, Apr 2025, 1,266 hard-to-find-fact questions; DR ≈ 51.5% vs GPT-4o+browse 1.9%) + **BrowseComp-Plus** (ACL 2026, fairer/transparent). Short-answer FIND-hard-facts, not long-form faithfulness.
- **GAIA** (general assistants; Tongyi DeepResearch 70.9 > o3). **FRAMES**, **ResearchQA**, **DeepConsult**.
- **ResearchRubrics** (arXiv 2511.07685) — prompts + rubrics for DR. **DRACO** (Perplexity's in-the-wild DR benchmark).

## 3. Long-form faithfulness (POLARIS's differentiator dimension)
- **FActScore** — atomic-claim PRECISION (decompose → verify each). **D-FActScore** for entity ambiguity.
- **SAFE** (Search-Augmented Factuality Evaluator) — scalable claim verification even w/ imperfect retrieval.
- **LongFact**; **2025-2026 gap: importance-aware RECALL** (arXiv 2604.03141) — current LLMs do precision >> recall; "did it cover the facts it SHOULD?" matters.
- **Citation precision/recall + span-level attribution** (ALCE-style) — the FACT dimension at finer grain.

## 4. Clinical factuality (POLARIS's domain — where it should win)
- **MedHallu** (arXiv 2502.14302) — 10k QA from PubMedQA, hallucinated answers via a **controlled pipeline** (= EXACTLY our human-free mechanical-injection oracle). Best models F1 ≈ 0.625 on HARD medical hallucinations → frontier tools struggle here.
- **FActBench** (medical, fine-grained, 4 gen tasks × 6 LLMs); **MedHallBench**; **FalseCite** (82k false claims + fabricated citations; citation fabrication up to 94% adversarial). Medical hallucination >60% without grounding.

## 5. LLM-as-judge methodology best practice (for our scorer)
- **Analytic rubrics** (criterion-by-criterion, root-cause-able) > pass/fail. Reference answers preferred (RACE does this).
- Biases: verbosity/formality, **position (>10% swing from order swap)**, bandwagon. Mitigate via **ensemble / meta-judge** (= our ≥3 cross-family panel), order/score-id randomization, calibration-based bias correction + CIs accounting for judge sensitivity/specificity, IRT on judges.
- GPT-4 judge ≈ 80% human agreement (≈ inter-human) when prompt+procedure controlled.
- Contamination: open-ended (no standard answer) less prone; close-ended needs held-out.

## 6. Convergence with POLARIS's existing design (the headline)
- Our **per-sentence provenance tokens + strict_verify + fabrication-rate safety contract** = FACT's citation-trustworthiness + claim-level factuality, at FINER granularity than any public DR benchmark.
- Our **human-free mechanical-injection oracle** (amendment §2, #922) = MedHallu's controlled pipeline = contamination-free, judge-free fabrication ground truth.
- Our **≥3 cross-family judge panel** = the ensemble/meta-judge bias-mitigation best practice.
- → POLARIS can credibly run the RECOGNIZED benchmark (DeepResearch Bench RACE+FACT) AND lead on the faithfulness/clinical-fabrication dimensions that are the recognized hard problem.

## 7. Plan skeleton — the harness loop (test → review → benchmark → Codex reason → Claude optimize → loop)
[TO SYNTHESIZE WITH CODEX FINDINGS]
- **Adopt**: DeepResearch Bench RACE+FACT (recognized) + MedHallu-style mechanical clinical injection (differentiator, human-free) + importance-aware recall.
- **Head-to-head**: POLARIS vs Perplexity/ChatGPT/Gemini DR on a held-out prompt set; score RACE (panel) + FACT (citation extract+verify, automatable) + mechanical fabrication-catch (judge-free).
- **Loop**: 1 test → 2 score (panel, §-1.1 claim-by-claim) → 3 benchmark table vs top-tier → 4 Codex root-cause + fix research → 5 Claude implements fix → 6 re-test on FRESH held-out slice + frozen regression slice.
- **Anti-overfit guardrails**: train/dev/test split; test never seen during optimize; contamination log; frozen regression set; report dev↔test gap.
- **Build order**: harness scaffold (prompt loader, multi-tool runner, RACE scorer, FACT scorer, mechanical clinical scorer, comparison emitter) → 10-20-prompt smoke for FIRST real data → scale to full set.

## Sources
- DeepResearch Bench: https://arxiv.org/pdf/2506.11763 ; https://deepresearch-bench.github.io/ ; https://github.com/Ayanami0730/deep_research_bench
- Leaderboard standings: https://futuresearch.ai/deep-research-bench/ ; https://huggingface.co/spaces/muset-ai/DeepResearch-Bench-Leaderboard
- BrowseComp: https://www.infoq.com/news/2025/05/openai-browsecomp-ai-benchmark/ ; BrowseComp-Plus https://github.com/texttron/BrowseComp-Plus
- ResearchRubrics: https://arxiv.org/pdf/2511.07685 ; DRACO https://research.perplexity.ai/articles/evaluating-deep-research-performance-in-the-wild-with-the-draco-benchmark
- FActScore/SAFE/recall: https://www.emergentmind.com/topics/factscore ; https://arxiv.org/abs/2604.03141
- Clinical: MedHallu https://arxiv.org/pdf/2502.14302 ; FActBench https://arxiv.org/pdf/2509.02198 ; MedHallBench https://arxiv.org/pdf/2412.18947
- LLM-as-judge: https://arxiv.org/pdf/2512.16041 ; https://arxiv.org/pdf/2402.10669
