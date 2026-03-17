# Deep Research Architecture Survey: Practitioner Insights

## Date: 2026-03-17
## Sources: 40+ web sources across GitHub repos, blog posts, documentation, papers, and practitioner discussions

---

## Table of Contents
1. [Executive Summary](#1-executive-summary)
2. [Commercial Systems Architecture](#2-commercial-systems-architecture)
3. [Open Source Implementations](#3-open-source-implementations)
4. [Canonical Pipeline Patterns](#4-canonical-pipeline-patterns)
5. [Key Architectural Decisions](#5-key-architectural-decisions)
6. [Common Pitfalls](#6-common-pitfalls)
7. [Benchmarks and Results](#7-benchmarks-and-results)
8. [Synthesis: What Actually Works](#8-synthesis-what-actually-works)
9. [Implications for POLARIS](#9-implications-for-polaris)

---

## 1. Executive Summary

After surveying 40+ sources including GitHub repos (GPT-Researcher, STORM, GraphRAG, LangGraph Open Deep Research), Anthropic/LangChain/HuggingFace engineering blogs, academic papers (CRAG, Self-RAG, Co-STORM, PaSa), and practitioner posts, a **clear consensus architecture** has emerged across all serious implementations:

**The winning pattern is: Plan -> Search -> Read -> Verify -> Iterate -> Synthesize**

Every successful system uses some variant of this loop, with the key differentiators being:
1. How deeply they decompose the planning step
2. Whether they use multi-agent or single-agent execution
3. How they handle verification/correction of retrieved content
4. How many iterations they allow before synthesis

The strongest signal from practitioners: **simplicity beats complexity**. Anthropic, LangChain, and HuggingFace all independently converged on the same conclusion: start with the simplest possible pipeline and only add complexity when measurably justified.

---

## 2. Commercial Systems Architecture

### 2.1 Gemini Deep Research (Google, Dec 2024)
**Source:** Google AI Developer Docs, Simon Willison's analysis

**Pipeline:** `Plan -> Search -> Read -> Iterate -> Output`

**Key Details:**
- Powered by Gemini 3.1 Pro (previously Gemini 2.0 Flash)
- Runs as a background agent (20-60 minutes per task)
- Autonomous: the agent decides when it has enough information
- Standard task: ~80 web searches, ~250K input tokens, ~60K output tokens ($2-3)
- Complex task: ~160 searches, ~900K input tokens, ~80K output tokens ($3-5)
- Supports multimodal input (images, PDFs, audio, video)
- Streams progress updates with intermediate reasoning
- Follow-up capability via `previous_interaction_id`

**Architectural Insight:** Gemini does NOT use a fixed number of iterations. The agent autonomously determines research depth. There is no pre-set outline; the report structure emerges from the research itself.

### 2.2 OpenAI Deep Research (Feb 2025)
**Source:** Simon Willison's tag analysis, OpenAI documentation

**Key Details:**
- Uses o3/o1 reasoning models
- GAIA benchmark: 67.36% (highest commercial score)
- Uses an Operator GUI agent for browser interaction (not just text scraping)
- Known to hallucinate about tool access (per OpenAI system card)
- Approximate cost per query: $0.50-$5.00

**Critical Observation from Willison:** "The one thing that can't be easily spotted is misinformation by omission." Surface-level presentation (headings, citations, confident prose) creates false impressions of expertise.

### 2.3 Perplexity Deep Research (Feb 2025)
**Source:** Simon Willison's analysis

**Key Details:**
- Approximate cost per call: $0.53
- Shares the same core pattern as Gemini and OpenAI: accumulating information from multiple websites and synthesizing reports

**Key Finding:** All three commercial systems converge on the same basic architecture -- iterative web search with accumulated context leading to synthesis. The differentiator is model capability, not pipeline architecture.

---

## 3. Open Source Implementations

### 3.1 GPT-Researcher (assafelovic)
**Source:** GitHub README, Tavily docs, LangGraph blog post

**Pipeline (Basic):**
1. Create domain-specific agent based on query
2. Generate research questions (planner agent)
3. For each question, trigger crawler agents (parallel)
4. Summarize each source, track provenance
5. Filter and aggregate into final report

**Pipeline (Multi-Agent / LangGraph):**
Seven specialized agents in sequence:
1. **Chief Editor** -- Coordinates workflow
2. **GPT Researcher** -- Initial broad research
3. **Editor** -- Creates outline from initial findings
4. **Reviewer** -- Validates against criteria
5. **Reviser** -- Refines based on review feedback
6. **Writer** -- Compiles final report with intro/conclusions
7. **Publisher** -- Outputs PDF/Docx/Markdown

**Key Architecture Decisions:**
- Planning BEFORE execution (planner-executor split)
- Parallel crawler agents per question (not sequential)
- Sub-graphs isolate parallel tasks to prevent race conditions
- Conditional edges enable reviewer-reviser feedback loops
- 20+ web sources aggregated per report
- Cost: ~$0.10, ~3 minutes per task (gpt-4o-mini + gpt-4o)

**Practitioner Lesson:** "Nearly all agents in production are customized towards the specific use case."

### 3.2 Stanford STORM / Co-STORM
**Source:** arXiv:2402.14207, arXiv:2408.15232, GitHub engine.py

**Pipeline (4 stages):**
1. **Knowledge Curation** -- Multi-perspective conversations with simulated experts
2. **Outline Generation** -- Synthesize collected info into structured outline
3. **Article Generation** -- Expand outline with citations
4. **Article Polishing** -- Refine and deduplicate

**Key Innovation: Perspective-Guided Question Asking**
- "Directly prompting the language model to ask questions does not work well"
- Discovers diverse perspectives by surveying existing articles on similar topics
- Simulates conversations between a "Wikipedia writer" and "topic expert grounded in Internet sources"
- This multi-perspective approach yielded 25% improvement in organization and 10% improvement in coverage vs. retrieval-augmented baselines

**Co-STORM (v2) Innovation:**
- Users observe and guide conversations among multiple LM agents instead of asking all questions themselves
- Dynamic mind map tracks discourse and uncovered information
- 70% of evaluators preferred it over search engines; 78% over RAG chatbots

**Architecture from engine.py:**
- Different LLMs for different stages (GPT-4o-mini for conversations, GPT-4o for polishing)
- Boolean flags control stage execution (partial reruns supported)
- Modular design: each phase independently callable, loads previous outputs from disk
- Unified Retriever with thread pooling across all stages

### 3.3 Microsoft GraphRAG
**Source:** GitHub, Microsoft Research blog

**Pipeline:**
1. **Text Segmentation** -- Divide corpus into TextUnits
2. **Entity Extraction** -- Extract entities, relationships, claims via LLM
3. **Hierarchical Clustering** -- Leiden algorithm organizes graph into communities
4. **Community Summarization** -- Bottom-up summaries for each community

**Query Modes:**
- **Global Search** -- Broad questions using community summaries
- **Local Search** -- Specific entities and neighbors
- **DRIFT Search** -- Entity-focused with community context
- **Basic Search** -- Vector similarity fallback

**Key Finding:** GraphRAG "consistently outperforms baseline RAG" on comprehensiveness, source attribution, and viewpoint diversity. For faithfulness, both approaches achieve similar levels.

**Critical Warning:** "GraphRAG indexing can be an expensive operation." Start small.

### 3.4 LangChain Open Deep Research
**Source:** GitHub, LangChain blog

**Pipeline (evolved from three earlier approaches):**
1. **Search Query Generation** -- Formulate targeted queries
2. **Web Search Execution** -- Retrieve via Tavily/MCP/native search
3. **Result Summarization** -- Compress with efficient models (gpt-4.1-mini)
4. **Iterative Research** -- Refine queries based on gathered info
5. **Finding Compression** -- Consolidate into key insights
6. **Final Report Generation** -- Synthesize with report model (gpt-4.1)

**Architecture Evolution (Critical Insight):**
"The developers evolved from earlier 'Plan-and-Execute' and 'Supervisor-Researcher' approaches toward a streamlined architecture that prioritizes performance through model capability rather than intricate orchestration."

**Four separate model roles:**
- Summarization Model (gpt-4.1-mini)
- Research Model (gpt-4.1)
- Compression Model (gpt-4.1)
- Report Model (gpt-4.1)

**Benchmark:** RACE score 0.4344 (#6 on Deep Research Bench), cost $45.98 for 58M tokens default config.

### 3.5 LangChain Open Deep Research (Blog Architecture)
**Source:** LangChain blog "Open Deep Research"

**Three-Phase Pipeline:**
1. **Scope** -- Clarify research parameters via user interaction, then compress into "comprehensive, yet focused research brief"
2. **Research** -- Supervisor-agent architecture delegates subtopics to parallel sub-agents
3. **Write** -- Single-pass report generation steered by the brief

**Critical Lessons:**
- "Isolation over coordination": Multi-agent works best for research (easily parallelized), NOT report writing
- Earlier parallel section-writing "faced a problem...the reports were disjoint"
- Sub-agents prune irrelevant findings before returning to supervisor (prevents context window exhaustion)
- Supervisors selectively spawn sub-agents based on complexity

### 3.6 HuggingFace Open Deep Research (smolagents)
**Source:** HuggingFace blog

**Pipeline:**
1. **Query Reception** -- Agent receives research question
2. **Planning Phase** -- Agent writes code to create research plan
3. **Research Execution Loop** -- Web searches, URL visits, extraction, parsing
4. **Synthesis Phase** -- Organize, cross-reference, format
5. **Output Generation** -- Comprehensive research summary

**Key Innovation: Code-Based Actions vs JSON**
- Code agents scored 55.15% on GAIA benchmark vs 33% for JSON agents (+22 points)
- 30% fewer tokens required
- More expressive for complex multi-step workflows

**GAIA Benchmark Results:**
| System | Score |
|--------|-------|
| GPT-4 (no agent) | ~7% |
| Magentic-One (JSON) | 46% |
| Open Deep Research | 55.15% |
| OpenAI Deep Research | 67.36% |

### 3.7 dzhng/deep-research (Minimal Implementation)
**Source:** GitHub

**Pipeline (Recursive Breadth-Depth):**
1. `generateSerpQueries()` -- Create queries from user input + accumulated learnings
2. `firecrawl.search()` -- Execute web searches
3. `processSerpResult()` -- Extract learnings and follow-up questions
4. `deepResearch()` -- Recursive call with reduced breadth/depth

**Key Pattern:**
```
Breadth halves with each recursion level
Depth decrements to zero
Previous findings inform next-level queries
Results deduplicated before return
```
- Breadth 3-10 recommended, Depth 1-5
- Goal: "simplest implementation...keep repo at <500 LoC"
- Concurrency limited to 2 parallel requests

### 3.8 Jina DeepResearch (Node.js)
**Source:** GitHub

**Pipeline:** `Query -> Search -> Read -> Reason -> (loop) -> Answer`

**Key Design Decisions:**
- Iterative loop persists until token budget exhaustion
- "Beast Mode" activated when budget exceeded (final answer generation)
- Failed search/reflection attempts disabled for subsequent iterations
- Answers lacking citations trigger additional research cycles
- Focus on "finding the right answers via iterative process" not long reports

**Critical Distinction:** Jina explicitly says their system solves a "fundamentally different problem from report generation tools like OpenAI's Deep Research."

---

## 4. Canonical Pipeline Patterns

### 4.1 Anthropic's Agent Pattern Taxonomy
**Source:** Anthropic Engineering Blog "Building Effective Agents"

Six patterns, from simplest to most complex:

1. **Augmented LLM** -- LLM + retrieval + tools + memory (foundation)
2. **Prompt Chaining** -- Sequential steps, each processing previous output (fixed path)
3. **Routing** -- Classify input, direct to specialized handler
4. **Parallelization** -- Sectioning (independent subtasks) or Voting (repeated for diversity)
5. **Orchestrator-Workers** -- Central LLM decomposes dynamically, delegates to workers
6. **Evaluator-Optimizer** -- Generator + feedback loop (iterative refinement)
7. **Autonomous Agent** -- Open-ended tool use with environmental feedback

**Critical Principle:** "Find the simplest solution possible, and only increase complexity when needed."

**Pitfalls warned about:**
- Over-engineering: "Adding complexity only when it demonstrably improves outcomes"
- Framework abstraction trap: Frameworks hide mechanics, making debugging difficult
- Tool design neglect: Poor tool specs cause compounding LLM errors
- They spent more time optimizing tools than the overall prompt (SWE-bench)

### 4.2 LangGraph's RAG Patterns
**Source:** LangGraph documentation

**Corrective RAG (CRAG):**
- Retrieve -> Grade relevance -> If irrelevant: rewrite query + retry -> Generate
- Lightweight evaluator assesses retrieved document quality
- Confidence degree determines: accept documents OR trigger web search augmentation
- "Decompose-then-recompose" algorithm filters irrelevant content

**Self-RAG:**
- Model decides WHEN to retrieve (not always)
- Special "reflection tokens" for self-assessment
- Controllable during inference
- 7B/13B models surpassed ChatGPT on QA, reasoning, fact verification

**Adaptive RAG:**
- Routes between retrieval and direct response based on query classification
- No retrieval for simple queries; full RAG for complex ones

### 4.3 LangChain's RAG Pipeline Ordering
**Source:** LangChain blog "Deconstructing RAG"

Five sequential considerations:
1. **Query Transformations** -- Make retrieval robust to input variability
2. **Routing** -- Where does the data live?
3. **Query Construction** -- What syntax needed? (SQL, Cypher, metadata filters)
4. **Indexing** -- How to design the index? (chunk size, multi-vector, embedding strategy)
5. **Post-Processing** -- How to combine/rank retrieved documents?

**Key failure modes:**
- Semantic content split unnaturally across chunks
- Redundant documents consuming tokens without unique information
- Poor user question formulation hampering retrieval
- Single vectorstore assumptions

### 4.4 RAG Technique Progression (NirDiamant/RAG_Techniques)
**Source:** GitHub, 34 documented techniques

**Recommended progression:**
1. Start foundational (basic RAG)
2. Enhance queries (HyDE, transformations)
3. Enrich context (chunk headers, semantic chunking)
4. Deploy advanced retrieval (reranking, fusion)
5. Iterate intelligently (feedback loops, adaptive retrieval)
6. Architect sophisticatedly (GraphRAG, Self-RAG, CRAG)
7. Evaluate rigorously throughout

**Most impactful techniques:**
- Reranking (post-retrieval ranking significantly improves relevance)
- Semantic chunking (superior to fixed-size for contextual coherence)
- Query transformation (HyDE/HyPE generate synthetic documents)
- Multi-faceted filtering (metadata beyond semantic similarity)
- Feedback loops (iterative refinement from initial results)
- Combining multiple techniques outperforms any individual approach

---

## 5. Key Architectural Decisions

### 5.1 Question Decomposition: Before or After Retrieval?

**Consensus: BEFORE retrieval, with refinement DURING retrieval.**

Every major system decomposes first:
- GPT-Researcher: Planner generates questions before crawlers execute
- STORM: Perspective discovery and simulated conversations before outline
- Gemini: Planning phase before search execution
- dzhng: Query generation before search, with follow-up questions after
- LangChain: Scoping phase before research delegation

But all also refine during retrieval:
- Jina: Failed attempts inform next iteration
- CRAG: Rewrites query when documents are irrelevant
- Self-RAG: Decides adaptively when to retrieve more
- dzhng: Follow-up questions feed into next recursion level

### 5.2 Single Agent vs Multi-Agent

**Split opinion, with a trend toward simplicity:**

**Multi-agent advocates:**
- GPT-Researcher: 7 specialized agents with clear roles
- LangChain blog: "Isolation over coordination" -- multi-agent prevents context window exhaustion
- LlamaIndex: Document agents per source with meta-agent orchestrator

**Single-agent advocates:**
- Jina: Single reasoning loop with tools
- dzhng: Single recursive function
- HuggingFace: Single code agent
- Anthropic: "Find the simplest solution possible"
- LangChain Open Deep Research (latest): Evolved FROM multi-agent TO streamlined single-agent

**Emerging consensus:** Use multi-agent for the RESEARCH phase (parallelizable), but single-agent for SYNTHESIS (coherence requires unified context).

### 5.3 Iterative vs Single-Pass

**Unanimous: Iterative is mandatory for quality.**

Every system uses iteration:
- Gemini: 80-160 searches in loops
- GPT-Researcher: Reviewer-Reviser feedback loops
- STORM: Multi-perspective conversations accumulate knowledge
- Jina: Loop until token budget exhaustion
- dzhng: Recursive depth with narrowing breadth
- CRAG: Rewrite-and-retry on low confidence

### 5.4 Report Writing: Parallel Sections vs Sequential

**Consensus: Sequential/unified writing is better than parallel section writing.**

LangChain explicitly tested both: "Earlier parallel section-writing faced a problem...the reports were disjoint."

All current leading systems write reports in a single pass or with a single writing agent, using the full accumulated context.

### 5.5 Verification: Pre-synthesis vs Post-synthesis

**Emerging pattern: BOTH, but pre-synthesis filtering is more impactful.**

- CRAG: Evaluates retrieval quality BEFORE generation
- Self-RAG: Reflects on both retrieval AND generation
- GPT-Researcher: Reviewer validates DURING synthesis, triggers revision
- STORM: Polish phase AFTER generation, but knowledge curation acts as pre-filter

---

## 6. Common Pitfalls (From Practitioners)

### 6.1 Context Window Exhaustion
**Source:** LangChain, HuggingFace, multiple practitioners

"Long research traces exceed LLM context limits (128K tokens)" -- HuggingFace

**Solutions:**
- Sub-agents prune irrelevant findings before returning (LangChain)
- Token budget management (Jina)
- Summarization of intermediate steps
- Role separation (cheap models for summarization, expensive for reasoning)

### 6.2 False Confidence in Output Quality
**Source:** Simon Willison

"Surface-level presentation -- headings, citations, confident prose -- creates false impressions of expertise."

"The one thing that can't be easily spotted is misinformation by omission."

### 6.3 Tool Design Neglect
**Source:** Anthropic

"Tool specifications deserve as much attention as overall prompts."
- Avoid formats requiring precise counts (diff chunk headers)
- JSON requires excessive escaping; markdown is often better
- Poor tool docs lead to compounding errors
- Anthropic spent MORE time on tool design than prompt design for SWE-bench

### 6.4 Over-Engineering
**Source:** Anthropic, LangChain

LangChain explicitly evolved AWAY from complex "Plan-and-Execute" and "Supervisor-Researcher" patterns toward simpler architecture. The key insight: model capability improvements often make complex orchestration unnecessary.

### 6.5 Semantic Cache Poisoning
**Source:** Eugene Yan

Semantic similarity caching is "a disaster waiting to happen" without careful constraints. Use deterministic caching (IDs, metadata) rather than open-ended semantic matching.

### 6.6 Benchmark Gaming vs Real Quality
**Source:** Jason Wei, Eugene Yan

- Identical benchmarks yield different scores across implementations due to prompt/eval methodology variations
- LLM evaluators have position bias, verbosity bias, and self-enhancement bias
- "Skip off-the-shelf benchmarks for domain-specific tasks" -- Eugene Yan
- Evals need 1000+ examples to minimize noise

### 6.7 Code Actions vs JSON Actions
**Source:** HuggingFace

JSON-based tool calling scored 33% on GAIA; code-based scored 55.15% (+22 points). Code actions use 30% fewer tokens and are more expressive. This is the highest-impact optimization HuggingFace found.

### 6.8 Hybrid Search is Non-Negotiable
**Source:** Eugene Yan, Weaviate, multiple sources

"Hybrid retrieval (traditional search index + embedding-based search) works better than either alone." Keyword search handles exact matches (names, IDs); semantic search handles conceptual relationships.

---

## 7. Benchmarks and Results

### 7.1 GAIA Benchmark (Agent Research Capability)
| System | Avg Score | Level 3 (Hard) |
|--------|-----------|----------------|
| GPT-4 (no agent) | ~7% | - |
| Magentic-One (JSON actions) | 46% | - |
| HuggingFace Open Deep Research | 55.15% | 47.6% |
| OpenAI Deep Research | 67.36% | 47.6% |

### 7.2 Deep Research Bench (RACE Score)
| System | RACE Score | Cost |
|--------|------------|------|
| LangChain Open Deep Research (default) | 0.4309 | $45.98 |
| LangChain + GPT-5 | 0.4943 | - |
| LangChain + Claude Sonnet 4 | 0.4401 | $187.09 |

### 7.3 STORM Evaluation
- 25% absolute increase in organization vs retrieval-augmented baselines
- 10% improvement in coverage breadth
- Expert Wikipedia editors confirmed advantages
- Co-STORM: 70% preferred over search engines, 78% over RAG chatbots

### 7.4 GraphRAG
- Consistently outperforms baseline RAG on comprehensiveness, attribution, viewpoint diversity
- Similar faithfulness to baseline RAG
- Expensive to index

### 7.5 PaSa (Academic Paper Search Agent)
- 7B model outperforms GPT-4o-based approaches by 37.78% recall@20
- Learned agent search strategy beats prompt-based by large margin

### 7.6 Self-RAG
- 7B/13B models surpassed ChatGPT on open-domain QA, reasoning, fact verification
- Key: on-demand retrieval (only when beneficial) + reflection tokens

---

## 8. Synthesis: What Actually Works

### 8.1 The Consensus Architecture

Based on all sources, the architecture that has converged across practitioners:

```
Phase 1: PLANNING (Before any retrieval)
  - Decompose query into sub-questions
  - Discover perspectives (STORM pattern)
  - Generate diverse search queries
  - Optionally: user clarification (LangChain "Scope" phase)

Phase 2: RESEARCH (Iterative, parallelizable)
  - Execute web + academic searches (hybrid: keyword + semantic)
  - Fetch and extract content from sources
  - Evaluate retrieval quality (CRAG pattern)
  - If low quality: rewrite queries, search again
  - Accumulate findings, track provenance
  - Multi-agent parallelization for independent sub-topics
  - Sub-agents summarize/prune before returning (prevent context bloat)

Phase 3: VERIFICATION (Pre-synthesis filtering)
  - Grade evidence relevance and quality
  - Detect stubs, paywalls, low-content sources
  - Cross-reference claims across sources
  - Filter/rank evidence by tier

Phase 4: SYNTHESIS (Unified, not parallel)
  - Single agent/model writes report with full context
  - Structured by outline (derived from research, not pre-set)
  - Citations grounded in verified evidence
  - NOT parallel section writing (causes disjoint reports)

Phase 5: POLISH (Post-synthesis)
  - Review for quality, faithfulness, coverage
  - Revise if needed (evaluator-optimizer pattern)
  - Final citation resolution
  - Format and publish
```

### 8.2 The Ten Commandments of Deep Research Architecture

1. **Decompose BEFORE retrieval** -- Plan first, search second. Every successful system does this.

2. **Iterate with narrowing focus** -- Start broad, get progressively more specific. dzhng's "breadth halves with each depth level" is the cleanest pattern.

3. **Verify DURING retrieval, not just after** -- CRAG and Self-RAG patterns: evaluate document quality as you go, not just at the end.

4. **Use different models for different roles** -- STORM, LangChain, and GPT-Researcher all use cheaper models for summarization and expensive models for reasoning/synthesis.

5. **Prune aggressively between phases** -- Sub-agents must summarize before returning to the orchestrator. Context window exhaustion is the #1 pipeline killer.

6. **Write reports unified, not in parallel** -- LangChain tested parallel section writing and abandoned it because "the reports were disjoint."

7. **Hybrid search is mandatory** -- BM25 + embeddings beats either alone. Every production system uses both.

8. **Token budgets prevent runaway** -- Jina's "token budget exhaustion" pattern prevents infinite loops. Time and cost caps are essential.

9. **Simplicity wins** -- Anthropic, LangChain, and HuggingFace all evolved TOWARD simpler architectures. Model capability improvements often obviate complex orchestration.

10. **Tool design matters more than prompt design** -- Anthropic spent more time on tool interfaces than prompts for SWE-bench. Poor tool specs cause compounding errors.

### 8.3 Anti-Patterns to Avoid

1. **Single-pass retrieval** -- One search query, one set of results, then generate. Every benchmark shows this fails.

2. **Parallel section writing without shared context** -- Produces disjoint, incoherent reports.

3. **Fixed iteration counts** -- Let the agent decide when it has enough information (Gemini pattern) or use quality gates.

4. **LLM-only evaluation** -- "ChemCrow study showed LLM evaluation concluded near-equivalence, but human evaluation showed large margins" (Lilian Weng). Always validate with domain-specific metrics.

5. **Semantic caching without constraints** -- "A disaster waiting to happen" (Eugene Yan).

6. **Complex multi-agent orchestration for simple tasks** -- Start with single-agent + tools, add agents only when measurably needed.

7. **Ignoring retrieval quality** -- CRAG showed that "RAG relies heavily on the relevance of retrieved documents." Garbage in, garbage out.

8. **JSON tool calling when code actions are possible** -- 22-point GAIA improvement from code-based actions (HuggingFace).

---

## 9. Implications for POLARIS

### 9.1 Current POLARIS Architecture Assessment

POLARIS v2 pipeline: `plan -> search -> storm -> fetch -> crag -> outline -> blueprint -> write*N -> verify*N -> assemble`

**Alignment with consensus:**
- Planning before retrieval: YES (planner agent)
- Iterative research: YES (multiple search iterations)
- STORM-style perspective discovery: YES (storm_interviews)
- CRAG-style retrieval evaluation: YES (crag node)
- Verification: YES (verify step)
- Evidence filtering: YES (tier-based)

**Potential misalignments to investigate:**
1. **Write*N (parallel section writing)** -- The consensus strongly warns against this. LangChain abandoned it because "reports were disjoint." Consider unified writing with section-by-section emission from a single context.

2. **Verify AFTER write** -- The consensus favors verification DURING retrieval (pre-synthesis). POLARIS has CRAG for retrieval quality, but the heavy verify*N step is post-write. Consider moving more verification upstream.

3. **Model role separation** -- The consensus uses different models for different roles (cheap for summarization, expensive for reasoning). POLARIS routes everything through Kimi K2.5. Consider tiered model assignment.

4. **Token budget / runaway prevention** -- POLARIS has had issues with verifier runaway (V2_006: 170 rewrites) and unbounded evidence growth (3831 evidence in iter 4). The consensus solution is explicit token/time budgets that trigger "beast mode" (force synthesis).

5. **Outline generation timing** -- POLARIS generates outline before writing. The consensus (Gemini, dzhng) suggests the outline should EMERGE from research, not be pre-planned. However, STORM also uses explicit outline generation, so this is not clear-cut.

### 9.2 Strongest Improvement Opportunities

Based on the survey:

1. **Unified section writing** -- Replace `write*N` (parallel per-section) with a single writing agent that produces sections sequentially while maintaining narrative coherence. This was the single biggest lesson from LangChain's experience.

2. **Pre-synthesis evidence verification** -- Move the heavy verification step BEFORE outline/write. Verify evidence quality during the research phase, not after synthesis. This aligns with CRAG and Self-RAG patterns.

3. **Recursive narrowing research** -- Adopt dzhng's "breadth halves with depth" pattern for research iteration. Start with broad queries, progressively narrow based on gaps identified in accumulated knowledge.

4. **Sub-agent result pruning** -- Each research sub-task should aggressively summarize/filter before returning results. This prevents the context bloat issues POLARIS has experienced (3831 evidence items).

5. **Quality-gated iteration** -- Instead of fixed iteration counts, use quality gates that determine whether to continue researching or proceed to synthesis. The Gemini pattern of "agent decides when it has enough" is the most robust.

---

## Source Index

| # | Source | Type | Key Contribution |
|---|--------|------|------------------|
| 1 | github.com/assafelovic/gpt-researcher | GitHub | 7-agent pipeline, planner-executor split |
| 2 | docs.gptr.dev | Docs | Pipeline steps, cost analysis |
| 3 | GPT-Researcher LangGraph blog | Blog | Multi-agent orchestration patterns |
| 4 | arxiv.org/abs/2402.14207 (STORM) | Paper | Perspective-guided research, 25% org improvement |
| 5 | arxiv.org/abs/2408.15232 (Co-STORM) | Paper | Collaborative agent research, 70% preference |
| 6 | github.com/stanford-oval/storm engine.py | Code | 4-stage modular pipeline, multi-LLM |
| 7 | github.com/microsoft/graphrag | GitHub | Graph-based RAG, community clustering |
| 8 | microsoft.github.io/graphrag | Docs | Pipeline details, query modes |
| 9 | Microsoft Research blog | Blog | GraphRAG benchmarks, comprehensiveness |
| 10 | github.com/langchain-ai/open-deep-research | GitHub | 6-step pipeline, RACE score 0.4344 |
| 11 | blog.langchain.com (Open Deep Research) | Blog | 3-phase pipeline, multi-agent lessons |
| 12 | blog.langchain.com (Multi-Agent Research) | Blog | Nested graphs, conditional edges |
| 13 | blog.langchain.com (Deconstructing RAG) | Blog | 5 considerations, failure modes |
| 14 | huggingface.co/blog/open-deep-research | Blog | Code vs JSON actions, GAIA benchmarks |
| 15 | anthropic.com (Building Effective Agents) | Blog | 6 patterns, simplicity principle, tool design |
| 16 | ai.google.dev (Gemini Deep Research API) | Docs | Plan-Search-Read-Iterate, cost structure |
| 17 | Simon Willison (deep-research tag) | Blog | Commercial system analysis, hallucination risks |
| 18 | github.com/dzhng/deep-research | GitHub | Recursive breadth-depth pattern, <500 LoC |
| 19 | github.com/jina-ai/node-DeepResearch | GitHub | Token budget management, beast mode |
| 20 | github.com/nickscamara/open-deep-research | GitHub | Reasoning model separation |
| 21 | arxiv.org/abs/2401.15884 (CRAG) | Paper | Corrective retrieval, confidence evaluation |
| 22 | arxiv.org/abs/2310.11511 (Self-RAG) | Paper | On-demand retrieval, reflection tokens |
| 23 | arxiv.org/abs/2501.10120 (PaSa) | Paper | RL-trained search agent, 37% recall improvement |
| 24 | arxiv.org/abs/2501.09136 (Agentic RAG Survey) | Paper | Taxonomy of agentic RAG architectures |
| 25 | lilianweng.github.io (LLM Agents) | Blog | Task decomposition, memory systems, tool use |
| 26 | eugeneyan.com (LLM Patterns) | Blog | Hybrid retrieval, eval-driven dev, cache risks |
| 27 | jxnl.co (RAG Predictions) | Blog | Reports > Q&A, template-based generation |
| 28 | latent.space (2025 Papers) | Blog | Agent architecture components, memory systems |
| 29 | jasonwei.net (Evals) | Blog | Evaluation reliability, contamination risks |
| 30 | newsletter.maartengrootendorst.com | Blog | Test-time compute, process reward models |
| 31 | qdrant.tech (Agentic RAG) | Blog | Framework comparison, routing vs autonomous |
| 32 | llamaindex.ai (Agentic RAG) | Blog | Document agents, meta-agent orchestration |
| 33 | deeplearning.ai (Agentic RAG course) | Course | Progressive complexity: router -> tools -> agents |
| 34 | weaviate.io (RAG intro) | Blog | Pipeline stages, evaluation framework |
| 35 | promptingguide.ai (RAG) | Guide | 3 RAG paradigms, technique taxonomy |
| 36 | github.com/NirDiamant/RAG_Techniques | GitHub | 34 techniques, progression model |
| 37 | github.com/jxnl/instructor discussions | GitHub | Agentic workflow patterns, tool calling |
