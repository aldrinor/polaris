# EU AI Act Article 11 Compliance Template

## POLARIS Sovereign Deep Research Platform

**Regulation**: Regulation (EU) 2024/1689 (EU AI Act)
**Article**: Article 11 — Technical Documentation
**Compliance Deadline**: August 2, 2026
**Last Updated**: 2026-02-27
**Document Status**: Template — requires customer-specific completion

---

## 1. Executive Summary

This document maps POLARIS capabilities to EU AI Act Article 11 requirements for technical documentation of AI systems. POLARIS is designed as a research augmentation tool that produces cited, verifiable reports. Its architecture inherently satisfies many Article 11 requirements through built-in audit trails, evidence chains, and verification pipelines.

### Risk Classification

Under Annex III of the EU AI Act, POLARIS as a research tool is classified as **limited-risk** for general use. Deployments in specific sectors (healthcare research, legal research, critical infrastructure analysis) may require **high-risk** assessment depending on the customer's use case.

| Use Case | Risk Level | Additional Requirements |
|----------|-----------|------------------------|
| General market research | Limited risk | Transparency obligations (Art. 52) |
| Healthcare/pharma research | Potentially high-risk | Full Art. 9-15 compliance |
| Legal/regulatory research | Potentially high-risk | Full Art. 9-15 compliance |
| Financial research | Potentially high-risk | Full Art. 9-15 compliance |
| Internal business intelligence | Minimal risk | Best practices only |

---

## 2. Article 11(1) — Technical Documentation Requirements

Article 11(1) requires that high-risk AI systems have technical documentation drawn up before the system is placed on the market or put into service, and kept up to date.

### 2.1 General Description of the AI System

| Requirement | POLARIS Implementation | Evidence |
|-------------|----------------------|----------|
| Intended purpose | Autonomous deep research report generation with verified citations | `architecture.md` Section 1.1 |
| Provider information | [CUSTOMER TO COMPLETE] | Company registration |
| Date of system version | Tracked via git commits and version tags | `git log --oneline` |
| Interaction with hardware/software | FastAPI server, LangGraph pipeline, ChromaDB, NLI models | `requirements.txt`, `architecture.md` |
| Description of forms of output | JSON research reports with bibliography, evidence chains, verification verdicts | `src/polaris_graph/schemas.py` |

### 2.2 Detailed Description of Elements and Development Process

| Requirement | POLARIS Implementation | Evidence |
|-------------|----------------------|----------|
| Development methods | 8-node LangGraph pipeline with iterative refinement | `src/polaris_graph/graph.py` |
| Design specifications | Pydantic schema-enforced data contracts between all pipeline nodes | `src/polaris_graph/schemas.py`, `src/polaris_graph/state.py` |
| System architecture | 8 sequential/iterative nodes: plan, search, storm, analyze, verify, evaluate, synthesize, search_gaps | `docs/architecture_diagram.md` |
| Training data | No custom model training; uses pre-trained LLMs via API. NLI model (flan-t5-large) is pre-trained on NLI benchmarks | Model cards on HuggingFace |
| Computational resources | Configurable: cloud mode (API-based) or sovereign mode (local GPU cluster) | `docs/deployment_guide.md` |

### 2.3 Description of Monitoring, Functioning, and Control

| Requirement | POLARIS Implementation | Evidence |
|-------------|----------------------|----------|
| Capabilities and limitations | Produces research reports; does NOT make decisions autonomously | `architecture.md` Section 1.1 |
| Degree of accuracy | Faithfulness measured via NLI verification: target >70%, achieved 80-100% in testing | Test history in `MEMORY.md` |
| Foreseeable unintended outcomes | Hallucination (mitigated by NLI verification), source bias (mitigated by STORM multi-perspective), citation poverty (mitigated by quality gates) | `logs/bug_log.md` |
| Human oversight measures | Researcher/Operator dual-view UI, manual review of all outputs, no automated action on reports | `docs/todo_list.md` Phase 1A.2 |

---

## 3. Article 9 — Risk Management System Mapping

