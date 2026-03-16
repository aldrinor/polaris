# SOC 2 Type II Evidence Mapping

## POLARIS Sovereign Deep Research Platform

**Framework**: AICPA SOC 2 Type II
**Trust Service Criteria**: 2017 (with 2022 updates)
**Last Updated**: 2026-02-27
**Document Status**: Evidence mapping template

---

## 1. Overview

This document maps POLARIS system capabilities and operational controls to SOC 2 Type II Trust Service Criteria. POLARIS provides built-in evidence generation for many SOC 2 controls through its audit trail, pipeline tracing, verification system, and quality gates.

### Scope

| Item | Description |
|------|-------------|
| System | POLARIS Sovereign Deep Research Platform |
| Deployment modes | Cloud (OpenRouter + external APIs) and Sovereign (air-gapped, local inference) |
| Infrastructure | Customer-managed (on-premises or cloud IaaS) |
| Data processed | Research queries, web content, academic papers, synthesized reports |
| Period | [COMPLETE: 12-month observation period] |

---

## 2. Security (Common Criteria)

### CC1 — Control Environment

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC1.1 — Commitment to integrity and ethical values | Code of conduct for AI-generated content: every claim must be cited, no fabricated data (LAW II: No Fake Working) | `CLAUDE.md` LAW II, `architecture.md` Section 1.3 |
| CC1.2 — Board oversight | Operator dashboard provides real-time pipeline visibility; dual-view architecture separates user and operator concerns | `src/polaris_graph/dashboard.py`, `docs/todo_list.md` Phase 1A.2 |
| CC1.3 — Management establishes structures | 8-node pipeline with defined quality gates at each stage; CASE_1 through CASE_4 gating decisions | `src/polaris_graph/graph.py`, `architecture.md` Section 9.3 |
| CC1.4 — Commitment to competence | Automated quality scoring: 5-signal evidence tier system (relevance, authority, density, freshness, grounding) | `src/polaris_graph/agents/analyzer.py` |
| CC1.5 — Accountability | Per-run cost ledger, per-call token tracking, per-claim verification verdicts with responsible model ID | `logs/pg_cost_ledger.jsonl`, `outputs/{id}/trace.jsonl` |

### CC2 — Communication and Information

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC2.1 — Information quality | NLI verification ensures claim quality; quality gates enforce minimum faithfulness (70%), evidence count (20+), citation count (30+) | `src/polaris_graph/agents/verifier.py`, `.env` PG_MIN_FAITHFULNESS |
| CC2.2 — Internal communication | JSONL trace events (8 event types) log every pipeline decision; session log captures all development decisions | `src/polaris_graph/tracing.py`, `logs/session_log.md` |
| CC2.3 — External communication | Reports include full bibliography with source URLs, verification verdicts, and evidence provenance | `outputs/{id}/result.json` |

### CC3 — Risk Assessment

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC3.1 — Risk objectives | Quality targets defined: faithfulness >= 70%, sources >= 20, words >= 10,000 | `src/polaris_graph/state.py` quality gate constants |
| CC3.2 — Risk identification | Pipeline identifies risks per research run: off-topic content, paywall sources, citation poverty, hallucination | Quality gates in `src/polaris_graph/agents/verifier.py` |
| CC3.3 — Fraud risk | Anti-embellishment prompting prevents LLM from fabricating quotes; source content verified against claims | `ARCH-4` in `.env`, `src/polaris_graph/agents/verifier.py` |
| CC3.4 — Change risk | Configuration changes tracked in `.env` with comments; all parameters externalized (LAW VI: Zero Hard-Coding) | `.env`, `CLAUDE.md` LAW VI |

### CC4 — Monitoring Activities

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC4.1 — Ongoing monitoring | Real-time SSE event streaming to browser dashboard; JSONL trace log with timestamps for every node | `src/polaris_graph/tracing.py`, `/api/events` SSE endpoint |
| CC4.2 — Deficiency evaluation | Quality gates trigger CASE_2 (partial evidence: re-search), CASE_3 (insufficient: re-plan), CASE_4 (critical: HALT) | `architecture.md` Section 9.3 |

