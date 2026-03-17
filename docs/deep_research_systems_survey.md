# Deep Research Systems: Architectural Survey

**Date:** 2026-03-17
**Purpose:** Comprehensive architectural comparison of 6 modern AI deep research systems to inform POLARIS v2 architecture decisions.

---

## Executive Summary

This survey analyzes six production deep research systems across their pipeline architectures, questioning strategies, iterative refinement mechanisms, report structuring approaches, and published benchmarks. The key architectural finding is that modern systems fall into three paradigms: **(1) perspective-guided pre-writing** (STORM), **(2) planner-executor-publisher multi-agent** (GPT-Researcher), and **(3) single-agent ReAct loops** (OpenAI, Gemini, Perplexity). Tavily represents a fourth paradigm: **reflection-based context engineering** that achieves SOTA with 66% fewer tokens than traditional ReAct.

---

## Comparison Table

| Dimension | Stanford STORM | GPT-Researcher | Tavily | OpenAI Deep Research | Gemini Deep Research | Perplexity Deep Research |
|-----------|---------------|----------------|--------|---------------------|---------------------|------------------------|
| **Architecture Type** | Pipeline (4 modules) | Multi-agent (7 agents) | Reflection loop | Single-agent ReAct (4-agent API wrapper) | Single-agent ReAct | RAG pipeline + reasoning |
| **Core Model** | Configurable (cheap for conv, strong for writing) | gpt-4o-mini (plan) + gpt-4o (write) | Not disclosed | o3-deep-research | Gemini 3.1 Pro | Opus 4.5 / Sonar |
| **Questions BEFORE or AFTER evidence?** | BEFORE (perspective-guided) | BEFORE (planner generates sub-questions) | DURING (reflection loop) | BEFORE (clarification) + DURING (ReAct) | BEFORE (plan review) + DURING (iterative) | DURING (parallel decomposition) |
| **Iterative Refinement** | Multi-turn simulated conversations | Review-revise loop per section | Reflect-search-reflect loop | ReAct plan-act-observe loop | Plan-search-read-iterate loop | Multi-pass query refinement (3-5 passes) |
| **Typical Latency** | 2-5 min | ~5 min | Not disclosed | 5-30 min | 5-20 min (60 min max) | 2-4 min |
| **Typical Cost** | Low (open source) | ~$0.40/report | Not disclosed | $200/mo subscription | $20/mo subscription | $20/mo subscription |
| **Sources per run** | Varies (internet search) | 20+ web sources | Not disclosed | 30-60 searches | 80-160 searches, 100+ pages | Dozens of parallel searches |
| **Report Structure** | Wikipedia-style with TOC | 5-6 page structured report | Structured report | Structured with inline citations | Structured with citations, sections | Executive summary + key insights + citations |
| **Human-in-Loop** | No (automated) | Yes (review step) | No | Yes (clarification questions) | Yes (plan review/modification) | No (direct execution) |
| **Open Source** | Yes (MIT) | Yes (Apache-2.0) | No (API only) | No (API) | No (API) | No (API) |
| **Key Innovation** | Perspective-guided questioning | Tree-structured recursive exploration | Reflection-based context engineering | RL-trained extended reasoning | Async task manager with shared state | Vespa-powered hybrid retrieval |

---

## Detailed Architecture Analysis

### 1. Stanford STORM

**Paper:** "Assisting in Writing Wikipedia-like Articles From Scratch" (arXiv:2402.14207)
**Repo:** github.com/stanford-oval/storm
**Website:** storm-project.stanford.edu

#### Pipeline Sequence (4 Modules)

