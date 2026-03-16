# HIPAA Security Rule Compliance Mapping

## POLARIS Sovereign Deep Research Platform

**Regulation**: Health Insurance Portability and Accountability Act (HIPAA) Security Rule (45 CFR Part 164, Subpart C)
**Last Updated**: 2026-02-27
**Document Status**: Compliance mapping template
**Deployment Mode**: Sovereign (required for HIPAA — no data egress)

---

## 1. Executive Summary

This document maps POLARIS sovereign deployment capabilities to HIPAA Security Rule requirements. POLARIS processes research queries and generates cited reports from public sources. In healthcare research contexts, research queries or report content may reference Protected Health Information (PHI). Sovereign deployment mode ensures all data remains within the covered entity's network boundary.

### Applicability Determination

| Scenario | HIPAA Applicable | Rationale |
|----------|-----------------|-----------|
| General market research (no PHI) | No | No PHI processed |
| Healthcare market research (aggregate data only) | Likely no | De-identified aggregate data is not PHI |
| Clinical research support (references patient populations) | Potentially yes | Queries or outputs may reference PHI |
| Medical device research (references clinical outcomes) | Potentially yes | May include identifiable health information |

**Recommendation**: Deploy in sovereign mode for all healthcare-adjacent use cases to eliminate data egress risk regardless of PHI determination.

---

## 2. Administrative Safeguards (164.308)

### 2.1 Security Management Process (164.308(a)(1))

| Requirement | POLARIS Implementation | Evidence |
|-------------|----------------------|----------|
| **(i) Risk analysis** | Pipeline risk identification: hallucination, source bias, data leakage, misinformation. Quality gates quantify risk per research run (faithfulness score, evidence tier distribution) | `architecture.md` risk model, quality gate configuration |
| **(ii) Risk management** | Multi-layer mitigation: NLI verification, balanced prompting, cross-source corroboration, citation diversity caps, evidence tier scoring | Verifier, NLI verifier, cross-reference agent |
| **(iii) Sanction policy** | Pipeline enforces quality standards programmatically: CASE_4 halts on critical failures, budget guard stops on cost overruns | CASE gating logic, `PG_BUDGET_GUARD_USD` |
| **(iv) Information system activity review** | JSONL trace logs (append-only), cost ledger, pipeline event log — all timestamped, all reviewable | `trace.jsonl`, `pg_cost_ledger.jsonl`, `polaris_graph.log` |

### 2.2 Assigned Security Responsibility (164.308(a)(2))

| Requirement | Implementation |
|-------------|---------------|
| Designated security official | [CUSTOMER TO COMPLETE: Assign HIPAA Security Officer responsible for POLARIS deployment] |
| Responsibilities | Monitor audit logs, review access, respond to security incidents, conduct periodic risk assessments |

### 2.3 Workforce Security (164.308(a)(3))

| Requirement | POLARIS Implementation | Customer Responsibility |
|-------------|----------------------|------------------------|
| **(i) Authorization/supervision** | RBAC: Researcher (read reports), Operator (view diagnostics), Admin (configure system) | Implement identity provider, assign roles |
| **(ii) Workforce clearance** | Role-based visibility: PHI-containing queries visible only to authenticated users with assigned roles | Background checks for personnel with Admin access |
| **(iii) Termination procedures** | Session-scoped authentication; no persistent user sessions after logout | Revoke credentials upon workforce departure |

### 2.4 Information Access Management (164.308(a)(4))

| Requirement | POLARIS Implementation |
|-------------|----------------------|
| **(i) Access authorization** | Three-tier RBAC (Researcher/Operator/Admin) with progressive data visibility |
| **(ii) Access establishment/modification** | Configuration-driven role assignment; changes logged |
| **(iii) Access termination** | Session-based; no persistent tokens after session end |

### 2.5 Security Awareness and Training (164.308(a)(5))

| Requirement | Customer Responsibility |
|-------------|------------------------|
| **(i) Security reminders** | Periodic reminders about POLARIS data handling policies |
| **(ii) Malicious software protection** | Host-level antivirus/EDR on POLARIS server |
| **(iii) Log-in monitoring** | Monitor authentication attempts to POLARIS dashboard |
| **(iv) Password management** | Enforce strong passwords for POLARIS access |