### CC5 — Control Activities

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC5.1 — Risk mitigation | Multi-layer verification: NLI (MiniCheck), LLM balanced prompting, cross-source corroboration, contradiction detection | Verifier, NLI verifier, cross-reference agent |
| CC5.2 — Technology controls | Pydantic schema validation on all data contracts; no wildcards imports; explicit dependency tracking | `src/polaris_graph/schemas.py`, `requirements.txt` |
| CC5.3 — Policy deployment | All policies enforced through code: quality gates are programmatic, not manual; preflight script validates compliance | `scripts/preflight.py` |

### CC6 — Logical and Physical Access Controls

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC6.1 — Logical access | Dual-view RBAC (Researcher/Operator) with different data visibility levels | Dashboard view mode toggle |
| CC6.2 — Access credentials | API keys stored in `.env`, never in source code, masked in logs (first 8 chars only) | `.env` (excluded from VCS via `.gitignore`) |
| CC6.3 — Access removal | Session-scoped authentication; SSE cursors per-client with automatic cleanup | `src/polaris_graph/live_server.py` |
| CC6.6 — System boundary | Sovereign mode: complete network isolation, zero data egress, air-gapped deployment option | `docs/deployment_guide.md` Section 5 |
| CC6.7 — Access restrictions | Endpoint-level permission matrix: Researcher, Operator, Admin roles with progressive access | `docs/architecture_diagram.md` Section 9 |
| CC6.8 — Unauthorized access prevention | Input validation (Pydantic: query length 5-2000 chars), CORS middleware, global exception handler suppresses stack traces | FastAPI middleware configuration |

### CC7 — System Operations

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC7.1 — Infrastructure management | Docker/Kubernetes deployment with health checks, resource limits, and persistent volumes | `docs/deployment_guide.md` Sections 3, 8 |
| CC7.2 — Change management | Git-based version control; all changes logged in session log with rationale | `logs/session_log.md`, git history |
| CC7.3 — Configuration management | 100+ environment variables externalized (LAW VI); YAML configuration files; no magic numbers | `.env`, `config/settings/` |
| CC7.4 — Security event detection | Circuit breaker detects consecutive API failures; budget guard detects cost anomalies; faithfulness monitoring detects quality degradation | `.env` PG_CIRCUIT_BREAKER_THRESHOLD, PG_BUDGET_GUARD_USD |
| CC7.5 — Security incident response | Pipeline HALT on CASE_4 (critical failure); cost budget exceeded stops execution; operator notification via dashboard | `architecture.md` Section 9.3 |

### CC8 — Change Management

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC8.1 — Change authorization | All configuration changes documented in `.env` with FIX-xxx comments explaining rationale | `.env` comments (e.g., "FIX-057: Increased from 150 to 180") |

### CC9 — Risk Mitigation (Vendors)

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| CC9.1 — Vendor risk management | Component table maps every external dependency to a local alternative; sovereign mode eliminates all vendor dependencies | `docs/architecture_diagram.md` Section 5 |
| CC9.2 — Vendor monitoring | Cost ledger tracks per-provider spend; circuit breaker monitors provider reliability | `logs/pg_cost_ledger.jsonl` |

---

## 3. Availability

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| A1.1 — Capacity management | Configurable concurrency limits (web: 25, academic: 1, analysis: 30, verification: 30); evidence caps prevent unbounded growth | `.env` concurrency variables |
| A1.2 — Recovery | LangGraph checkpoint/resume; pipeline recovers from crash at last completed node; state persisted in SQLite | `src/polaris_graph/checkpoint_manager.py` |
| A1.3 — Backup/restore | Output files in `outputs/`, state in `state/`, logs in `logs/` — all filesystem-based, standard backup procedures apply | Directory structure |

---

## 4. Processing Integrity

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| PI1.1 — Quality objectives | Defined quality targets: faithfulness >= 70%, evidence >= 20, citations >= 30, sources >= 20, words >= 10,000 | `src/polaris_graph/state.py` |
| PI1.2 — Input validation | Pydantic schema validation on all inputs; ResearchRequest validates query length (5-2000 chars), depth preset | `src/polaris_graph/schemas.py` |
| PI1.3 — Processing accuracy | NLI verification (MiniCheck flan-t5-large) verifies every claim against source content; balanced prompting requires evidence for AND against | `src/polaris_graph/agents/verifier.py`, `src/polaris_graph/agents/nli_verifier.py` |
| PI1.4 — Output completeness | Quality gates enforce minimum output: word count >= 10,000, citations >= 30, unique sources >= 20; CASE_2 triggers re-iteration if below thresholds | Quality gate logic in evaluate node |
| PI1.5 — Output delivery | JSON output with full report, evidence, bibliography, metrics; SSE real-time events during processing | `outputs/{id}/result.json`, `/api/events` |

