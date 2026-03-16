# POLARIS Architecture Documentation

**Version**: 1.0.0
**Last Updated**: 2026-02-27

---

## 1. System Overview

```
+============================================================================+
|                        POLARIS SOVEREIGN DEEP RESEARCH                      |
+============================================================================+
|                                                                             |
|  +------------------+    +------------------+    +---------------------+    |
|  |   Web Dashboard  |    |   FastAPI Server  |    |   Pipeline Engine   |    |
|  |  (Browser UI)    |--->|   (live_server)   |--->|   (LangGraph)       |    |
|  |                  |<---|   Port 8000       |<---|   8-Node Graph      |    |
|  |  - Report View   |SSE |   - REST API      |    |   - plan            |    |
|  |  - Evidence      |    |   - SSE Events    |    |   - search          |    |
|  |  - Dashboard     |    |   - Health Check  |    |   - storm           |    |
|  +------------------+    +------------------+    |   - analyze          |    |
|                                                   |   - verify           |    |
|                                                   |   - evaluate         |    |
|                                                   |   - synthesize       |    |
|                                                   |   - search_gaps      |    |
|                                                   +---------------------+    |
|                                    |                        |                |
|                          +---------+---------+    +---------+---------+      |
|                          |   LLM Backend     |    |   Data Layer      |      |
|                          |                   |    |                   |      |
|                          | Cloud: OpenRouter  |    | ChromaDB (VWM)   |      |
|                          |   OR               |    | SQLite Caches    |      |
|                          | Local: vLLM        |    | JSONL Traces     |      |
|                          +-------------------+    | JSON Outputs      |      |
|                                                   +-------------------+      |
|                                                                             |
|  +----------------------------------------------------------------------+   |
|  |                        External Services Layer                        |   |
|  |                                                                       |   |
|  |  Search:  Serper | Exa | Semantic Scholar | OpenAlex | DuckDuckGo    |   |
|  |  Fetch:   Jina | Firecrawl | Crawl4AI | Trafilatura | httpx         |   |
|  |  Verify:  MiniCheck NLI (local GPU) | CrossEncoder | SemHash        |   |
|  +----------------------------------------------------------------------+   |
+============================================================================+
```

---

## 2. Cloud Mode Data Flow

```
  Browser                 POLARIS Server                    Cloud APIs
  -------                 --------------                    ----------

  User types             POST /api/research
  research query  -----> {query, depth}
                         |
                         v
                  PipelineRunner.start()
                         |
                  build_and_run(query)
                         |
                         v
                  +------+-------+
                  | 1. PLAN      |-------> OpenRouter (Kimi K2.5)
                  | Generate 50  |         "Generate sub-queries for: ..."
                  | sub-queries  |<------- {queries: [...]}
                  +------+-------+
                         |
                  +------+-------+
                  | 2. SEARCH    |-------> Serper (web search)
                  | Execute      |-------> Semantic Scholar (academic)
                  | federated    |-------> Exa (neural search)
                  | search       |<------- {urls, snippets, metadata}
                  +------+-------+
                         |
                  +------+-------+
                  | 3. STORM     |-------> OpenRouter (Kimi K2.5)
                  | 5 expert     |         "As a [Scientist], what would
                  | perspective  |          you ask about [topic]?"
                  | interviews   |<------- {perspectives, insights}
                  +------+-------+
                         |
                  +------+-------+
                  | 4. ANALYZE   |-------> Jina / Crawl4AI (fetch pages)
                  | Fetch pages, |-------> OpenRouter (Kimi K2.5)
                  | extract      |         "Extract atomic facts from: ..."
                  | evidence     |<------- {evidence: [{quote, source}]}
                  +------+-------+
                         |
                  +------+-------+
                  | 5. VERIFY    |-------> MiniCheck NLI (local GPU)
                  | NLI + LLM   |-------> OpenRouter (LLM fallback)
                  | verification |<------- {verdicts: [SUPPORTED/NOT]}
                  +------+-------+
                         |
                  +------+-------+
                  | 6. EVALUATE  |-------> OpenRouter (Kimi K2.5)
                  | Gap analysis |         "What topics are missing?"
                  | + iteration  |<------- {gaps: [...], iterate: bool}
                  | decision     |
                  +------+-------+
                         |
                  If iterate=true, loop to SEARCH_GAPS then PLAN
                         |
                  +------+-------+
                  | 7. SYNTHESIZE|-------> OpenRouter (Kimi K2.5)
                  | Cluster ->   |         "Write section about [topic]
                  | Outline ->   |          citing evidence [1][2][3]..."
                  | Sections ->  |<------- {report: {sections, citations}}
                  | Citations    |
                  +------+-------+
                         |
                  GET /api/events
  SSE events <--- TraceTailer ---- trace.jsonl
                         |
  Report renders         v
  in browser <--- GET /api/research/result/{id}
                  {report, evidence, bibliography, scores}
```