### 3.1 Risk Identification

| Risk Category | Identified Risks | Mitigation in POLARIS |
|---------------|-----------------|----------------------|
| **Hallucination** | LLM generates unsupported claims | NLI verification (MiniCheck flan-t5-large), balanced prompting (verify AND disprove), cross-source corroboration |
| **Source bias** | Over-reliance on single source type | STORM multi-perspective interviews (5 expert viewpoints), federated search across 6+ engines, citation diversity caps |
| **Data leakage** | Research data sent to third parties | Sovereign mode: air-gapped deployment, zero data egress. Cloud mode: API-only interaction, no persistent storage at provider |
| **Misinformation propagation** | Reports contain inaccurate claims | Quality gates (minimum faithfulness 70%), evidence tier scoring (GOLD/SILVER/BRONZE), minimum citation requirements |
| **Automation bias** | Users trust AI output uncritically | Reports include verification verdicts per claim, faithfulness scores per section, evidence provenance chains |

### 3.2 Risk Mitigation Measures

| Measure | Implementation | Verification Method |
|---------|---------------|-------------------|
| NLI claim verification | Every extracted claim verified against source content | `src/polaris_graph/agents/verifier.py`, `src/polaris_graph/agents/nli_verifier.py` |
| Multi-perspective research | STORM methodology: 5 expert perspectives, 3 rounds each | `src/polaris_graph/agents/storm_interviews.py` |
| Source authority scoring | 5-signal scoring: relevance, authority, density, freshness, grounding | `src/polaris_graph/agents/analyzer.py` |
| Citation frequency caps | Maximum 4-5 citations per source, 33% max per section | `.env` configuration: `PG_MAX_CITATIONS_PER_SOURCE`, `PG_MAX_SOURCE_PCT_PER_SECTION` |
| Quality gates | Minimum faithfulness, evidence count, word count, citation count | `src/polaris_graph/state.py` quality gate configuration |
| Iteration loops | Pipeline re-searches and re-verifies until quality thresholds met (max 5 iterations) | `src/polaris_graph/graph.py` evaluate node |

### 3.3 Residual Risk Assessment

| Residual Risk | Probability | Impact | Monitoring |
|---------------|------------|--------|------------|
| NLI false positive (claim marked SUPPORTED when false) | Low (NLI accuracy ~75-80%) | Medium | Cross-source corroboration, LLM fallback verification |
| Source content changes after research | Medium | Low | Timestamp tracking, URL archival in evidence |
| Adversarial source manipulation | Low | High | Domain blocklist, authority scoring, multi-source triangulation |

---

## 4. Article 10 — Data Governance Mapping

### 4.1 Data Sources

| Data Type | Source | Governance |
|-----------|--------|-----------|
| Web search results | Serper, Exa, DuckDuckGo | API-retrieved, URL-referenced, content not stored permanently |
| Academic papers | Semantic Scholar, OpenAlex | Metadata and abstracts, with DOI/URL provenance |
| Page content | Jina, Crawl4AI, Trafilatura | Fetched on-demand, content-hashed, paywall detection |
| User queries | Browser input | Stored in pipeline state, accessible to Researcher and Operator |

### 4.2 Data Quality Measures

| Measure | Implementation |
|---------|---------------|
| Source quality scoring | 5-signal tier system (GOLD >= 0.65, SILVER >= 0.42, BRONZE below) |
| Domain blocklist | Pinterest, Quora, Reddit, Facebook, Twitter, GrandViewResearch, marketing sites filtered |
| Paywall detection | Content < 500 chars flagged as potential paywall, quote-only verification applied |
| Deduplication | SemHash semantic dedup (threshold 0.85), per-URL cap (5 evidence items max) |
| Off-topic filtering | Embedding similarity gate (threshold 0.30) removes irrelevant content |
| Contradiction detection | NLI CrossEncoder identifies conflicting claims across sources |

### 4.3 Data Processing Record

Every pipeline run generates:

| Artifact | Path | Contents |
|----------|------|----------|
| Trace log | `outputs/{vector_id}/trace.jsonl` | Timestamped events for every pipeline node |
| Cost ledger | `logs/pg_cost_ledger.jsonl` | Per-LLM-call cost, tokens, model, duration |
| Evidence registry | `outputs/{vector_id}/result.json` | All evidence with source URL, quote, verification verdict |
| Bibliography | `outputs/{vector_id}/result.json` | All cited sources with metadata |

---

## 5. Article 13 — Transparency Requirements

### 5.1 Audit Trail

POLARIS provides a multi-layer audit trail that traces every claim in the final report back to its source:

```
Final Report Sentence
  |
  +-- [1] Citation reference
       |
       +-- Bibliography entry (URL, title, authors, year)
            |
            +-- Evidence item (quote, source content, verification verdict)
                 |
                 +-- NLI verification score (0.0-1.0)
                 |
                 +-- Cross-source corroboration (supporting sources)
                 |
                 +-- Source quality signals (relevance, authority, density, freshness, grounding)
                      |
                      +-- Search query that found this source
                           |
                           +-- STORM perspective that generated this query
                                |
                                +-- Original user research question
```

### 5.2 Evidence Chain Completeness

| Chain Link | Data Captured | Stored In |
|------------|--------------|-----------|
| User query | Original research question, timestamp | `result.json` |
| Search queries | Generated sub-queries, perspective source | `trace.jsonl` |
| Search results | URLs, snippets, engine, timestamp | `trace.jsonl` |
| Fetched content | Full text, content hash, fetch method | Evidence registry |
| Extracted evidence | Quote, atomic facts, relevance score | `result.json` |
| Verification verdict | SUPPORTED/NOT_SUPPORTED, NLI score, verification type | `result.json` |
| Synthesis | Section text, evidence IDs used, faithfulness score | `result.json` |
| Final report | Complete report, bibliography, metrics | `result.json` |

### 5.3 Verification Verdicts

Every claim in the report carries a machine-verifiable verdict:

| Verdict | Meaning | NLI Score Range |
|---------|---------|-----------------|
| `SUPPORTED` | Claim is entailed by source content | >= 0.75 |
| `NOT_SUPPORTED` | Claim is not entailed by source content | < 0.75 |
| `CONTRADICTED` | Source content contradicts the claim | CrossEncoder NLI > 0.70 |

---

## 6. Article 14 — Human Oversight

### 6.1 Design for Human Oversight

| Requirement | POLARIS Implementation |
|-------------|----------------------|
| Interpretable outputs | Reports in natural language with inline citations; evidence explorer with 5-signal radar charts |
| Ability to override | Operator can cancel pipeline at any time; no automated actions taken on report content |
| Ability to decide not to use | Reports are advisory only; no downstream automation |
| Monitoring capability | Real-time SSE event stream, Rich dashboard, JSONL trace logs |

### 6.2 Dual-View Architecture

| View | Audience | Visible Information |
|------|----------|-------------------|
| **Researcher View** | End users | Report text, citations, bibliography, quality summary bar, evidence explorer |
| **Operator View** | IT/compliance staff | All Researcher data PLUS: pipeline events, token costs, model names, batch sizes, trace events, configuration, faithfulness per section |

---

## 7. Article 15 — Accuracy, Robustness, Cybersecurity

### 7.1 Accuracy Measures

| Metric | Target | Measurement Method | Historical Performance |
|--------|--------|--------------------|----------------------|
| Faithfulness | >= 70% | NLI verification (MiniCheck) | 80-100% across 50+ test runs |
| Citation accuracy | >= 95% | Claim-to-source semantic match | 99.3% ID preservation |
| Source diversity | >= 20 unique sources | URL deduplication count | 13-47 sources per report |
| Word count | >= 10,000 | Character count | 7,500-12,600 words per report |
| Citation count | >= 30 | Citation marker count | 109-304 citations per report |

### 7.2 Robustness Measures