```
Topic Input
  |
  v
[Module 1: Knowledge Curation]
  |-- Step 1a: Perspective Discovery
  |     Survey existing articles on similar topics
  |     Extract table of contents from Wikipedia articles
  |     Identify 5-10 diverse perspectives/angles
  |
  |-- Step 1b: Simulated Conversations (per perspective)
  |     For each perspective:
  |       Wikipedia Writer (with perspective) asks questions
  |       Topic Expert (grounded in internet sources) answers
  |       Writer asks follow-up questions based on answers
  |       Continue for N turns (typically 3-5)
  |       Each answer triggers retrieval from trusted sources
  |
  v
[Module 2: Outline Generation]
  |-- Curate collected information from all conversations
  |-- Generate hierarchical outline structure
  |-- Organize by topic sections and subsections
  |
  v
[Module 3: Article Generation]
  |-- Populate each outline section with collected information
  |-- Add inline citations to retrieved sources
  |-- Generate section-by-section content
  |
  v
[Module 4: Article Polishing]
  |-- Refine for presentation quality
  |-- Ensure citation consistency
  |-- Final article output
```

#### Key Architectural Decisions

1. **Questions come BEFORE evidence in each conversation turn.** The perspective-guided writer formulates questions first, then the expert retrieves and answers. But the conversations themselves ARE the evidence collection mechanism -- questions and evidence collection are interleaved.

2. **Perspective discovery is the critical innovation.** Rather than asking generic questions, STORM discovers diverse angles (e.g., for "AI Ethics": philosopher, engineer, policymaker, affected community member) and has each perspective ask domain-specific questions.

3. **Two-model strategy:** Cheaper/faster models for simulated conversations (high volume), more powerful models for article generation (quality-critical).

4. **Co-STORM extension** adds real-time human participation: LLM Experts generate grounded answers, a Moderator produces thought-provoking questions, and humans can observe or inject utterances. Maintains a dynamic mind map organizing collected information hierarchically.

#### Benchmarks

| Metric | Score |
|--------|-------|
| Organization (vs. baseline) | +25% absolute improvement |
| Coverage breadth (vs. baseline) | +10% improvement |
| FreshWiki dataset | 100 articles, heading soft recall + heading entity recall |
| Primary error type | Source bias transfer (not hallucination) |

---

### 2. GPT-Researcher

**Repo:** github.com/assafelovic/gpt-researcher (25.7K stars)
**Docs:** docs.gptr.dev

#### Pipeline Sequence (Standard Mode: 5 Phases)

```
User Query
  |
  v
[Phase 1: Planning]
  |-- ResearchConductor analyzes query
  |-- Planner (STRATEGIC_LLM / gpt-4o-mini) decomposes into sub-questions
  |-- plan_research_outline() generates sub-queries
  |-- Sub-queries designed to "form an objective opinion"
  |
  v
[Phase 2: Data Gathering] (Parallel)
  |-- For each sub-question (concurrent):
  |     Search via configured retrievers (Tavily, Google, DuckDuckGo)
  |     Scrape URLs via BrowserManager (JavaScript rendering)
  |     Load local documents (if report_source="local" or "hybrid")
  |     Query MCP servers (if configured)
  |
  v
[Phase 3: Context Processing]
  |-- Embed all gathered content
  |-- Similarity-based compression to relevant chunks
  |-- Filter by relevance to original query
  |
  v
[Phase 4: Generation] (SMART_LLM / gpt-4o)
  |-- Synthesize report from compressed context
  |-- Optional image generation
  |-- Inline citations from tracked sources
  |
  v
[Phase 5: Output]
  |-- Format conversion (PDF, DOCX, Markdown)
  |-- Publish
```

#### Deep Research Mode (Tree Exploration)

```
User Query + Config(breadth=4, depth=2, concurrency=4)
  |
  v
[Level 0: Breadth Exploration]
  |-- Generate N=breadth search queries (diverse aspects)
  |-- Execute all queries concurrently (semaphore-limited)
  |-- Extract learnings from each result set
  |
  v
[Level 1: Depth Diving] (Recursive)
  |-- For each promising branch:
  |     Generate follow-up questions based on learnings
  |     Execute deeper searches with reduced breadth (breadth/2)
  |     Extract additional learnings
  |     Aggregate into branch context
  |
  v
[Level 2+: Continue recursion until depth=0]
  |
  v
[Synthesis]
  |-- Trim to word limit while retaining most relevant findings
  |-- Generate final report
```