### 2.6 Security Incident Procedures (164.308(a)(6))

| Requirement | POLARIS Implementation | Customer Responsibility |
|-------------|----------------------|------------------------|
| **(i) Response and reporting** | Pipeline HALT on CASE_4 (critical failure); budget exceeded stops execution; circuit breaker detects API provider failures | Establish incident response team and procedures for POLARIS-related security events |

### 2.7 Contingency Plan (164.308(a)(7))

| Requirement | POLARIS Implementation | Customer Responsibility |
|-------------|----------------------|------------------------|
| **(i) Data backup plan** | All state in filesystem (`outputs/`, `state/`, `logs/`); ChromaDB SQLite-backed; LangGraph checkpoint persistence | Implement regular backup schedule for POLARIS data directories |
| **(ii) Disaster recovery** | Checkpoint/resume: pipeline recovers at last completed node after crash; state files are portable | Establish RTO/RPO targets; test recovery procedures |
| **(iii) Emergency mode operation** | Sovereign mode operates independently of external services; air-gapped deployment continues during network outages | Document manual research procedures as fallback |
| **(iv) Testing and revision** | [CUSTOMER TO COMPLETE] | Conduct annual contingency plan testing |
| **(v) Applications and data criticality analysis** | [CUSTOMER TO COMPLETE] | Assess criticality of POLARIS for healthcare operations |

### 2.8 Evaluation (164.308(a)(8))

| Requirement | Implementation |
|-------------|---------------|
| Periodic security evaluation | [CUSTOMER TO COMPLETE: Annual security assessment of POLARIS deployment, including penetration testing of web interface and API endpoints] |

### 2.9 Business Associate Contracts (164.308(b)(1))

| Deployment Mode | BAA Required? | With Whom |
|----------------|---------------|-----------|
| Sovereign (air-gapped) | No | No business associates — all processing local |
| Sovereign (intranet) | Potentially | Internal IT services if separate entity |
| Cloud mode | Yes | OpenRouter, Serper, Exa, Jina, Semantic Scholar (if PHI in queries) |

**Recommendation**: Use sovereign mode to eliminate BAA requirements for PHI-containing research.

---

## 3. Physical Safeguards (164.310)

### 3.1 Facility Access Controls (164.310(a)(1))

| Requirement | Sovereign Mode Implementation |
|-------------|-------------------------------|
| **(i) Contingency operations** | POLARIS server in secured data center with generator backup; air-gapped network segment |
| **(ii) Facility security plan** | [CUSTOMER TO COMPLETE: Physical security controls for server room housing POLARIS] |
| **(iii) Access control/validation** | [CUSTOMER TO COMPLETE: Badge access, visitor logs for POLARIS server location] |
| **(iv) Maintenance records** | [CUSTOMER TO COMPLETE: Hardware maintenance log for POLARIS server and GPU hardware] |

### 3.2 Workstation Use (164.310(b))

| Requirement | Implementation |
|-------------|---------------|
| Workstation policies | [CUSTOMER TO COMPLETE: Policies for workstations accessing POLARIS dashboard — screen lock, clean desk, authorized locations] |

### 3.3 Workstation Security (164.310(c))

| Requirement | Implementation |
|-------------|---------------|
| Physical safeguards for workstations | [CUSTOMER TO COMPLETE: Physical restrictions for devices accessing POLARIS — cable locks, restricted areas] |

### 3.4 Device and Media Controls (164.310(d))

| Requirement | POLARIS Implementation | Customer Responsibility |
|-------------|----------------------|------------------------|
| **(i) Disposal** | Research outputs in `outputs/` directory; secure deletion with `shred` or equivalent | Establish media sanitization procedures |
| **(ii) Media re-use** | ChromaDB collections scoped to research session; checkpoint data in SQLite files | Wipe persistent storage before repurposing hardware |
| **(iii) Accountability** | All output files include vector_id, timestamps, and pipeline metadata | Track all media containing POLARIS outputs |
| **(iv) Data backup and storage** | State files are portable filesystem artifacts | Encrypt backups at rest |

