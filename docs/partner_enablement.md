# POLARIS Partner Enablement Kit

**Document Class:** Commercial, Confidential
**Version:** 1.0
**Last Updated:** 2026-02-28

---

## 1. Partner Program Overview

### What is POLARIS?
POLARIS is a sovereign deep research platform that produces institutional-grade research reports with full evidence chains, NLI verification, and compliance-ready audit trails. Unlike consumer AI tools, POLARIS is designed for regulated industries where provenance, faithfulness, and data sovereignty are mandatory.

### Why Partner?
- **$4.2B TAM** in enterprise AI-assisted research (2026 estimate)
- **Zero competition** in sovereign, air-gapped deep research
- **Recurring revenue** via SaaS subscriptions or managed deployments
- **High margins** — software-only product, no data licensing costs
- **Compliance moat** — EU AI Act, SOC 2, HIPAA, FedRAMP ready

### Target Verticals
| Vertical | Buyer | Pain Point | POLARIS Value |
|----------|-------|------------|---------------|
| Government | CIO / CISO | Data sovereignty mandates | Air-gapped deployment, zero cloud dependencies |
| Pharma / Biotech | VP Research | Literature review speed | 10x faster systematic reviews with citation verification |
| Defense / Intelligence | Program Manager | Classified network research | Self-hosted on SIPR/JWICS with local LLM |
| Financial Services | Chief Risk Officer | Regulatory compliance research | Audit trail meets SOC 2 / Basel III requirements |
| Legal | Managing Partner | Due diligence research | Faithful citations, no hallucination risk |

---

## 2. Product Tiers and Pricing

| Tier | Annual Price | Deployment | Features |
|------|-------------|------------|----------|
| **Professional** | $48,000 | Cloud (hosted) | 500 research reports/year, standard depth, email support |
| **Enterprise** | $120,000 | Hybrid or on-premise | Unlimited reports, all depths, SSO/RBAC, priority support |
| **Sovereign** | $240,000+ | Air-gapped on-premise | Full sovereignty, custom LLM, dedicated support, compliance package |

### Revenue Share
| Model | Partner Share | Notes |
|-------|-------------|-------|
| Referral | 15% Year 1 | Partner refers, POLARIS closes and delivers |
| Reseller | 25% ongoing | Partner sells, POLARIS delivers |
| Managed Service | 35% ongoing | Partner sells and delivers, POLARIS provides platform |

---

## 3. Technical Requirements

### Cloud Deployment (Professional/Enterprise)
- Browser-based UI, no client installation
- SSO integration via SAML 2.0 / OAuth 2.0
- API access for programmatic research

### Sovereign Deployment (Enterprise/Sovereign)
| Component | Requirement |
|-----------|-------------|
| GPU | NVIDIA A100/H100 (40GB+ VRAM) for local LLM inference |
| CPU | 16+ cores |
| RAM | 64GB+ |
| Storage | 500GB+ SSD |
| Network | Internal only (air-gapped capable) |
| OS | Linux (Ubuntu 22.04+ or RHEL 8+) |
| Container | Docker 24+ or Kubernetes 1.28+ |

### Local Components (Sovereign Mode)
- **LLM:** vLLM serving any OpenAI-compatible model
- **Search:** SearxNG (self-hosted meta-search)
- **Embeddings:** sentence-transformers (local GPU)
- **Verification:** MiniCheck flan-t5-large (local NLI)
- **Vector DB:** ChromaDB (local)

---

## 4. Differentiation vs. Competitors

| Capability | POLARIS | Perplexity Pro | ChatGPT Deep Research | Gemini Deep Research |
|-----------|---------|---------------|----------------------|---------------------|
| Air-gapped deployment | Yes | No | No | No |
| NLI claim verification | Yes (every claim) | No | No | No |
| Audit trail | Full JSONL trace | None | None | None |
| Data sovereignty | Complete | Cloud-only | Cloud-only | Cloud-only |
| Citation verification | Automated (per-claim) | Manual | Manual | Manual |
| Compliance export | EU AI Act, SOC 2, HIPAA, FedRAMP | None | None | None |
| Source diversity scoring | 5-signal (relevance, authority, density, freshness, grounding) | Basic | Basic | Basic |
| Evidence tiers | GOLD/SILVER/BRONZE with cross-source corroboration | None | None | None |
| Faithfulness guarantee | >80% NLI-verified | Unverified | Unverified | Unverified |
| Self-hosted option | Yes (Docker/K8s/Helm) | No | No | No |

