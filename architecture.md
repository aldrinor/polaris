# POLARIS System Architecture

## Document Purpose

This document defines the complete architecture for POLARIS - a production-grade research pipeline that processes **175 research vectors** across **13 stages** to produce comprehensive market intelligence for C-POLAR antimicrobial coating technology.

**Design Philosophy**: Complete, traceable, resumable. Every vector is processed. Every decision is logged. Every claim is cited.

---

## Current State (2026-01-31)

### Status Summary

| Component | Status |
|-----------|--------|
| **Pipeline** | OPERATIONAL - Snowball Test S1V1-S1V6 VALIDATED |
| **Faithfulness** | 95.7% (Grade A) |
| **Engine** | TRANSITIONING: Gemini 3 Pro → Fireworks (KIMI K2.5) |
| **Next Vector** | S1V7 (pending quota refresh or engine swap) |

### Operation Unshackle (FIX 83-87)

The "Funnel of Death" was identified causing 95% evidence loss:
- 471 search results → 2 after cross-encoder (99.6% rejection)
- Synthesizer starved of evidence for report generation

**Fixes Applied:**

| Fix | Component | Change | Impact |
|-----|-----------|--------|--------|
| FIX 80 | `state.py:1` | sys.setrecursionlimit(150) | Prevents stack overflow |
| FIX 83 | `synthesizer_agent.py:77` | MAX_REVISION_EVIDENCE 30→200 | Amnesia cure |
| FIX 84 | `relevance_filter.py:780-848` | Dynamic cross-encoder filter | Guarantees minimum evidence |
| FIX 85 | `analyst_agent.py:56` | MAX_RESULTS_TOTAL 60→250 | Lifts analyst cap |
| FIX 86 | `depth_config.py:42` | top_queries_limit 15→50 | More query generation |
| FIX 87 | `thresholds.py:211-213` | max_results_per_query 5→15 | More results per query |

### Engine Transition: Fireworks (KIMI K2.5)

**Decision**: Replace Gemini 3 Pro with Fireworks-hosted KIMI K2.5 1T model.

**Rationale**:
- Gemini 3 Pro quota exhausted (429 RESOURCE_EXHAUSTED)
- Fireworks offers 195 tokens/second (fastest available)
- KIMI K2.5: 1 trillion parameter MoE model (32B active), MIT license
- Cost: $0.90/M tokens (vs Gemini ~$6/M)
- No Canadian server available; using US-West (Washington) - ~20ms latency acceptable

**Implementation TODO**:
1. Add Fireworks API key to .env: `FIREWORKS_API_KEY=...`
2. Update `src/llm/` with Fireworks client
3. Update model configuration in `config/settings/models.yaml`

---

## 1. System Overview

### 1.1 Mission Statement

POLARIS generates comprehensive research intelligence by:
- Processing **175 unique research vectors** across 13 strategic analysis stages
- Producing **verifiable, cited research reports** with <5% hallucination rate
- Building **persistent knowledge** across vectors through tri-level memory
- Supporting **regional and global geographic targeting** per stage requirements
- Enabling **resumable execution** that never loses progress

### 1.2 Domain Context: C-POLAR Antimicrobial Coating

POLARIS serves the C-POLAR business intelligence mission:
- **Product**: Long-duration (5-year) antimicrobial coating technology
- **Applications**: Household water filters, HVAC systems, medical devices, food processing equipment, etc.
- **Markets**: North America, Europe, Asia Pacific (regional) and Global markets
- **Analysis**: From contamination problem identification through go-to-market strategy

### 1.3 Core Invariants (Non-Negotiable)

1. **175 Vectors Exactly**: System halts if vector count != 175
2. **No Hard-Coding**: All parameters from config/env/CLI, never inline
3. **No Uncited Claims**: Every factual statement links to a source
4. **No Silent Failures**: All errors surface with clear diagnostics
5. **Full Traceability**: Every output traceable to input sources
6. **Resumable State**: Progress persisted after every phase completion

### 1.4 Success Metrics (SOTA Targets)

| Metric | Target | Measurement |
|--------|--------|-------------|
| Hallucination Rate | <5% | Atomic fact verification against sources |
| Citation Accuracy | >95% | Claim-to-source semantic match |
| Source Diversity | 10+ unique sources | Distinct URLs per report |
| Content Coverage | >80% | Query constraints addressed |
| Word Count | 2000+ | Research report length |
| Verified Claims | 30+ | Claims passing NLI verification |
| Vector Completion | 100% | All 175 vectors processed successfully |
| **FactScore** | >0.80 | Atomic facts verified / total atomic facts (SOTA) |
| **G-Eval Coherence** | >4.0/5.0 | LLM-as-judge coherence rating (SOTA) |
| **G-Eval Fluency** | >4.0/5.0 | LLM-as-judge fluency rating (SOTA) |
| **G-Eval Consistency** | >4.0/5.0 | LLM-as-judge consistency rating (SOTA) |
| **G-Eval Relevance** | >4.0/5.0 | LLM-as-judge relevance rating (SOTA) |
| **Filler Ratio** | <5% | Verbose phrases / total content (SOTA) |

---

## 2. The 175 Vector System

### 2.1 Vector Architecture

A **vector** represents a single research question combining:
- **Stage**: One of 13 strategic analysis stages (1-13)
- **Application**: Target product category (e.g., "Household_Water_Filter")
- **Region**: Geographic scope (NORTH_AMERICA, EUROPE, ASIA_PACIFIC, or GLOBAL)

**Vector ID Format**: `S{stage}V{index}_{application}_{region}`

Examples:
```
S1V1_Household_Water_Filter_NORTH_AMERICA
S4V3_HVAC_Systems_GLOBAL
S8V2_Medical_Devices_EUROPE
```

### 2.2 The 13 Stages

| Stage | Name | Vectors | Scope | Purpose |
|-------|------|---------|-------|---------|
| 1 | Contamination Problem Identification | 35 | Regional | Identify pathogen contamination rates, biofilm patterns, transmission pathways |
| 2 | Cost of Pain Quantification | 21 | Regional | Quantify economic impact: treatment costs, losses, infrastructure damage |
| 3 | Solution Landscape Analysis | 15 | Regional | Map existing antimicrobial solutions, efficacy, limitations |
| 4 | Technology Gap Identification | 10 | Global | Identify gaps current solutions cannot address |
| 5 | C-POLAR Value Proposition | 12 | Global | Quantify C-POLAR's unique value vs alternatives |
| 6 | Market Size Quantification | 8 | Regional | TAM/SAM/SOM analysis by region and segment |
| 7 | Competitive Intelligence | 16 | Global | Competitor analysis, patents, market positioning |
| 8 | Regulatory Pathway Analysis | 10 | Regional | FDA/EPA/regional regulatory requirements |
| 9 | Technical Feasibility Assessment | 10 | Global | Manufacturing integration, partnership readiness |
| 10 | Business Model Design | 8 | Global | Revenue models, pricing, partnerships |
| 11 | Financial Modeling | 10 | Global | Forecasting, break-even, ROI analysis |
| 12 | Risk Assessment | 10 | Global | Partner risks, market risks, IP risks |
| 13 | Go-to-Market Strategy | 10 | Global | Launch sequencing, channel strategy, scaling |

**Total: 175 vectors**

### 2.3 Regional vs Global Policy

```
REGIONAL_STAGES = {1, 2, 3, 6, 8}
GLOBAL_STAGES = {4, 5, 7, 9, 10, 11, 12, 13}
```

**Regional Stages (1, 2, 3, 6, 8)**:
- Run separately for NORTH_AMERICA, EUROPE, ASIA_PACIFIC
- Search queries include geographic targeting
- Content filtered for regional relevance
- Memory segregated by region within stage

**Global Stages (4, 5, 7, 9, 10, 11, 12, 13)**:
- Run once with GLOBAL scope
- Aggregate insights across all regions
- Draw from LTM-Stage memory of completed regional stages

### 2.4 Vector Question Templates

Each stage has question templates with `{application}` and `{region}` placeholders:

```python
# Stage 1 Example Templates (35 total)
"What pathogen contamination rates exist in {application} for {region}?"
"What bacterial biofilm formation patterns occur on {application} surfaces in {region}?"
"What viral transmission pathways are documented for {application} environments in {region}?"
...

# Stage 7 Example Templates (16 total)
"What direct antimicrobial competitor identification and classification exists for {application} in {region}?"
"What indirect competitor and substitute technology analysis exists for {application} in {region}?"
...
```

### 2.5 Application Categories

Applications are product/environment categories for C-POLAR coating:

| Category | Example Applications |
|----------|---------------------|
| Water Systems | Household_Water_Filter, Municipal_Water_Treatment, Industrial_Cooling |
| HVAC | Residential_HVAC, Commercial_HVAC, Hospital_Ventilation |
| Medical | Medical_Devices, Surgical_Instruments, Hospital_Surfaces |
| Food | Food_Processing_Equipment, Food_Storage, Restaurant_Surfaces |
| Infrastructure | Public_Transportation, School_Facilities, Office_Buildings |

---

## 3. Pipeline Phases (0-12)

### 3.1 Phase Overview

Each vector passes through 13 sequential processing phases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VECTOR PROCESSING PIPELINE                           │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Phase 0: Initialization & Novelty Check                                    │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 1: Contextualization (HPRP from LTM)                                 │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 2: Query Generation (Diversified Sub-Queries)                        │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 3: Search Execution (Federated Multi-Engine)                         │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 4: Relevance Filtering (Two-Stage IsREL)                             │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 5: VWM Indexing (Semantic Chunking + Embedding)                      │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 6: NLI Integrity (Contradiction Detection)                           │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 7: Dual RAG Analysis (Evidence-Grounded Synthesis)                   │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 8: Claim Verification (NLI Evidence Validation)                      │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 9: Adversarial QA (Stress Testing Claims)                            │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 10: Gating Logic (CASE 1/2/3/4 Decision)                             │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 11: Knowledge Integration (LTM Promotion)                            │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 12: Research Packaging (Final Report Assembly)                       │
│     │                                                                        │
│     ▼                                                                        │
│  Phase 13: Narrative Synthesis (Cross-Vector Integration)                   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Phase 0: Initialization & Novelty Check

**Purpose**: Initialize VWM, check for duplicate/near-duplicate vectors.

**Input**:
```python
@dataclass
class Phase0Input:
    vector_id: str  # e.g., "S1V1_Household_Water_Filter_NORTH_AMERICA"
    application: str
    region: str
    stage: int
```

**Process**:
1. Parse vector_id to extract stage, application, region
2. Create or recover VWM collection for this vector
3. Compute SHA256 fingerprint of vector question
4. Check LTM-Global and LTM-Stage for similar existing research
5. If similarity > 0.95, flag as duplicate with peer vector ID

**Output**:
```python
@dataclass
class Phase0Output:
    vector_id: str
    status: str  # "proceed" | "duplicate" | "near_duplicate"
    fingerprint: str  # SHA256 hash
    vwm_collection: str  # ChromaDB collection name
    peer_vector_id: Optional[str]  # If duplicate detected
    similarity_score: Optional[float]
    timestamps: Dict[str, str]
```

**Quality Gate**:
- VWM collection created or recovered
- Fingerprint recorded
- Duplicate detection executed

### 3.3 Phase 1: Contextualization

**Purpose**: Retrieve relevant prior knowledge from LTM to inform research strategy.

**Input**: Phase0Output + LTM access

**Process**:
1. Query LTM-Stage for same-stage prior research
2. Query LTM-Global for cross-stage relevant content
3. Apply HPRP (Hierarchical Prior Relevance Prioritization)
4. Generate strategic research plan based on knowledge gaps

**Output**:
```python
@dataclass
class Phase1Output:
    vector_id: str
    strategic_plan: Dict  # {knowledge_gaps, priorities, strategies}
    ltm_stage_hits: int
    ltm_global_hits: int
    prior_knowledge_summary: str
    research_focus_areas: List[str]
```

**Quality Gate**:
- Strategic plan JSON is valid and non-empty
- Knowledge gaps identified
- Focus areas derived from LTM analysis

### 3.4 Phase 2: Query Generation (SOTA: STORM Perspective-Guided)

**Purpose**: Generate diversified search queries from vector question using STORM methodology.

**Input**: Phase1Output + vector question template

**SOTA Enhancement - STORM Perspective-Guided Generation**:
Based on Stanford STORM methodology (Shao et al.), this phase now generates queries from multiple expert perspectives to ensure comprehensive topic coverage:

