# Detailed Feature Comparison

## POLARIS vs. Perplexity Max vs. ChatGPT Pro vs. Gemini Ultra vs. Claude Max

**Last Updated:** 2026-02-27
**Methodology:** POLARIS metrics from 47+ production test runs (PG_TEST_003-PG_TEST_047). Competitor metrics from published independent studies, benchmark evaluations, and publicly documented capabilities as of February 2026.

---

## 1. Verification and Factual Accuracy (6 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Claim Verification Method** | NLI model (MiniCheck flan-t5-large, 770M params, 75% LLM-AggreFact benchmark) — independent fact-checking model, NOT LLM self-assessment | None — inline citations without entailment verification | None — LLM self-assessment of its own output | Grounding API — checks against Google Search results (limited to web-available content) | None — LLM self-assessment |
| **Cross-Source Verification** | Yes — claims verified against independent sources from different URLs to break circular self-checking (FIX-048-K1, NLI CrossEncoder) | No | No | No | No |
| **Measured Faithfulness** | 80-100% (NLI-verified across production test runs; best: 100% in PG_TEST_019, typical: 80.5% in PG_TEST_039) | ~63% (37% citation failure rate in independent verification studies) | ~60% (40% fabrication rate in research contexts per Stanford HALLmarks) | ~70% (grounding API accuracy varies significantly by domain and query complexity) | ~65% (self-reported; no independent measurement methodology published) |
| **Hallucination Detection (Post-Synthesis)** | Dual-layer: NLI verification (pre-synthesis) + LettuceDetect ModernBERT token-level audit (post-synthesis, KRLabsOrg/lettucedect-large-modernbert-en-v1) | None | None | None | None |
| **Hallucination Remediation** | Automatic rewrite of sections exceeding 30% hallucination ratio; flagged sections go through iterative refinement with fresh evidence injection | N/A | N/A | N/A | N/A |
| **Anti-Embellishment Controls** | ARCH-4 balanced prompting (asks model to verify AND disprove); FIX-QUOTE post-extraction quote validation; substance scoring rejects thin evidence | None documented | None documented | None documented | None documented |

---

## 2. Evidence Quality Scoring (7 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Multi-Signal Evidence Scoring** | 5-signal weighted composite: Semantic Relevance (0.25), Source Authority (0.25), Content Density (0.20), Freshness (0.10), Factual Grounding (0.20) | None — all sources treated equally | None | None | None |
| **Evidence Tiering** | GOLD (>= 0.65 composite), SILVER (>= 0.40), BRONZE (< 0.40); veto rules force BRONZE for thin quotes (< 5 words), low substance (< 0.2), junk content | None | None | None | None |
| **Source Authority Scoring** | Domain tier system: Tier 1 (.gov, .edu, PubMed, Nature, Science — 0.95), Tier 2 (professional associations — 0.80), Tier 3 (major news — 0.60), Tier 4 (general web — 0.40), Blocklist (marketing sites — 0.00) | No domain differentiation | No domain differentiation | Some preference for authoritative sources (undocumented) | No domain differentiation |
| **Blog/Commercial Source Demotion** | 70% relevance penalty for blog, commercial, marketing, affiliate, opinion, and sponsored source types (NRC-6) | No | No | No | No |
| **Paywall Detection** | Content < 500 chars triggers quote_only verification; paywall domain blocklist (40+ domains) prevents citation of unverifiable paywalled content | No | No | No | No |
| **Content Substance Scoring** | Per-evidence substance score based on word count, numeric data presence, sentence structure, and specificity; minimum thresholds for SILVER (0.2) and GOLD (0.4) | No | No | No | No |
| **Snippet Evidence Capping** | Snippet-only evidence (search result preview text without full content fetch) capped at SILVER maximum; cannot achieve GOLD (FIX-D3) | No — snippets treated same as full content | No | No | No |

---

