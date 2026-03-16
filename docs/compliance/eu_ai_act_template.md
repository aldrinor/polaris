# EU AI Act Article 11 Conformity Documentation Template

## POLARIS Sovereign Deep Research Platform

**Document Version:** 1.0
**Classification:** Compliance Template — EU AI Act (Regulation (EU) 2024/1689)
**Applicable Articles:** Article 11 (Technical Documentation), Article 9 (Risk Management), Article 10 (Data Governance), Article 13 (Transparency), Article 14 (Human Oversight)
**Last Updated:** 2026-02-27

---

## 1. System Identification

| Field | Value |
|-------|-------|
| **System Name** | POLARIS Sovereign Deep Research Platform |
| **Provider** | [Organization Name] |
| **Risk Classification** | Limited Risk (Article 6 — not listed in Annex III; general-purpose AI system used as research tool) |
| **Intended Purpose** | Automated deep research report generation with verified citations, NLI-based fact-checking, and complete audit trails |
| **Deployment Model** | On-premises sovereign deployment (air-gapped option) or cloud-hosted with customer-controlled infrastructure |
| **Version** | [Semantic Version] |
| **Date of Conformity Assessment** | [Date] |

---

## 2. Article 11(1)(a) — General Description of the AI System

### 2.1 System Purpose

POLARIS is a sovereign deep research platform that processes research queries through an 8-node verified pipeline to produce comprehensive, citation-grounded research reports. The system is designed for organizations that require:

- Verifiable factual accuracy with NLI-based claim verification
- Complete provenance chains from source document to final claim
- Air-gapped deployment capability for data sovereignty
- Full audit trails meeting regulatory documentation requirements

### 2.2 Intended Use

POLARIS generates research intelligence by:

- Processing research queries across 13 strategic analysis stages covering 175 research vectors
- Searching federated sources (web, academic, government databases)
- Conducting multi-perspective STORM interviews (Stanford methodology, arXiv:2402.14207) with 8 expert personas
- Extracting and verifying atomic claims against source material using NLI models
- Producing reports with minimum 30 verified citations from 20+ unique sources
- Maintaining a complete evidence chain for every factual claim

### 2.3 Interaction with Other Systems

| Integration Point | Protocol | Data Flow |
|-------------------|----------|-----------|
| Search Engines (Serper, Exa, Tavily, Semantic Scholar, OpenAlex) | REST API / HTTPS | Outbound queries, inbound search results |
| LLM Provider (OpenRouter / vLLM) | REST API / HTTPS | Outbound prompts, inbound completions |
| NLI Verification (MiniCheck flan-t5-large, local) | Local GPU inference | In-process claim verification |
| Hallucination Detection (LettuceDetect, local) | Local GPU inference | In-process token-level audit |
| Vector Database (ChromaDB, local) | In-process | Evidence embedding storage and retrieval |
| Content Fetching (Jina Reader, Firecrawl, trafilatura) | REST API / HTTPS | Source document retrieval |

### 2.4 Hardware and Software Requirements

| Component | Minimum Specification |
|-----------|-----------------------|
| GPU | NVIDIA with 8GB+ VRAM (CUDA compatible) for NLI/hallucination models |
| CPU | 8 cores, 3.0GHz+ |
| RAM | 32GB |
| Storage | 100GB SSD |
| OS | Windows 10/11, Ubuntu 22.04+, or any Docker-compatible OS |
| Python | 3.11+ |
| Network | Internet access (cloud mode) or fully air-gapped (sovereign mode) |

---

## 3. Article 11(1)(b) — Detailed Description of Pipeline Elements

### 3.1 Eight-Node Pipeline Architecture

POLARIS implements an 8-node LangGraph workflow. Each node is a discrete processing stage with defined inputs, outputs, and quality gates.

