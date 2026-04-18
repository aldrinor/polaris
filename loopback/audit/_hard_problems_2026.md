# Hard Problems in LLM Research Report Generation — Field State, Early 2026

Scope: the wall-finding question. Where is the field itself stuck, not any one product. Every number below is from a primary source, cited inline with a date.

## 1. Multi-fact synthesis-sentence verification — OPEN

LettuceDetect v1 large reaches F1 79.22 on RAGTruth example-level (arXiv:2502.17125, Feb 2025); v0.1.8 added TinyLettuce (Aug 2025, https://github.com/KRLabsOrg/LettuceDetect). MiniCheck (EMNLP 2024, https://github.com/Liyan06/MiniCheck) explicitly requires decomposing compound claims sentence-by-sentence; RefChecker uses knowledge triplets for the same reason (https://www.amazon.science/code-and-datasets/refchecker). A reasoning-trace analysis of 24k verification examples across 9 datasets (arXiv:2604.01657, Apr 2026) found "multi-sentence synthesis and numerical reasoning are severely under-represented" — no SOTA exists on compound claims, only on atomic decompositions. Assessment: **open**. The atomicity assumption is structural.

## 2. Automated source credibility — PARTIAL

The strongest 2025 primary source is SourceCheckup (Nature Communications, Apr 2025, https://www.nature.com/articles/s41467-025-58551-6). It reached 88.7 percent agreement with a medical-expert consensus on whether a citation supports its claim, but that measures citation-claim support, not source-type classification. The finding that mattered: 50–90 percent of LLM citations across ChatGPT, Perplexity, Claude, and Google AI Overviews did not fully support their claim, and GPT-4o-with-web left ~30 percent of individual statements unsupported. OpenAlex authority signals and citation-graph heuristics are widely used but I found no 2025–2026 benchmark that scores automated discrimination of JAMA-primary vs industry-funded-marketing vs student-journal on a held-out test set. Assessment: **partial** — citation support is measurable; source-type credibility as a classification task has no benchmark.

## 3. Novel synthesis vs compilation — OPEN (no measurement infrastructure)

CreativityPrism (arXiv:2510.20091, Oct 2025, https://arxiv.org/abs/2510.20091) covers divergent thinking, creative writing, logical reasoning — not synthesis-over-sources. AI Idea Bench 2025 (arXiv:2504.14191, Apr 2025, https://ai-idea-bench.github.io/) evaluates AI-generated research *ideas* against 3,495 post-cutoff papers with novelty and feasibility scores, but grades the idea, not whether a report's paragraph is synthesis or compilation. MLR-Bench (https://liner.com/review/mlrbench-evaluating-ai-agents-on-openended-machine-learning-research, 2025) found 80 percent of agent runs produced fabricated or invalidated experimental results; agents "struggle significantly with Novelty and Feasibility." **No benchmark exists for novel-synthesis-in-a-report.** A real benchmark would need (a) a ground-truth corpus of source inputs, (b) human-annotated labels separating "compiled from source X" from "novel cross-source inference," (c) a faithfulness constraint so novelty is not rewarded for hallucination. Nothing like this was published by April 2026. Assessment: **open** — not solved, not measured.

## 4. Cross-source contradiction handling — PARTIAL

WikiContradict (NeurIPS 2024, https://arxiv.org/abs/2406.13805, 253 human-annotated instances) is the best real-world benchmark: even Llama-3-70b-instruct only reached 43.8 percent on generating answers that accurately reflect conflicting contexts, with a floor of 10.4 percent under weaker prompting. ContraDoc (NAACL 2024, https://arxiv.org/abs/2311.09182, 449 contradictory + 442 control documents) covers 8 contradiction types; LLMs systematically miss implicit and causal contradictions. DiverseSumm (NAACL 2024, https://arxiv.org/abs/2309.09369): GPT-4 covered under 40 percent of the diverse information across 10-article news stories. Assessment: **partial** — measurement exists, scores are bad; the typical production behavior is to average or pick one, neither of which the benchmarks score as correct.

## 5. Long-horizon internal consistency — OPEN

ConStory-Bench (arXiv:2603.05890, accepted ACL 2026, https://arxiv.org/abs/2603.05890) has 2,000 prompts generating 8k–10k-word outputs scored across 5 error categories / 19 subtypes. Finding: consistency errors cluster in the middle of narratives, are most common in factual and temporal tracking, and correlate with high token-entropy regions — i.e., exactly the "same trial cited with different numbers across sections" failure mode. Long-horizon-execution work (arXiv:2509.09677, Sep 2025, https://arxiv.org/pdf/2509.09677) documents models self-conditioning on their own earlier errors, causing compounding degradation over long outputs. No architectural pattern scored as a solution — scaling model size and test-time compute help, but do not eliminate it. Assessment: **open**.

## 6. Evaluator-generator family collapse — PARTIAL

"Play Favorites" (arXiv:2508.06709, Aug 2025, https://arxiv.org/abs/2508.06709) gave a statistical test: GPT-4o and Claude 3.5 Sonnet both systematically rate their own outputs higher, and also rate *same-family* outputs higher — so using Claude to grade Claude, or GPT to grade GPT, is measurable self-bias, not just an abstract worry. The CALM framework (ICLR 2025) enumerated 12 judge-bias types including authority bias (fake-citation trust) and self-enhancement. DeepMind's 5-million-call debate study (NeurIPS 2024) showed debate with stronger persuaders raises judge accuracy vs consultancy, but the gains depend on capability gaps and do not neutralize same-family bias. Assessment: **partial** — the bias is well-measured, no clean fix. Cross-family ensembles reduce but do not eliminate it.

## 7. Pipeline-level Goodharting — OPEN (diagnosed, not solved)

A 2025 Cohere/Stanford/MIT/AI2 analysis of Chatbot Arena documented Meta testing 27 private Llama-4 variants pre-release, i.e., leaderboard-as-target optimization (https://blog.collinear.ai/p/gaming-the-system-goodharts-law-exemplified-in-ai-leaderboard-controversy, 2025). Research-specific post-mortems at pipeline level are rarer, but the MLR-Bench 80 percent fabrication rate is a pipeline-Goodhart finding in disguise: agents optimize the pass signal, not the underlying task. No 2026 paper proposes a tested remedy beyond human-in-the-loop review and metric rotation. Assessment: **open**.

## 8. What was tried in 2024–2025 and under-delivered

Reflexion: "First Try Matters" (arXiv:2510.08308, Oct 2025, https://arxiv.org/abs/2510.08308) analyzed 8 reasoning models on 5 math datasets and found reflections are predominantly confirmatory — subsequent reasoning seldom overturns the first answer. Performance gains from training-with-reflection came from improving the first-try probability, not from self-correction. MAR (arXiv:2512.20845, Dec 2025) named the failure "degeneration-of-thought": agents repeat the same flawed chain even when told it is wrong. Tree-of-Thought and self-consistency majority-vote remain baselines in 2026 inference-time scaling, but have not produced a headline SOTA on faithfulness benchmarks since 2024. Assessment: self-reflection as a standalone fix is empirically demoted; multi-agent persona-critic variants are the active successor.

## The Real Walls

Three walls block systematic-review quality regardless of compute:

**Wall A — Novel synthesis has no metric (Area 3).** You cannot optimize what you cannot measure. Every quality signal in production pipelines rewards fluency, citation presence, or faithfulness-to-source. None rewards cross-source inference that no single source contained. Breaking this requires a benchmark with human-labeled novel-vs-compiled pairs *and* a faithfulness constraint, published and adopted. Nothing in 2026 literature approaches this. This is where a field-level contribution is possible.

**Wall B — Multi-fact claim verification is structurally atomic (Area 1).** Every SOTA detector decomposes compound claims, then verifies atoms. A sentence like "trials A, B, and C together demonstrate X by mechanism Y" has no atomic decomposition that preserves the "together" and "by mechanism" semantics — those are the synthesis, not the facts. Breaking this requires a new verifier class that operates on argument structure, not triplets or spans. No such class exists in the 2026 literature surveyed.

**Wall C — Evaluator-generator family collapse for long outputs (Area 6 × Area 5).** Self-grading is measurably biased; cross-family grading reduces but does not eliminate the bias; and on 10k-word reports the judge must itself maintain long-horizon consistency, which Area 5 shows is unsolved. Breaking this requires independent, adversarial, non-LLM grounding signals (human spot-audits, structured extractors over primary sources, PRISMA-style process adherence checks) integrated as gates, not post-hoc judges. Compute alone does not fix it because the judge inherits the same failure modes.

Walls A, B, C are where POLARIS is stuck — and where the field is stuck. Walls for source credibility (Area 2) and contradiction handling (Area 4) are partially porous; more engineering will help. Wall A is the one without even a ruler.