```
┌─────────────────────────────────────────────────────────────────┐
│                    STORM PERSPECTIVE FLOW                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Perspective Generation (4-6 experts)                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ "Water Quality Scientist" - contamination mechanisms       │ │
│  │ "Public Health Expert" - disease transmission pathways     │ │
│  │ "Regulatory Affairs Specialist" - EPA/FDA compliance       │ │
│  │ "Environmental Engineer" - filtration system design        │ │
│  │ "Epidemiologist" - outbreak patterns and prevention        │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  Step 2: Perspective-to-Query Generation                         │
│  Each expert generates 3-5 queries from their viewpoint          │
│                              │                                   │
│                              ▼                                   │
│  Step 3: Perspective-to-Bucket Mapping                          │
│  Scientist/Engineer → academic bucket                            │
│  Regulatory Specialist → government bucket                       │
│  Public Health → news/industry bucket                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Process**:
1. **STORM Perspectives**: Generate 4-6 expert perspectives relevant to the topic
2. **Perspective Queries**: Each perspective generates targeted search queries
3. Apply query rebalancer for bucket distribution
4. Generate authority-anchored variants (site:*.gov, site:*.edu)
5. Apply geographic targeting for regional stages
6. Deduplicate and lint queries

**Query Buckets** (from config):
```yaml
query_distribution:
  academic: 0.30      # Peer-reviewed sources
  government: 0.20    # Regulatory/official
  industry: 0.25      # Trade publications
  news: 0.15          # Recent developments
  general: 0.10       # Broad web search
```

**Output**:
```python
@dataclass
class Phase2Output:
    vector_id: str
    final_queries: List[str]  # Minimum 20 queries
    query_count: int
    bucket_distribution: Dict[str, int]
    geographic_targeting: bool
    authority_anchors_applied: int
    storm_perspectives: List[Dict]  # NEW: Expert perspectives used
    queries_by_perspective: Dict[str, List[str]]  # NEW: Queries per perspective
```

**Quality Gate**:
- final_queries >= configured minimum (20)
- All buckets represented
- No hard-coded queries
- Geographic targeting for regional stages
- At least 4 perspectives generated (SOTA)

### 3.5 Phase 3: Search Execution

**Purpose**: Execute federated search across multiple engines.

**Supported Engines**:
| Engine | Use Case | Rate Limit | Priority |
|--------|----------|------------|----------|
| Google CSE | General web | 100/day | 1 |
| Serper | General web | 2500/month | 2 |
| PubMed | Medical/scientific | Unlimited | 1 (health) |
| Semantic Scholar | Academic | 100/5min | 1 (research) |
| OpenAlex | Academic metadata | Unlimited | 2 |

**Process**:
1. Route queries to appropriate engines based on bucket type
2. Execute searches in parallel with semaphore-bounded concurrency
3. Fetch full content from URLs (Googlebot UA, Playwright fallback)
4. Handle PDF extraction, paywall detection, rate limiting
5. Deduplicate results by URL

**Output**:
```python
@dataclass
class Phase3Output:
    vector_id: str
    search_results: List[SearchResult]
    urls_attempted: int
    urls_success: int
    urls_failed: int
    content_by_engine: Dict[str, int]
    total_content_chars: int
    fetch_methods: Dict[str, int]  # requests/playwright/archive
```

**Quality Gate**:
- True async execution (not sequential)
- Multiple engines used
- Success rate > 60%
- No sequential loop limiters

### 3.6 Phase 4: Relevance Filtering (SOTA: RCS Map + Source Quality)

**Purpose**: Score and filter content by query relevance AND source quality.

**SOTA Enhancement - RCS Map (Ranking and Contextual Summarization)**:
Based on PaperQA2 methodology (Skarlinski et al.), this phase now includes:
1. **Source Quality Scoring**: Semantic Scholar API for citation metrics
2. **Domain Tier Scoring**: Government/academic sources prioritized
3. **Contextual Summarization**: Key claims extracted per chunk

**Three-Stage Architecture**:

```
Stage 1: HARD GATE (Embedding Similarity)
├── Method: Dense retrieval (OpenAI/local embeddings)
├── Threshold: 0.35 (permissive)
├── Purpose: Remove obviously irrelevant content
└── Latency: <10ms per chunk

Stage 2: SOFT GATE (Cross-Encoder Reranking)
├── Method: ms-marco-MiniLM-L-6-v2 cross-encoder
├── Threshold: 0.55 (selective)
├── Purpose: Identify truly relevant content
└── Latency: ~100ms per chunk

Stage 3: SOURCE QUALITY SCORING (NEW - SOTA)
├── Method: Semantic Scholar API + Domain Tier Scoring
├── Components:
│   ├── Citation count (normalized log scale)
│   ├── Influential citation count (weighted 2x)
│   ├── Reference count (breadth indicator)
│   └── Domain tier (see below)
└── Latency: ~50ms per source (cached)

Score Fusion (UPDATED):
├── fused_score = 0.4 * hard_score + 0.6 * soft_score
├── quality_adjusted = fused_score * 0.80 + source_quality * 0.20
└── Tier assignment based on quality_adjusted score
```

**Domain Tier Scoring**:
| Tier | Domains | Base Score |
|------|---------|------------|
| Tier 1 | cdc.gov, epa.gov, nih.gov, pubmed, nature.com, science.org | 0.95 |
| Tier 2 | nsf.gov, waterrf.org, awwa.org, professional associations | 0.80 |
| Tier 3 | Major news (nytimes, reuters, bbc) | 0.60 |
| Tier 4 | General web | 0.40 |
| Blacklist | linkedin.com, medium.com, grandviewresearch, marketing sites | 0.00 |

**RCS Map - Contextual Summary**:
```python
@dataclass
class ContextualSummary:
    chunk_id: str
    contextual_summary: str  # 1-2 sentence summary relevant to query
    key_claims: List[str]    # Atomic claims extractable from chunk
    relevance_to_query: str  # Brief relevance statement
```

**Relevance Tiers**:
| Tier | Quality-Adjusted Score | Usage |
|------|------------------------|-------|
| Gold | >= 0.70 | Primary evidence, direct citation |
| Silver | 0.55-0.69 | Supporting evidence, context |
| Bronze | 0.40-0.54 | Background information |
| Rejected | < 0.40 | Not used |

**Output**:
```python
@dataclass
class Phase4Output:
    vector_id: str
    chunks_input: int
    chunks_passed: int
    chunks_rejected: int
    tier_distribution: Dict[str, int]  # gold/silver/bronze
    relevance_scores: List[float]
    source_quality_scores: Dict[str, float]  # NEW: Per-URL quality scores
    contextual_summaries: List[ContextualSummary]  # NEW: RCS Map summaries
    domain_tier_distribution: Dict[str, int]  # NEW: Tier 1/2/3/4 counts
```

### 3.7 Phase 5: VWM Indexing

**Purpose**: Chunk documents semantically and index in Vector Working Memory.

**Chunking Strategy**:
```python
STAGE_CHUNKING_TEMPLATE_MAP = {
    # Academic stages -> research_paper template
    1: "research_paper", 4: "research_paper", 5: "research_paper",
    7: "research_paper", 9: "research_paper", 11: "research_paper", 12: "research_paper",

    # Government/report stages -> technical_report template
    2: "technical_report", 3: "technical_report", 6: "technical_report", 8: "technical_report",

    # Business stages -> news_article template
    10: "news_article", 13: "news_article"
}
```

**Process**:
1. Apply stage-appropriate chunking template
2. Generate embeddings (GPU if available, CPU fallback)
3. Store chunks in VWM with full metadata
4. Promote high-quality chunks to LTM-Stage

**Chunk Metadata**:
```python
@dataclass
class ChunkMetadata:
    chunk_id: str
    source_url: str
    source_title: str
    source_domain: str
    fetch_timestamp: str
    content_hash: str
    geographic_scope: List[str]
    relevance_tier: str
    verification_status: str
```

**Output**:
```python
@dataclass
class Phase5Output:
    vector_id: str
    chunks_indexed: int
    vwm_collection_size: int
    embeddings_generated: int
    gpu_used: bool
    ltm_promotions: int
```

### 3.8 Phase 6: NLI Integrity (SOTA: Enhanced Contradiction Mining)

**Purpose**: Detect contradictions within evidence with thematic clustering and narrative generation.

**Model**: DeBERTa-v3-large-mnli (GPU accelerated)

**SOTA Enhancement - Contradiction Mining with Narratives**:
Goes beyond simple pairwise NLI to provide actionable intelligence about evidence conflicts:

```
┌─────────────────────────────────────────────────────────────────┐
│              CONTRADICTION MINING PIPELINE                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Claim Extraction                                        │
│  ├── Extract key claim from each chunk                          │
│  └── Domain classification (contamination, effectiveness, etc.) │
│                              │                                   │
│  Step 2: Thematic Clustering                                     │
│  ├── Group chunks by topic:                                     │
│  │   - contamination_rates                                      │
│  │   - pathogen_types                                           │
│  │   - filter_effectiveness                                     │
│  │   - maintenance_requirements                                 │
│  │   - cost_factors                                             │
│  │   - regional_differences                                     │
│  │   - regulatory_compliance                                    │
│  │   - health_outcomes                                          │
│  └── Within-cluster contradiction focus                         │
│                              │                                   │
│  Step 3: Pairwise NLI (within clusters)                         │
│  ├── Same-topic pairs get priority                              │
│  ├── Cross-topic pairs sampled                                  │
│  └── Confidence threshold filtering                             │
│                              │                                   │
│  Step 4: Narrative Generation                                    │
│  ├── Per-cluster contradiction summary                          │
│  ├── Source attribution                                         │
│  └── Actionable research implications                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Process**:
1. Extract key claim from each chunk for efficient comparison
2. Cluster chunks by thematic topic (8 categories)
3. Generate within-cluster chunk pairs for contradiction checking
4. Cap pairs at MAX_NLI_PAIRS (config) for performance
5. Run NLI classification: ENTAILMENT | NEUTRAL | CONTRADICTION
6. Generate human-readable narratives per contradiction cluster
7. Compute integrity score with topic-weighted penalties

**Contradiction Cluster Output**:
```python
@dataclass
class ContradictionCluster:
    topic: str  # e.g., "contamination_rates"
    contradictions: List[Tuple[str, str, float]]  # (chunk_a, chunk_b, confidence)
    narrative: str  # "Sources disagree about contamination rates: CDC reports 15% while EPA states 8%..."
    severity: str  # "high" | "medium" | "low"
    research_implication: str  # "Further investigation needed on regional measurement methodology"
```

**Output**:
```python
@dataclass
class Phase6Output:
    vector_id: str
    pairs_checked: int
    contradictions_found: int
    integrity_score: float  # 0.0-1.0
    contradiction_details: List[Dict]
    status: str  # "pass" | "warn" | "fail"
    contradiction_clusters: Dict[str, ContradictionCluster]  # NEW: By topic
    contradiction_narratives: List[str]  # NEW: Human-readable summaries
    thematic_distribution: Dict[str, int]  # NEW: Chunks per theme
```

**Quality Gate**:
- Integrity score > 0.85 to proceed
- Contradictions logged for review
- Contradiction narratives generated for all high-severity conflicts (SOTA)

### 3.9 Phase 7: Dual RAG Analysis (SOTA: Outline-First + Thematic Clustering)

**Purpose**: Generate evidence-grounded analysis using structured outline and thematic organization.

**SOTA Enhancement - Outline-First Generation**:
Based on best practices from Long-Form Question Answering research, this phase now:
1. **Generates outline first** before writing content
2. **Clusters evidence by theme** (concept, not source)
3. **Uses sliding context** per outline section

**Dual RAG Architecture**:
```
RAG-1: Dense Retrieval
├── Query VWM with embedding similarity
├── Retrieve top-K chunks per sub-query
└── Context budget: 8000 tokens

RAG-2: Sparse Retrieval (BM25)
├── Keyword-based retrieval
├── Retrieve top-K chunks per sub-query
└── Merge with RAG-1 results (RRF fusion)
```

**SOTA Pipeline**:
```
┌─────────────────────────────────────────────────────────────────┐
│             OUTLINE-FIRST GENERATION PIPELINE                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Thematic Claim Clustering                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Group chunks by CONCEPT, not source:                       │ │
│  │ - contamination_rates: [chunk_3, chunk_15, chunk_22]       │ │
│  │ - pathogen_types: [chunk_7, chunk_11, chunk_28]            │ │
│  │ - filter_effectiveness: [chunk_1, chunk_8, chunk_19]       │ │
│  │ - maintenance_requirements: [chunk_5, chunk_24]            │ │
│  │ - cost_factors: [chunk_12, chunk_31]                       │ │
│  │ - regional_differences: [chunk_9, chunk_17, chunk_26]      │ │
│  │ - regulatory_compliance: [chunk_4, chunk_20]               │ │
│  │ - health_outcomes: [chunk_6, chunk_14, chunk_29]           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│  Step 2: Outline Generation                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Generate structured outline from themes:                    │ │
│  │ 1. Introduction (background, scope)                        │ │
│  │ 2. Primary Finding: Contamination Patterns                 │ │
│  │ 3. Key Finding: Pathogen Distribution                      │ │
│  │ 4. Analysis: Filter Performance Comparison                 │ │
│  │ 5. Discussion: Regional Variations                         │ │
│  │ 6. Implications: Health and Regulatory                     │ │
│  │ 7. Conclusion (synthesis, not new claims)                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│  Step 3: Sliding Context Assembly                                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ For each section:                                          │ │
│  │ 1. Select relevant theme clusters                          │ │
│  │ 2. Apply token budget (2000-3000 tokens/section)          │ │
│  │ 3. Prioritize Gold tier, then Silver                      │ │
│  │ 4. Generate section with [CITE:chunk_id] tokens           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Process**:
1. Retrieve relevant chunks via dual RAG
2. **Cluster chunks by thematic topic** (8 categories)
3. **Generate structured outline** from available themes
4. For each outline section, **assemble sliding context** from relevant clusters
5. Generate section content with explicit citation tokens [CITE:chunk_id]
6. Extract confidence score and thinking process

**Outline Section Schema**:
```python
@dataclass
class OutlineSection:
    id: str  # e.g., "finding_1"
    title: str  # e.g., "Contamination Patterns in North American Water Filters"
    target_themes: List[str]  # Themes to draw from
    target_words: int  # Word count target
    content_guidance: str  # Brief guidance for content generation
