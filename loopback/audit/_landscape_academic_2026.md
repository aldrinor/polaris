# Academic landscape for LLM-powered research synthesis, early 2026

Skeptical survey, not a roundup. Window: Jan 2025 – Apr 2026. Every specific claim below has a URL. Where a search came up empty I say so.

## (a) What is genuinely new since Jan 2026

The narrow Jan 2026–Apr 2026 window is thin. The substantive artefact is **DeepHalluBench** (arXiv 2601.22984, Jan 30 2026) — a process-aware benchmark that audits the full deep-research-agent trajectory rather than end-to-end outputs. Authors explicitly conclude "no agent achieves robust reliability" across OpenAI, Gemini, Perplexity, Qwen, Grok, and Salesforce DRAs, flagging "unfaithful grounding and information neglect" as pervasive. Their PIES taxonomy (Planning/Summarization × Explicit/Implicit) is an analytic step beyond span-match scoring. https://arxiv.org/abs/2601.22984

Also in-window: Nature's editorial on fabricated citations polluting the literature (https://www.nature.com/articles/d41586-026-00969-z), and GPTZero's audit of NeurIPS 2025 proceedings finding 100+ hallucinated references across 53 accepted papers (Fortune, Jan 21 2026, https://fortune.com/2026/01/21/neurips-ai-conferences-research-papers-hallucinations/). Genesis Mission (DeepMind + DOE, Dec 2025) is a scale-up of Gemini for government science, not a synthesis advance. https://cloud.google.com/blog/topics/public-sector/how-google-public-sector-and-google-deepmind-can-power-the-genesis-mission-and-a-new-era-of-scientific-discovery

Most real momentum in this space landed **before** Jan 2026: Ai2 Asta and AstaBench (Aug 2025, https://allenai.org/blog/astabench); Google's AI co-scientist (arXiv:2502.18864, Feb 2025); ReportBench (arXiv:2508.15804, Aug 2025); ResearcherBench (arXiv:2507.16280, Jul 2025); FutureHouse Aviary (arXiv:2412.21154, Dec 2024). Be honest: "what's new since Jan 2026" is mostly new *critique*, not new *capability*.

## (b) What benchmark numbers actually say

Four independent late-2025 benchmarks triangulate a clear ceiling:

- **AstaBench** (2,400 problems, 11 benchmarks, 57 agents): Asta v0 = **53.0%**, ReAct+gpt-5 = 43.3–44.0%, best open-weight = 12.4%, and "no agent scoring above 34%" on data analysis. Ai2's own framing: "AI is still far from solving the challenge of scientific research assistance." https://allenai.org/blog/astabench
- **ResearcherBench** (65 frontier AI questions): OpenAI Deep Research = Coverage **70.32** / Faithfulness **84.0** / Groundedness **34.0**; Gemini DR = 69.29 / 86.0 / 59.0; Perplexity DR = 48.46 / 85.0 / 56.0. https://researcherbench.github.io/
- **ReportBench** (reverse-engineered survey tasks, ByteDance): OpenAI DR reference precision **0.385** vs Gemini **0.145**; OpenAI citation match **78.87%**; Gemini produced 32.42 citations per report vs OpenAI's 9.89. https://arxiv.org/abs/2508.15804
- **LitQA2** (PaperQA2 paper, Sep 2024): PaperQA2 66% vs PhD humans 64.3% — but this is 200 multiple-choice items, not synthesis. https://arxiv.org/html/2409.13740v1

The **ResearcherBench** money quote for anyone building a grounded-report pipeline: "High groundedness (citation coverage) doesn't necessarily correlate with research quality for frontier questions — valuable insights often emerge from creative synthesis rather than explicit source attribution." That is a direct admission that faithfulness-to-source and novel-analytical-view trade off.

**Gap I could not fill:** no benchmark in the set above treats *synthesis quality* — novelty, contradiction resolution, non-trivial integration — as a primary metric. AstaBench scores task completion. ResearcherBench has qualitative insight dimensions but is 65 items and evaluator-dependent. ReportBench rewards *recall of the expert's citation list*, which rewards imitation, not insight. FActScore/LongFact are span-match at the atomic-fact level; FActScore is explicitly "blind to narrative manipulations that montage correct facts in misleading order" (aclanthology.org/2025.findings-emnlp.880.pdf). The synthesis-quality benchmark does not appear to exist in early 2026.

## (c) Critiques the field itself acknowledges

Independent evaluations have become blunt. Columbia Tow Center (Mar 2025, 1,600 queries, 8 AI search engines) found failures in **>60%** of citations; Grok-3 Search failed **94%**, Perplexity the best at 37%, and Gemini/Grok-3 returned fabricated or broken URLs on more than half of responses. https://www.cjr.org/tow_center/we-compared-eight-ai-search-engines-theyre-all-bad-at-citing-news.php

University of Sydney Business School (Feb 2025): OpenAI Deep Research "produces polished reports" but "can miss key details, struggle with recent information and sometimes invents facts." https://theconversation.com/openais-new-deep-research-agent-is-still-just-a-fallible-tool-not-a-human-level-expert-249496

Journal of Clinical Epidemiology scoping review, Lieberum et al.: LLMs for systematic reviews are "on the rise, but not yet ready for use." https://www.jclinepi.com/article/S0895-4356(25)00079-4/fulltext Evaluations were split: 54% promising, 24% neutral, 22% nonpromising. Attempts to automate Cochrane RoB2 risk-of-bias scoring achieved only "limited success, far from replacing human reviewers."

OpenAI's own Oct 2025 hallucination post-mortem: evaluation regimes reward guessing over uncertainty, and reasoning-tuned models (o3, o4-mini, GPT-4o) show *higher* hallucination rates than predecessors. https://www.infoq.com/news/2025/10/openai-llm-hallucinations/

Independent librarian commentary (Aaron Tay's substack, 2025) treats Consensus, Elicit, Undermind as useful literature-discovery tools but not systematic-review replacements. https://aarontay.substack.com/p/a-2025-deep-dive-of-consensus-promises

## (d) Who narrowed vs who is still claiming end-to-end

**Still ambitious, end-to-end rhetoric:**
- **FutureHouse**: PaperQA2 framed as "first AI agent to conduct entire scientific literature reviews" (marketing, Sep 2024, https://www.futurehouse.org/research-announcements/wikicrow). In 2025 they launched *narrower* adjacent benchmarks — LAB-Bench (biology), BixBench (bioinformatics) — which reads as portfolio broadening, not a walkback. https://github.com/Future-House
- **Ai2 Asta** (Aug 2025): full-stack ambition — agents, benchmarks, resources. But AI2 publishes its own ceiling ("far from solved"), which is honest.
- **Google DeepMind AI co-scientist** (Feb 2025): ambitious in biomedical hypothesis generation, with three in-vitro validations. Different lane from literature synthesis — don't conflate.

**De facto narrowed / never claimed end-to-end:**
- **Stanford STORM / Co-STORM**: authors explicitly note source bias and fact-misassociation, position output as "helpful for the pre-writing stage" rather than publication-ready. Co-STORM adds human-in-the-loop. https://storm-project.stanford.edu/research/storm/
- **Elicit, Consensus, Undermind, SciSpace**: commercial tools that stayed in literature search / per-claim extraction / consensus surfacing. Elicit's 2025 SR-support proof-of-concept (Hilkenmeier et al., SAGE) positions it as a **second reviewer**, not autonomous. https://journals.sagepub.com/doi/10.1177/08944393251404052

## Honest assessment

The field is **stuck on the triple-constraint** the caller cares about — strong faithfulness, broad credible citation, and novel analytical view — and is **splitting into viable narrower products**. Literature discovery (Undermind, Consensus), per-claim extraction (Elicit as second reviewer), hypothesis generation (DeepMind co-scientist), and citation auditing (AI-powered audit protocols, arXiv:2511.04683) are converging. End-to-end autonomous systematic review remains unsolved — AstaBench's 53% ceiling and ResearcherBench's groundedness-vs-insight anti-correlation are the two most honest public signals that the 10K-word cited-report problem has no current breakthrough, only tradeoffs.

Word count: ~1,180.
