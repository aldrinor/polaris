# POLARIS v3 Architecture Recommendation

**Date:** 2026-03-17
**Based on:** 80+ sources across 4 parallel research streams (production systems, academic papers, practitioner discussions, 2026 SOTA analysis)
**Purpose:** Define the optimal pipeline sequence for Gemini-level deep research quality

---

## The Verdict: Where POLARIS Is Right and Where It's Wrong

### What POLARIS Gets RIGHT (keep)
| Feature | Validation Source |
|---------|------------------|
| Planning before search | Every production system, every academic paper |
| STORM perspective discovery | Stanford STORM: +25% organization, +10% coverage |
| CRAG retrieval evaluation | CRAG paper: +6.9pp on PopQA vs Self-RAG |
| Evidence tiering (GOLD/SILVER/BRONZE) | All systems use quality-based evidence ranking |
| v1 sequential section writing | LangChain tested parallel, abandoned it: "reports were disjoint" |
| NLI-based verification | MiniCheck: 96x faster than LLM verification, comparable accuracy |
| Hybrid search (web + academic) | Eugene Yan: "Hybrid retrieval is non-negotiable in production" |

### What POLARIS Gets WRONG (must change)

| Current POLARIS | Industry Consensus | Evidence Strength |
|---|---|---|
| **Questions decomposed at SYNTHESIZE time** | Questions BEFORE + DURING search | Every system. "No system waits until after evidence to generate questions" |
| **Static outline (one-shot from clusters)** | Dynamic outline evolving with evidence | WebWeaver (ICLR 2026): "Neither search-then-outline nor outline-then-search is optimal" |
| **Verify in separate phase AFTER synthesis** | Verify DURING retrieval + DURING writing | "From Fluent to Verifiable" (2025): "Post-hoc verification does not scale" |
| **Single model for everything** | Different models for different roles | STORM, LangChain, GPT-Researcher all use tiered models |
| **No critic/reflection loop** | Critic agent drastically improves quality | Anthropic: multi-agent with critic >90% better. Self-RAG: removing critic "significantly degrades" |
| **Raw evidence accumulates unbounded** | Reflection-based context management | Tavily: 66% token savings via distill-then-discard pattern |
| **No query complexity routing** | Adaptive depth per sub-question | Adaptive-RAG: wrong strategy = wrong answers |

---

## The Recommended Pipeline

Based on convergence across all 80+ sources, here is the optimal sequence:

```
                    ┌─────────────────────────────┐
                    │  Phase 1: SCOPE + DECOMPOSE  │
                    │  (1-2 LLM calls, cheap model)│
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Phase 2: SEARCH + EXPLORE   │◄──────────┐
                    │  (parallel per sub-question) │           │
                    └──────────────┬──────────────┘           │
                                   │                          │
                    ┌──────────────▼──────────────┐           │
                    │  Phase 3: DYNAMIC OUTLINE    │───────────┘
                    │  (evolves with evidence)     │  gap found
                    └──────────────┬──────────────┘  → search more
                                   │
                    ┌──────────────▼──────────────┐
                    │  Phase 4: SYNTHESIZE         │
                    │  + INLINE VERIFICATION       │
                    │  + CRITIC LOOP               │
                    │  (sequential, expensive model)│
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │  Phase 5: ASSEMBLE + AUDIT   │
                    └─────────────────────────────┘
```