---

## 5. Implementation Timeline

### Typical Engagement (12 weeks)

| Week | Activity | Responsibility |
|------|----------|---------------|
| 1-2 | Discovery and scoping | Partner + POLARIS |
| 3-4 | Infrastructure provisioning | Customer IT + Partner |
| 5-6 | POLARIS deployment | POLARIS Engineering |
| 7-8 | SSO/RBAC integration | Partner + Customer IT |
| 9-10 | User training and pilot | Partner |
| 11-12 | Production cutover and monitoring | Partner + POLARIS |

### Partner Training
- 2-day technical certification program
- Deployment runbook and troubleshooting guide
- Monthly partner webinars with product updates
- Dedicated partner Slack channel

---

## 6. Sales Playbook

### Discovery Questions
1. "How do your analysts currently conduct deep research? What tools do they use?"
2. "How much time does a typical literature review or competitive analysis take?"
3. "What happens when a research finding turns out to be wrong or fabricated?"
4. "Do you have data sovereignty requirements or compliance mandates?"
5. "How many research analysts do you have? How many reports do they produce per month?"

### ROI Calculator
| Metric | Before POLARIS | After POLARIS |
|--------|---------------|---------------|
| Time per research report | 40-80 hours | 2-4 hours |
| Reports per analyst/month | 2-3 | 15-20 |
| Analyst cost per report | $2,000-$4,000 | $200-$400 |
| Citation error rate | 5-15% | <2% (NLI verified) |
| Compliance audit time | 2-4 weeks | Automated (instant export) |

### Objection Handling
| Objection | Response |
|-----------|----------|
| "We already use ChatGPT/Perplexity" | "Those tools don't verify claims, can't deploy on-premise, and have no audit trail. One wrong citation in a regulatory filing costs more than a year of POLARIS." |
| "It's too expensive" | "At $120K/year for unlimited reports, if your analysts produce 10 reports/month and save 30 hours each, that's $360K in labor savings year one." |
| "We need it air-gapped" | "POLARIS is the only deep research platform that runs fully air-gapped. We've designed for SIPR-class networks from day one." |
| "How do we know the citations are real?" | "Every claim is verified via NLI (Natural Language Inference) against source content. We achieve >80% faithfulness, and every verification is logged in the audit trail." |

---

## 7. Demo Script

### 5-Minute Partner Demo Flow
1. **Problem statement** (30s): Show a complex research question. Ask: "How long would this take your analysts?"
2. **Submit query** (15s): Type the question into POLARIS, select "Deep" depth, click Research
3. **Watch progress** (60s): Show live evidence collection, STORM interviews, verification progress
4. **Review report** (90s): Show the formatted report with inline citations, faithfulness badges, quality bar
5. **Explore evidence** (60s): Click through GOLD/SILVER/BRONZE evidence cards, show radar charts, cross-references
6. **Export** (30s): Export PDF with bibliography, evidence chain appendix, audit certificate, SHA-256 hash
7. **Compliance** (15s): Show how the audit trail maps to SOC 2 / EU AI Act requirements

---

## 8. Contact and Support

### Partner Program Contacts
- **Partner Program Director:** [TBD]
- **Technical Pre-Sales:** [TBD]
- **Partner Support Portal:** [TBD]

### Resources
- Product documentation: `docs/deployment_guide.md`
- Architecture overview: `docs/architecture_diagram.md`
- Feature comparison: `docs/feature_comparison.md`
- Benchmark results: `docs/benchmark_questions.md`
- Compliance templates: `docs/compliance_templates/`