```

**Output**:
```python
@dataclass
class Phase7Output:
    vector_id: str
    analysis_text: str
    thinking_process: str
    confidence_score: float
    chunks_used: int
    citation_tokens: List[str]  # [CITE:xyz] markers
    token_usage: Dict[str, int]
    outline: List[OutlineSection]  # NEW: Generated outline
    themed_chunks: Dict[str, List[str]]  # NEW: Chunks by theme
    sections_generated: int  # NEW: Number of outline sections completed
```

### 3.10 Phase 8: Claim Verification (SOTA: FactScore + QA Verification)

**Purpose**: Verify claims through atomic fact decomposition and hybrid NLI + QA verification.

**SOTA Enhancement - FactScore Atomic Decomposition**:
Based on FactScore methodology (Min et al.), this phase now:
1. **Decomposes claims into atomic facts** for granular verification
2. **Uses hybrid NLI + QA verification** for higher accuracy
3. **Tracks verification at atomic level** for precise hallucination detection

**Verification Pipeline**:
```
┌─────────────────────────────────────────────────────────────────┐
│              FACTSCORE VERIFICATION PIPELINE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Atomic Fact Decomposition                               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Original: "E. coli contamination affects 15% of North      │ │
│  │           American water filters according to CDC data"    │ │
│  │                              │                              │ │
│  │ Atomic Facts:                ▼                              │ │
│  │ 1. "E. coli causes contamination in water filters"         │ │
│  │ 2. "The contamination rate is 15%"                         │ │
│  │ 3. "This applies to North American water filters"          │ │
│  │ 4. "The data source is CDC"                                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│  Step 2: NLI Verification (Primary)                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Model: DeBERTa-v3-large-mnli                               │ │
│  │ For each atomic fact:                                      │ │
│  │   Input: (evidence_chunk, atomic_fact)                     │ │
│  │   Output: ENTAILMENT | NEUTRAL | CONTRADICTION             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│  Step 3: QA Verification (Supplementary)                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Convert fact to verification question:                     │ │
│  │   Fact: "The contamination rate is 15%"                    │ │
│  │   Question: "What percentage is mentioned for              │ │
│  │             contamination rate?"                           │ │
│  │   Extract answer from evidence                             │ │
│  │   Match: Does extracted answer support fact?               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│  Step 4: Hybrid Scoring                                          │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ - If NLI = ENTAILMENT → verified (high confidence)         │ │
│  │ - If NLI = NEUTRAL + QA confirms → verified (medium)       │ │
│  │ - If NLI = CONTRADICTION → rejected                        │ │
│  │ - If NLI = NEUTRAL + QA fails → unverified                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Atomic Fact Types**:
| Type | Pattern | QA Question Template |
|------|---------|---------------------|
| Numeric | Contains percentages, counts, measurements | "What [metric] is mentioned?" |
| Entity | Contains named entities (CDC, EPA, pathogens) | "What [entity type] is referenced?" |
| Temporal | Contains dates, time periods | "What time period is mentioned?" |
| Geographic | Contains locations, regions | "What location/region is specified?" |
| Causal | Contains cause-effect relationships | "What causes/leads to [effect]?" |

**Output**:
```python
@dataclass
class AtomicFact:
    fact_id: str
    text: str
    fact_type: str  # numeric, entity, temporal, geographic, causal
    parent_claim_id: str
    nli_result: str  # entailed, neutral, contradicted
    nli_confidence: float
    qa_verified: bool  # NEW: QA verification result
    qa_confidence: float  # NEW: QA match confidence
    final_status: str  # verified, partial, rejected, unverified

@dataclass
class Phase8Output:
    vector_id: str
    claims_input: int
    claims_verified: int
    claims_partial: int
    claims_rejected: int
    atomic_facts_total: int  # NEW: Total atomic facts extracted
    atomic_facts_verified: int  # NEW: Atomic facts verified
    factscore: float  # NEW: FactScore metric (verified/total)
    verification_details: List[Dict]
    qa_verification_rate: float  # NEW: QA success rate
```

**Quality Gate**:
- FactScore >= 0.80 for CASE_1 (high quality)
- FactScore >= 0.60 for CASE_2 (acceptable, needs review)
- FactScore < 0.60 triggers CASE_3 or CASE_4

### 3.11 Phase 9: Adversarial QA

**Purpose**: Stress-test claims with adversarial questions.

**Process**:
1. Generate 3-5 adversarial questions targeting claims
2. Attempt to answer from evidence (should succeed if claims valid)
3. Compute evidence strength and signal novelty
4. Flag claims that cannot be defended

**Output**:
```python
@dataclass
class Phase9Output:
    vector_id: str
    adversarial_questions: List[str]
    answers: List[str]
    evidence_strength: float  # 0.0-1.0
    signal_novelty: float  # 0.0-1.0
    claims_defended: int
    claims_failed: int
```

### 3.11 Phase 10: Gating Logic

**Purpose**: Decide final disposition of research.

**Gating Cases**:

| Case | Condition | Action |
|------|-----------|--------|
| CASE_1 | Sufficient evidence, high confidence | Finalize and promote to LTM-Global |
| CASE_2 | Partial evidence, medium confidence | Schedule refinement iteration |
| CASE_3 | Insufficient evidence, low confidence | Return gap report, schedule retry |
| CASE_4 | Critical failure (contradictions, etc.) | Escalate for human review |

**Decision Logic**:
```python
def gating_decision(state: PipelineState) -> GatingCase:
    if state.integrity_score < 0.70:
        return CASE_4  # Critical failure

    if state.sufficiency_score >= 0.80 and state.confidence >= 0.70:
        return CASE_1  # Finalize

    if state.sufficiency_score >= 0.50:
        return CASE_2  # Iterate for refinement

    return CASE_3  # Insufficient evidence
```

**Output**:
```python
@dataclass
class Phase10Output:
    vector_id: str
    gating_case: str  # "CASE_1" | "CASE_2" | "CASE_3" | "CASE_4"
    justification: str
    next_action: str
    sufficiency_score: float
    confidence_score: float
    integrity_score: float
```

### 3.12 Phase 11: Knowledge Integration

**Purpose**: Persist finalized research to LTM-Global.

**Process** (CASE_1 only):
1. Package verified claims with citations
2. Update LTM-Global with finalized research
3. Cross-reference with related vectors
4. Archive raw outputs

**Output**:
```python
@dataclass
class Phase10Output:
    vector_id: str
    ltm_global_updated: bool
    claims_persisted: int
    cross_references: List[str]
    archive_path: str
```

### 3.13 Phase 12: Research Packaging (SOTA: Grounded Conclusions + Chain of Density)

**Purpose**: Assemble final research report with grounded conclusions and dense, filler-free content.

**SOTA Enhancement - Report Quality Improvements**:
Based on research on hallucination prevention and content density:
1. **Grounded Conclusions**: Conclusions derived ONLY from findings already in report
2. **Chain of Density**: Iterative densification without information loss
3. **Filler Removal**: Automatic removal of verbose padding phrases

**Grounded Conclusion Pipeline**:
```
┌─────────────────────────────────────────────────────────────────┐
│              GROUNDED CONCLUSION GENERATION                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  PROBLEM: Previous conclusions often introduced new claims or   │
│           drifted to unrelated topics (e.g., biosand filters    │
│           when discussing North American water contamination)   │
│                                                                  │
│  SOLUTION:                                                       │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Step 1: Collect all previous section content               │ │
│  │         (executive_summary + findings + analysis)          │ │
│  │                              │                              │ │
│  │ Step 2: Pass to conclusion prompt with STRICT constraint:  │ │
│  │         "Your conclusion MUST be derived ONLY from         │ │
│  │          findings already presented in this report.        │ │
│  │          Do NOT introduce new data, statistics, or         │ │
│  │          topics not already discussed above."              │ │
│  │                              │                              │ │
│  │ Step 3: Extractive fallback if LLM adds new claims:        │ │
│  │         Pull key sentences from existing sections          │ │
│  │         rather than generating new content                 │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Chain of Density Pipeline**:
```
┌─────────────────────────────────────────────────────────────────┐
│                 CHAIN OF DENSITY PROMPTING                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Iteration 1: Generate initial summary (~300 words)             │
│       ↓                                                         │
│  Iteration 2: "Make this denser by adding 1-2 key entities     │
│               without increasing length"                        │
│       ↓                                                         │
│  Iteration 3: "Further densify, ensuring no information is     │
│               lost from previous iteration"                     │
│       ↓                                                         │
│  Iteration 4: Final density pass (if needed)                   │
│                                                                  │
│  Result: Dense, information-rich content without filler        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Filler Phrase Removal**:
Automatic removal of 50+ verbose patterns including:
- "It is worth noting that" → removed
- "It is important to note that" → removed
- "In order to" → "to"
- "Due to the fact that" → "because"
- "At this point in time" → "now"
- "In the event that" → "if"
- "For the purpose of" → "to"
- "With regard to" → "regarding"
- And many more...

**Report Structure**:
```markdown
## Executive Summary
[150-200 words, dense, no filler]

## Background and Context
[200-300 words]

## Key Findings
[100-150 words per finding with [1], [2] citations]

### Finding 1: [Title]
[Detailed explanation with citations]

### Finding 2: [Title]
[Detailed explanation with citations]

## Analysis and Implications
[300-400 words]

## Limitations and Gaps
[150-200 words]

## Conclusion
[200-300 words, GROUNDED in findings above only]

## References
[1] Author. "Title." Source, Date. URL
[2] Author. "Title." Source, Date. URL
```

**Output**:
```python
@dataclass
class Phase12Output:
    vector_id: str
    output_type: str  # "answer" | "gap_report"
    report_text: str
    word_count: int
    citations: List[Citation]
    citation_count: int
    confidence_band: str  # "high" | "medium" | "low"
    chain_of_density_iterations: int  # NEW: CoD iterations applied
    filler_phrases_removed: int  # NEW: Count of filler removals
    conclusion_grounding_score: float  # NEW: How grounded is conclusion
```

**Quality Gate**:
- Word count >= 2000 (deep_research mode)
- Citation count >= 5
- Filler ratio < 5% (after removal)
- Conclusion contains no new claims not in prior sections

### 3.14 Phase 13: Narrative Synthesis

**Purpose**: Integrate across vectors within stage.

**Process** (runs after all vectors in stage complete):
1. Aggregate findings across stage vectors
2. Identify cross-vector patterns and themes
3. Generate stage-level executive summary
4. Prepare input for next stage (if applicable)

---

## 4. Tri-Level Memory Architecture

### 4.1 Memory Hierarchy

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        TRI-LEVEL MEMORY HIERARCHY                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  VWM (Vector Working Memory)                                        │     │
│  │  ──────────────────────────────────────────────────────────────────│     │
│  │  Scope: Single vector execution                                     │     │
│  │  Lifetime: Vector processing (cleared after completion)             │     │
│  │  Contents: Retrieved chunks, intermediate results                   │     │
│  │  Storage: ChromaDB collection per vector                           │     │
│  │  Size Limit: 1000 chunks max                                        │     │
│  │  Collection Name: vwm_{vector_id}                                   │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼ (promote verified, high-quality chunks)       │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  LTM-Stage (Long-Term Memory - Stage Level)                         │     │
│  │  ──────────────────────────────────────────────────────────────────│     │
│  │  Scope: All vectors within a stage                                  │     │
│  │  Lifetime: Stage execution (persists across vectors)                │     │
│  │  Contents: Verified claims, high-quality sources                    │     │
│  │  Storage: ChromaDB collection per stage+region                      │     │
│  │  Size Limit: 10,000 chunks per stage                               │     │
│  │  Collection Name: ltm_stage_{stage}_{region}                        │     │
│  │  Example: ltm_stage_1_NORTH_AMERICA                                │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼ (promote finalized CASE_1 research)           │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  LTM-Global (Long-Term Memory - Global)                             │     │
│  │  ──────────────────────────────────────────────────────────────────│     │
│  │  Scope: All research across all stages                              │     │
│  │  Lifetime: Persistent (survives all runs)                          │     │
│  │  Contents: Finalized reports, cross-stage knowledge                 │     │
│  │  Storage: ChromaDB persistent collection                            │     │
│  │  Size Limit: Unlimited (with compaction)                            │     │
│  │  Collection Name: ltm_global                                        │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Memory Operations