#### Multi-Agent Mode (7 Agents via LangGraph)

| Agent | Role | Model |
|-------|------|-------|
| ChiefEditorAgent | Master orchestrator | STRATEGIC_LLM |
| EditorAgent | Generates research outline + sections | STRATEGIC_LLM |
| ResearchAgent | Deep research per section | SMART_LLM |
| ReviewerAgent | Validates draft quality | SMART_LLM |
| ReviserAgent | Improves drafts from feedback | SMART_LLM |
| WriterAgent | Compiles sections + intro/conclusion | SMART_LLM |
| PublisherAgent | Format conversion | N/A |

**Review-Revision Loop:** ResearchAgent -> ReviewerAgent -> ReviserAgent -> (loop until quality passes) -> WriterAgent -> PublisherAgent

#### Key Architectural Decisions

1. **Questions come BEFORE evidence.** The planner generates all sub-questions upfront before any search occurs.
2. **Parallel execution** of searches per sub-question.
3. **Embedding-based compression** reduces context before LLM synthesis.
4. **Deep Research mode uses tree-structured recursion** with decreasing breadth at each depth level.

#### Benchmarks

| Benchmark | GPT-Researcher | Notes |
|-----------|----------------|-------|
| DeepResearchGym (CMU, May 2025) | #1 overall | Beat Perplexity, OpenAI, OpenDeepSearch, HuggingFace |
| Citation quality | Highest | CMU evaluation |
| Report quality | Highest | CMU evaluation |
| Cost per report | ~$0.40 | vs $200/mo for OpenAI |
| Time per report | ~5 minutes | Standard mode |

---

### 3. Tavily Deep Research

**Blog:** tavily.com/blog/research-en/ (also on HuggingFace)
**API:** tavily.com

#### Pipeline Sequence (Reflection Loop)

```
User Query
  |
  v
[Iteration 1..N: Reflect-Search-Reflect Loop]
  |
  |-- [Search]: Tavily Advanced Search
  |     Returns pre-processed, relevant content chunks
  |     (not raw HTML -- context-managed retrieval)
  |
  |-- [Distill]: Compress findings into reflections
  |     Tool outputs -> key insights (short summaries)
  |     Only reflections persist in context window
  |     Raw tool outputs are DISCARDED from context
  |
  |-- [Reflect]: Evaluate coverage
  |     Use ONLY past reflections as context
  |     Decide: search more or generate report?
  |     If scope narrowing -> explore untapped domains
  |     If sufficient -> proceed to generation
  |
  v (repeat until convergence)
  |
[Final Generation]
  |-- Re-introduce RAW source content (not just reflections)
  |-- This prevents information loss during synthesis
  |-- Generate structured report with citations
  |-- Source attribution from global state tracking
```

#### Token Efficiency Innovation

```
Traditional ReAct (quadratic growth):
  Total tokens = n + 2n + 3n + ... + mn = n * m(m+1)/2

Tavily Reflection (linear growth):
  Total tokens = n + n + n + ... + n = n * m

Savings factor = (m+1)/2
  Example: 10 iterations = 5.5x token savings = 66% reduction
```

#### Key Architectural Decisions

1. **Questions emerge DURING the reflection loop**, not upfront. The system collects, reflects, and decides what to search next iteratively.
2. **Context engineering is the core innovation.** By keeping only reflections (not raw outputs) in context, they achieve linear rather than quadratic token scaling.
3. **Source deduplication via global state** prevents revisiting the same information and detects when scope is narrowing.
4. **Raw content returns only at final generation** to ensure no information loss.
5. **Failure modes are first-class design considerations**, not afterthoughts.

#### Benchmarks

| Benchmark | Tavily Research | Notes |
|-----------|----------------|-------|
| DeepResearch Bench | #1 (SOTA at time of publication) | Leaderboard on HuggingFace |
| Token efficiency | 66% reduction vs Open Deep Research | Linear vs quadratic scaling |
| Optimization target | Directional feedback + reliability | Not benchmark scores |