## 3. Search and Source Diversity (8 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Search Engines** | 6 federated engines: Serper (web), Exa (semantic), Tavily (web), Semantic Scholar (academic, API-key authenticated), OpenAlex (academic, unlimited), DuckDuckGo (fallback) | Proprietary search index | Bing Search API | Google Search | No real-time search capability |
| **Queries Generated Per Research** | 50 sub-queries across 9 perspectives with 3 amplification variants each | Single query with reformulation | Single query with reformulation | Single query with reformulation | No search — relies on training data |
| **Unique Sources Per Report** | 18-47 (measured: 18 in PG_TEST_039, 47 in PG_TEST_036/037) | 5-10 | 3-8 | 5-15 | 3-10 (from training data, not live search) |
| **Academic Search Integration** | Semantic Scholar API (rate-limited, API key authenticated, citation graph traversal) + OpenAlex (unlimited metadata) | Limited academic coverage | No dedicated academic search | Google Scholar (limited API) | No search capability |
| **Citation Chasing (Snowball Search)** | Yes — follows citation chains from high-quality sources using S2 citation graph; max 10 papers per chase (FIX-306) | No | No | No | No |
| **Geographic Targeting** | Region-specific query routing for regional analysis stages (North America, Europe, Asia Pacific); geographic keywords injected into search queries | No geographic targeting | No geographic targeting | Some geographic awareness | No search |
| **Domain Blocklist** | 40+ blocked domains: marketing sites, low-quality aggregators, paywalled content farms, social media (LinkedIn, Medium, Reddit) | Unknown filtering | Partial (undocumented) | Unknown filtering | N/A |
| **Content Fetching Methods** | Multi-method with fallback chain: Jina Reader -> Firecrawl -> trafilatura -> Playwright headless browser -> httpx; concurrent fetching (20 connections) | Proprietary crawler | Bing API (limited content) | Google API (limited content) | No content fetching |

---

## 4. Multi-Perspective Analysis (4 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **STORM Methodology** | Yes — Stanford STORM implementation (arXiv:2402.14207): dynamic perspective discovery, multi-round interview simulation, outline generation from conversations | No | No | No | No |
| **Expert Personas** | 8 personas across 9 perspectives: Scientific, Regulatory, Industry, Economic, Public Health, Historical, Regional, Methodological, Emerging Trends | Single-perspective analysis | Single-perspective analysis | Single-perspective analysis | Single-perspective analysis |
| **Multi-Round Interviews** | 4 question-answer-followup rounds per perspective with live search enrichment during interviews | N/A | N/A | N/A | N/A |
| **Perspective-to-Query Routing** | Queries routed to appropriate search engines by perspective: Scientific -> academic, Regulatory -> government, Industry -> trade publications, etc. | N/A | N/A | N/A | N/A |

---

## 5. Audit Trail and Compliance (8 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Structured Pipeline Trace** | JSONL with 8 event types: node_start, node_end, fetch, llm_call, quality_gate, evidence, verification, synthesis. 1,302+ events per typical run. | None | None | None | None |
| **Per-Claim Verification Verdict** | SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED with confidence score (0.0-1.0) and supporting evidence IDs | Citation presence only (no verification verdict) | No verification data | Grounding score (opaque, no per-claim breakdown) | No verification data |
| **Evidence Provenance Chain** | 8-layer: user query -> sub-query -> search result -> fetched content -> extracted claim -> evidence_id -> verification verdict -> citation in report | URL link only | URL link only | URL link only | No provenance |
| **Cost Transparency** | Per-operation cost ledger (JSONL) with model, input/output tokens, cost per call, cumulative session cost. Typical run: $0.72-$4.95. | Subscription (opaque per-query cost) | Subscription (opaque) | Subscription (opaque) | Subscription (opaque) |
| **EU AI Act Article 11** | Pre-built conformity documentation template mapping audit trail to specific Article 11 requirements (technical documentation, risk management, data governance, transparency, human oversight) | Not available | Not available | Not available | Not available |
| **SOC 2 Type II** | Evidence mapping document covering CC1-CC9, Availability, Processing Integrity, Confidentiality, Privacy | Shared responsibility model (limited) | Shared responsibility model (limited) | Shared responsibility model (limited) | Shared responsibility model (limited) |
| **HIPAA Security Rule** | Technical safeguard mapping with 4-layer audit architecture (JSONL trace, session log, cost ledger, progress ledger) | Not applicable (cloud data processing) | Not applicable | Not applicable | Not applicable |
| **Audit Certificate** | SHA-256 hash of inputs/outputs, query, vector ID, claims count, evidence count, sources, word count, pipeline version, timestamp — included in PDF export | Not available | Not available | Not available | Not available |