| Measure | Implementation |
|---------|---------------|
| Pipeline checkpointing | LangGraph SQLite checkpointing; resume on crash |
| Timeout handling | Per-node, per-batch, per-LLM-call timeouts with graceful degradation |
| Retry logic | Exponential backoff on API failures, batch-level retry for verification |
| Circuit breaker | Skip provider after N consecutive failures (configurable) |
| Evidence caps | Bounded evidence pools prevent unbounded memory/compute growth |
| Budget guard | Hard USD limit per pipeline run prevents cost runaway |

### 7.3 Cybersecurity Measures

| Measure | Implementation |
|---------|---------------|
| Secret management | API keys in `.env` file, never committed to VCS, masked in logs |
| Network isolation | Sovereign mode: air-gapped, zero egress |
| Input validation | Pydantic models validate all inputs (query length 5-2000 chars) |
| Output sanitization | No user-supplied content in LLM prompts without escaping |
| Dependency management | Pinned versions in `requirements.txt`, no wildcard imports |

---

## 8. Customer-Specific Sections

**Instructions**: The following sections must be completed by the deploying organization based on their specific use case, jurisdiction, and risk assessment.

### 8.1 Provider Information

| Field | Value |
|-------|-------|
| Legal entity name | [COMPLETE] |
| Registration number | [COMPLETE] |
| Contact person (AI compliance) | [COMPLETE] |
| Date of first deployment | [COMPLETE] |
| Intended markets (EU member states) | [COMPLETE] |

### 8.2 Use Case Classification

| Field | Value |
|-------|-------|
| Primary use case | [COMPLETE: e.g., market research, healthcare research, legal analysis] |
| Annex III risk category | [COMPLETE: high-risk or not] |
| Affected persons categories | [COMPLETE: who is affected by the AI system's output] |
| Sector-specific requirements | [COMPLETE: e.g., MDR for medical, MiFID II for financial] |

### 8.3 Conformity Assessment

| Step | Status | Evidence |
|------|--------|----------|
| Risk assessment completed | [COMPLETE] | [Link to risk assessment document] |
| Technical documentation prepared | This document | This file |
| Quality management system | [COMPLETE] | [Link to QMS documentation] |
| Conformity declaration signed | [COMPLETE] | [Link to declaration] |
| CE marking affixed | [COMPLETE] | [Applicable for high-risk only] |

### 8.4 Post-Market Monitoring Plan

| Activity | Frequency | Responsible |
|----------|-----------|-------------|
| Faithfulness score monitoring | Per research run | [COMPLETE] |
| User feedback collection | [COMPLETE] | [COMPLETE] |
| Incident reporting | As needed | [COMPLETE] |
| Annual compliance review | Yearly | [COMPLETE] |
| Model update impact assessment | Per update | [COMPLETE] |

---

## 9. Annex IV — Technical Documentation Checklist

Per Annex IV of the EU AI Act, the following must be documented:

| # | Requirement | POLARIS Coverage | Section |
|---|-------------|-----------------|---------|
| 1 | General description | System overview, intended purpose, versions | 2.1 |
| 2 | Detailed description of elements | Pipeline nodes, data contracts, schemas | 2.2 |
| 3 | Monitoring, functioning, control | Quality gates, iteration logic, human oversight | 2.3 |
| 4 | Risk management system | 5 risk categories, 6 mitigation measures | 3 |
| 5 | Data governance | 4 data sources, 6 quality measures, processing record | 4 |
| 6 | Transparency | 8-layer audit trail, verification verdicts | 5 |
| 7 | Human oversight | Dual-view UI, cancel capability, advisory-only output | 6 |
| 8 | Accuracy metrics | 5 metrics with targets and historical performance | 7.1 |
| 9 | Robustness measures | 6 resilience mechanisms | 7.2 |
| 10 | Cybersecurity | 5 security measures, sovereign deployment option | 7.3 |

---

## 10. Document Maintenance

This document must be updated:
- Before each new version deployment
- When the underlying LLM model changes
- When new data sources are added or removed
- When the risk classification changes
- Annually as part of post-market monitoring

**Document Owner**: [COMPLETE]
**Next Review Date**: [COMPLETE]
**Approval Authority**: [COMPLETE]