---

## 3. Sovereign Mode Data Flow

```
  Browser                 POLARIS Server              Local Services
  -------                 --------------              --------------

  User types             POST /api/research
  research query  -----> {query, depth}
                         |
                         v
                  PipelineRunner.start()
                         |
                  build_and_run(query)
                         |
                         v
                  +------+-------+
                  | 1. PLAN      |-------> vLLM (localhost:8080)
                  | Generate 50  |         Qwen2.5-32B-Instruct
                  | sub-queries  |<------- {queries: [...]}
                  +------+-------+
                         |
                  +------+-------+
                  | 2. SEARCH    |-------> SearxNG (localhost:8888)
                  | Execute      |         Local metasearch engine
                  | federated    |         (indexes intranet + cached web)
                  | search       |<------- {urls, snippets, metadata}
                  +------+-------+
                         |
                  +------+-------+
                  | 3. STORM     |-------> vLLM (localhost:8080)
                  | 5 expert     |         Same model, same API format
                  | perspective  |         Only the URL changed
                  | interviews   |<------- {perspectives, insights}
                  +------+-------+
                         |
                  +------+-------+
                  | 4. ANALYZE   |-------> Crawl4AI (local Playwright)
                  | Fetch pages, |-------> Trafilatura (local CPU)
                  | extract      |-------> vLLM (localhost:8080)
                  | evidence     |<------- {evidence: [{quote, source}]}
                  +------+-------+
                         |
                  +------+-------+
                  | 5. VERIFY    |-------> MiniCheck NLI (local GPU)
                  | NLI + LLM   |         flan-t5-large on CUDA
                  | verification |         No cloud call needed
                  +------+-------+
                         |
                  +------+-------+
                  | 6. EVALUATE  |-------> vLLM (localhost:8080)
                  | Gap analysis |
                  +------+-------+
                         |
                  +------+-------+
                  | 7. SYNTHESIZE|-------> vLLM (localhost:8080)
                  | Full report  |         Same synthesis pipeline
                  | generation   |         Zero data egress
                  +------+-------+
                         |
                  GET /api/events
  SSE events <--- TraceTailer ---- trace.jsonl
                         |
  Report renders         v
  in browser <--- GET /api/research/result/{id}
```

---

## 4. "Change One URL" Proof

The entire POLARIS system uses OpenAI-compatible APIs. Switching from cloud to sovereign requires changing exactly **3 environment variables**:

```bash
# ============ CLOUD MODE ============
OPENROUTER_API_KEY=sk-or-v1-your-real-key
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_DEFAULT_MODEL=moonshotai/kimi-k2.5

# ============ SOVEREIGN MODE ============
OPENROUTER_API_KEY=not-needed
OPENROUTER_BASE_URL=http://localhost:8080/v1    # <-- vLLM
OPENROUTER_DEFAULT_MODEL=Qwen/Qwen2.5-32B-Instruct
```

**Why this works**: The `OpenRouterClient` in `src/polaris_graph/llm/openrouter_client.py` uses the standard OpenAI Python SDK with a configurable `base_url`. vLLM exposes an identical OpenAI-compatible API at `/v1/chat/completions`. No code changes are required.

For search, disable cloud search APIs and enable local alternatives:

```bash
# Cloud search off
PG_EXA_ENABLED=0
PG_JINA_ENABLED=0
PG_FIRECRAWL_ENABLED=0
PG_SOURCE_CONFIDENCE_ENABLED=0

# Local alternatives on
PG_CRAWL4AI_ENABLED=1
PG_TRAFILATURA_ENABLED=1
# SearxNG replaces Serper via SERPER_BASE_URL override
```

---

## 5. Component Table