| Operation | Description | Tier |
|-----------|-------------|------|
| `query(text, filters)` | Retrieve relevant chunks | All |
| `store(chunk, metadata)` | Store new chunk | VWM, LTM-Stage |
| `promote(chunk_id, to_tier)` | Move chunk up hierarchy | VWM→Stage, Stage→Global |
| `compact()` | Deduplicate and summarize | LTM-Stage, LTM-Global |
| `clear()` | Clear collection | VWM only |

### 4.3 Promotion Criteria

**VWM → LTM-Stage**:
- Relevance tier: Gold or Silver
- Verification status: Verified
- Citation count: > 0

**LTM-Stage → LTM-Global**:
- Gating case: CASE_1 (finalized)
- Confidence score: >= 0.70
- Cross-reference validation: Pass

---

## 5. Orchestration Model

### 5.1 State Files

**state/work_queue.json**: Full list of 175 vectors
```json
{
  "total_vectors": 175,
  "vectors": [
    {
      "vector_id": "S1V1_Household_Water_Filter_NORTH_AMERICA",
      "stage": 1,
      "application": "Household_Water_Filter",
      "region": "NORTH_AMERICA",
      "status": "pending"
    },
    ...
  ]
}
```

**state/progress_ledger.jsonl**: Append-only execution log
```json
{"ts":"2026-01-17T10:00:00Z","vector_id":"S1V1_Household_Water_Filter_NORTH_AMERICA","phase":0,"status":"running","attempt":1}
{"ts":"2026-01-17T10:01:00Z","vector_id":"S1V1_Household_Water_Filter_NORTH_AMERICA","phase":0,"status":"completed","runtime_sec":60.5,"sha256_output":"abc123"}
{"ts":"2026-01-17T10:01:05Z","vector_id":"S1V1_Household_Water_Filter_NORTH_AMERICA","phase":1,"status":"running","attempt":1}
```

**state/last_pointer.json**: Resume point
```json
{
  "vector_id": "S1V1_Household_Water_Filter_NORTH_AMERICA",
  "phase": 3,
  "attempt": 1,
  "timestamp": "2026-01-17T10:15:00Z"
}
```

### 5.2 Orchestrator Loop

```python
async def orchestrate_pipeline():
    """Main orchestration loop for processing all 175 vectors."""

    # Load work queue
    work_queue = load_work_queue()
    assert len(work_queue.vectors) == 175, "Vector count mismatch!"

    # Resume from last pointer if exists
    resume_point = load_last_pointer()

    for vector in work_queue.vectors:
        if vector.status == "completed":
            continue

        for phase in range(0, 13):
            # Check progress ledger
            if is_phase_completed(vector.vector_id, phase):
                continue

            # Write running status
            append_ledger(vector.vector_id, phase, "running")

            try:
                # Execute phase
                result = await execute_phase(vector, phase)

                # Write completed status
                append_ledger(vector.vector_id, phase, "completed", result)

                # Update last pointer
                update_last_pointer(vector.vector_id, phase + 1)

            except Exception as e:
                # Write failed status
                append_ledger(vector.vector_id, phase, "failed", error=str(e))

                # Decide retry vs skip
                if should_retry(vector, phase):
                    continue  # Will retry on next loop
                else:
                    break  # Skip to next vector
```

### 5.3 Concurrency Control

```yaml
# config/settings/concurrency.yaml
max_concurrent_vectors: 1        # Process one vector at a time
max_concurrent_fetches: 10       # Parallel URL fetches within Phase 3
max_concurrent_embeddings: 4     # Parallel embedding batches
gpu_utilization_target: 0.80     # Backpressure threshold
```

---

## 6. Citation System (Late Binding)

### 6.1 Late Binding Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LATE BINDING CITATION FLOW                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  DURING CLAIM EXTRACTION (Phase 7):                                          │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  LLM generates: "Water contamination affects 50% [CITE:chunk_42]"   │     │
│  │  Citation Registry registers chunk_42 as potential citation         │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  DURING NLI VERIFICATION (Phase 6/8/9):                                        │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  If chunk_42 fails verification:                                    │     │
│  │     registry.mark_blocked("chunk_42", "NLI_CONTRADICTION")          │     │
│  │  If chunk_42 has geographic mismatch:                               │     │
│  │     registry.mark_blocked("chunk_42", "REGION_MISMATCH")           │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  DURING FINALIZATION (Phase 12):                                             │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  text, citations = registry.finalize(text_with_cite_tokens)         │     │
│  │                                                                      │     │
│  │  If chunk_42 not blocked:                                           │     │
│  │     [CITE:chunk_42] → [1]                                           │     │
│  │     citations.append({number: 1, url: "...", title: "..."})        │     │
│  │                                                                      │     │
│  │  If chunk_42 blocked:                                               │     │
│  │     [CITE:chunk_42] → [removed]                                     │     │
│  │     (or sentence removed entirely)                                  │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                              │                                               │
│                              ▼                                               │
│  FINAL OUTPUT:                                                               │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  "Water contamination affects 50% [1]"                              │     │
│  │                                                                      │     │
│  │  References:                                                         │     │
│  │  [1] Smith et al. "Water Quality Study." Nature, 2025. https://...  │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Citation Registry API

```python
class CitationRegistry:
    def register(self, evidence_id: str, url: str, title: str, metadata: Dict) -> None:
        """Register a chunk as potential citation source."""

    def mark_blocked(self, evidence_id: str, reason: str) -> None:
        """Block a citation from appearing in final output."""

    def is_blocked(self, evidence_id: str) -> bool:
        """Check if citation is blocked."""

    def finalize(self, text: str) -> Tuple[str, List[Citation]]:
        """Convert [CITE:id] tokens to [N] and build citations array."""

    def get_stats(self) -> Dict:
        """Return registration/blocking/finalization statistics."""
```

---

## 7. Quality Gates

### 7.1 Per-Phase Gates

| Phase | Gate | Threshold | Fail Action |
|-------|------|-----------|-------------|
| 0 | VWM created | Required | Halt |
| 1 | Strategic plan valid | Required | Halt |
| 2 | Query count | >= 20 | Retry with expanded templates |
| 3 | Fetch success rate | >= 60% | Warn, continue |
| 4 | Chunks passed | >= 10 | Iterate (CASE_2) |
| 5 | VWM indexed | >= 10 chunks | Iterate (CASE_2) |
| 6 | Integrity score | >= 0.70 | CASE_4 escalation |
| 7 | Confidence score | >= 0.50 | Iterate (CASE_2) |
| 8 | Evidence strength | >= 0.60 | Iterate (CASE_2) |
| 9 | Gating decision | CASE_1/2/3/4 | Per-case action |
| 10 | LTM update | CASE_1 only | Skip if not CASE_1 |
| 11 | Word count | >= 2000 | Revise |
| 11 | Citation count | >= 5 | Revise |

### 7.2 Output Quality Gate (Final)

```python
@dataclass
class QualityGateResult:
    passed: bool
    overall_score: float
    checks: Dict[str, CheckResult]
    issues: List[str]

def quality_gate(report: Phase11Output) -> QualityGateResult:
    checks = {}

    # Citation count
    checks["citation_count"] = CheckResult(
        passed=report.citation_count >= 5,
        actual=report.citation_count,
        threshold=5
    )

    # Word count
    checks["word_count"] = CheckResult(
        passed=report.word_count >= 2000,
        actual=report.word_count,
        threshold=2000
    )

    # Source diversity
    unique_sources = len(set(c.domain for c in report.citations))
    checks["source_diversity"] = CheckResult(
        passed=unique_sources >= 5,
        actual=unique_sources,
        threshold=5
    )

    # Overall
    passed = all(c.passed for c in checks.values())
    score = sum(1 for c in checks.values() if c.passed) / len(checks)

    return QualityGateResult(passed=passed, overall_score=score, checks=checks)
```

---

## 8. Data Schemas

### 8.1 Vector Schema

```python
@dataclass
class Vector:
    id: str                    # "S1V1_Household_Water_Filter_NORTH_AMERICA"
    stage: int                 # 1-13
    stage_name: str           # "Contamination Problem Identification"
    vector_number: int        # 1-35 (varies by stage)
    question: str             # Full question text
    question_template: str    # Template with {application} {region}
    application: str          # "Household_Water_Filter"
    region: str               # "NORTH_AMERICA" | "EUROPE" | "ASIA_PACIFIC" | "GLOBAL"
    is_regional: bool         # True for stages 1,2,3,6,8
    chunking_template: str    # "research_paper" | "technical_report" | "news_article"
```

### 8.2 Research Report Schema

```python
@dataclass
class ResearchReport:
    # Identity
    vector_id: str
    stage: int
    application: str
    region: str

    # Output
    output_type: str              # "answer" | "gap_report"
    answer: str                   # Full report text
    word_count: int

    # Citations
    citations: List[Citation]
    citation_count: int

    # Quality
    confidence_score: float       # 0.0-1.0
    confidence_band: str          # "high" | "medium" | "low"
    sufficiency_score: float
    integrity_score: float
    quality_gate_passed: bool

    # Verification
    verified_claims: List[Claim]
    claims_total: int
    claims_verified: int
    claims_failed: int

    # Execution
    gating_case: str              # "CASE_1" | "CASE_2" | "CASE_3" | "CASE_4"
    execution_time_seconds: float
    retrieval_iterations: int
    sources_fetched: int
    sources_used: int

    # Provenance
    gatekeeper_decisions: List[GatekeeperDecision]
    phase_outputs: Dict[int, Any]
```

### 8.3 Citation Schema

```python
@dataclass
class Citation:
    number: int               # Sequential [1], [2], etc.
    evidence_id: str          # Internal chunk ID
    url: str                  # Source URL
    title: str                # Document title
    domain: str               # e.g., "nature.com"
    author: Optional[str]
    date: Optional[str]
    doi: Optional[str]
    similarity_score: float   # Relevance to claim
    verification_status: str  # "verified" | "partial" | "unverified"
```

### 8.4 Progress Ledger Entry Schema

```python
@dataclass
class LedgerEntry:
    ts: str                   # ISO-8601 timestamp
    vector_id: str
    phase: int
    status: str               # "running" | "completed" | "failed" | "skipped"
    attempt: int
    input_paths: List[str]
    output_path: Optional[str]
    sha256_input: Optional[str]
    sha256_output: Optional[str]
    runtime_sec: Optional[float]
    notes: Optional[str]
    error: Optional[str]
```

---

## 9. API Specifications

### 9.1 External APIs

| API | Purpose | Auth | Rate Limit | Config Key |
|-----|---------|------|------------|------------|
| OpenAI GPT-4/GPT-5 | LLM generation | API key | 10K TPM | OPENAI_API_KEY |
| Google CSE | Web search | Key + CX | 100/day | GOOGLE_CSE_API_KEY, GOOGLE_CSE_CX |
| Serper | Web search | API key | 2500/month | SERPER_API_KEY |
| PubMed | Medical papers | None | Unlimited | N/A |
| Semantic Scholar | Academic | API key | 100/5min | S2_API_KEY |
| OpenAlex | Academic metadata | None | Unlimited | N/A |

### 9.2 Internal APIs

**run_vector(vector_id, mode, config)**:
```python
async def run_vector(
    vector_id: str,                    # "S1V1_Household_Water_Filter_NORTH_AMERICA"
    mode: str = "deep_research",       # "requirements" | "deep_research" | "hierarchical"
    max_iterations: int = 5,
    timeout_seconds: int = 600,
    config_path: str = "config/settings"
) -> ResearchReport:
    """Execute full pipeline for a single vector."""
```

**run_stage(stage, application, regions, config)**:
```python
async def run_stage(
    stage: int,                        # 1-13
    application: str,                  # "Household_Water_Filter"
    regions: List[str] = None,         # Auto-determined if None
    config_path: str = "config/settings"
) -> List[ResearchReport]:
    """Execute all vectors in a stage."""
```

**run_full_pipeline(application, config)**:
```python
async def run_full_pipeline(
    application: str,                  # "Household_Water_Filter"
    config_path: str = "config/settings"
) -> Dict[int, List[ResearchReport]]:
    """Execute all 175 vectors for an application."""
```

---

## 10. Error Handling

### 10.1 Error Taxonomy

| Category | Examples | Action |
|----------|----------|--------|
| API Errors | Rate limit, timeout, 5xx | Retry with exponential backoff |
| Content Errors | Parse failure, empty, paywall | Skip URL, log warning |
| Verification Errors | NLI timeout, model OOM | Fallback to rule-based check |
| Generation Errors | LLM timeout, malformed | Retry with simplified prompt |
| Critical Errors | VWM corruption, config missing | Halt with CASE_4 |

