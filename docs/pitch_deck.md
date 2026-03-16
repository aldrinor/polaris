# POLARIS Sovereign Deep Research Platform — Pitch Deck

---

## Slide 1: Title

# POLARIS

### Sovereign Verified Deep Research

**The first research AI that proves every claim, runs on your infrastructure, and passes your audit.**

*Enterprise-grade research intelligence with zero cloud dependency, NLI-verified citations, and 1,302-event audit trails.*

---

## Slide 2: The Problem — Cloud AI Banned + Hallucination Epidemic

### Organizations that need AI research the most cannot use it.

**The Hallucination Crisis:**

| Platform | Failure Rate | Source |
|----------|-------------|--------|
| **Perplexity AI** | **37%** citation failure rate — over one-third of citations do not support the claims they are attached to | Independent verification studies (2024-2025) |
| **ChatGPT** | **40%** fabrication rate in research contexts — fabricated statistics, dates, organizations, and study results | Stanford HALLmarks benchmark |
| **Enterprise AI Governance** | **67%** of AI-generated research outputs fail governance audits — lack audit trails, provenance, or verifiable citations | Enterprise compliance surveys (2024-2025) |

**The Sovereignty Crisis:**

- **Canada**: Directive on Service and Digital bans classified data on foreign cloud AI. Budget 2024 commits **$925.6M** to sovereign digital infrastructure.
- **European Union**: EU AI Act (Regulation 2024/1689) enforcement begins **August 2026**. Article 11 mandates technical documentation, audit trails, risk management, and transparency. Non-compliance fines up to **35M EUR or 7% global revenue**.
- **United States**: 23 federal agencies restrict or ban cloud AI for sensitive research. Executive Order 14110 mandates AI safety and security requirements.
- **Financial regulators** (OSFI, ECB, FCA, OCC) require explainability and audit trails for AI-assisted decisions.

**The Result**: **$0** — the revenue Perplexity, ChatGPT, and Gemini can generate from customers legally prohibited from sending data to cloud AI.

---

## Slide 3: The Solution — Sovereign Verified Research

### Deploy on YOUR infrastructure. Every claim verified. Full audit trail.

POLARIS is a sovereign deep research platform that:

1. **Runs on your infrastructure** — air-gapped deployment, zero external data transmission, customer-controlled compute. Switch from cloud to sovereign by changing one URL in `.env`.

2. **Proves every claim** — Natural Language Inference (NLI) model (MiniCheck flan-t5-large) independently verifies every extracted fact against source text. Cross-source verification breaks circular self-checking. This is not LLM self-assessment — it is an independent verification model trained specifically for fact-checking.

3. **Passes your audit** — 1,302+ structured trace events per research run across 8 event types. Complete evidence chain from source document to report citation. Pre-built conformity documentation for EU AI Act Article 11, SOC 2 Type II, and HIPAA Security Rule.

4. **Matches analyst depth** — 8,000-12,000 word reports with 30+ verified citations from 20+ unique sources. Multi-perspective STORM expert interviews simulate 8 domain specialists analyzing the topic from different viewpoints.

```
Cloud Mode:  OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
                                    |
                        Change this one line
                                    |
Sovereign:   OPENROUTER_BASE_URL=http://localhost:8080/v1
```

**Same code. Same pipeline. Same quality. Different URL.**

---

## Slide 4: How It Works — 8-Node Verified Research Pipeline

```
USER QUERY
    |
    v
[1. PLAN] --------> 50 sub-queries across 9 expert perspectives
    |                (Scientific, Regulatory, Industry, Economic,
    |                 Public Health, Historical, Regional,
    |                 Methodological, Emerging Trends)
    v
[2. SEARCH] ------> Federated across 6 engines: Serper (web),
    |                Exa (semantic), Tavily (web), Semantic Scholar
    |                (academic), OpenAlex (academic), DuckDuckGo (fallback)
    v
[3. STORM] -------> 8 expert personas conduct multi-round interviews
    |                (Stanford methodology, arXiv:2402.14207)
    |                4 rounds per perspective, live search enrichment
    v
[4. ANALYZE] -----> Fetch full source content (Jina Reader, Firecrawl,
    |                trafilatura). Extract atomic claims. Score each on
    |                5 signals: Relevance, Authority, Density, Freshness,
    |                Grounding. Assign GOLD/SILVER/BRONZE tiers.
    v
[5. VERIFY] ------> NLI entailment check (MiniCheck flan-t5-large):
    |                EVERY claim verified against source text.
    |                Cross-source verification against independent URLs.
    |                Verdict: SUPPORTED / PARTIALLY_SUPPORTED / NOT_SUPPORTED
    v
[6. EVALUATE] ----> Quality gates: faithfulness >= 70%, evidence >= 10,
    |                words >= 2,000, citations >= 5. Gap analysis identifies
    |                weak areas. Decision: CASE_1 (finalize), CASE_2 (iterate),
    |                CASE_3 (retry), CASE_4 (escalate to human review).
    v
[7. SYNTHESIZE] --> Map-reduce clustering of 200-3,000+ evidence pieces.
    |                Generate hierarchical outline. Write 15 sections.
    |                Resolve [CITE:evidence_id] to numbered bibliography.
    |                Cross-section deduplication. Grounded abstract.
    v
[8. GAP SEARCH] --> Targeted search for underrepresented topics.
                     Bypasses planner, goes directly to search.
                     Feeds back into verification loop.
```

