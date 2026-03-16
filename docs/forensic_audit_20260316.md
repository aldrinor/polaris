# POLARIS Forensic Audit: March 16, 2026

## The Brutal Truth

3 E2E runs. $16.11 spent. Zero complete output. The problems are architectural, not bugs.

---

## Part 1: What Gemini/ChatGPT Do vs What We Do

### The Fundamental Difference

| Aspect | Gemini Deep Research | ChatGPT Deep Research | POLARIS |
|--------|---------------------|----------------------|---------|
| Architecture | Single agent, continuous reasoning loop | Single agent, RL-trained tool use | 8-node LangGraph sequential pipeline |
| Models | 1 model (Gemini Pro) | 1 model (o3) | 1 model (Kimi K2.5/Qwen) for everything |
| Extraction | Inline during reasoning | Inline during reasoning | **744 separate LLM calls** |
| Citation | Inline during synthesis | Inline during synthesis | **Separate post-synthesis pass (42 min)** |
| Verification | Self-correcting via RL training | Self-correcting via RL training | **Separate NLI + LLM verification passes** |
| Timeout | Server-side hard kill | Tool call budget + hard kill | **Checked at node boundaries only** |
| Completion | 5-20 minutes | 5-30 minutes | **200+ minutes** |
| Cost/query | $2-5 | $1.30-3.40 | **$6-8 (with zero output)** |
| Context | 1M token window holds everything | 200K context | **JSON serialization between every node** |
| Progress | Streaming events throughout | All intermediate steps exposed | **42-min dark zone with no events** |

### The Core Insight

Gemini and ChatGPT have **no separate extraction phase**. The model reads source content, reasons about relevance, extracts key facts, and writes the report — all in one continuous inference session. Our 744 extraction calls are an anti-pattern that doesn't exist in any production deep research system.

Both systems also do **inline citation** during synthesis. The LLM inserts `[1]`, `[2]` as it writes. No separate citation resolution pass. No 42-minute dark zone.

Neither system runs **separate verification passes**. Their models are trained via RL to self-correct. We run NLI verification, LLM verification, hallucination detection, AND quality gate expansion — 4 separate verification mechanisms, none of which Gemini or ChatGPT use.

---

## Part 2: The 5 Root Causes (With Solutions From Best Practice)

### RC-1: Structured Data Extraction is Catastrophically Expensive

**Problem:** 744 LLM calls at 110s each = $4.45 (53% of budget)
**Why it exists:** We extract structured data from EVERY source in a separate LLM call
**How Gemini solves it:** No separate extraction. Reading + extraction + reasoning in one loop.

**Solution (Priority 1):** Eliminate per-source extraction entirely. Two options:
- **Option A (Inline):** Include source content in the synthesis prompt. The LLM extracts as it writes sections. 744 calls -> 15 calls (one per section).
- **Option B (Batch):** Group 10-20 sources per extraction call using a mini model ($0.40/M input). 744 calls -> 40 calls at 1/10th the cost.

**Expected impact:** $4.45 -> $0.20-0.50. 200 min -> 10-20 min.

### RC-2: Timeout Not Enforced

**Problem:** max_execution_minutes=60 but runs go 200-267 minutes
**Why it exists:** Timeout only checked at LangGraph node boundaries. Long nodes blow past.
**How OpenAI solves it:** Tool call budget (max_tool_calls) + server-side hard kill.

**Solution (Priority 4):**
- **Immediate:** Wrap every LLM call in `asyncio.wait_for(coro, timeout=deadline-now)`. Calculate remaining time from a monotonic deadline.
- **Better:** Replace time budget with **call budget**. Set `max_llm_calls=150`, `max_search_calls=80`. Deterministic and testable.
- **Best:** Depth presets: `rapid` (20 evidence, 30 min), `balanced` (100 evidence, 60 min), `deep` (500 evidence, 120 min).

### RC-3: 42-Minute Dark Zone