### 10.2 Retry Policy

```yaml
# config/settings/retry.yaml
retry_policy:
  max_retries: 3
  initial_delay_ms: 1000
  max_delay_ms: 30000
  exponential_base: 2
  jitter_factor: 0.1

  retryable_errors:
    - "rate_limit"
    - "timeout"
    - "connection_reset"
    - "5xx"
```

### 10.3 Logging

```python
# Log format
"{timestamp} [{level}] [{phase}:{vector_id}] [{function}:{line}] {message}"

# Example
"2026-01-17T10:15:30Z [INFO] [P3:S1V1_HWF_NA] [fetch_url:245] Fetched https://example.com (3.2s, 15KB)"
```

---

## 11. Phase Runner System

### 11.1 Standard CLI Interface

Every phase script MUST implement this standard CLI:

```bash
python phase{N}_{name}.py \
  --vector-id <id> \
  --input <path-to-prev-phase-json> \
  --output <outputs/auto-name-if-omitted> \
  --config <config/settings.yml> \
  --max-concurrency <int> \
  --device cuda|cpu \
  [--self-test]
```

**CLI Arguments**:

| Argument | Required | Description |
|----------|----------|-------------|
| `--vector-id` | Yes | Vector ID (e.g., `S1V1_Household_Water_Filter_NORTH_AMERICA`) |
| `--input` | Yes | Path to previous phase's output JSON |
| `--output` | No | Output path (auto-generated if omitted) |
| `--config` | No | Config directory (default: `config/settings`) |
| `--max-concurrency` | No | Override concurrency limit |
| `--device` | No | `cuda` or `cpu` (default: auto-detect) |
| `--self-test` | No | Run phase self-test instead of normal execution |

### 11.2 Output File Naming Convention

**Phase Outputs**:
```
outputs/P{phase}/{vector_id}__P{phase}__{YYYYMMDD}_{HHMMSS}.json
```

Example:
```
outputs/P3/S1V1_Household_Water_Filter_NORTH_AMERICA__P3__20260117_101530.json
```

**Log Files**:
```
logs/S{stage}V{index}__{application}__{region}__P{phase}__{YYYYMMDD}_{HHMMSS}.log
```

Example:
```
logs/S1V1__Household_Water_Filter__NORTH_AMERICA__P3__20260117_101530.log
```

**Debug Dumps** (on exception):
```
logs/S1V1__Household_Water_Filter__NORTH_AMERICA__P3__20260117_101530__debug.log
```

### 11.3 Console Logging Format

```python
# Format
"[PHASE-{phase}][{vector_id}][{level}] {message}"

# Examples
"[PHASE-3][S1V1_HWF_NA][INFO] Starting federated search with 25 queries"
"[PHASE-3][S1V1_HWF_NA][DEBUG] Serper returned 47 results for query 'antimicrobial coating'"
"[PHASE-3][S1V1_HWF_NA][ERROR] Google CSE rate limit hit, switching to fallback"
```

### 11.4 Phase Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PHASE EXECUTION LIFECYCLE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. STARTUP                                                                  │
│     ├── Parse CLI arguments                                                  │
│     ├── Load configuration                                                   │
│     ├── Validate input file exists                                          │
│     ├── Check CUDA availability (log device info)                           │
│     └── Write progress_ledger.jsonl: status="running"                       │
│                                                                              │
│  2. EXECUTION                                                                │
│     ├── Load input from previous phase                                      │
│     ├── Execute phase logic                                                  │
│     ├── Stream logs to console and file                                     │
│     └── Handle errors with retry/fallback                                   │
│                                                                              │
│  3. COMPLETION (Success)                                                     │
│     ├── Write output JSON                                                   │
│     ├── Compute SHA256 of output                                            │
│     ├── Write progress_ledger.jsonl: status="completed"                     │
│     ├── Update last_pointer.json                                            │
│     └── Return exit code 0                                                  │
│                                                                              │
│  4. COMPLETION (Failure)                                                     │
│     ├── Write debug dump with stack trace                                   │
│     ├── Write progress_ledger.jsonl: status="failed"                        │
│     ├── Do NOT update last_pointer.json                                     │
│     └── Return exit code 1                                                  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 11.5 Self-Test Mode

Every phase MUST implement `--self-test` mode:

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    # ... other args ...
    args = parser.parse_args()

    if args.self_test:
        run_self_tests()
        sys.exit(0)

    # Normal execution
    run_phase(args)
```

**Self-Test Requirements per Phase**:

| Phase | Test | Pass Criteria |
|-------|------|---------------|
| 0 | Two identical inputs | Second flagged as duplicate |
| 1 | Blank LTM cold-start | Still yields structured plan |
| 2 | GPT disabled | Pattern engine produces >= 20 queries |
| 3 | Missing Google key | Fallback to Serper/PubMed works |
| 4 | Inject irrelevant chunks | All rejected (score < 0.35) |
| 5 | Large document | Bounded chunks, stable memory |
| 6 | Contradictory chunks | Integrity score drops below gate |
| 7 | API disabled | Fallback produces structured output with low confidence |
| 8 | Force new info discovery | Novelty score increases |
| 9 | Inputs for each CASE | Correct decision for each |
| 10 | CASE_1 input | LTM-Global count increases |
| 11 | Missing mandatory section | Non-zero exit code |

### 11.6 Per-Phase Done Checklists

**Phase 0 – Initialization & Novelty**:
- [ ] VWM collection created or recovered
- [ ] SHA256 fingerprint recorded
- [ ] Global & stage similarity checked
- [ ] Duplicate path sets proceed=False with peer vector ID
- [ ] Output JSON: status, fingerprint, vwm_collection, timestamps

**Phase 1 – Contextualization**:
- [ ] HPRP retrieval from LTM-Stage/LTM-Global
- [ ] Strategic plan JSON with knowledge_gaps, priorities, strategies
- [ ] Streaming capture & token usage recorded

**Phase 2 – Query Generation**:
- [ ] No hard-coded queries
- [ ] Distribution derived from config
- [ ] Deduplication & linting applied
- [ ] Authority anchors applied
- [ ] final_queries >= configured minimum (20)

**Phase 3 – Search Execution**:
- [ ] True async with semaphore (not sequential)
- [ ] Source counts by engine logged
- [ ] Unique URLs counted
- [ ] Content fetch success rate logged
- [ ] JS/PDF handling implemented
- [ ] Paywall routing documented

**Phase 4 – Relevance Filtering**:
- [ ] Two-stage IsREL (hard + soft gate)
- [ ] Score fusion applied
- [ ] Tier assignment (gold/silver/bronze/rejected)
- [ ] Chunks passed >= minimum threshold

**Phase 5 – VWM Indexing**:
- [ ] Semantic chunking with stage-appropriate template
- [ ] GPU embeddings generated (or explicit CPU fallback)
- [ ] VWM add succeeds (or logged failure)
- [ ] High-quality chunk promotion to LTM-Stage

**Phase 6 – NLI Integrity**:
- [ ] NLI (GPU) contradiction scan
- [ ] Pair cap applied for performance
- [ ] Numeric consistency check
- [ ] Integrity score/status with thresholds

**Phase 7 – Dual RAG Analysis**:
- [ ] Evidence-grounded analysis text
- [ ] thinking_process captured
- [ ] confidence score computed
- [ ] Top-K chunk selection
- [ ] Context budgeting (no prompt overflow)
- [ ] [CITE:chunk_id] tokens in output

**Phase 9 – Adversarial QA**:
- [ ] 3-5 adversarial questions generated
- [ ] Answers grounded in evidence
- [ ] evidence_strength computed
- [ ] signal_novelty computed

**Phase 10 – Gating Logic**:
- [ ] CASE_1/2/3/4 decision made
- [ ] Clear justification provided
- [ ] Case 2/3 never discards previous outputs
- [ ] Retry scheduled if not CASE_1

**Phase 11 – Knowledge Integration**:
- [ ] LTM-Global update only on CASE_1
- [ ] Claims persisted with citations
- [ ] Cross-references created
- [ ] Archive path recorded

**Phase 12 – Research Packaging**:
- [ ] Late binding applied ([CITE:x] → [1])
- [ ] Citations array finalized
- [ ] Word count >= 2000 (deep_research mode)
- [ ] Citation count >= 5
- [ ] success=True only on CASE_1

### 11.7 Red Flags (Halt Immediately)

The system MUST halt immediately if any of these conditions are detected:

| Red Flag | Detection | Action |
|----------|-----------|--------|
| Vector count != 175 | work_queue.json validation | HALT |
| Missing phase file | Phase import fails | HALT |
| Placeholders in output | Regex scan for TODO/FIXME | HALT |
| Stage/region policy violated | Regional stage with GLOBAL | HALT |
| Sequential search/fetch | No async/semaphore usage | HALT |
| Hard-coded vector IDs | Static analysis | HALT |
| Hard-coded thresholds | Static analysis | HALT |
| Demo-only code path | `--test-fixture` off but demo code runs | HALT |

---

## 12. Session Management

### 12.1 Session Startup Protocol

At the start of EVERY execution, the system MUST:

```
STEP 1:  Load CLAUDE.md and ground_rules.md (validate SHA256)
STEP 2:  Load config/.env (fail fast if API keys missing)
STEP 3:  Load state/work_queue.json (validate 175 vectors)
STEP 4:  Load state/progress_ledger.jsonl (parse all entries)
STEP 5:  Load state/last_pointer.json (identify resume point)
STEP 6:  Check logs/restart.md exists → follow restart protocol
STEP 7:  Log session initialization with timestamp and context
STEP 8:  Enumerate CUDA devices and log availability
STEP 9:  Verify external API connectivity (health checks)
STEP 10: Begin execution from resume point or start
```

### 12.2 Restart Protocol

If execution was interrupted (crash, timeout, manual stop):

1. **Check `logs/restart.md`** for explicit restart instructions
2. **Read `state/last_pointer.json`** to find last successful checkpoint:
   ```json
   {
     "vector_id": "S1V5_HVAC_Systems_EUROPE",
     "phase": 4,
     "attempt": 1,
     "timestamp": "2026-01-17T10:15:00Z"
   }
   ```
3. **Validate checkpoint**:
   - Confirm output file exists for last completed phase
   - Verify SHA256 matches ledger entry
4. **Resume execution**:
   - Start from phase N+1 (if phase N completed)
   - Or retry phase N (if phase N was "running")
5. **Log resume** in session_log.md with evidence

### 12.3 Graceful Shutdown

On SIGINT/SIGTERM:

```python
def graceful_shutdown(signum, frame):
    """Handle graceful shutdown on interrupt."""
    logger.warning("Shutdown signal received, completing current operation...")

    # 1. Mark current phase as interrupted (not failed)
    append_ledger(current_vector_id, current_phase, "interrupted")

    # 2. Write restart instructions
    write_restart_md(
        vector_id=current_vector_id,
        phase=current_phase,
        message="Interrupted by user. Resume from this point."
    )

    # 3. Update last_pointer to safe checkpoint
    # (last COMPLETED phase, not current)
    update_last_pointer(last_completed_vector, last_completed_phase)

    # 4. Cleanup resources
    cleanup_vwm_connections()
    cleanup_gpu_memory()

    # 5. Exit cleanly
    sys.exit(130)  # 128 + SIGINT(2)
```

### 12.4 Violation Protocol

When a violation is detected:

| Severity | Examples | Action |
|----------|----------|--------|
| **CRITICAL** | Spec violation, hard-coding, placeholders | STOP immediately, fix, log cause/prevention |
| **HIGH** | Silent simplification, missing quality gate | REVERT, implement full logic, log |
| **MEDIUM** | Suboptimal performance, missing log | Fix within session, log |
| **LOW** | Style violation, missing comment | Fix when convenient, log |

**Violation Log Entry**:
```
[VIOLATION] CRITICAL
- Type: Hard-coded threshold
- Location: phase4_relevance.py:123
- Code: `if score > 0.5:`  # Should be from config
- Fix: Replace with `if score > config.relevance.soft_threshold:`
- Prevention: Add pre-commit hook to scan for numeric literals
```

### 12.5 Audit Triggers

Automatic self-audit MUST be performed when:

| Trigger | Audit Scope |
|---------|-------------|
| New file created | File naming, location, purpose |
| Edit > 50 lines | Logic correctness, test coverage |
| Repeated error (3x) | Root cause analysis |
| Memory > 70% | Memory leak check, cleanup |
| Phase takes > 5 min | Performance bottleneck analysis |
| API error rate > 10% | API health, rate limit check |

---

## 13. Configuration

### 13.1 Environment Variables

```bash
# API Keys
OPENAI_API_KEY=sk-...
GOOGLE_CSE_API_KEY=...
GOOGLE_CSE_CX=...
SERPER_API_KEY=...
S2_API_KEY=...

# Paths
CHROMA_PERSIST_DIR=./memory/chroma_db
OUTPUT_DIR=./outputs
LOG_DIR=./logs
STATE_DIR=./state