### Phase 1: SCOPE + DECOMPOSE
**Purpose:** Understand what to research before searching
**Model:** Cheap (query enrichment doesn't need expensive reasoning)
**Steps:**
1. Classify query complexity (Adaptive-RAG: simple/moderate/complex)
2. Decompose into 6-10 sub-questions as a DAG (Plan*RAG: +15.8% over iterative RAG)
3. Discover 5-8 perspectives (STORM: survey similar topics for diverse angles)
4. Generate 3-5 search queries per sub-question
5. Assign analytical focus per sub-question (aggregate/compare/explain/tabulate/challenge)

**What changes from current POLARIS:**
- Sub-questions drive search (currently: search drives everything)
- Perspectives inform query generation (currently: STORM happens after search)
- Analytical focus assigned upfront (currently: never assigned)

### Phase 2: SEARCH + EXPLORE (Iterative, 3-5 rounds)
**Purpose:** Collect evidence targeted at each sub-question
**Model:** Cheap for extraction, mid-tier for CRAG evaluation
**Steps per round:**
1. Execute searches per sub-question (parallel)
2. Fetch + extract content (parallel, with content quality gate)
3. CRAG evaluation per retrieval (correct/ambiguous/incorrect)
4. If incorrect → rewrite query, search again (CRAG corrective loop)
5. STORM interviews (1-2 rounds, interleaved with search)
6. **Distill findings into reflections** (Tavily pattern)
   - Compress each round's findings into key insights
   - Only reflections persist in context for next round
   - Raw sources tracked in separate store for Phase 4
7. Check evidence saturation (convergence = stop searching)

**What changes from current POLARIS:**
- Search is sub-question-targeted (currently: broad queries)
- CRAG evaluates and corrects during search (currently: CRAG is a separate node)
- Reflection-based context prevents token bloat (currently: all evidence accumulates)
- STORM interleaved with search (currently: separate sequential node)
- 3-5 rounds with convergence check (currently: fixed iterations)

### Phase 3: DYNAMIC OUTLINE (Interleaved with Phase 2)
**Purpose:** Structure the report around evidence, not assumptions
**Model:** Reasoning model (outline quality is high-leverage)
**Steps:**
1. After round 1 of search: generate initial outline from sub-questions + evidence
2. After round 2-3: refine outline based on new evidence (WebWeaver pattern)
3. Map evidence to sections using embedding similarity
4. Identify gaps: sections with <3 evidence pieces trigger targeted search (back to Phase 2)
5. Assign per-section: evidence bindings, confidence scores, analytical focus
6. Final outline = question-driven structure with evidence-proportional depth

**What changes from current POLARIS:**
- Outline generated DURING search, not after (currently: plan_report() called in synthesize node)
- Outline refines 2-3 times (currently: one-shot generation)
- Gap detection triggers more search (currently: search_gaps only after synthesis fails quality gate)
- Evidence mapped continuously (currently: _assign_evidence_to_sections() called once)

### Phase 4: SYNTHESIZE + INLINE VERIFY + CRITIC
**Purpose:** Write analytical report with continuous quality control
**Model:** Expensive reasoning model (this is where quality happens)
**Steps per section (sequential, NOT parallel):**
1. Retrieve raw source content for this section's evidence (Tavily: re-introduce raw at synthesis)
2. Format evidence with structured cards (methodology, conditions, comparable metrics)
3. Write section with analytical instructions (AGGREGATE/COMPARE/EXPLAIN/TABULATE/CHALLENGE)
4. **Inline verification:** Check each claim against evidence DURING writing (Self-RAG ISSUP pattern)
5. **Critic review:** Evaluate section for analytical depth, not just faithfulness
6. If critic finds deficiencies → rewrite with specific instructions
7. Move to next section with shared context (cross-section coherence)

**What changes from current POLARIS:**
- Verification happens DURING writing (currently: separate verify node AFTER all sections written)
- Critic evaluates each section (currently: no critic — quality gate only checks surface metrics)
- Sequential with shared context (v1 already does this — keep it)
- Raw sources re-introduced at synthesis (currently: evidence is what LLM sees, truncated)

### Phase 5: ASSEMBLE + AUDIT
**Purpose:** Final quality control and output
**Steps:**
1. Cross-section dedup and coherence transitions
2. Generate grounded abstract from actual report content
3. "Contradictions and Open Questions" section (surface what's unresolved)
4. Final citation audit (all citations resolve to real sources)
5. Quality gates: word count, citations, faithfulness, analytical depth
6. Forensic audit (audit_v3_report.py)

**What changes from current POLARIS:** Minor — this is largely what we already do.

---

## Model Routing Strategy

**The consensus is clear: use different models for different roles.**

| Role | Model Tier | Why | Cost Impact |
|------|-----------|-----|-------------|
| Query decomposition | Cheap (mini) | Simple task, many calls | -60% |
| Search query generation | Cheap (mini) | Template-based | -80% |
| Content extraction | Mid-tier | Needs comprehension | Neutral |
| CRAG evaluation | Small NLI model | Binary relevance judgment | -90% |
| Evidence card enrichment | Mid-tier | Structured extraction | Neutral |
| Outline generation | Expensive (reasoning) | High-leverage decision | Worth it |
| Section writing | Expensive (reasoning) | Quality-critical | Worth it |
| Critic review | Expensive (reasoning) | Judgment task | Worth it |
| Citation resolution | Cheap (mini) | Pattern matching | -80% |

**McKinsey estimate: Model routing reduces API costs 60-80% while maintaining >95% quality.**

Current POLARIS routes ALL calls through Qwen 3.5 Plus at $0.26/$1.56 per M tokens. A routed approach would use a cheaper model for ~70% of calls.

---

## What This Means for the v3 Sprint 1 Changes We Just Made

The 8 root cause fixes (RC-1 through RC-8) remain valid — they improve synthesis quality regardless of pipeline ordering. But they're treating symptoms of a deeper architectural problem:

| v3 Sprint Fix | Still Valid? | But... |
|---|---|---|
| RC-2: Analytical prompt | YES | Only affects write_section() — moves the needle at synthesis, but can't fix bad evidence |
| RC-3: Question decomposition | YES, but WRONG LOCATION | Should happen at Phase 1 (SCOPE), not Phase 4 (SYNTHESIZE). Currently questions can't influence search. |
| RC-1: Evidence cards | YES | Enrichment during analysis is correct timing |
| RC-6: Comparison tables | YES | Pre-formatted data for LLM is proven effective |
| RC-5: Surface contradictions | YES | But contradictions should be detected DURING search, not just surfaced at write time |
| RC-8: Depth gate | YES | Critic loop is better (evaluates during writing, not after) |
| RC-4: Content quality gate | YES | Should run during Phase 2 SEARCH, which it does |
| RC-7: Source diversity | YES, but WRONG LOCATION | Perspective queries should be part of Phase 1 DECOMPOSE, not appended after search |

**The honest assessment:** The v3 Sprint 1 changes improve output quality within the current architecture. But the architecture itself is the bottleneck. RC-3 (question decomposition) at synthesize time means questions can't drive search — they can only organize what was already found.

---

## Implementation Priority

### Option A: Incremental (Low risk, moderate improvement)
Keep current v1 graph. Enable v3 Sprint 1-4 flags. Measure improvement.
- **Pro:** Working code, proven stability, measurable
- **Con:** Questions still can't drive search. Outline still one-shot. No critic loop.
- **Expected improvement:** 30-40% gap closure (prompt fixes only)

### Option B: Architectural Rewrite (High risk, transformative)
Rebuild graph with the recommended 5-phase pipeline.
- **Pro:** Addresses root causes, not symptoms. Aligns with industry consensus.
- **Con:** Major rewrite. Risk of v2-style regression.
- **Expected improvement:** 80-95% gap closure

### Option C: Hybrid (Recommended)
Move question decomposition and outline generation earlier in the EXISTING graph, add critic loop, keep everything else.

Specific changes to v1 graph nodes:
1. **plan node:** Add sub-question decomposition + perspective-driven query generation (move RC-3 here)
2. **search node:** Target searches at sub-questions, not generic queries
3. **analyze node:** Keep CRAG + add evidence card enrichment (RC-1). Run content quality gate (RC-4).
4. **NEW: outline node** (after analyze, before synthesize): Generate outline from sub-questions + evidence. If gaps → loop back to search.
5. **synthesize node:** Write sequentially with analytical prompts (RC-2). Add inline critic per section (RC-8 upgraded).
6. **Remove separate verify node:** Fold verification INTO synthesize (inline verify per section)
7. **search_gaps node:** Driven by outline gaps, not quality gate failures

**Pro:** Moves the highest-leverage changes (question timing, outline timing, critic) without full rewrite.
**Con:** Still within LangGraph constraints. Not as clean as a fresh design.
**Expected improvement:** 60-75% gap closure

---

## The 10 Commandments of Deep Research Architecture
(Distilled from 80+ sources)

1. **Decompose BEFORE search** — Plan first, search second. Every successful system does this.
2. **The outline is a living document** — Not a one-time generation. Evolves with evidence. (WebWeaver, ICLR 2026)
3. **Verify DURING writing, not after** — Post-hoc verification cannot recover missing reasoning chains.
4. **Parallel search, sequential synthesis** — Research concurrently, write with full context. (95.6% of configs)
5. **A Critic agent is essential** — It drastically improves quality. (Anthropic, Self-RAG)
6. **Different models for different roles** — Cheap for extraction, expensive for reasoning. (60-80% cost savings)
7. **Prune aggressively between phases** — Context window exhaustion is the #1 pipeline killer.
8. **Token budgets prevent runaway** — Cap evidence, cap iterations, force synthesis when budget exhausted.
9. **Contradictions are features, not bugs** — Surface them explicitly. Disabling conflict resolution significantly lowers correctness.
10. **Simplicity wins** — Anthropic, LangChain, and HuggingFace all evolved TOWARD simpler architectures. Only add complexity when measurably justified.

---

## Sources Summary

### Production Systems Surveyed
- Stanford STORM (arXiv:2402.14207)
- GPT-Researcher (github.com/assafelovic/gpt-researcher, 25.7K stars)
- Tavily Deep Research (HuggingFace blog)
- OpenAI Deep Research (o3-deep-research)
- Google Gemini Deep Research (Gemini 3.1 Pro)
- Perplexity Deep Research (Sonar)
- LangChain Open Deep Research
- HuggingFace Open Deep Research (smolagents)
- Jina DeepResearch
- dzhng/deep-research
- Tongyi DeepResearch (Alibaba)
- WebWeaver (ICLR 2026)
- RhinoInsight

### Academic Papers Cited
- CRAG (ICLR 2025), Self-RAG (ICLR 2024 Oral), Adaptive-RAG (NAACL 2024)
- RAPTOR (ICLR 2024), GraphRAG (Microsoft 2024), Plan*RAG (2024)
- IRCoT (ACL 2023), RT-RAG (2025), Search-o1 (EMNLP 2025)
- HippoRAG (NeurIPS 2024), RQ-RAG (COLM 2024)
- "Searching for Best Practices in RAG" (EMNLP 2024)
- "From Fluent to Verifiable" (2025)
- A-RAG (2025), Modular RAG (2024)
- DeepResearch Bench, DRACO, DR.BENCH, DeepTRACE, DEFT

### Practitioner Sources
- Anthropic Engineering Blog ("Building Effective Agents")
- LangChain Blog ("Open Deep Research", "Deconstructing RAG")
- HuggingFace Blog (smolagents deep research)
- Simon Willison (deep research analysis)
- Eugene Yan (RAG best practices)
- Lilian Weng (LLM agent survey)