---

## 4. Technical Safeguards (164.312)

### 4.1 Access Control (164.312(a)(1))

| Requirement | POLARIS Implementation | Evidence |
|-------------|----------------------|----------|
| **(i) Unique user identification** | Per-client SSE cursors; session-based authentication | Live server client tracking |
| **(ii) Emergency access procedure** | Admin role has full system access; checkpoint/resume enables recovery | RBAC role hierarchy |
| **(iii) Automatic logoff** | [CUSTOMER TO IMPLEMENT: Session timeout configuration for dashboard access] | Web server session management |
| **(iv) Encryption and decryption** | Sovereign mode: all data at rest on local filesystem (encrypt with dm-crypt/BitLocker); data in transit: TLS for internal services | Deployment configuration |

### 4.2 Audit Controls (164.312(b))

| Audit Layer | Implementation | Format | Retention |
|-------------|---------------|--------|-----------|
| Pipeline trace | JSONL append-only log per research run | `outputs/{id}/trace.jsonl` | Configurable |
| LLM cost ledger | Per-call cost, tokens, model, timestamp | `logs/pg_cost_ledger.jsonl` | Configurable |
| Application log | Structured logging with levels (DEBUG-CRITICAL) | `logs/polaris_graph.log` | Configurable |
| Evidence registry | Per-claim verification verdicts with source provenance | `outputs/{id}/result.json` | Configurable |
| Access log | HTTP request log from FastAPI/uvicorn | Standard access log | Configurable |

#### HIPAA Audit Trail Record Format

Each pipeline trace event contains:

```json
{
  "timestamp": "2026-02-27T14:30:00.000Z",
  "event_type": "node_start|node_end|evidence_extract|verify_claim|quality_gate|cost_record|error|iteration",
  "node": "plan|search|storm|analyze|verify|evaluate|synthesize|search_gaps",
  "vector_id": "WEB_20260227_abc123",
  "iteration": 1,
  "details": {
    "action": "Description of action taken",
    "input_count": 50,
    "output_count": 47,
    "duration_seconds": 12.5,
    "model": "moonshotai/kimi-k2.5",
    "cost_usd": 0.003
  }
}
```

#### Minimum Audit Events Captured

| Event | Data Captured | HIPAA Relevance |
|-------|--------------|-----------------|
| Research query submitted | User query text, timestamp, depth preset | Who accessed what, when |
| Pipeline started | Vector ID, configuration snapshot | System activity |
| Search executed | Queries, engines, result counts | Data collection record |
| Content fetched | URLs, content length, fetch method | External data access |
| Evidence extracted | Quotes, sources, atomic facts | Data processing record |
| Claim verified | Claim text, verdict, NLI score | Quality assurance |
| Quality gate decision | CASE determination, metrics | Decision audit |
| Report generated | Word count, citation count, faithfulness | Output record |
| Pipeline completed | Duration, cost, final metrics | System activity |
| Error/failure | Error type, stack trace (sanitized), retry action | Incident record |

### 4.3 Integrity (164.312(c)(1))

| Requirement | POLARIS Implementation |
|-------------|----------------------|
| **(i) Mechanism to authenticate ePHI** | Content hashing: every fetched source content-hashed (SHA256); evidence items carry content fingerprints; JSONL logs are append-only |

#### Data Integrity Chain

```
Source Content (fetched)
  |-- content_hash: SHA256 of raw content
  |-- fetch_timestamp: ISO 8601
  |-- fetch_method: jina|crawl4ai|trafilatura|httpx
  |
  v
Evidence Item (extracted)
  |-- quote: exact text from source
  |-- source_url: origin URL
  |-- source_content_hash: links back to source
  |
  v
Verification Verdict
  |-- claim: text being verified
  |-- verdict: SUPPORTED|NOT_SUPPORTED
  |-- nli_score: 0.0-1.0 probability
  |-- source_evidence_id: links back to evidence
  |
  v
Report Section
  |-- content: prose with [CITE:id] markers
  |-- evidence_ids: list of evidence used
  |-- faithfulness: aggregate score
  |
  v
Final Report
  |-- bibliography: resolved citations
  |-- metrics: aggregate quality scores
  |-- trace_file: path to full audit trail
```

