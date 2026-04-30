# POLARIS — Supported Scope

**Version:** v1.0
**Last updated:** 2026-04-30

This document defines what research questions POLARIS will and will not accept, and the criteria the scope-classification substrates (`M-INT-4` LLM scope + `M-INT-5` domain router) use to route each query.

---

## In-scope (5 curated domains)

POLARIS v1.0 routes incoming research questions to one of 5 scope templates. Each template defines the evidence sources, claim structure, and quality gates the pipeline applies.

### 1. `clinical` — Clinical efficacy + safety

**Accepts:**
- Drug trial efficacy comparisons (e.g., "tirzepatide vs semaglutide HbA1c outcomes in T2DM")
- Comparative therapeutics across drug classes
- Regulatory submission summaries (FDA, EMA, Health Canada, NICE, PMDA, TGA, MHRA)
- Adverse event surveillance (FAERS, EudraVigilance)
- Mechanism-of-action questions when grounded in clinical trial evidence

**Rejects:**
- Patient-specific medical advice
- Off-label use recommendations
- Predictive prognosis for individuals

### 2. `due_diligence` — Investment due diligence

**Accepts:**
- Company financial profile + comparative market positioning
- Industry sizing + growth projections
- Competitive landscape mapping
- Regulatory + macro risk surveys

**Rejects:**
- Buy/sell recommendations on specific securities
- Real-time market data (POLARIS evidence is dated)

### 3. `policy` — Public policy + regulation

**Accepts:**
- Legislative + regulatory text analysis
- Comparative policy across jurisdictions
- Agency guidance summarization (federal + state + international)
- Impact assessment of proposed regulation

**Rejects:**
- Voting recommendations
- Lobbying-targeted content

### 4. `tech` — Technology + engineering

**Accepts:**
- Software architecture pattern surveys
- Deployment + scaling pattern comparisons
- Open-source ecosystem analysis
- Standards body output (W3C, IETF, ISO, IEEE)

**Rejects:**
- Specific vendor recommendations
- Performance benchmarking on user-supplied workloads

### 5. `custom` — Operator-defined

Any scope explicitly defined by an operator with a documented `custom.yaml` template. Requires:
- Explicit `domain` field
- At least one `evidence_tier` definition
- A claim-structure rubric

---

## Out-of-scope (explicit refusals)

POLARIS v1.0 will **refuse** the following query classes:

| Class | Why | Substrate that catches it |
|---|---|---|
| Real-time market quotes | Evidence has provenance dates, not live ticker | M-INT-4 scope LLM |
| Patient-specific medical advice | Not certified for clinical decision support | M-INT-4 scope LLM |
| Children's safety / CSAM-adjacent | Hard refuse | M-INT-4 scope LLM |
| Bioweapon / CBRN synthesis | Hard refuse | M-INT-4 scope LLM |
| Active election misinformation | Refuse pending legal framework | M-INT-4 scope LLM |
| Multi-language non-English | Extraction substrates assume English | Scope template `language` field |
| Multi-step reasoning > 3 hops | V19 is single-query | M-INT-5 domain router |

---

## Routing flow

```
Research question
   ↓
M-INT-4 (LLM scope classifier)
   ├── verdict: in_scope     → continue
   ├── verdict: out_of_scope → refuse with reason
   └── verdict: uncertain    → operator review queue
   ↓
M-INT-5 (domain router)
   ├── outcome: routed       → use template's evidence adapters
   ├── outcome: ambiguous    → fallback to keyword classifier
   └── outcome: refused      → refuse (template doesn't support)
   ↓
[Phase 2b: scope gate] → strict checks → live retrieval
```

---

## Quality gates per template

Each template defines minimum thresholds for:

- **Corpus adequacy**: minimum sources per evidence tier (T1 primary, T2 secondary, etc.)
- **Frame coverage**: % of slot fields that must be populated from evidence (M-58 frame validator)
- **Strict verify**: per-sentence content-word + numeric match rate (≥40% per section)

A query that fails corpus adequacy → `abort_corpus_inadequate` (no LLM tokens billed).

A query whose generated prose fails strict verify on every section → `abort_no_verified_sections` (verdict report, not a hallucinated pseudo-report).

---

## Operator override

Operators with `admin` or `owner` role on an org can:

- Override the M-INT-5 domain routing decision (logged in M-D3 telemetry)
- Inject a custom evidence corpus via `M-INT-10` Drive connector
- Adjust the corpus adequacy threshold per-run (logged with reason)

Each override generates a decision-telemetry record (M-D3 phase 1) for downstream M-D4 calibration.

---

## Roadmap (post-v1.0)

| Stretch goal | Earliest version |
|---|---|
| Multilingual scope classifier (DE/FR/ES/JA/ZH) | v1.2 |
| Real-time financial data integration | v1.3 (requires licensed feed) |
| Patient-specific clinical decision support | NEVER (legal moat) |
| Multi-hop reasoning (≥3 hops) | v2.0 |
| Custom domain template authoring UI | v1.1 |

---

## Compliance posture

POLARIS v1.0 supports:

- SOC2 Type II evidence map (`docs/compliance/soc2_evidence_map.md`)
- HIPAA audit trail (`docs/compliance/hipaa_audit_trail.md`) — for clinical template only, when run under a BAA
- EU AI Act Article 14 (human oversight) via M-INT-6 operator review queue + M-INT-9 contract drafting
- GDPR data minimization via M-INT-10 narrow Drive connector + workspace_id scoping

Multi-tenant isolation requires either separate FastAPI processes per tenant OR explicit org-role checks on every endpoint (M-15a/b auth substrate).