# Performance
MAX_CONCURRENT_FETCHES=10
FETCH_TIMEOUT_SECONDS=30
LLM_TIMEOUT_SECONDS=60
MAX_RETRIEVAL_ITERATIONS=5
GPU_DEVICE=0

# Quality Thresholds
RELEVANCE_HARD_THRESHOLD=0.35
RELEVANCE_SOFT_THRESHOLD=0.55
VERIFICATION_THRESHOLD=0.60
MIN_CITATION_COUNT=5
MIN_WORD_COUNT=2000
```

### 13.2 Config Files

```
config/
├── .env                      # API keys and secrets
├── settings/
│   ├── thresholds.yaml      # Quality thresholds
│   ├── chunking.yaml        # Chunking parameters
│   ├── models.yaml          # Model configurations
│   ├── search_sources.yaml  # Search engine settings
│   ├── geographic_regions.yaml
│   └── quality_gates.yaml
└── vector_library.py         # 175 vector definitions
```

---

## 14. Monitoring

### 14.1 Key Metrics

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `vectors_completed` | Total vectors successfully processed | N/A |
| `vectors_failed` | Total vectors in CASE_3/4 | > 10% |
| `phase_latency_p95` | 95th percentile phase time | > 5 min |
| `hallucination_rate` | Claims failing verification | > 10% |
| `citation_accuracy` | Citations semantically matching | < 90% |
| `fetch_success_rate` | URLs successfully fetched | < 70% |

### 14.2 Progress Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│                    POLARIS PROGRESS DASHBOARD                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Overall: 87/175 vectors (49.7%)  ████████████░░░░░░░░░         │
│                                                                  │
│  Stage 1:  35/35 ████████████████████ 100%                      │
│  Stage 2:  21/21 ████████████████████ 100%                      │
│  Stage 3:  15/15 ████████████████████ 100%                      │
│  Stage 4:  10/10 ████████████████████ 100%                      │
│  Stage 5:   6/12 ██████████░░░░░░░░░░  50%                      │
│  Stage 6:   0/8  ░░░░░░░░░░░░░░░░░░░░   0%                      │
│  ...                                                             │
│                                                                  │
│  Current: S5V7_Household_Water_Filter_GLOBAL @ Phase 4          │
│  Last completed: S5V6 (CASE_1) - 2026-01-17 10:15:30           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 15. Implementation Checklist

### Phase 1: Foundation
- [ ] Vector library with 175 vectors validated
- [ ] Work queue generation from vector library
- [ ] Progress ledger with atomic writes
- [ ] Last pointer for resume capability
- [ ] ChromaDB setup with tri-level collections

### Phase 2: Pipeline Core
- [ ] Phase 0: Initialization with novelty check
- [ ] Phase 1: LTM contextualization
- [ ] Phase 2: Query generation with rebalancer
- [ ] Phase 3: Federated search with fallbacks
- [ ] Phase 4: Two-stage IsREL filtering

### Phase 3: Intelligence
- [ ] Phase 5: Semantic chunking with templates
- [ ] Phase 6: NLI integrity checking
- [ ] Phase 7: Dual RAG synthesis
- [ ] Phase 8: Claim verification
- [ ] Phase 9: Adversarial QA
- [ ] Phase 10: Gating logic

### Phase 4: Integration
- [ ] Phase 11: LTM-Global promotion
- [ ] Phase 12: Report packaging
- [ ] Phase 13: Cross-vector synthesis
- [ ] Citation registry with late binding
- [ ] Quality gates per phase

### Phase 5: Production
- [ ] Orchestrator with concurrency control
- [ ] Error handling and retry logic
- [ ] Monitoring and alerting
- [ ] Documentation and runbooks

---

## Appendix A: Stage-Vector Matrix

| Stage | Regional Vectors | Global Vectors | Total |
|-------|-----------------|----------------|-------|
| 1 | 35 × 3 regions | - | 105 |
| 2 | 21 × 3 regions | - | 63 |
| 3 | 15 × 3 regions | - | 45 |
| 4 | - | 10 | 10 |
| 5 | - | 12 | 12 |
| 6 | 8 × 3 regions | - | 24 |
| 7 | - | 16 | 16 |
| 8 | 10 × 3 regions | - | 30 |
| 9 | - | 10 | 10 |
| 10 | - | 8 | 8 |
| 11 | - | 10 | 10 |
| 12 | - | 10 | 10 |
| 13 | - | 10 | 10 |

**Note**: The 175 vectors count is per-application template count. When running for a specific application with all regions, the actual execution count varies based on regional expansion.

---

## Appendix B: Detailed Component Schemas

### B.1 Query Analyzer Output

```python
@dataclass
class AnalyzedQuery:
    original_query: str
    intent: str  # "factual", "comparative", "exploratory", "evaluative"
    hard_constraints: List[Constraint]  # Must be satisfied
    soft_constraints: List[Constraint]  # Should be satisfied
    geographic_scope: Optional[str]  # "NORTH_AMERICA", "EUROPE", "GLOBAL"
    temporal_scope: Optional[str]  # "recent_5_years", "historical", "all"
    sub_queries: List[str]  # Decomposed search queries
    expected_answer_type: str  # "report", "list", "comparison", "single_fact"
    domain_hints: List[str]  # e.g., ["medical", "regulatory"]
    authority_requirements: str  # "any", "authoritative", "peer_reviewed"
```

**Hard Constraints** (must appear in evidence):
- Specific entities mentioned (e.g., "C-POLAR", "antimicrobial")
- Geographic requirements (e.g., "North America only")
- Temporal requirements (e.g., "after 2020")
- Domain requirements (e.g., "peer-reviewed")

**Soft Constraints** (should appear if possible):
- Topical relevance
- Source authority preferences
- Recency preferences

### B.2 Content Fetcher Output

```python
@dataclass
class FetchedDocument:
    url: str
    title: str
    content: str  # Full extracted text
    content_type: str  # "html", "pdf", "snippet_only"
    fetch_status: str  # "success", "partial", "failed"
    fetch_method: str  # "requests", "playwright", "archive", "academic_api"
    metadata: DocumentMetadata
    word_count: int
    fetch_timestamp: str
    content_hash: str  # SHA256 for deduplication
    extraction_confidence: float  # 0.0-1.0

@dataclass
class DocumentMetadata:
    author: Optional[str]
    date: Optional[str]
    doi: Optional[str]
    journal: Optional[str]
    abstract: Optional[str]
    keywords: List[str]
    language: str
    geographic_mentions: List[str]
```

**Content Fetch Pipeline**:
```
URL → URL Classify → Academic? → Academic Fetcher (DOI/PubMed/S2)
                   → PDF? → PDF Extractor (PyMuPDF)
                   → Paywall? → Bypass Strategy (Archive.org, Googlebot)
                   → Standard? → HTML Fetcher (requests → Playwright fallback)
```

### B.3 Sufficiency Checker Output

```python
@dataclass
class SufficiencyResult:
    is_sufficient: bool
    confidence: float  # 0.0-1.0
    coverage_score: float  # What % of constraints addressed
    evidence_depth: float  # Quality and quantity of evidence
    missing_constraints: List[str]  # Unaddressed requirements
    recommendation: str  # "proceed", "iterate", "insufficient"
    epistemic_state: str  # "high_confidence", "medium", "low", "uncertain"

    # Detailed breakdown
    hard_constraint_coverage: Dict[str, bool]
    soft_constraint_coverage: Dict[str, float]
    gold_chunk_count: int
    silver_chunk_count: int
    unique_source_count: int
    total_evidence_words: int
```

**Sufficiency Thresholds** (from config):
```yaml
sufficiency:
  min_gold_chunks: 5
  min_total_chunks: 15
  min_unique_sources: 5
  min_evidence_words: 10000
  hard_constraint_coverage: 1.0  # All must be met
  soft_constraint_coverage: 0.6  # 60% should be met
```

### B.4 Claim Extractor Output

```python
@dataclass
class Claim:
    claim_id: str  # Unique identifier
    text: str  # The claim statement
    claim_type: str  # "factual", "statistical", "comparative", "causal"
    evidence_ids: List[str]  # Chunk IDs supporting this claim
    primary_source_url: str  # Main source URL
    confidence: float  # Extraction confidence
    atomic_facts: List[AtomicFact]  # Decomposed atomic statements
    verification_status: str  # "pending", "verified", "partial", "rejected"
    geographic_scope: Optional[str]  # Region this claim applies to
    temporal_scope: Optional[str]  # Time period this claim applies to

@dataclass
class AtomicFact:
    fact_id: str
    text: str  # Single verifiable statement
    parent_claim_id: str
    verification_result: Optional[str]  # "entailed", "neutral", "contradicted"
    verification_score: Optional[float]
```

**Claim Extraction Prompt**:
```
Extract factual claims from the following evidence that answer this query:
Query: {query}

Evidence:
{formatted_chunks}

For each claim:
1. State the claim clearly and specifically
2. Cite the evidence ID supporting it: [CITE:chunk_id]
3. Categorize as: factual, statistical, comparative, or causal
4. Note geographic and temporal scope if applicable

Output format:
- Claim: [claim text] [CITE:chunk_id]
- Type: [claim_type]
- Scope: [geographic] / [temporal]
```

### B.5 NLI Verifier Output

```python
@dataclass
class VerificationResult:
    claim_id: str
    status: str  # "supported", "partial", "rejected"
    support_score: float  # 0.0-1.0 (entailed facts / total facts)
    contradiction_score: float  # 0.0-1.0 (contradicted facts / total facts)
    neutral_score: float  # 0.0-1.0 (neutral facts / total facts)
    atomic_facts_total: int
    atomic_facts_supported: int
    atomic_facts_contradicted: int
    atomic_facts_neutral: int
    evidence_used: List[str]  # Chunk IDs
    issues: List[VerificationIssue]  # Specific problems found

@dataclass
class VerificationIssue:
    issue_type: str  # "contradiction", "unsupported", "partial_match"
    atomic_fact: str
    evidence_text: str
    explanation: str
```

**NLI Verification Pipeline**:
```
┌─────────────────────────────────────────────────────────────────┐
│  For each (claim, evidence) pair:                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Atomic Fact Decomposition                              │
│  "X reduces Y by 50% in region Z"                               │
│     → ["X reduces Y", "Reduction is 50%", "Applies to region Z"]│
│                                                                  │
│  Step 2: NLI Classification (per atomic fact)                   │
│  Model: DeBERTa-v3-large-mnli (GPU accelerated)                 │
│  Input: (evidence_text, atomic_fact)                            │
│  Output: ENTAILMENT (0.92) | NEUTRAL (0.05) | CONTRADICTION (0.03)│
│                                                                  │
│  Step 3: Aggregate Scores                                       │
│  support_score = entailed_facts / total_facts                   │
│  contradiction_score = contradicted_facts / total_facts         │
│                                                                  │
│  Step 4: Verification Decision                                  │
│  SUPPORTED: support >= 0.60, contradiction == 0                 │
│  PARTIAL: support >= 0.40, contradiction < 0.2                  │
│  REJECTED: contradiction > 0 OR support < 0.40                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix C: Testing Strategy

### C.1 Test Pyramid

```
                    ┌─────────────┐
                    │   E2E Tests │  (10%)
                    │  Full vector│
                    │  execution  │
                    └─────────────┘
                   ┌───────────────┐
                   │ Integration   │  (30%)
                   │ Multi-phase   │
                   │ workflows     │
                   └───────────────┘
                  ┌─────────────────┐
                  │   Unit Tests    │  (60%)
                  │ Single function │
                  │ or component    │
                  └─────────────────┘
```

### C.2 Test Categories

| Category | What We Test | Example | Location |
|----------|--------------|---------|----------|
| Unit | Individual functions | `test_semantic_chunker_splits_correctly` | `tests/unit/` |
| Integration | Phase-to-phase flow | `test_phase3_to_phase4_handoff` | `tests/integration/` |
| E2E | Full vector pipeline | `test_s1v1_produces_valid_report` | `tests/e2e/` |
| Regression | Fixed bugs stay fixed | `test_bug_401_threshold_not_too_strict` | `tests/regression/` |
| Golden | Known-good outputs | `test_s1v1_matches_golden_output` | `tests/golden/` |
| Contract | Phase I/O schemas | `test_phase4_output_matches_schema` | `tests/contract/` |

### C.3 Quality Metrics Tests