| Component | Purpose | Cloud API | Sovereign Alternative |
|-----------|---------|-----------|----------------------|
| **LLM Inference** | Query planning, evidence extraction, synthesis, gap analysis | OpenRouter (Kimi K2.5, 400+ models) | vLLM + Qwen2.5-32B / Llama 3.1 70B |
| **Web Search** | Query execution, result retrieval | Serper (Google results) | SearxNG (self-hosted metasearch) |
| **Neural Search** | Semantic similarity search | Exa (neural search API) | Disabled or local Elasticsearch |
| **Academic Search** | Peer-reviewed paper retrieval | Semantic Scholar API | OpenAlex (open academic graph) |
| **Content Extraction** | Full-page content from URLs | Jina Reader (JS rendering) | Crawl4AI + Trafilatura (local) |
| **Premium Extraction** | Anti-bot bypass, complex sites | Firecrawl API | Crawl4AI with Playwright |
| **NLI Verification** | Claim-to-source faithfulness | MiniCheck flan-t5-large (local) | Same (already local) |
| **Embeddings** | Semantic similarity, dedup | sentence-transformers (local) | Same (already local) |
| **Contradiction Detection** | Cross-source NLI | CrossEncoder (local) | Same (already local) |
| **Semantic Dedup** | Evidence deduplication | SemHash Model2Vec (local) | Same (already local) |
| **Source Authority** | Domain trust scoring | Open PageRank API | Disabled or custom scoring |
| **Vector Store** | Evidence storage, retrieval | ChromaDB (local) | Same (already local) |
| **Caching** | Search, content, evidence | SQLite (local) | Same (already local) |
| **Checkpointing** | Pipeline resume on crash | LangGraph SQLite (local) | Same (already local) |
| **Cost Tracking** | LLM spend monitoring | JSONL ledger (local) | Same (already local) |

---

## 6. API Dependency Map

```
                           POLARIS Pipeline
                                 |
        +------------------------+------------------------+
        |                        |                        |
   LLM Calls              Search Calls             Fetch Calls
   (All phases)            (Phase 2)               (Phase 4)
        |                        |                        |
        v                        v                        v
  OpenRouterClient         SearcherAgent            AnalyzerAgent
        |                   |    |    |              |    |    |
        v                   v    v    v              v    v    v
  OpenRouter API        Serper  S2  Exa           Jina  C4AI Traf
  (or vLLM)             (web) (acad)(neural)     (JS)  (local)(local)
        |                   |    |    |              |    |    |
        |                   |    |    |              |    |    |
  Swap: change          Swap: Swap: Swap:        Swap: Already Already
  OPENROUTER_BASE_URL   SearxNG OpenAlex disable  C4AI  local  local

  Legend:
  S2   = Semantic Scholar     C4AI = Crawl4AI
  Traf = Trafilatura          Exa  = Exa neural search
```

### When Each API Is Called

| API | Called During | Frequency Per Vector | Swappable |
|-----|-------------|---------------------|-----------|
| OpenRouter/vLLM | All 8 nodes | 50-200 LLM calls | URL swap |
| Serper | search node | 50-120 queries | SearxNG |
| Semantic Scholar | search node | 20-100 queries (1 RPS) | OpenAlex |
| Exa | search node | 5-10 queries | Disable |
| Jina | analyze node | 30-200 pages | Crawl4AI |
| Firecrawl | analyze node (fallback) | 0-20 pages | Crawl4AI |
| Open PageRank | analyze node | 1 bulk call | Disable |
| OpenAlex | search node | 10-30 queries | Already free/open |

---

## 7. Pipeline Node Diagram

```
                    +===========+
                    |   START   |
                    +===========+
                         |
                         v
                  +------+-------+
                  |    PLAN      |  Generate 50 sub-queries via STORM
                  |              |  perspectives + amplification variants
                  +------+-------+
                         |
              +----------+----------+
              |                     |
              v                     v
       +------+-------+     +------+-------+
       |   SEARCH     |     | SEARCH_GAPS  |  (FIX-307: targeted gap
       |              |     |              |   search, bypasses planner)
       | Serper + S2  |     | Gap-targeted |
       | + Exa +      |     | queries only |
       | agentic loop |     +------+-------+
       +------+-------+            |
              |                    |
              +----------+---------+
                         |
                         v
                  +------+-------+
                  |    STORM     |  5 expert perspectives x 3 rounds
                  | INTERVIEWS   |  Multi-perspective knowledge
                  +------+-------+
                         |
                         v
                  +------+-------+
                  |   ANALYZE    |  Fetch pages (Jina/C4AI/Traf)
                  |              |  Extract atomic facts + quotes
                  |              |  5-signal tier scoring
                  +------+-------+
                         |
                         v
                  +------+-------+
                  |    VERIFY    |  NLI verification (MiniCheck)
                  |              |  + LLM balanced prompting
                  |              |  + cross-source corroboration
                  +------+-------+
                         |
                         v
                  +------+-------+      iterate=true
                  |   EVALUATE   |----------+
                  |              |          |
                  | Gap analysis |     +----+----+
                  | Convergence  |     | Loop to |
                  | check        |     | PLAN or |
                  +------+-------+     | SEARCH_ |
                         |             | GAPS    |
                   iterate=false       +---------+
                         |
                         v
                  +------+-------+
                  |  SYNTHESIZE  |  Map-reduce clustering
                  |              |  Report outline generation
                  |              |  Per-section writing + citations
                  |              |  Cross-section dedup + coherence
                  |              |  Citation resolution + bibliography
                  +------+-------+
                         |
                         v
                    +===========+
                    |    END    |
                    +===========+
                         |
                         v
               outputs/polaris_graph/
                 {vector_id}/
                   result.json      (full report + evidence)
                   trace.jsonl      (pipeline event log)
                   bibliography.json (resolved citations)
```