**Problem:** 6 sequential post-synthesis operations with no trace events
**Why it exists:** Citation resolution, revision, quality audit all run as separate passes
**How Gemini solves it:** Inline citation during synthesis. No post-synthesis passes.

**Solution (Priority 5):**
- **Immediate:** Add trace events before/after each of the 6 operations
- **Better:** Inline citations during synthesis (include source content in prompt, LLM inserts [N] as it writes)
- **Best:** Eliminate non-essential passes entirely. Gemini runs ZERO separate verification passes.

### RC-4: 8-Node Sequential Pipeline

**Problem:** plan->search->storm->analyze->verify->evaluate->synthesize->search_gaps = 200+ min minimum
**Why it exists:** Each node runs to completion before the next starts
**How Gemini solves it:** Single continuous reasoning loop. No inter-stage serialization.
**How LangChain Open Deep Research solves it:** 3 stages: Plan -> Research (parallel) -> Write.

**Solution (Priority 3):**
- **Collapse to 3 stages:** Plan -> Research (parallel sub-agents per sub-topic) -> Write
- **Merge search + analyze + verify** into one "Research" mega-stage
- **Eliminate evaluate + search_gaps** (fold into synthesis prompt)

### RC-5: 30+ MB State Through LangGraph

**Problem:** fetched_content (22+ MB) + evidence (5 MB) + claims (4 MB) serialized at every node
**Why it exists:** Unbounded accumulation with no caps. LangGraph serializes full state.
**How Gemini solves it:** Everything in model context window. No inter-node serialization.

**Solution (Priority 2):**
- **Immediate:** Cap fetched_content. Externalize to content store (which already exists).
- **Better:** Only pass evidence IDs through state, not full content. Nodes fetch content on demand.
- **Best:** Collapse pipeline stages to eliminate serialization boundaries.

---

## Part 3: Hidden Holes (27 Issues Found)

### CRITICAL / HIGH (Must Fix)

| # | Issue | Impact |
|---|-------|--------|
| 06 | Unbounded fetched_content in LangGraph state (22+ MB) | Memory pressure, slow node transitions |
| 14 | Uploaded document evidence uses wrong field names | G3 feature completely broken |
| 20 | Synchronous embedding blocks async event loop | All concurrent tasks stall for 5-15s |
| 21 | 30+ MB state serialization at every node boundary | Multi-second delays, high memory |
| 26 | Citation scrambling during expansion passes | Citations point to wrong sources |
| 01 | Hallucination detector hydration failure swallowed | Quality gate degrades silently |
| 18 | 100+ env vars with no coherence validation | Misconfiguration causes wasted runs |

### MEDIUM (Should Fix)

| # | Issue | Impact |
|---|-------|--------|
| 04 | Evidence list concurrent mutation in analyzer | Cap exceeded by bounded amount |
| 07 | Unbounded structured_data accumulation | Memory growth |
| 09 | Full prompt+response in every trace event | 20 MB trace files |
| 11 | Sequential LLM calls for cluster viability | 15 extra calls, ~75s |
| 12 | Individual claim retry with no backoff | Wastes credits on transient errors |
| 15 | Citation map reversal collision risk | Silent citation corruption |
| 16 | aiohttp session per URL fetch (300 sessions) | TCP churn |
| 19 | PG_MIN_TOTAL_WORDS misleading (never used as gate) | Configuration confusion |
| 22 | trafilatura still in fallback despite ban | Contradicts design intent |
| 23 | No circuit breaker for 403 errors | Log flooding |
| 24 | Budget check races with concurrent calls | Budget overshoot |
| 25 | Abstract replacement regex fragile | Duplicate abstracts |
| 27 | Section revision drops citations silently | Uncited claims |

---

## Part 4: Feature Flag State (Disabled vs Still Active)