| Node | Function | Quality Gate | Threshold |
|------|----------|--------------|-----------|
| 1. **Plan** | Generate 50 sub-queries across 9 STORM perspectives | Query count | >= 20 |
| 2. **Search** | Execute federated web + academic + Exa searches | Fetch success rate | >= 60% |
| 3. **STORM Interviews** | Multi-perspective expert interview simulation (8 personas, 4 rounds each) | Perspective diversity | >= 4 perspectives |
| 4. **Analyze** | Fetch full content, extract atomic claims with 5-signal quality scoring | Evidence pieces extracted | >= 10 |
| 5. **Verify** | NLI-based claim verification against source text (MiniCheck flan-t5-large) | Faithfulness score | >= 0.70 |
| 6. **Evaluate** | Gap analysis, decide whether to iterate or finalize | Integrity score | >= 0.70 |
| 7. **Synthesize** | Cluster evidence, generate outline, write sections, resolve citations | Word count / citation count | >= 2,000 words, >= 5 citations |
| 8. **Search Gaps** | Targeted gap search for underrepresented topics | Coverage improvement | Measurable gain |

### 3.2 Model Inventory

| Model | Purpose | Parameters | License | Deployment |
|-------|---------|------------|---------|------------|
| Kimi K2.5 1T (via OpenRouter/Fireworks) | Query planning, evidence extraction, synthesis, gap analysis | 1 trillion (32B active MoE) | MIT | Cloud API or local vLLM |
| MiniCheck flan-t5-large | NLI claim verification | 770M | Apache 2.0 | Local GPU inference |
| LettuceDetect ModernBERT | Token-level hallucination detection | ~350M | Open | Local GPU inference |
| FaithLens 8B (optional) | Enhanced NLI verification (F1: 87.3) | 8B | Open | Local GPU inference |
| Sentence Transformers (all-MiniLM-L6-v2) | Embedding generation for semantic search | 22M | Apache 2.0 | Local CPU/GPU inference |
| ms-marco-MiniLM-L-6-v2 | Cross-encoder relevance reranking | 22M | Apache 2.0 | Local CPU/GPU inference |
| DeBERTa-v3-large-mnli | NLI contradiction detection in evidence | 434M | MIT | Local GPU inference |

### 3.3 5-Signal Evidence Quality Scoring

Every evidence piece is scored on five independent signals before tier assignment:

| Signal | Weight | Source | Description |
|--------|--------|--------|-------------|
| Semantic Relevance | 0.25 | Embedding cosine similarity (claim vs. query) | Measures topical alignment between extracted claim and original research question |
| Source Authority | 0.25 | Domain authority scoring + source confidence | Government (.gov), academic (.edu), peer-reviewed journals receive highest scores |
| Content Density | 0.20 | Quote substance analysis (word count, numeric data, specificity) | Measures information richness of the extracted evidence |
| Freshness | 0.10 | Publication year with exponential decay | Prioritizes recent sources while retaining seminal works |
| Factual Grounding | 0.20 | NLI self-check score (post-verification) | MiniCheck model's entailment probability for the claim against source text |

**Tier Assignment:**

| Tier | Composite Threshold | Usage in Report |
|------|---------------------|-----------------|
| GOLD | >= 0.65 | Primary evidence, direct citation, highest confidence claims |
| SILVER | >= 0.40 | Supporting evidence, contextual claims |
| BRONZE | < 0.40 | Background information, supplementary context |

**Veto Rules (force BRONZE):** Quote under 5 words, substance score under 0.2, detected junk/boilerplate content, snippet-only evidence capped at SILVER.

---

## 4. Article 9 — Risk Management System

### 4.1 Risk Identification