---

### 4. OpenAI Deep Research

**API:** platform.openai.com/docs/guides/deep-research
**Blog:** openai.com/index/introducing-deep-research/
**Cookbook:** developers.openai.com/cookbook/examples/deep_research_api/

#### Pipeline Sequence (API: 4-Agent Orchestration)

```
User Query
  |
  v
[Agent 1: Triage Agent] (gpt-4o-mini)
  |-- Evaluates: Does the query have enough context?
  |-- Route A: Needs clarification -> transfer to Clarification Agent
  |-- Route B: Sufficient context -> transfer to Instruction Agent
  |
  v (if Route A)
[Agent 2: Clarification Agent] (gpt-4o-mini)
  |-- Generates structured follow-up questions
  |-- Collects user responses
  |-- Enriches original query with additional context
  |-- Transfers to Instruction Agent
  |
  v
[Agent 3: Instruction Agent] (gpt-4o-mini)
  |-- Converts enriched query into precise research brief
  |-- Specifies scope, depth, format requirements
  |-- Transfers to Research Agent
  |
  v
[Agent 4: Research Agent] (o3-deep-research-2025-06-26)
  |-- Executes ReAct loop: Plan -> Act -> Observe -> Repeat
  |
  |-- [Plan]: Decompose into sub-questions
  |     Create internal research strategy
  |     Identify subtopics and investigation order
  |
  |-- [Act]: Execute tools
  |     WebSearchTool: Bing Search for web sources
  |     HostedMCPTool: Internal document retrieval (optional)
  |     Code Interpreter: Python for calculations/visualizations
  |     File parser: PDF, images, HTML
  |
  |-- [Observe]: Process results
  |     Read returned webpages
  |     Extract relevant information
  |     Identify gaps in coverage
  |
  |-- [Iterate]: Progressive refinement
  |     Backtrack from dead ends (paywalls, irrelevant results)
  |     Pivot strategies based on new information
  |     Continue until coverage-based stopping condition
  |
  v
[Output]
  |-- Structured report with inline citations
  |-- Every factual claim accompanied by citation
  |-- Multimodal support (text, images, tables)
```

#### Stopping Conditions
- **Coverage-based:** Sufficient sources per sub-question
- **Hard limits:** 20-30 minute wall-clock time; 30-60 search calls maximum

#### Key Architectural Decisions

1. **Questions come BEFORE evidence (clarification phase)** AND **DURING evidence collection (ReAct loop).** Two-stage questioning.
2. **Single reasoning agent (o3)** does all the heavy lifting. The 4-agent API wrapper is just for query enrichment.
3. **RL-trained for research:** The model was trained via end-to-end reinforcement learning in simulated research environments with real tools.
4. **Extended chain-of-thought** maintains focus through lengthy reasoning chains without hallucinating.
5. **Cost optimization:** Cheap models (gpt-4o-mini) handle triage/clarification/instruction; expensive model (o3) only for actual research.

#### Benchmarks

| Benchmark | OpenAI Deep Research | Notes |
|-----------|---------------------|-------|
| Humanity's Last Exam (HLE) | 26.6% | Best among deep research systems |
| GAIA Level 1 | 78.66% | Real-world problem solving |
| GAIA Level 2 | 73.21% | |
| GAIA Level 3 | 58.03% | |
| GAIA Average | 72.57% | Previous best: 63.64% |
| DeepResearch Bench (RACE) | 46.98 | #2 behind Gemini (48.88) |
| DeepResearch Bench (Instruction-Following) | 49.27 | #1 |
| Professional assessment | "Better than intern work" | Blind test by professionals |

---

### 5. Google Gemini Deep Research

**API:** ai.google.dev/gemini-api/docs/deep-research
**Blog:** blog.google/technology/developers-tools/deep-research-agent-gemini-api/

#### Pipeline Sequence