---

## 6. Deployment and Data Sovereignty (6 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **On-Premises Deployment** | Full air-gapped capability; POLARIS_DEPLOYMENT_MODE=sovereign disables ALL external API calls; fail-loud on any external request attempt | Cloud only | Cloud only | Cloud only | Cloud only |
| **Local LLM Inference** | vLLM serving any OpenAI-compatible model (default: Kimi K2.5, 1T params, MIT license) | Not available | Not available | Not available | Not available |
| **Local NLI Verification** | MiniCheck flan-t5-large (770M params, Apache 2.0) on customer GPU; optional FaithLens 8B (F1: 87.3) | N/A | N/A | N/A | N/A |
| **Local Search** | SearxNG self-hosted meta-search engine | Not available | Not available | Not available | Not available |
| **Data Residency** | Customer-controlled — deploy in any jurisdiction (EU, Canada, US, air-gapped) | US-based cloud (data processed in US) | US-based cloud | US-based cloud (regional options) | US-based cloud |
| **Vendor Data Access** | Zero vendor access in sovereign mode; all compute, storage, and networking on customer infrastructure | Vendor has access to queries and content | Vendor has access | Vendor has access | Vendor has access |

---

## 7. Report Quality and Output (5 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Report Length (Typical)** | 8,000-12,000 words (measured: 11,583 in PG_TEST_039, 12,616 in PG_TEST_040) | 500-2,000 words | 1,000-3,000 words | 500-2,000 words | 1,000-4,000 words |
| **Report Structure** | Up to 15 sections with hierarchical outline generated from evidence clustering; map-reduce for >200 evidence pieces; cross-section deduplication (Jaccard threshold 0.80) | 3-5 paragraphs | 5-10 paragraphs with headings | 3-5 paragraphs | 5-10 paragraphs with headings |
| **Citations Per Report** | 100-300 (measured: 191 in PG_TEST_039, 304 in PG_TEST_032) | 5-15 inline citations | 5-20 inline citations | 10-30 inline citations | 5-15 inline citations |
| **Contradiction Detection** | DeBERTa-v3-large-mnli identifies conflicting claims within evidence; thematic clustering for within-topic comparison; narrative conflict summaries | Not available | Not available | Not available | Not available |
| **Evidence Per Report** | 200-3,400 pieces (measured: 1,011 in PG_TEST_039, 3,444 in PG_TEST_032), each with 5-signal scoring and tier assignment | N/A (no evidence database) | N/A | N/A | N/A |

---

## 8. Campaign and Enterprise Features (5 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Multi-Vector Campaigns** | 175 research vectors across 13 strategic analysis stages (contamination identification through go-to-market strategy) | Single queries only | Single queries only | Single queries only | Single queries only |
| **Cross-Vector Memory** | Tri-level memory: VWM (session context), LTM-Stage (per-analysis-stage accumulation), LTM-Global (persistent cross-campaign knowledge) using ChromaDB | No cross-query memory | Conversation context (limited window) | No cross-query memory | Project-level context (limited) |
| **Quality Gates** | 6 enforcement points: queries >= 20, fetch success >= 60%, evidence >= 10, faithfulness >= 0.70, words >= 2,000, citations >= 5. Each configurable via environment variables. | None documented | None documented | None documented | None documented |
| **Iterative Refinement** | Up to 3 refinement iterations; gap search targets weak areas; re-verification on new evidence; CASE_1/2/3/4 gating logic with human escalation | Single pass | Limited (1-2 refinements in Deep Research mode) | Multi-step (undocumented iteration count) | Single pass |
| **Pipeline Observability** | Rich real-time dashboard: SSE event streaming, node timing, LLM call costs, evidence accumulation, verification progress, batch metrics | N/A | Progress indicator | Progress indicator | Streaming text only |