| Risk Category | Specific Risk | Mitigation | Verification |
|---------------|---------------|------------|--------------|
| **Hallucination** | LLM generates claims not grounded in source material | NLI verification (MiniCheck), LettuceDetect token-level audit, iterative rewrite | Faithfulness score measured per run; target >= 0.70; achieved 80.5-100% in production tests |
| **Source Quality** | Low-quality, paywalled, or off-topic sources contaminate evidence | 5-signal scoring, domain blocklist (40+ domains), paywall detection (FIX-STUB), off-topic gate, blog/commercial source penalty | Tier distribution logged; GOLD/SILVER/BRONZE counts in every trace |
| **Citation Fabrication** | Fabricated URLs or misattributed claims | Late-binding citation resolution (Phase 11 only), bibliography URL validation, evidence_id-to-source traceability | Citation count and source diversity logged; dead URL detection at export |
| **Circular Verification** | Model verifies its own generated claims | Cross-source NLI verification (FIX-048-K1): claims verified against independent sources from different URLs | Cross-source verification count logged in trace events |
| **Bias Amplification** | Single-perspective analysis misses critical viewpoints | STORM multi-perspective interviews with 8+ personas across 9 perspectives (Scientific, Regulatory, Industry, Economic, Public_Health, Historical, Regional, Methodological, Emerging_Trends) | Perspective coverage distribution logged; minimum 4 perspectives enforced |
| **Data Sovereignty** | Research data processed outside customer jurisdiction | Air-gapped sovereign deployment mode; all inference models run locally; no external API calls in sovereign mode | Deployment mode flag (POLARIS_DEPLOYMENT_MODE=sovereign) with fail-loud on any external request |
| **Stale Information** | Outdated sources lead to incorrect conclusions | Freshness signal in 5-signal scoring (weight 0.10); publication year decay; gap search for underrepresented timeframes | Freshness distribution logged in evidence metadata |
| **Contradictory Evidence** | Pipeline presents contradictory claims without resolution | Phase 6 NLI contradiction mining with DeBERTa-v3-large-mnli; thematic clustering; narrative conflict reports | Contradiction count and conflict resolution logged |

### 4.2 Residual Risk Assessment

| Residual Risk | Probability | Impact | Acceptance Rationale |
|---------------|-------------|--------|----------------------|
| LLM occasionally leaks chain-of-thought reasoning | Low (mitigated by defense-in-depth scrubber) | Low (cosmetic, not factual) | Multi-layer CoT scrubbing; thinking_mode=False for prose generation |
| Paywall sources provide incomplete content | Medium | Medium | FIX-STUB detects content < 500 chars; quote_only verification for thin content; paywall domain blocklist |
| Semantic Scholar API returns off-topic academic papers | Medium | Low | Academic result cap (50/query, 500 total); interleave 60/40 web/academic; embedding-based relevance filter |

### 4.3 Risk Monitoring

POLARIS implements continuous risk monitoring through:

- **JSONL Trace Events**: 1,302 structured events per typical research run across 8 event types (node_start, node_end, fetch, llm_call, quality_gate, evidence, verification, synthesis)
- **Quality Gates**: Per-node thresholds that halt or trigger iteration when not met
- **Gating Cases**: Four-case decision framework at evaluation node
  - CASE_1: Sufficient evidence, high confidence — finalize and promote to long-term memory
  - CASE_2: Partial evidence — schedule refinement iteration (up to 3 iterations)
  - CASE_3: Insufficient evidence — return gap report, retry with targeted search
  - CASE_4: Critical failure — HALT pipeline, escalate for human review
- **Cost Ledger**: Per-run cost tracking with session-level aggregation

---

## 5. Article 10 — Data and Data Governance

### 5.1 Training Data

POLARIS does not fine-tune or retrain models. All models are used as-is from their published checkpoints:

| Model | Training Data | Bias Assessment |
|-------|---------------|-----------------|
| MiniCheck flan-t5-large | LLM-AggreFact benchmark (770M params, published evaluation: 75.0% accuracy) | Evaluated on standardized fact-checking benchmarks |
| LettuceDetect ModernBERT | Standard NER/hallucination corpora | Published evaluation on hallucination detection benchmarks |
| Kimi K2.5 1T | Moonshot AI training corpus (MIT licensed) | General-purpose; no domain-specific fine-tuning applied |

### 5.2 Input Data Governance