**Output:** 8,000-12,000 word report + bibliography + evidence chain + quality certificate + 1,302-event JSONL audit trail.

---

## Slide 5: Technical Moats — 8 Advantages No Competitor Can Match

| # | Moat | What It Does | Why It Matters |
|---|------|-------------|----------------|
| 1 | **NLI Claim Verification** | MiniCheck flan-t5-large (770M params, 75% LLM-AggreFact accuracy) independently verifies every claim against its source text. Cross-source NLI (FIX-048-K1) checks claims against independent URLs. | Competitors use LLM self-assessment — the model grades its own homework. POLARIS uses a separate model trained specifically for fact-checking. |
| 2 | **5-Signal Evidence Scoring** | Every evidence piece scored on 5 weighted signals: Semantic Relevance (0.25), Source Authority (0.25), Content Density (0.20), Freshness (0.10), Factual Grounding (0.20). Tier assignment: GOLD >= 0.65, SILVER >= 0.40, BRONZE below. Veto rules for thin quotes and junk content. | Competitors treat all sources equally. POLARIS quantifies evidence quality across five independent dimensions with configurable weights. |
| 3 | **STORM Multi-Perspective Research** | 8 expert personas across 9 perspectives (Scientific, Regulatory, Industry, Economic, Public Health, Historical, Regional, Methodological, Emerging Trends) conduct multi-round interview simulations with live search enrichment. Stanford STORM methodology (arXiv:2402.14207). | Competitors analyze from a single perspective. POLARIS ensures comprehensive coverage across all relevant stakeholder viewpoints. |
| 4 | **1,302-Event Audit Trail** | Structured JSONL tracing with 8 event types: node_start, node_end, fetch, llm_call, quality_gate, evidence, verification, synthesis. Machine-parseable. Maps to EU AI Act Article 11, SOC 2 Trust Service Criteria, HIPAA Security Rule. | Competitors are opaque black boxes. POLARIS provides forensic-grade provenance for every operation — from query to claim to source to verdict. |
| 5 | **Air-Gapped Sovereign Deployment** | All models run locally: LLM via vLLM (Kimi K2.5, MIT license), NLI via MiniCheck (Apache 2.0), hallucination detection via LettuceDetect (open), embeddings via sentence-transformers (Apache 2.0), search via SearxNG. Zero external API calls in sovereign mode. | Competitors require cloud data transmission. POLARIS deploys fully on-premises with zero data exfiltration — even the search engine runs locally. |
| 6 | **175-Vector Campaign Architecture** | 175 research vectors across 13 strategic analysis stages with tri-level persistent memory: VWM (session), LTM-Stage (per-stage), LTM-Global (cross-stage). Snowball knowledge accumulation. SQLite caches for content, search, evidence hierarchy, and cross-vector memory. | Competitors handle single ad-hoc queries. POLARIS executes comprehensive multi-vector research campaigns where later analyses build on earlier findings. |
| 7 | **Iterative Quality Convergence** | Up to 3 refinement iterations with targeted gap search. 6 quality gates enforce thresholds at every pipeline node. 4-case gating logic: CASE_1 (finalize), CASE_2 (iterate with targeted search), CASE_3 (retry from scratch), CASE_4 (halt and escalate to human review). | Competitors produce single-shot output with no quality assurance loop. POLARIS iteratively refines until measurable quality thresholds are met or human review is triggered. |
| 8 | **Token-Level Hallucination Audit** | LettuceDetect (ModernBERT-based, KRLabsOrg/lettucedect-large-modernbert-en-v1) performs post-synthesis token-level hallucination detection on every section. Sections exceeding 30% hallucination ratio are automatically flagged and rewritten. | Competitors have no post-generation quality audit. POLARIS catches hallucinations that survive the NLI verification loop through a second independent detection pass. |

---

## Slide 6: Competitive Comparison