---

## 5. Confidentiality

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| C1.1 — Confidential data identification | User queries and research outputs classified as confidential; API keys classified as secret | `.env` (secrets), `outputs/` (confidential) |
| C1.2 — Confidential data disposal | Session-scoped VWM collections; configurable retention policy; sovereign mode keeps all data on-premises | ChromaDB collection lifecycle |
| C1.3 — Confidential data protection | Sovereign mode: air-gapped deployment, zero data egress; Cloud mode: API-only interaction, no persistent storage at LLM providers | `docs/deployment_guide.md` Section 5 |

---

## 6. Privacy

| Criterion | POLARIS Evidence | Artifacts |
|-----------|-----------------|-----------|
| P1.1 — Privacy notice | System processes research queries, not personal data by default; no PII collection in standard operation | System design documentation |
| P1.2 — Consent | Research queries submitted voluntarily by authenticated users | User interaction model |
| P3.1 — Personal data collection | POLARIS does not collect or process PII in standard operation; research queries may incidentally contain PII — customer responsibility to manage | Data processing agreement template |
| P4.1 — Data use | Research outputs used solely for the requesting user's research purposes | Terms of service |
| P6.1 — Data quality | Source content verified through NLI; evidence quality scored through 5-signal system; deduplication prevents redundant data | Verification pipeline |
| P8.1 — Data disposal | Configurable output retention; ChromaDB collections scoped to research session; no persistent external data storage | Retention policy configuration |

---

## 7. Evidence Collection Matrix

### Automated Evidence (Generated Per Pipeline Run)

| Evidence Type | Location | Frequency | SOC 2 Criteria |
|---------------|----------|-----------|-----------------|
| Pipeline trace log | `outputs/{id}/trace.jsonl` | Per run | CC4.1, PI1.3 |
| Cost ledger | `logs/pg_cost_ledger.jsonl` | Per LLM call | CC1.5, CC9.2 |
| Verification verdicts | `outputs/{id}/result.json` | Per claim | PI1.3, CC2.1 |
| Quality gate decisions | `outputs/{id}/trace.jsonl` | Per iteration | CC3.2, CC4.2 |
| Source quality scores | `outputs/{id}/result.json` | Per source | PI1.2, CC2.1 |
| Error/retry logs | `logs/polaris_graph.log` | As needed | CC7.4, CC7.5 |
| Checkpoint state | `state/` SQLite | Per node | A1.2 |

### Manual Evidence (Customer Responsibility)

| Evidence Type | Purpose | SOC 2 Criteria |
|---------------|---------|-----------------|
| Access reviews | Periodic review of user access | CC6.1, CC6.3 |
| Change approval records | Approval for configuration changes | CC8.1 |
| Incident response logs | Security incident documentation | CC7.5 |
| Vendor risk assessments | Annual API provider evaluation | CC9.1 |
| Business continuity tests | Disaster recovery testing | A1.2, A1.3 |
| Privacy impact assessments | PII handling evaluation | P1.1, P3.1 |

---

## 8. Auditor Notes

### Key Strengths for SOC 2 Audit

1. **Immutable trace logs**: JSONL append-only format with timestamps provides tamper-evident audit trail
2. **Per-claim verification**: Every factual claim verified against source with machine-readable verdict
3. **Configurable quality thresholds**: All quality gates externalized as environment variables with documented defaults
4. **Dual deployment modes**: Sovereign mode eliminates third-party data processing concerns
5. **Cost tracking**: Per-call, per-model cost attribution enables budget monitoring

### Areas Requiring Customer Implementation

1. **Authentication system**: POLARIS provides RBAC framework; customer must implement identity provider integration
2. **Network security**: Customer responsible for firewall rules, TLS certificates, network monitoring
3. **Physical security**: Customer responsible for data center physical controls (relevant for sovereign mode)
4. **Incident response**: Customer must establish incident response procedures and team
5. **Business continuity**: Customer must implement backup/restore procedures for `outputs/`, `state/`, `logs/`