### Iteration Logic

```
EVALUATE node decides:
  |
  +-- CASE_1: Sufficient evidence, high confidence
  |   Action: Proceed to SYNTHESIZE (finalize)
  |
  +-- CASE_2: Partial evidence, some gaps
  |   Action: Route to SEARCH_GAPS for targeted queries
  |   Then: ANALYZE -> VERIFY -> EVALUATE again
  |   Max iterations: PG_MAX_ITERATIONS (default 5)
  |
  +-- CASE_3: Insufficient evidence
  |   Action: Route back to PLAN for full re-query
  |   Then: Full pipeline loop
  |
  +-- CASE_4: Critical failure
      Action: HALT pipeline, escalate for review
```

---

## 8. Data Flow: JSON Contracts Between Phases

Every pipeline node communicates through the `ResearchState` TypedDict. Key state fields:

```
ResearchState (TypedDict)
|
+-- original_query: str           # User's research question
+-- vector_id: str                # Unique identifier
+-- iteration_count: int          # Current iteration (1-5)
|
+-- queries: list[str]            # Plan -> Search
|   Generated sub-queries (50+)
|
+-- search_results: list[dict]    # Search -> Analyze
|   {url, title, snippet, source_type, engine}
|
+-- storm_insights: list[dict]    # Storm -> Analyze
|   {perspective, question, answer, evidence}
|
+-- evidence: list[dict]          # Analyze -> Verify
|   {id, quote, source_url, source_title,
|    relevance, confidence, tier, atomic_facts}
|
+-- claims: list[dict]            # Verify -> Evaluate
|   {claim, verdict, nli_score, source_id,
|    is_faithful, verification_type}
|
+-- gap_analysis: dict            # Evaluate -> Search_Gaps/Plan
|   {gaps, covered_topics, missing_perspectives,
|    should_iterate, case}
|
+-- report: dict                  # Synthesize -> Output
|   {title, abstract, sections[], bibliography[],
|    word_count, citation_count, faithfulness}
|
+-- timestamps: dict              # Timing for every node
+-- cost_usd: float               # Accumulated LLM cost
+-- trace_events: list            # Observability events
```

### Output JSON Structure

```json
{
  "vector_id": "WEB_20260227_abc123",
  "query": "What are the latest advances in...",
  "report": {
    "title": "...",
    "abstract": "...",
    "sections": [
      {
        "heading": "Section Title",
        "content": "Paragraph text with [1][2] citations...",
        "evidence_ids": ["ev_001", "ev_002"],
        "faithfulness": 0.95,
        "word_count": 1200
      }
    ],
    "bibliography": [
      {
        "id": 1,
        "title": "Source Title",
        "url": "https://...",
        "authors": "...",
        "year": 2025,
        "tier": "GOLD"
      }
    ]
  },
  "metrics": {
    "total_words": 12450,
    "total_citations": 187,
    "unique_sources": 42,
    "faithfulness": 0.89,
    "evidence_count": 1282,
    "iterations": 3,
    "cost_usd": 1.31,
    "duration_minutes": 84
  }
}
```

---

## 9. Security Model