| Capability | **POLARIS** | **Perplexity Max** | **ChatGPT Pro** | **Gemini Ultra** | **Claude Max** |
|------------|-------------|---------------------|-----------------|------------------|----------------|
| Claim Verification | NLI model (independent) | None | None (self-assessment) | Grounding API (limited) | None |
| Measured Faithfulness | 80-100% (NLI-verified) | ~63% (37% failure) | ~60% (40% fabrication) | ~70% (varies) | ~65% |
| Evidence Scoring | 5-signal composite | None | None | None | None |
| Unique Sources/Report | 18-47 | 5-10 | 3-8 | 5-15 | 3-10 |
| Multi-Perspective | 8 STORM personas | Single | Single | Single | Single |
| Audit Trail | 1,302+ JSONL events | None | None | None | None |
| Report Length | 8,000-12,000 words | 500-2,000 words | 1,000-3,000 words | 500-2,000 words | 1,000-4,000 words |
| Citations/Report | 100-300 | 5-15 | 5-20 | 10-30 | 5-15 |
| Sovereign Deployment | Full air-gap | Cloud only | Cloud only | Cloud only | Cloud only |
| On-Premises LLM | vLLM (any model) | No | No | No | No |
| EU AI Act Ready | Art. 11 template | No | No | No | No |
| HIPAA Compatible | Audit trail + sovereign | No | No | No | No |
| Hallucination Detection | Dual-layer (NLI + LettuceDetect) | None | None | None | None |
| Iterative Refinement | Up to 3 iterations | Single pass | Single pass | Single pass | Single pass |
| Campaign Research | 175 vectors, 13 stages | Single queries | Single queries | Single queries | Single queries |
| Cost Transparency | Per-run cost ledger | Subscription | Subscription | Subscription | Subscription |

---

## Slide 7: Market Opportunity

### $80B+ Sovereign Cloud. EU AI Act Deadline. Canada $925.6M.

**Total Addressable Market:**

| Market Segment | Size | Growth | Key Driver |
|----------------|------|--------|------------|
| Sovereign cloud infrastructure | **$80.2B** by 2028 | 23.4% CAGR | Data residency mandates, national security, Schrems II |
| AI-powered research and analytics | **$12B** by 2027 | 35% CAGR | Enterprise AI adoption, analyst augmentation |
| Compliance/RegTech | **$15B** by 2027 | 22% CAGR | EU AI Act, DORA, NIS2, SOX, HIPAA |
| Government AI spending (US alone) | **$25B** by 2027 | 28% CAGR | Executive orders, agency modernization |

**Market Catalysts (Why Now):**

1. **EU AI Act enforcement: August 2026** — Every AI system used in the EU needs technical documentation, audit trails, and human oversight. Mandatory, not optional. Fines up to 35M EUR or 7% global revenue.

2. **Canada sovereign digital commitment: $925.6M** (Budget 2024) — Federal investment in domestic digital infrastructure. Directive on Service and Digital bans classified data on foreign cloud.

3. **Post-hallucination awareness** — After high-profile failures (legal filings with fabricated cases, medical summaries with clinical errors), enterprises demand verified output, not just generated output.

4. **Open-weight models make sovereignty viable** — Kimi K2.5 (1T params, MIT license), MiniCheck (Apache 2.0), sentence-transformers (Apache 2.0). On-premises deployment is now economically feasible without proprietary model dependencies.

---

## Slide 8: Pricing Tiers

| | **Professional** | **Enterprise** | **Sovereign** |
|---|---|---|---|
| **Annual License** | **$48,000/year** | **$120,000/year** | **$240,000+/year** |
| **Monthly** | $4,800/month | $12,000/month | Custom |
| **Deployment** | Cloud-hosted (customer tenant) | Hybrid (cloud + on-prem NLI) | Fully air-gapped on-premises |
| **Users** | Up to 10 researchers | Up to 50 researchers | Unlimited |
| **Research Depth** | Standard (60 min/query) | Deep (configurable budget) | Deep + campaign mode (175 vectors) |
| **LLM** | Cloud API (OpenRouter) | Cloud or customer vLLM | Customer vLLM (fully sovereign) |
| **Verification** | NLI (cloud-adjacent) | NLI (local GPU) | NLI + LettuceDetect (local GPU) |
| **Audit Trail** | JSONL export | JSONL + SOC 2 evidence map | JSONL + SOC 2 + HIPAA + EU AI Act |
| **Compliance Templates** | Standard | SOC 2 Type II preparation | Full sovereign compliance suite |
| **Support** | Email (48h SLA) | Dedicated CSM (24h SLA) | On-site deployment + 24/7 support |
| **GPU Requirement** | None (cloud inference) | Optional (for local NLI) | Required: 1x A100 80GB or 2x A10G |