```
User Query
  |
  v
[Step 1: Query Analysis + Plan Generation]
  |-- AI analyzes research question
  |-- Creates structured research plan with subtopics
  |-- Breaks problem into sub-tasks
  |-- Determines parallel vs sequential execution order
  |
  v
[Step 2: Plan Review] (Human-in-loop)
  |-- User examines proposed strategy
  |-- Can add, remove, or modify sections
  |-- Approve to proceed
  |
  v
[Step 3: Iterative Search + Read Loop]
  |-- For each sub-task:
  |     Formulate search queries (google_search tool)
  |     Read results (url_context tool)
  |     Identify knowledge gaps
  |     Search again for missing information
  |     Ground on all information gathered so far
  |
  |-- Typical scale:
  |     Standard: ~80 search queries, ~250K input tokens
  |     Complex: ~160 search queries, ~900K input tokens
  |     Token caching: 50-70% of input tokens cached
  |
  v
[Step 4: Analysis + Synthesis]
  |-- Analyze patterns across all gathered information
  |-- Extract key insights
  |-- Powered by Gemini 3.1 Pro's 1M token context window
  |
  v
[Step 5: Report Generation]
  |-- Structured report: intro, main sections, analysis, conclusions
  |-- Properly formatted citations
  |-- Real-time progress updates during generation
```

#### API Implementation

```
interactions.create(background=true, stream=true)
  -> interaction.start event (capture interaction_id)
  -> thinking_summaries (real-time progress)
  -> interaction.complete event
  -> Follow-up: previous_interaction_id for clarifications
```

#### Async Task Manager Innovation

Google developed a novel asynchronous task manager that maintains shared state between the planner and task models. This enables:
- Graceful error recovery without restarting entire tasks
- Decoupled initiation and result retrieval
- Stateful polling architecture
- Reconnection via `last_event_id`

#### Key Architectural Decisions

1. **Questions come BEFORE evidence (plan phase)** AND **DURING evidence collection (iterative search).** Human reviews the plan before execution.
2. **Single-agent architecture** -- one Gemini 3.1 Pro model handles planning, searching, reading, and reasoning.
3. **Trained via multi-step reinforcement learning for search** -- autonomous navigation of complex information landscapes.
4. **Strongest factuality model** -- Gemini 3 Pro specifically trained to minimize hallucinations.
5. **60-minute maximum window** -- typically completes in ~20 minutes.

#### Benchmarks

| Benchmark | Gemini Deep Research | Notes |
|-----------|---------------------|-------|
| DeepResearch Bench (RACE Overall) | 48.88 | #1 among all deep research agents |
| DeepResearch Bench (Effective Citations) | 111.21 | Exceptional citation density |
| Searches per task (standard) | ~80 | With ~250K input tokens |
| Searches per task (complex) | ~160 | With ~900K input tokens |
| Typical completion time | ~20 min | 60 min maximum |

---

### 6. Perplexity Deep Research

**API:** docs.perplexity.ai (Sonar Deep Research model)
**Blog:** perplexity.ai/hub/blog/introducing-perplexity-deep-research
**Benchmark:** DRACO (perplexity.ai)

#### Pipeline Sequence (5 Stages)

```
User Query
  |
  v
[Stage 1: Query Intent Parsing]
  |-- LLM parses semantic intent (not keyword matching)
  |-- Interprets context, nuance, and underlying goal
  |-- No clarification step -- direct execution
  |
  v
[Stage 2: Query Decomposition]
  |-- Split query into subtopics/dimensions
  |-- Generate parallel sub-queries per dimension
  |-- Dispatch sub-queries concurrently
  |
  v
[Stage 3: Multi-Stage Retrieval] (Parallel, 3-5 passes)
  |-- Pass 1: Broad retrieval
  |     Hybrid search: lexical + semantic (Vespa AI engine)
  |     Merge into hybrid candidate set (high recall)
  |
  |-- Prefiltering: Remove non-responsive content
  |
  |-- Multi-stage ranking:
  |     Early: Lexical + embedding-based scorers (speed)
  |     Later: Cross-encoder reranker models (quality)
  |
  |-- Pass 2-5: Refined queries based on gaps found
  |     Cross-reference findings for accuracy
  |     Flag conflicting claims for double-checking
  |
  v
[Stage 4: Synthesis]
  |-- Structured notes from partial answers
  |-- Conflict resolution across sources
  |-- Claim extraction and evidence aggregation
  |
  v
[Stage 5: Report Generation]
  |-- Citation-aware summarization
  |-- Executive summary
  |-- Key insights with timelines
  |-- Actionable recommendations
  |-- Reliability/uncertainty notes
  |-- Verifiable source links
```