---

## 9. Cost and Licensing (4 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Pricing Model** | Annual license: Professional $48K, Enterprise $120K, Sovereign $240K+ | $20/month (Pro) or $200/month (Max) | $200/month (Pro) | $19.99/month (Ultra) | $100-200/month (Max) |
| **Per-Report Cost** | Cloud: $0.72-$4.95 (transparent, logged per-call); Sovereign: $0.05-$0.30 (electricity + amortized hardware) | Included in subscription (opaque per-query) | Included (opaque) | Included (opaque) | Included (opaque) |
| **Model Licensing** | All open: Kimi K2.5 (MIT), MiniCheck (Apache 2.0), LettuceDetect (open), sentence-transformers (Apache 2.0). Zero proprietary dependencies in sovereign mode. | Proprietary | Proprietary (GPT-4/o1) | Proprietary (Gemini) | Proprietary (Claude) |
| **Vendor Lock-In** | None — all models replaceable, OpenAI-compatible API standard, standard JSON output formats | High — proprietary index and models | High — GPT-4 dependency | High — Gemini dependency | High — Claude dependency |

---

## 10. Speed and Operational Characteristics (3 Features)

| Feature | POLARIS | Perplexity Max | ChatGPT Pro | Gemini Ultra | Claude Max |
|---------|---------|----------------|-------------|--------------|------------|
| **Research Time (Standard)** | 60-90 minutes (configurable via PG_MAX_EXECUTION_MINUTES) | 2-5 minutes | 5-15 minutes (Deep Research: 15-30 min) | 5-15 minutes | 2-5 minutes |
| **Concurrent Research** | Single-worker (sequential queue for multi-user; H100 optimization planned) | Multiple concurrent | Multiple concurrent | Multiple concurrent | Multiple concurrent |
| **Real-Time Progress** | SSE event stream with per-node progress, evidence count, faithfulness score, phase labels | Progress bar | Progress indicator | Progress indicator | Streaming text |

---

## Summary: Where POLARIS Wins

| Advantage | Why It Matters |
|-----------|----------------|
| **Only sovereign-deployable option** | The only deep research platform that can run fully air-gapped with zero data exfiltration — critical for government, defense, and regulated industries |
| **Only independently verified output** | The only platform with per-claim NLI verification using a dedicated fact-checking model (not LLM self-assessment) producing machine-readable verdicts |
| **Only compliance-ready platform** | The only platform with pre-built conformity documentation for EU AI Act Article 11, SOC 2 Type II, and HIPAA Security Rule |
| **Deepest research output** | 10-20x more citations, 3-10x more unique sources, 3-6x longer reports than any competitor |
| **Complete evidence chain** | Full provenance from user query to report citation including verification verdicts — no other platform provides this |

## Where Competitors Win

| Advantage | Why It Matters |
|-----------|----------------|
| **Speed** | Cloud competitors deliver in 2-15 minutes vs. POLARIS 60-90 minutes — appropriate for quick lookups |
| **Concurrency** | Cloud competitors handle multiple simultaneous users; POLARIS is currently single-worker |
| **Consumer pricing** | $20-200/month vs. $48K+/year — POLARIS is enterprise-grade, not consumer-grade |
| **Zero deployment** | SaaS requires no infrastructure; POLARIS sovereign mode requires GPU hardware and IT deployment |
| **Broader general knowledge** | Cloud competitors have larger training data for general Q&A; POLARIS is optimized for deep research with verified citations |