```python
def test_output_quality(report: ResearchReport):
    """Validate report meets quality standards."""
    # Confidence threshold
    assert report.confidence_score >= 0.6, \
        f"Confidence too low: {report.confidence_score}"

    # Citation requirements
    assert len(report.citations) >= 5, \
        f"Not enough citations: {len(report.citations)}"

    # Verification rate
    verification_rate = report.claims_verified / max(report.claims_total, 1)
    assert verification_rate >= 0.8, \
        f"Verification rate too low: {verification_rate}"

    # Word count
    assert report.word_count >= 2000, \
        f"Report too short: {report.word_count} words"

    # Source diversity
    unique_domains = len(set(c.domain for c in report.citations))
    assert unique_domains >= 5, \
        f"Not enough source diversity: {unique_domains} domains"

    # No orphan citations
    cited_numbers = set(re.findall(r'\[(\d+)\]', report.answer))
    actual_numbers = set(c.number for c in report.citations)
    assert cited_numbers == actual_numbers, \
        f"Citation mismatch: cited={cited_numbers}, actual={actual_numbers}"

def test_no_hallucination_markers(report: ResearchReport):
    """Check for common hallucination patterns."""
    hallucination_patterns = [
        r'\[CITE:[^\]]+\]',  # Unreplaced cite tokens
        r'\[\d+\](?!\s*[A-Z])',  # Citation not followed by content
        r'According to .* \[\d+\].*\[\d+\]',  # Double citation (suspicious)
    ]
    for pattern in hallucination_patterns:
        matches = re.findall(pattern, report.answer)
        assert len(matches) == 0, f"Hallucination pattern found: {matches}"
```

### C.4 Phase-Specific Test Requirements

| Phase | Required Tests | Pass Criteria |
|-------|---------------|---------------|
| 0 | VWM creation, duplicate detection | Collection exists, fingerprint stored |
| 1 | LTM query, strategic plan generation | Plan has gaps and focus areas |
| 2 | Query generation, bucket distribution | >= 20 queries, all buckets populated |
| 3 | Search execution, content fetch | >= 60% success rate |
| 4 | IsREL filtering, tier assignment | Chunks have scores and tiers |
| 5 | Chunking, embedding, VWM indexing | Chunks indexed with embeddings |
| 6 | NLI integrity check | Integrity score calculated |
| 7 | RAG synthesis, citation tokens | Analysis has [CITE:x] markers |
| 8 | Adversarial QA | Questions generated and answered |
| 9 | Gating decision | CASE_1/2/3/4 assigned with justification |
| 10 | LTM promotion (CASE_1 only) | Claims persisted if CASE_1 |
| 11 | Report assembly, late binding | Citations finalized to [1], [2] |

---

## Appendix D: Resource Requirements

### D.1 Hardware Requirements

| Resource | Minimum | Recommended | Notes |
|----------|---------|-------------|-------|
| CPU | 4 cores | 8+ cores | For parallel fetching |
| RAM | 16 GB | 32+ GB | Embedding models load to RAM |
| GPU | None | NVIDIA RTX 3080+ (10GB VRAM) | For NLI and embeddings |
| Storage | 50 GB | 200+ GB | ChromaDB + outputs |
| Network | 10 Mbps | 100+ Mbps | For concurrent fetching |

### D.2 GPU Memory Requirements

| Model | VRAM Required | Fallback |
|-------|---------------|----------|
| DeBERTa-v3-large-mnli | ~3 GB | CPU (10x slower) |
| sentence-transformers (embeddings) | ~1 GB | CPU (5x slower) |
| Cross-encoder reranker | ~1 GB | CPU (8x slower) |
| **Total GPU** | ~5 GB | All can run on CPU |

### D.3 API Cost Estimates (per vector)

| API | Calls/Vector | Cost/Call | Est. Cost/Vector |
|-----|--------------|-----------|------------------|
| OpenAI GPT-4 | 3-5 | ~$0.03-0.10 | $0.15-0.50 |
| Serper | 20-30 | ~$0.004 | $0.08-0.12 |
| Google CSE | 10-15 | Free (100/day) | $0.00 |
| **Total/Vector** | | | **$0.25-0.65** |
| **Total/175 Vectors** | | | **$44-114** |

---

## Appendix E: Decision Log Template

Use this template to track architectural decisions:

| Field | Description |
|-------|-------------|
| **Decision ID** | Unique identifier (e.g., DEC-001) |
| **Date** | Decision date |
| **Decision** | What was decided |
| **Options Considered** | Alternatives evaluated |
| **Choice** | Selected option |
| **Rationale** | Why this choice |
| **Trade-offs** | What we gave up |
| **Stakeholders** | Who was involved |
| **Status** | Proposed / Accepted / Superseded |

**Example Decisions**:

| Decision | Options Considered | Choice | Rationale |
|----------|-------------------|--------|-----------|
| Embedding model | OpenAI, Cohere, Local E5 | OpenAI text-embedding-3-small | Best quality/cost ratio |
| NLI model | DeBERTa, BART-MNLI, T5-NLI | DeBERTa-v3-large-mnli | Highest accuracy on benchmarks |
| Chunking strategy | Fixed-size, Semantic, Hybrid | Semantic with overlap | Better retrieval quality |
| Citation format | Numeric [1], Author-date | Numeric | Simpler, cleaner in reports |
| Memory backend | ChromaDB, Pinecone, Weaviate | ChromaDB | Local, no API costs, sufficient scale |
| Search fallback | Sequential, Parallel | Parallel with fallback chain | Better latency, resilience |

---

## Appendix F: Glossary

| Term | Definition |
|------|------------|
| C-POLAR | Long-duration antimicrobial coating technology |
| Vector | Single research question (stage + application + region) |
| Stage | One of 13 strategic analysis categories |
| VWM | Vector Working Memory (session-scoped) |
| LTM-Stage | Long-Term Memory at stage level |
| LTM-Global | Persistent long-term memory |
| IsREL | Two-stage relevance filtering (hard + soft gate) |
| Late Binding | Deferring citation numbering until after verification |
| CASE_1/2/3/4 | Gating decisions (finalize/iterate/gap/escalate) |
| HPRP | Hierarchical Prior Relevance Prioritization |
| NLI | Natural Language Inference (entailment checking) |
| RRF | Reciprocal Rank Fusion (for merging retrieval results) |
| TAM/SAM/SOM | Total/Serviceable/Obtainable Addressable Market |
| Atomic Fact | Smallest verifiable unit of information |
| Chunk | Segment of document content (~500-1500 words) |
| Hallucination | Generated content not supported by evidence |
| Sufficiency | Having enough evidence to answer query |
| **FactScore** | Ratio of verified atomic facts to total atomic facts (SOTA) |
| **G-Eval** | LLM-as-judge evaluation framework (SOTA) |
| **Chain of Density** | Iterative summarization for information density (SOTA) |
| **STORM** | Perspective-guided question generation methodology (SOTA) |
| **RCS Map** | Ranking and Contextual Summarization from PaperQA2 (SOTA) |

---

## Appendix G: SOTA Evaluation Module

### G.1 Overview

The evaluation module (`src/utils/evaluation.py`) provides comprehensive quality assessment using state-of-the-art metrics:

```
┌─────────────────────────────────────────────────────────────────┐
│                    EVALUATION PIPELINE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Input: Generated report + Evidence corpus                       │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ FactScore Evaluation                                        │ │
│  │ ├── Decompose report into atomic facts                      │ │
│  │ ├── Verify each fact against evidence                       │ │
│  │ └── Score = verified_facts / total_facts                   │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ G-Eval Evaluation (LLM-as-Judge)                            │ │
│  │ ├── Coherence: Logical flow and structure                   │ │
│  │ ├── Fluency: Grammar and readability                        │ │
│  │ ├── Consistency: Internal non-contradiction                 │ │
│  │ └── Relevance: Addresses the research question              │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Citation Metrics                                            │ │
│  │ ├── citation_count: Total citations used                    │ │
│  │ ├── citation_density: Citations per 100 words              │ │
│  │ ├── unique_sources: Distinct URLs cited                     │ │
│  │ └── orphan_citations: Unresolved [CITE:x] tokens           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  Output: EvaluationResult with all metrics                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### G.2 FactScore Implementation

```python
class FactScoreEvaluator:
    """
    Implements FactScore (Min et al., 2023) for hallucination detection.

    FactScore measures the precision of generated text by:
    1. Decomposing text into atomic facts
    2. Verifying each fact against a knowledge source
    3. Computing: score = supported_facts / total_facts
    """

    def decompose_to_facts(self, text: str) -> List[str]:
        """Break text into atomic, verifiable facts."""

    def verify_fact(self, fact: str, evidence: str) -> Tuple[bool, float, str]:
        """Verify a single fact against evidence corpus."""

    def evaluate(self, text: str, evidence: List[str]) -> FactScoreResult:
        """Compute FactScore for generated text."""

@dataclass
class FactScoreResult:
    score: float                    # 0.0-1.0, higher is better
    total_facts: int
    supported_facts: int
    unsupported_facts: int
    fact_details: List[Dict]        # Per-fact verification details
```

### G.3 G-Eval Implementation

```python
class GEvalEvaluator:
    """
    Implements G-Eval (Liu et al., 2023) for LLM-as-judge evaluation.

    Evaluates four dimensions:
    - Coherence: Logical structure and flow
    - Fluency: Grammar, readability, naturalness
    - Consistency: No internal contradictions
    - Relevance: Addresses the research question
    """

    DIMENSION_PROMPTS = {
        "coherence": "Rate the coherence of this text on a scale of 1-5...",
        "fluency": "Rate the fluency of this text on a scale of 1-5...",
        "consistency": "Rate the consistency of this text on a scale of 1-5...",
        "relevance": "Rate how well this text addresses the question on 1-5..."
    }

    async def evaluate_dimension(self, text: str, dimension: str) -> Tuple[float, str]:
        """Evaluate a single dimension."""

    async def evaluate(self, text: str) -> GEvalResult:
        """Evaluate all dimensions."""

@dataclass
class GEvalResult:
    coherence: float      # 1.0-5.0
    fluency: float        # 1.0-5.0
    consistency: float    # 1.0-5.0
    relevance: float      # 1.0-5.0
    overall: float        # Average of all dimensions
    explanations: Dict[str, str]  # Per-dimension justifications
```

### G.4 Citation Metrics

```python
@dataclass
class CitationMetrics:
    citation_count: int           # Total [N] citations found
    unique_sources: int           # Distinct URLs cited
    citation_density: float       # Citations per 100 words
    orphan_citations: int         # Unresolved [CITE:x] tokens
    valid_citation_rate: float    # Valid citations / total citations
```

### G.5 Combined Evaluation

```python
async def evaluate_report(
    report_text: str,
    evidence_chunks: List[str],
    valid_chunk_ids: Set[str],
    llm_client: Any
) -> EvaluationResult:
    """
    Run full evaluation suite on a generated report.

    Returns:
        EvaluationResult with:
        - factscore: FactScoreResult
        - geval: GEvalResult
        - citations: CitationMetrics
        - overall_quality: float (weighted combination)
        - recommendations: List[str] (improvement suggestions)
    """
```

### G.6 Quality Thresholds

| Metric | Excellent | Good | Acceptable | Poor |
|--------|-----------|------|------------|------|
| FactScore | >= 0.90 | >= 0.80 | >= 0.70 | < 0.70 |
| G-Eval Coherence | >= 4.5 | >= 4.0 | >= 3.5 | < 3.5 |
| G-Eval Fluency | >= 4.5 | >= 4.0 | >= 3.5 | < 3.5 |
| G-Eval Consistency | >= 4.5 | >= 4.0 | >= 3.5 | < 3.5 |
| G-Eval Relevance | >= 4.5 | >= 4.0 | >= 3.5 | < 3.5 |
| Citation Density | >= 3.0 | >= 2.0 | >= 1.0 | < 1.0 |
| Orphan Citations | 0 | <= 2 | <= 5 | > 5 |

---

**Document Version**: 3.0 (SOTA UPGRADE)
**Last Updated**: 2026-01-19
**Author**: POLARIS Architecture Team

**Changelog**:
- v3.1: **PIPELINE REPAIR** - Critical bug fixes and resilience patterns (2026-01-26)
  - See Section 16 for complete details
- v3.0: **SOTA UPGRADE** - Comprehensive state-of-the-art improvements across pipeline
  - P2: STORM perspective-guided query generation
  - P4: Semantic Scholar API + RCS Map + domain tier scoring
  - P6: Enhanced contradiction mining with thematic clustering
  - P7: Outline-first generation + thematic claim clustering
  - P8: FactScore atomic decomposition + QA-based verification
  - P12: Grounded conclusions + Chain of Density + filler removal
  - New: Evaluation module (FactScore, G-Eval metrics)
- v2.2: Fixed section numbering (13.x, 14.x, 15.x), verified Phase Runner and Session Management sections complete
- v2.1: Added Phase Runner System (Section 11) and Session Management (Section 12), restored Appendices B-F
- v2.0: Added 175 vector system, 13 stages, regional/global policy, pipeline phases 0-12
- v1.0: Initial architecture document

---

## 16. Pipeline Repair Patterns (2026-01-26)

This section documents critical fixes implemented to resolve pipeline failures, including async concurrency bugs, search quality issues, and state persistence improvements.

### 16.1 Root Cause Analysis

On 2026-01-25, the pipeline failed catastrophically:
- **Symptom**: Pipeline hung for 3+ hours, lost all work
- **Root Cause**: `_run_async()` concurrency bug in `search_agent.py`
- **Cascade**: `asyncio.run()` in thread -> event loop closed -> Serper 100% failure -> DuckDuckGo fallback -> 66% garbage results -> LLM hung on garbage input

### 16.2 Phase 0: Critical Blocking Fixes

#### P0.1 LLM Timeout Enforcement
**File**: `src/agents/base_agent.py`

```python
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