```
+================================================================+
|                     SECURITY LAYERS                              |
+================================================================+
|                                                                  |
|  Layer 1: Network Boundary                                       |
|  +---------------------------------------------------------+    |
|  | Cloud Mode: TLS 1.3 for all external API calls          |    |
|  | Sovereign Mode: Air-gapped, zero egress                  |    |
|  | Firewall: whitelist-only outbound (cloud) or DROP all    |    |
|  +---------------------------------------------------------+    |
|                                                                  |
|  Layer 2: Authentication                                         |
|  +---------------------------------------------------------+    |
|  | API Key Auth:  Authorization: Bearer {token}             |    |
|  | Session Mgmt:  Per-client SSE cursor isolation           |    |
|  | CORS Policy:   Configurable allowed_origins              |    |
|  +---------------------------------------------------------+    |
|                                                                  |
|  Layer 3: Authorization (RBAC)                                   |
|  +---------------------------------------------------------+    |
|  | Researcher Role:                                         |    |
|  |   GET  /api/research/result/{id}  -- Read reports        |    |
|  |   POST /api/research              -- Submit queries      |    |
|  |   GET  /api/events                -- SSE events          |    |
|  |                                                          |    |
|  | Operator Role:                                           |    |
|  |   All Researcher permissions PLUS:                       |    |
|  |   GET  /api/pipeline/status       -- Pipeline internals  |    |
|  |   GET  /api/pipeline/config       -- Configuration       |    |
|  |   POST /api/pipeline/cancel       -- Cancel pipeline     |    |
|  |   GET  /api/trace/{id}            -- Trace events        |    |
|  |                                                          |    |
|  | Admin Role:                                              |    |
|  |   All Operator permissions PLUS:                         |    |
|  |   POST /api/config                -- Update config       |    |
|  |   GET  /api/cost                  -- Cost ledger         |    |
|  |   GET  /health                    -- Health check        |    |
|  +---------------------------------------------------------+    |
|                                                                  |
|  Layer 4: Data Protection                                        |
|  +---------------------------------------------------------+    |
|  | Secrets: .env file (never committed to VCS)              |    |
|  | API Keys: masked in logs (first 8 chars only)            |    |
|  | Output: stored locally, no cloud upload                  |    |
|  | Caching: SQLite with filesystem-level permissions        |    |
|  | Traces: JSONL append-only (tamper-evident)               |    |
|  +---------------------------------------------------------+    |
|                                                                  |
|  Layer 5: Audit Trail                                            |
|  +---------------------------------------------------------+    |
|  | Every LLM call:  logged with cost, tokens, model, time  |    |
|  | Every search:    logged with engine, query, result count |    |
|  | Every verdict:   logged with claim, source, NLI score    |    |
|  | Every decision:  logged with rationale, evidence IDs     |    |
|  | Pipeline trace:  JSONL with 8 event types per node       |    |
|  | Cost ledger:     per-call USD tracking                   |    |
|  +---------------------------------------------------------+    |
|                                                                  |
+================================================================+
```

### Endpoint Permissions Matrix

| Endpoint | Method | Researcher | Operator | Admin |
|----------|--------|------------|----------|-------|
| `/` | GET | Yes | Yes | Yes |
| `/health` | GET | No | No | Yes |
| `/api/research` | POST | Yes | Yes | Yes |
| `/api/research/result/{id}` | GET | Yes | Yes | Yes |
| `/api/events` | GET | Yes | Yes | Yes |
| `/api/pipeline/status` | GET | No | Yes | Yes |
| `/api/pipeline/cancel` | POST | No | Yes | Yes |
| `/api/pipeline/config` | GET | No | Yes | Yes |
| `/api/trace/{id}` | GET | No | Yes | Yes |
| `/api/config` | POST | No | No | Yes |
| `/api/cost` | GET | No | No | Yes |

---

## 10. Memory Architecture

```
+================================================================+
|                    TRI-LEVEL MEMORY SYSTEM                       |
+================================================================+
|                                                                  |
|  VWM (Vector Working Memory) — Per-Research Session              |
|  +---------------------------------------------------------+    |
|  | ChromaDB collection per vector_id                        |    |
|  | Contains: chunks, embeddings, metadata                   |    |
|  | Lifecycle: created at search, used through synthesis      |    |
|  | Persistence: SQLite-backed, survives restarts             |    |
|  +---------------------------------------------------------+    |
|                         |                                        |
|                   Promotion (high-quality chunks)                 |
|                         v                                        |
|  LTM-Stage — Per Analysis Stage                                  |
|  +---------------------------------------------------------+    |
|  | Aggregated knowledge from all vectors in a stage         |    |
|  | Used for: contextualization (Phase 1), gap analysis      |    |
|  | Cross-vector dedup prevents redundant research           |    |
|  +---------------------------------------------------------+    |
|                         |                                        |
|                   Promotion (verified, cross-referenced)          |
|                         v                                        |
|  LTM-Global — Persistent Knowledge Base                          |
|  +---------------------------------------------------------+    |
|  | Organization-wide verified knowledge                     |    |
|  | Used for: future research contextualization              |    |
|  | Includes: citation chains, evidence hierarchies          |    |
|  +---------------------------------------------------------+    |
|                                                                  |
+================================================================+

  SQLite Cache Layer (5 databases):
  +------------------+------------------+------------------+
  | content_cache    | search_cache     | evidence_hier    |
  | (fetched pages)  | (search results) | (evidence tree)  |
  +------------------+------------------+------------------+
  | session_feedback | cross_vector     |
  | (quality scores) | (cross-ref data) |
  +------------------+------------------+
```