### 4.4 Person or Entity Authentication (164.312(d))

| Requirement | Implementation |
|-------------|---------------|
| Authentication mechanism | [CUSTOMER TO IMPLEMENT: SSO integration, MFA for dashboard access, API key authentication for programmatic access] |

### 4.5 Transmission Security (164.312(e)(1))

| Requirement | POLARIS Implementation |
|-------------|----------------------|
| **(i) Integrity controls** | Pydantic schema validation on all API request/response payloads; malformed input returns HTTP 422 |
| **(ii) Encryption** | Sovereign mode: TLS 1.3 for all internal service communication (vLLM, SearxNG, dashboard); Cloud mode: TLS 1.3 for all external API calls |

---

## 5. De-Identification Requirements

### 5.1 POLARIS and PHI De-Identification

POLARIS processes research queries and synthesizes reports from public sources. It does not inherently process PHI. However, in healthcare research contexts:

| PHI Risk Point | Mitigation |
|---------------|------------|
| Research query contains PHI | Sovereign mode: query never leaves network; Cloud mode: BAA required with LLM provider |
| Report references identifiable patient data | Reports cite public sources; no patient-level data in standard operation |
| Evidence contains incidental PHI | Source content is public web pages and academic papers; no clinical data ingestion |

### 5.2 Safe Harbor Method (164.514(b)(2))

If POLARIS outputs are used in contexts requiring de-identification:

| Identifier | POLARIS Handling |
|-----------|-----------------|
| Names | Not collected; research queries should not contain patient names |
| Geographic data | Research may reference geographic regions (NORTH_AMERICA, EUROPE, etc.) at aggregate level |
| Dates | Source publication dates only; no treatment dates |
| Phone/fax numbers | Not collected |
| Email addresses | Not collected |
| SSN/Medical record numbers | Not collected |
| Account numbers | Not collected |
| URLs/IP addresses | Source URLs logged (public web pages, not patient portals) |
| Biometric identifiers | Not collected |
| Photographic images | Not collected |

### 5.3 Expert Determination (164.514(b)(1))

[CUSTOMER TO COMPLETE: If using Expert Determination method, document the qualified expert's analysis that POLARIS outputs do not contain individually identifiable health information]

---

## 6. Implementation Checklist

### Sovereign Deployment (Required for HIPAA)

| Step | Status | Notes |
|------|--------|-------|
| Deploy POLARIS in air-gapped network segment | [ ] | No internet egress |
| Configure vLLM with local model | [ ] | Qwen2.5-32B or equivalent |
| Configure SearxNG for intranet search | [ ] | Or disable web search |
| Enable filesystem encryption (dm-crypt/BitLocker) | [ ] | Encrypt `outputs/`, `state/`, `logs/` |
| Configure TLS for all internal services | [ ] | vLLM, SearxNG, POLARIS |
| Implement authentication (SSO/MFA) | [ ] | Customer identity provider |
| Configure session timeout | [ ] | Automatic logoff per policy |
| Establish backup schedule | [ ] | Minimum daily for `state/`, `outputs/` |
| Configure audit log retention | [ ] | Minimum 6 years per HIPAA |
| Conduct risk assessment | [ ] | Annual requirement |
| Execute security awareness training | [ ] | For all POLARIS users |
| Document incident response procedures | [ ] | POLARIS-specific procedures |
| Test contingency plan | [ ] | Annual requirement |
| Execute BAA with any business associates | [ ] | N/A if fully sovereign |

---

## 7. Document Maintenance

| Activity | Frequency | Responsible |
|----------|-----------|-------------|
| Risk assessment update | Annual | HIPAA Security Officer |
| Audit log review | Monthly | HIPAA Security Officer |
| Access review | Quarterly | HIPAA Security Officer |
| Contingency plan test | Annual | IT Operations |
| Policy review | Annual | Compliance Team |
| Training completion | Annual | All POLARIS users |