#### Key Architectural Decisions

1. **Questions come DURING search**, not before. No upfront clarification -- direct parallel decomposition and search.
2. **Speed-optimized architecture** -- most tasks complete in 2-4 minutes (fastest among all systems).
3. **Vespa AI powers retrieval** -- massive-scale hybrid search combining vector search, lexical search, structured filtering, and ML-based ranking.
4. **Multi-stage ranking pipeline** progressively refines from high-recall to high-precision.
5. **Source traceability is first-class** -- users can inspect where every claim comes from.

#### Benchmarks

| Benchmark | Perplexity Deep Research | Notes |
|-----------|------------------------|-------|
| Humanity's Last Exam (HLE) | 21.1% | Behind OpenAI (26.6%) |
| SimpleQA factuality | 93.9% | Factuality leader among AI search tools |
| Hallucination rate | <3.5% | |
| DeepResearch Bench (Citation Accuracy) | 90.24% | #1 in citation precision |
| DeepResearch Bench (RACE Overall) | 42.25 | #4 among deep research agents |
| DRACO benchmark | Published own benchmark | Cross-Domain Accuracy, Completeness, Objectivity |
| Typical completion time | 2-4 min | Fastest among all systems |

---

## Cross-System Analysis

### When Do Questions Happen?

| System | Pre-Research Questions | During-Research Questions | Post-Research Refinement |
|--------|----------------------|--------------------------|-------------------------|
| STORM | Perspective discovery (question types defined upfront) | Simulated conversation follow-ups (interleaved) | No |
| GPT-Researcher | Planner generates all sub-questions upfront | No (standard mode); Yes (deep research tree mode) | Review-revise loop |
| Tavily | No | Reflection loop generates new queries iteratively | Raw source re-read at final generation |
| OpenAI | Clarification agent asks user | ReAct loop generates queries iteratively | No (single pass) |
| Gemini | Plan generation + human review | Iterative search generates gap-filling queries | Follow-up via previous_interaction_id |
| Perplexity | No (direct execution) | 3-5 progressive search passes with refined queries | No |

### How They Handle Iterative Refinement

| System | Mechanism | Iterations | What Changes Between Iterations |
|--------|-----------|------------|-------------------------------|
| STORM | Multi-turn simulated conversations | 3-5 turns per perspective | Follow-up questions based on previous answers |
| GPT-Researcher | Review-revise loop (multi-agent); Recursive tree (deep mode) | Until quality passes; depth=2 default | Reviewer feedback improves drafts; deeper subtopic exploration |
| Tavily | Reflect-search-reflect | Until convergence | Only reflections (not raw data) inform next iteration; 66% fewer tokens |
| OpenAI | ReAct plan-act-observe | 30-60 search calls max, 20-30 min max | Backtrack from dead ends; pivot strategies based on findings |
| Gemini | Plan-search-read-iterate | ~80-160 searches over ~20 min | Gap identification; ground on all prior info before next search |
| Perplexity | Multi-pass query refinement | 3-5 passes | Refine queries based on what data is missing |

### Report Structure Comparison