### Properly Disabled
- `PG_MOST_ENABLED=0` -- MoST fully disabled, correct gate, safe default
- `PG_HALLUCINATION_AUDIT_ENABLED=0` -- Dashboard-only flag (cosmetic)
- `PG_HALLUCINATION_DETECT_ENABLED=0` -- NLI hallucination detector (JUST FIXED - was silently active)

### STILL ACTIVE (evaluate whether needed)
- `PG_STRUCTURED_DATA_EXTRACTION=1` -- THE BIGGEST COST PROBLEM ($4.45/run)
- `PG_CHART_GENERATION_ENABLED=1` -- Matplotlib subprocess in dark zone
- `PG_CLUSTER_VIABILITY_ENABLED=1` -- 15 extra LLM calls
- `PG_CITATION_AGENT_ENABLED=1` -- 15 extra LLM calls in dark zone
- `PG_CORROBORATION_ENABLED=1` -- O(n^2) embedding similarity
- `PG_STORM_ENABLED=1` -- All 5 interviews timed out in run #2

### Naming Hazard
`PG_HALLUCINATION_DETECT_ENABLED` vs `PG_HALLUCINATION_AUDIT_ENABLED` — two flags that sound the same but control completely different things. This caused the wrong flag to be disabled.

---

## Part 5: GPU vs CPU Audit

| Operation | Model | Current Device | Should Be |
|-----------|-------|---------------|-----------|
| NLI verification | flan-t5-large (770M) | GPU (auto-detect) | GPU (correct) |
| Hallucination detection | flan-t5-large (shared) | GPU (auto-detect) | DISABLED |
| Embeddings | all-MiniLM-L6-v2 (22M) | Auto-detect (no logging) | GPU + add logging |
| CrossEncoder | nli-deberta-v3-base | Auto-detect (no flag gate) | GPU + add flag gate |
| SemHash | Model2Vec | CPU (by design) | CPU (correct) |
| Matplotlib charts | subprocess | CPU | CPU (correct) |

**Action needed:** Add device logging to embedding service. Add feature flag gate to CrossEncoder.

---

## Part 6: Recommended Action Plan (Priority Order)

### Phase A: Stop the Bleeding (30 min, $0)
1. Disable `PG_STRUCTURED_DATA_EXTRACTION=0` (kills 53% of cost)
2. Disable `PG_CLUSTER_VIABILITY_ENABLED=0` (kills 15 extra LLM calls)
3. Disable `PG_CITATION_AGENT_ENABLED=0` (kills 15 extra LLM calls in dark zone)
4. Disable `PG_CORROBORATION_ENABLED=0` (kills O(n^2) embedding)
5. Disable `PG_STORM_ENABLED=0` (all interviews timeout anyway)
6. Cap fetched_content in state to 50 entries max
7. Add cooperative timeout to every LLM call

### Phase B: Architectural Redesign (days)
1. Replace per-source extraction with inline extraction during synthesis
2. Inline citations during synthesis (eliminate post-synthesis dark zone)
3. Collapse 8 nodes to 3 (Plan -> Research -> Write)
4. Replace time budget with call budget
5. Externalize fetched_content to content store
6. Add streaming progress events to all operations

### Phase C: Quality Improvements
1. Fix uploaded document evidence schema (ISSUE-14)
2. Fix citation scrambling in expansion (ISSUE-26)
3. Fix synchronous embedding blocking event loop (ISSUE-20)
4. Add env var coherence validation
5. Eliminate confusing duplicate flag names

---

## Sources

- Google Gemini Deep Research API Docs
- OpenAI Deep Research Guide
- LangChain Open Deep Research (GitHub + blog)
- Egnyte Deep Research Agent architecture
- Step-DeepResearch (arXiv 2512.20491)
- Deep Research Agents survey (arXiv 2506.18096)
- CiteFix (arXiv 2504.15629)
- ZenML Steerable Deep Research
- HuggingFace smolagents
- ByteByteGo system design analysis