def call_llm_structured(self, messages, output_schema, timeout=None):
    timeout = timeout or self.config.timeout_seconds  # Default 120s
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(structured_llm.invoke, messages)
        try:
            response = future.result(timeout=timeout)
            return response
        except FuturesTimeoutError:
            logger.error(f"LLM timeout after {timeout}s")
            return None
```

#### P0.2 Gemini Transport Fix
**File**: `src/agents/base_agent.py`

```python
self.llm = ChatGoogleGenerativeAI(
    model=model_name,
    transport="rest",  # CRITICAL: Prevents gRPC hanging
)
```

#### P0.3 Synchronous Serper Implementation
**File**: `src/agents/search_agent.py`

```python
def _serper_search_sync(query: str, search_type: str = "search", **kwargs) -> list:
    """Synchronous Serper API - replaces broken _run_async()."""
    response = requests.post(url, json={"q": query, **kwargs}, headers=headers, timeout=30)
    return response.json().get("organic", [])
```

### 16.3 Phase 1: Search Quality Gates

| Fix | File | Description |
|-----|------|-------------|
| P1.1 | analyst_agent.py | Pre-LLM keyword filter + domain-specific keywords |
| P1.2 | search.yaml | Domain blocklist (fandom.com, youtube.com, etc.) |
| P1.3 | graph.py | Cross-encoder threshold 0.1 -> 0.35 |
| P1.4 | analyst_agent.py | Circuit breaker after 50 sources with 0 extractions |
| P1.5 | analyst_agent.py | Cross-encoder filter BEFORE content fetching |
| P1.6 | search_agent.py | Semantic Scholar rate limiting with exponential backoff |

### 16.4 Phase 2: State Persistence

| Fix | File | Description |
|-----|------|-------------|
| P2.1 | analyst_agent.py | Checkpoint after content fetch |
| P2.2 | analyst_agent.py | Checkpoint after each batch |
| P2.5 | analyst_agent.py | Socket cleanup with context managers |

### 16.5 Phase 3: LLM Optimization

| Fix | File | Description |
|-----|------|-------------|
| P3.1 | extraction.yaml, models.yaml | Reduced extraction targets, increased token budget |
| P3.2 | base_agent.py | Progress logging for LLM calls |

### 16.6 Sprint 1 SOTA Improvements

| Fix | Description | Impact |
|-----|-------------|--------|
| 1.1 Trash Compactor | Filter BRONZE/UNVERIFIED evidence before synthesis | -70% garbage |
| 1.2 Model Restoration | Use gemini-3-pro-preview with thinking_budget | +15% faithfulness |
| 1.3 Disable Verifier | Bypass broken verifier loop | -$35-40, -7 hours |
| 1.4 Fix Parser | Make access_date/metadata Optional | 0 parse failures |
| 1.5 Remove Word Pressure | Remove "2000 words" requirement | +10% density |

### 16.7 Success Criteria

| Criterion | Target |
|-----------|--------|
| No hangs | Pipeline completes or fails gracefully |
| No event loop errors | 0 "Event loop is closed" in logs |
| Quality results | <10% irrelevant results reaching LLM |
| Crash recovery | Can resume from checkpoints |
| Reasonable time | Single vector < 60 minutes |

---

## 17. v4 Hybrid Architecture (Future Enhancement)

The v4 Hybrid Architecture represents the next evolution of POLARIS, combining proven patterns from previous versions to maximize both research quality and operational efficiency.

### 17.1 Design Philosophy

The v4 architecture follows the principle of "best of breed" selection:

| Component | Source | Rationale |
|-----------|--------|-----------|
| **Discovery** | v3 | Comprehensive multi-source search with academic integration |
| **Filtering** | v2 | Efficient cross-encoder gate before expensive operations |
| **Synthesis** | v3 | Iterative section-by-section with outline-first approach |
| **Verification** | v2 | Strict faithfulness checking with real NLI scores |

### 17.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        v4 HYBRID PIPELINE                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐            │
│  │   TRIAGE    │────>│   PLANNER   │────>│ SUPERVISOR  │            │
│  │  (novelty)  │     │  (queries)  │     │  (routing)  │            │
│  └─────────────┘     └─────────────┘     └──────┬──────┘            │
│                                                  │                    │
│  ┌───────────────────────────────────────────────┼───────────────┐  │
│  │                    v3 DISCOVERY               │               │  │
│  │  ┌─────────────┐                              v               │  │
│  │  │   SEARCH    │ ◄─── Multi-source: Serper + S2 + CrossRef   │  │
│  │  │   AGENT     │ ◄─── Academic enrichment                     │  │
│  │  │             │ ◄─── Domain blocklist filtering              │  │
│  │  └──────┬──────┘                                              │  │
│  └─────────┼─────────────────────────────────────────────────────┘  │
│            │                                                         │
│  ┌─────────┼─────────────────────────────────────────────────────┐  │
│  │         │              v2 FILTERING                           │  │
│  │         v                                                      │  │
│  │  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     │  │
│  │  │  KEYWORD    │────>│CROSS-ENCODER│────>│   CONTENT   │     │  │
│  │  │  FILTER     │     │   GATE      │     │   FETCH     │     │  │
│  │  │ (relevance) │     │ (th=0.35)   │     │ (parallel)  │     │  │
│  │  └─────────────┘     └─────────────┘     └──────┬──────┘     │  │
│  └─────────────────────────────────────────────────┼─────────────┘  │
│                                                     │                │
│  ┌─────────────────────────────────────────────────┼─────────────┐  │
│  │                    v3 SYNTHESIS                 │             │  │
│  │                                                  v             │  │
│  │  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     │  │
│  │  │  ANALYST    │────>│ SYNTHESIZER │────>│   AUDITOR   │     │  │
│  │  │  AGENT      │     │   AGENT     │     │   AGENT     │     │  │
│  │  │ (extract)   │     │ (section)   │     │  (MiniCheck)│     │  │
│  │  └─────────────┘     └─────────────┘     └──────┬──────┘     │  │
│  └─────────────────────────────────────────────────┼─────────────┘  │
│                                                     │                │
│  ┌─────────────────────────────────────────────────┼─────────────┐  │
│  │                    v2 VERIFICATION              │             │  │
│  │                                                  v             │  │
│  │  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     │  │
│  │  │  VERIFIER   │────>│   CRITIC    │────>│  FINALIZE   │     │  │
│  │  │   AGENT     │     │   AGENT     │     │   NODE      │     │  │
│  │  │ (NLI real)  │     │ (gaps)      │     │ (citations) │     │  │
│  │  └─────────────┘     └─────────────┘     └─────────────┘     │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### 17.3 Component Specifications

#### 17.3.1 v3 Discovery Module

**Purpose:** Maximize evidence coverage through comprehensive multi-source search.

**Components:**
- **Multi-Source Search**: Parallel queries to Serper (web), Semantic Scholar (academic), CrossRef (DOIs)
- **Academic Enrichment**: Automatic DOI resolution and citation extraction
- **Domain Filtering**: Pre-configured blocklist (fandom, youtube, pinterest, etc.)
- **Query Amplification**: STORM-style perspective-guided query generation

**Configuration:**
```yaml
# config/v4/discovery.yaml
discovery:
  sources:
    serper:
      enabled: true
      max_results_per_query: 10
    semantic_scholar:
      enabled: true
      max_results_per_query: 5
      rate_limit_delay_ms: 1100
    crossref:
      enabled: true
      max_results_per_query: 3

  query_amplification:
    perspectives:
      - scientific
      - regulatory
      - commercial
      - consumer
    queries_per_perspective: 5
    total_max_queries: 30
```

#### 17.3.2 v2 Filtering Module

**Purpose:** Efficiently filter irrelevant content before expensive LLM operations.

**Components:**
- **Keyword Filter**: Topic-specific keyword matching from query
- **Cross-Encoder Gate**: ms-marco-MiniLM-L-6-v2 with threshold 0.35
- **Circuit Breaker**: Stop after 50 sources with 0% relevance

**Critical Path:**
```
Raw Results → Keyword Filter → Cross-Encoder → Fetch Content
     100           60              25              25
```

**Configuration:**
```yaml
# config/v4/filtering.yaml
filtering:
  keyword_filter:
    enabled: true
    min_keyword_matches: 1
    domain_keywords_enabled: true

  cross_encoder:
    model: "cross-encoder/ms-marco-MiniLM-L-6-v2"
    threshold: 0.35
    batch_size: 32

  circuit_breaker:
    max_failures: 50
    trigger_action: "CASE_3"
```

#### 17.3.3 v3 Synthesis Module

**Purpose:** Generate high-quality, grounded research output through iterative refinement.

**Components:**
- **Analyst Agent**: Extract entities, facts, claims with configurable limits
- **Synthesizer Agent**: Section-by-section generation with late-binding citations
- **Auditor Agent**: MiniCheck-based sentence-level factuality scoring

**Flow:**
```
Evidence → Extract → Cluster → Outline → Section Draft → Audit → Revise
```

**Configuration:**
```yaml
# config/v4/synthesis.yaml
synthesis:
  extraction:
    entities_per_source: 5
    facts_per_source: 10
    claims_per_source: 5

  outline:
    min_sections: 4
    max_sections: 8
    require_evidence_per_section: 3

  drafting:
    max_tokens_per_section: 1500
    citation_style: "late_binding"

  auditing:
    model: "bespoke-minicheck-7b"
    min_sentence_score: 0.7
    fail_action: "revise"
```

#### 17.3.4 v2 Verification Module

**Purpose:** Ensure factual accuracy through strict NLI-based verification.

**Components:**
- **Verifier Agent**: DeBERTa-v3-large-mnli for claim-evidence alignment
- **Critic Agent**: Gap analysis and contradiction detection
- **Finalize Node**: Late-binding citation resolution

**Verification Chain:**
```
Draft Section → Extract Claims → Verify vs Evidence → Score → Accept/Reject
```

**Configuration:**
```yaml
# config/v4/verification.yaml
verification:
  nli:
    model: "microsoft/deberta-v3-large-mnli"
    entailment_threshold: 0.80
    contradiction_threshold: 0.70
    batch_size: 16

  critic:
    min_faithfulness: 0.70
    min_evidence_coverage: 0.60
    max_hallucination_rate: 0.10

  gating:
    CASE_1: "faithfulness >= 0.85 AND coverage >= 0.80"
    CASE_2: "faithfulness >= 0.70 AND coverage >= 0.60"
    CASE_3: "faithfulness >= 0.50"
    CASE_4: "faithfulness < 0.50"
```

### 17.4 Implementation Roadmap

| Phase | Timeline | Components | Dependencies |
|-------|----------|------------|--------------|
| **Alpha** | Week 1-2 | Config schemas, module interfaces | v3.1 stable |
| **Beta** | Week 3-4 | Discovery + Filtering integration | Alpha complete |
| **RC** | Week 5-6 | Synthesis + Verification integration | Beta complete |
| **GA** | Week 7+ | Production deployment, monitoring | RC validated |

### 17.5 Migration Path

**From v3.1 to v4:**

1. **Configuration Migration**
   - Split existing configs into module-specific files
   - Add new v4 section to existing configs
   - Feature flag for gradual rollout

2. **Code Changes**
   - Abstract filter interfaces for pluggable components
   - Add module-level toggle switches
   - Preserve existing agent code, wrap with new orchestration

3. **Testing Strategy**
   - A/B testing with parallel pipelines
   - Compare v3.1 vs v4 on same vectors
   - Measure: latency, cost, faithfulness, coverage

### 17.6 Expected Improvements

| Metric | v3.1 Baseline | v4 Target | Improvement |
|--------|---------------|-----------|-------------|
| Faithfulness | 0.70 | 0.85 | +21% |
| Evidence Coverage | 0.60 | 0.80 | +33% |
| Latency (per vector) | 45 min | 30 min | -33% |
| LLM Cost | $0.50 | $0.35 | -30% |
| Relevance Rate | 70% | 90% | +29% |

### 17.7 Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Increased complexity | Modular design with clear interfaces |
| Performance regression | Comprehensive benchmarking before rollout |
| Breaking changes | Feature flags for incremental adoption |
| Cost increase from more sources | Efficient filtering reduces downstream costs |

### 17.8 Success Criteria

The v4 Hybrid Architecture is successful when:

1. **Quality:** Faithfulness score >= 0.85 on benchmark vectors
2. **Coverage:** Evidence coverage >= 0.80 for research queries
3. **Efficiency:** 30% reduction in per-vector processing time
4. **Cost:** 30% reduction in API costs through better filtering
5. **Reliability:** Zero silent failures, all errors logged and recoverable