| Data Source | Governance Control | Retention Policy |
|-------------|-------------------|------------------|
| Web Search Results | Domain blocklist (40+ blocked domains including marketing, paywall, and low-quality sites); domain tier scoring (Tier 1: .gov/.edu, Tier 4: general web) | Stored in outputs/polaris_graph/ as JSON; configurable retention |
| Academic Papers (Semantic Scholar, OpenAlex) | API-key authenticated access; rate limiting (1 RPS); result cap per query | Stored in outputs/ with full provenance metadata |
| Fetched Source Content | Paywall detection (< 500 chars triggers quote_only mode); content cap at 10K chars per source; minimum content threshold (200 chars) | Cached in SQLite content cache with configurable TTL |
| User Queries | Input validation (5-2,000 characters); no PII collection by default | Stored with vector_id in outputs/ |

### 5.3 Output Data Governance

| Output | Governance Control | Traceability |
|--------|-------------------|--------------|
| Research Report | Every claim linked to evidence_id; every evidence_id linked to source_url; bibliography with full provenance | Complete chain: claim -> evidence_id -> source_url -> fetched content -> verification verdict |
| Evidence Database | 5-signal quality scoring; tier assignment (GOLD/SILVER/BRONZE); verification verdict (SUPPORTED/PARTIALLY_SUPPORTED/NOT_SUPPORTED) | Full scoring breakdown per evidence piece in JSONL trace |
| Audit Trail | JSONL structured events; SHA-256 fingerprints on vector inputs; timestamps on all operations | Machine-parseable trace file per research run |

### 5.4 Data Lineage

Every fact in a POLARIS report has a complete lineage:

```
User Query
  -> Plan Node: 50 sub-queries across 9 perspectives
    -> Search Node: federated search results with source URLs
      -> STORM Node: multi-perspective interview evidence
        -> Analyze Node: atomic claim extraction with source attribution
          -> Verify Node: NLI entailment check against source text
            -> Evaluate Node: quality gate decision (CASE 1-4)
              -> Synthesize Node: claim -> [CITE:evidence_id] -> bibliography entry -> source URL
```

---

## 6. Article 13 — Transparency and Provision of Information to Deployers

### 6.1 System Capabilities and Limitations

**Capabilities:**
- Produces research reports of 8,000-12,000 words with 30+ verified citations from 20+ unique sources
- Achieves 80-100% faithfulness scores (measured by NLI verification against source text)
- Processes research queries in 60-90 minutes (standard depth, cloud API mode)
- Supports 175 research vectors across 13 strategic analysis stages
- Provides complete audit trail with 1,302+ structured trace events per run

**Limitations:**
- Faithfulness depends on source availability and quality; paywalled or thin sources reduce verification accuracy
- Academic search quality depends on Semantic Scholar/OpenAlex coverage for the specific domain
- LLM synthesis quality varies by topic complexity; highly technical domains may require domain-specific model tuning
- Processing time increases with evidence volume (up to 3 iterations, 60-minute budget per run)
- Air-gapped mode requires local GPU infrastructure and pre-deployed models

### 6.2 User-Facing Transparency

POLARIS provides the following transparency features in its dashboard:

| Feature | Description | Article 13 Requirement |
|---------|-------------|------------------------|
| Per-Section Faithfulness Badges | Each section heading shows verification percentage | Users informed of confidence level per section |
| Evidence Explorer with Radar Charts | 5-axis visualization (Relevance/Authority/Density/Freshness/Grounding) per evidence source | Users can inspect evidence quality signals |
| GOLD/SILVER/BRONZE Tier Badges | Visual quality tier indicators on each evidence card | Users understand relative evidence quality |
| Citation Popovers | Hover any citation to see source title, quote, URL, and verification verdict | Users can verify any claim against its source |
| Quality Summary Bar | Displays faithfulness %, evidence count, source count at report level | Users have aggregate quality metrics |
| Audit Certificate | SHA-256 hash of inputs/outputs, query, vector ID, claims count, evidence count, sources, words, timestamp | Deployers have reproducibility proof |
| STORM Perspectives Summary | Shows which expert personas were consulted and their perspectives | Users understand analytical breadth |