| System | Report Type | Typical Length | Citation Style | Unique Feature |
|--------|-------------|---------------|----------------|----------------|
| STORM | Wikipedia-style article | Long-form | Inline references | Table of contents, hierarchical sections |
| GPT-Researcher | Structured research report | 5-6 pages | Source attribution | Section-by-section with intro/conclusion |
| Tavily | Structured report | Not disclosed | Source attribution | Source deduplication via global state |
| OpenAI | Comprehensive report | Up to 15K+ words | Inline citations per claim | Multimodal (text, images, code, tables) |
| Gemini | Structured report | Long-form | Formatted citations | Real-time progress updates |
| Perplexity | Analyst-style report | Medium-form | Verifiable source links | Executive summary + uncertainty notes |

---

## DeepResearch Bench Leaderboard (Published Results)

### RACE Framework (Report Quality)

| Rank | System | Overall | Comprehensiveness | Depth | Instruction-Following | Readability |
|------|--------|---------|-------------------|-------|-----------------------|-------------|
| 1 | Gemini-2.5-Pro DR | 48.88 | - | - | - | - |
| 2 | OpenAI Deep Research | 46.98 | - | - | 49.27 (#1) | - |
| 3 | Perplexity Deep Research | 42.25 | - | - | - | - |
| 4 | Grok Deeper Search | 40.24 | - | - | - | - |
| 5 | Claude-3.7-Sonnet w/Search | 40.67 | - | - | - | - |

### FACT Framework (Citation Quality)

| Metric | Best System | Score |
|--------|-------------|-------|
| Effective Citations (count) | Gemini-2.5-Pro DR | 111.21 |
| Citation Accuracy (%) | Perplexity DR | 90.24% |

### Other Benchmarks

| Benchmark | #1 System | #1 Score | #2 System | #2 Score |
|-----------|-----------|----------|-----------|----------|
| Humanity's Last Exam (HLE) | OpenAI DR | 26.6% | Perplexity DR | 21.1% |
| GAIA (real-world) | OpenAI DR | 72.57% avg | Previous best | 63.64% |
| SimpleQA (factuality) | Perplexity DR | 93.9% | - | - |
| DeepResearchGym (CMU) | GPT-Researcher | #1 overall | - | - |
| DeepResearch Bench (SOTA) | Tavily Research | #1 at publication | - | - |

---

## Key Architectural Patterns for POLARIS v2

### Pattern 1: Reflection-Based Context Engineering (Tavily)
- **Takeaway:** Do not propagate raw tool outputs through the loop. Distill into reflections. Re-introduce raw sources only at final generation.
- **Token savings:** 66% reduction, linear vs quadratic scaling.
- **POLARIS applicability:** HIGH. Our current pipeline accumulates all evidence in state, leading to context bloat.

### Pattern 2: Perspective-Guided Pre-Writing (STORM)
- **Takeaway:** Discover diverse perspectives BEFORE generating questions. Each perspective drives a focused conversation that generates both questions AND evidence simultaneously.
- **POLARIS applicability:** HIGH. Our STORM interviews already implement this. Could be enhanced with better perspective discovery.

### Pattern 3: Plan-Review-Execute (Gemini)
- **Takeaway:** Generate a research plan, let the user (or quality gate) review/modify it, then execute with iterative gap-filling.
- **POLARIS applicability:** MEDIUM. We lack a plan review step. Adding one could prevent wasted search effort.

### Pattern 4: Query Enrichment Before Expensive Research (OpenAI)
- **Takeaway:** Use cheap models for triage/clarification/instruction. Only invoke expensive research models with enriched, well-scoped queries.
- **POLARIS applicability:** HIGH. Our planner could pre-enrich queries before expensive search+analysis.

### Pattern 5: Tree-Structured Recursive Exploration (GPT-Researcher)
- **Takeaway:** Breadth-first then depth-first exploration with decreasing breadth at each level. Concurrent processing with semaphore-based limits.
- **POLARIS applicability:** MEDIUM. Could replace our flat search approach with hierarchical exploration.

### Pattern 6: Multi-Stage Retrieval Ranking (Perplexity)
- **Takeaway:** Progressive refinement from high-recall retrieval through lexical/embedding scoring to cross-encoder reranking.
- **POLARIS applicability:** HIGH. Our current relevance filtering is single-stage. Multi-stage would improve precision.

---

## Critical Decision: Questions Before vs. During vs. After Evidence

The survey reveals a clear industry consensus:

1. **Pre-research questions (planning/decomposition):** All systems except Tavily and Perplexity generate some form of plan or sub-questions before searching. This improves search focus.

2. **During-research questions (iterative):** All systems except basic GPT-Researcher standard mode generate new questions during research based on findings. This fills gaps.

3. **No system waits until after all evidence is collected to generate questions.** The "collect everything first, then analyze" approach is obsolete.

**Recommendation for POLARIS:** Adopt a hybrid approach:
- Phase 1: Perspective-guided question generation (like STORM)
- Phase 2: Parallel search with reflection-based context (like Tavily)
- Phase 3: Gap-filling iterative search (like OpenAI/Gemini)
- Phase 4: Report synthesis with raw source re-introduction (like Tavily)

---

## Sources

### Stanford STORM
- [Stanford STORM Research Project](https://storm-project.stanford.edu/research/storm/)
- [GitHub: stanford-oval/storm](https://github.com/stanford-oval/storm)
- [arXiv:2402.14207 - STORM Paper](https://arxiv.org/abs/2402.14207)

### GPT-Researcher
- [GitHub: assafelovic/gpt-researcher](https://github.com/assafelovic/gpt-researcher)
- [DeepWiki: GPT-Researcher Architecture](https://deepwiki.com/assafelovic/gpt-researcher)
- [GPT-Researcher Deep Research Blog](https://docs.gptr.dev/blog/2025/02/26/deep-research)
- [Deep Web Research with AG2 and GPT Researcher](https://docs.ag2.ai/latest/docs/blog/2026/03/03/GPT-Researcher-AG2/)

### Tavily
- [Building Deep Research: How we Achieved SOTA (HuggingFace)](https://huggingface.co/blog/Tavily/tavily-deep-research)
- [Tavily Blog: Building Deep Research](https://tavily.com/blog/research-en/)

### OpenAI Deep Research
- [How OpenAI's Deep Research Works (PromptLayer)](https://blog.promptlayer.com/how-deep-research-works/)
- [OpenAI Deep Research API Cookbook](https://developers.openai.com/cookbook/examples/deep_research_api/introduction_to_deep_research_api_agents)
- [OpenAI Deep Research API Guide](https://platform.openai.com/docs/guides/deep-research)
- [Helicone: OpenAI Deep Research Comparison](https://www.helicone.ai/blog/openai-deep-research)

### Google Gemini Deep Research
- [Gemini Deep Research API Docs](https://ai.google.dev/gemini-api/docs/deep-research)
- [Google Blog: Build with Gemini Deep Research](https://blog.google/innovation-and-ai/technology/developers-tools/deep-research-agent-gemini-api/)
- [Gemini Deep Research Complete Guide 2025](https://www.digitalapplied.com/blog/google-gemini-deep-research-guide)

### Perplexity Deep Research
- [Perplexity Help Center: Pro Search](https://www.perplexity.ai/help-center/en/articles/10352903-what-is-pro-search)
- [Perplexity: Sonar Deep Research](https://docs.perplexity.ai/getting-started/models/models/sonar-deep-research)
- [DRACO Benchmark Paper](https://r2cdn.perplexity.ai/pplx-draco.pdf)
- [PUNKU.AI: Full Benchmark Comparison](https://www.punku.ai/blog/comprehensive-analysis-deep-research-implementations)

### Cross-System Surveys
- [HuggingFace: Deep Research Technology Survey](https://huggingface.co/blog/exploding-gradients/deepresearch-survey)
- [arXiv: Comprehensive Survey of Deep Research Systems](https://arxiv.org/html/2506.12594v1)
- [DeepResearch Bench](https://deepresearch-bench.github.io/)
- [Egnyte: Inside the Architecture of a Deep Research Agent](https://www.egnyte.com/blog/post/inside-the-architecture-of-a-deep-research-agent)