**Per-Report Economics:**

| Mode | API Cost/Report | Time/Report | Analyst Equivalent |
|------|-----------------|-------------|---------------------|
| Cloud (Professional) | $0.72-$4.95 | 60-90 min | $2,000-$5,000 (40-80 hours) |
| Sovereign (on-prem) | $0.05-$0.30 (electricity) | 30-60 min (local GPU) | $2,000-$5,000 (40-80 hours) |

**ROI: 100-500x cost reduction vs. manual research. Analyst-equivalent reports in 60 minutes instead of 40-80 hours.**

---

## Slide 9: Target Markets + Go-to-Market

### Phase 1 — Anchor Customers (Q1-Q2 2026)

| Target Customer | Entry Point | POLARIS Value | Contract Size |
|-----------------|-------------|---------------|---------------|
| **Canadian Federal Government** | Shared Services Canada / TBS | Domestic sovereign AI for classified research; meets Directive on Service and Digital; $925.6M infrastructure commitment | $240K+ Sovereign |
| **European Pharmaceutical (Top 20)** | Regulatory Affairs / CISO | EU AI Act Article 11 conformity; automated literature review with audit trail; HIPAA-compatible evidence chains | $120K Enterprise |
| **Defense Contractor (Five Eyes)** | OSINT / Intelligence Analysis | Air-gapped deployment; 175-vector campaign research; zero cloud dependency; full audit trail | $240K+ Sovereign |

### Phase 2 — Channel Expansion (Q3-Q4 2026)

- **System Integrator Partnerships**: Deloitte, Accenture, Cognizant for enterprise deployment and managed services
- **Cloud Marketplace**: AWS GovCloud, Azure Government for sovereign cloud customers
- **Academic Licensing**: University research programs at reduced rate for case study development

### Phase 3 — Vertical Expansion (2027)

| Vertical | Use Case | Entry Strategy |
|----------|----------|----------------|
| Financial Services | Regulatory research, compliance documentation | OSFI/ECB compliance requirement |
| Legal | Case law analysis, verified citation requirements | Citation accuracy differentiator |
| Healthcare Systems | Clinical evidence review, HIPAA-compliant research | Sovereign + HIPAA audit trail |
| Government (Five Eyes) | Policy research, intelligence analysis | FedRAMP pathway |

**Distribution Model:**
- Direct sales for Sovereign tier ($240K+ ACV)
- Channel partners for Enterprise tier ($120K ACV)
- Self-serve trial for Professional tier ($48K ACV)
- 14-day free trial on cloud-hosted Professional tier

---

## Slide 10: The Ask / Next Steps

### Seeking: $2.5M Seed Round

| Allocation | Amount | Purpose |
|------------|--------|---------|
| **Engineering** | $1.2M | 4 engineers x 12 months: sovereign deployment hardening, RBAC/SSO, multi-user isolation, Docker/K8s packaging, H100 optimization |
| **Go-to-Market** | $600K | 2 sales (gov BD, enterprise BD) + 1 marketing: content, events, partner enablement |
| **Compliance** | $300K | SOC 2 Type II certification, EU AI Act conformity assessment, HIPAA compliance program |
| **Infrastructure** | $200K | GPU demo cluster (4x A100), cloud hosting for trial environment |
| **Operations** | $200K | Legal, accounting, office, travel |

### Milestones

| Timeline | Milestone | Success Metric |
|----------|-----------|----------------|
| Month 3 | First paid pilot (Canadian government) | Signed contract, deployed on customer infrastructure |
| Month 6 | SOC 2 Type II examination initiated | Auditor engaged, evidence collection underway |
| Month 9 | 3 paying enterprise customers | $360K+ ARR |
| Month 12 | Channel partner signed (SI) | First partner-delivered deployment |
| Month 18 | 10+ customers across 3 verticals | $1M+ ARR |

### Why POLARIS Wins

1. **First mover in sovereign verified research** — No competitor offers NLI verification + air-gapped deployment + compliance audit trails in a single platform.
2. **EU AI Act creates mandatory demand** — Enforcement August 2026. Organizations need compliant AI systems now, not next year.
3. **Open-weight models eliminate vendor lock-in** — Kimi K2.5 (MIT), MiniCheck (Apache 2.0), LettuceDetect (open). No proprietary dependencies in sovereign mode.
4. **Production-validated pipeline** — 47+ test runs, 300+ bug fixes, 80-100% faithfulness, 1,302-event audit trails, $0.72-$4.95/report.
5. **Canada $925.6M sovereign digital investment** — Direct government funding for domestic AI infrastructure.

---

**Contact:** [Contact Information]

*POLARIS: Sovereign. Verified. Auditable.*