### 6.3 Deployer Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| Architecture Specification | Complete system design with pipeline flow, quality gates, and invariants | `architecture.md` |
| Ground Rules | Operational directives, error handling, hygiene standards | `ground_rules.md` |
| Deployment Guide | Hardware requirements, installation, configuration, validation | `docs/deployment_guide.md` |
| Runbook | Operational procedures for pipeline monitoring and troubleshooting | `docs/runbook.md` |
| API Documentation | REST API endpoints, request/response schemas, SSE event format | Inline in `src/live_server.py` |

---

## 7. Article 14 — Human Oversight

### 7.1 Human Oversight Mechanisms

| Mechanism | Implementation | Oversight Level |
|-----------|----------------|-----------------|
| **Quality Gate Review** | CASE_4 (critical failure) halts pipeline and escalates to human operator | Mandatory human intervention on critical failures |
| **Operator View (Pipeline Console)** | Real-time dashboard showing pipeline trace, cost breakdown, quality metrics, batch progress | Continuous monitoring capability |
| **Iteration Control** | Maximum 3 iterations enforced; configurable via PG_MAX_ITERATIONS; operator can cancel at any time | Human control over iteration depth |
| **Cancel Button** | UI cancel button and API endpoint to stop any running pipeline | Immediate human intervention capability |
| **Budget Controls** | Per-run cost tracking via JSONL cost ledger; configurable execution time limit (PG_MAX_EXECUTION_MINUTES) | Financial and temporal guardrails |
| **Post-Generation Audit** | LettuceDetect token-level hallucination audit flags sections exceeding 30% hallucination ratio for human review | Automated flag for human review |
| **Export with Audit Certificate** | PDF export includes SHA-256 hash, pipeline version, quality metrics for human verification | Human-verifiable output integrity |

### 7.2 Operator Roles

| Role | Access Level | Oversight Responsibility |
|------|-------------|--------------------------|
| Researcher | Use system, view reports, export PDFs | Review report quality, verify citations |
| Operator | Full pipeline console, diagnostic panels | Monitor pipeline health, review CASE_4 escalations |
| Manager | Review completed reports, quality trends | Approve reports for distribution |
| Auditor | Read-only access to trace logs and audit exports | Verify compliance, review evidence chains |
| Admin | Full configuration access, user management | Manage system settings, deployment configuration |

---

## 8. Conformity Assessment Checklist

| Requirement | Article | POLARIS Implementation | Evidence |
|-------------|---------|------------------------|----------|
| Technical documentation maintained | Art. 11(1) | This document + architecture.md + all docs/ | Document version control |
| Risk management system | Art. 9 | Quality gates, gating cases, NLI verification, hallucination detection | JSONL trace events with quality_gate event type |
| Data governance measures | Art. 10 | Domain blocklist, tier scoring, content caps, paywall detection, input validation | Evidence metadata with full provenance |
| Transparency to deployers | Art. 13 | Dashboard UI, audit certificates, deployer documentation | User-facing transparency features documented above |
| Human oversight capability | Art. 14 | Operator view, cancel, CASE_4 escalation, iteration control, budget limits | Dashboard screenshots, API documentation |
| Logging capabilities | Art. 12 | JSONL structured tracing (1,302+ events/run), session logs, cost ledger | `logs/pg_trace_{vector_id}.jsonl` |
| Accuracy and robustness | Art. 15 | 5-signal scoring, NLI cross-source verification, iterative refinement | Faithfulness scores from production test runs |
| Cybersecurity | Art. 15(4) | Air-gapped mode, local inference, no external data exfiltration in sovereign mode | Deployment mode configuration |

---

## 9. Document Maintenance

This conformity documentation must be updated when:

- Pipeline architecture changes (node additions, model swaps)
- Quality gate thresholds are modified
- New data sources are integrated
- Deployment model changes (new sovereignty features)
- Risk assessment identifies new risks or mitigations

**Review Schedule:** Quarterly, or upon any material change to pipeline components.

**Responsible Party:** [Designated EU AI Act Compliance Officer]

---

*This template is designed to support conformity assessment under Regulation (EU) 2024/1689 (EU AI Act). Organizations deploying POLARIS should adapt this template to their specific deployment context, risk classification, and national implementation requirements.*
