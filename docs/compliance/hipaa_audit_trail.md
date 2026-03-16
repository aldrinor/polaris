# HIPAA Security Rule Audit Trail Format

## POLARIS Sovereign Deep Research Platform

**Document Version:** 1.0
**Classification:** Compliance Documentation — HIPAA Security Rule (45 CFR Part 164)
**Applicable Provisions:** Technical Safeguards (Section 164.312)
**Last Updated:** 2026-02-27

---

## 1. Applicability Statement

POLARIS Sovereign Deep Research Platform may process research queries related to healthcare, pharmaceutical, medical device, or public health domains. When deployed by a Covered Entity or Business Associate, POLARIS audit trail capabilities support compliance with the HIPAA Security Rule technical safeguards.

**Important:** POLARIS does not store, process, or transmit Protected Health Information (PHI) in its standard configuration. This document describes how POLARIS audit trail infrastructure satisfies HIPAA technical safeguard requirements when the platform is deployed in healthcare research contexts where incidental PHI exposure is possible through fetched source content.

---

## 2. Technical Safeguards Mapping

### 2.1 Access Control (Section 164.312(a)(1))

**Standard:** Implement technical policies and procedures for electronic information systems that maintain electronic protected health information to allow access only to those persons or software programs that have been granted access rights.

#### 2.1.1 Unique User Identification (Required)

| Requirement | POLARIS Implementation | Evidence |
|-------------|------------------------|----------|
| Assign a unique name and/or number for identifying and tracking user identity | Each research run receives a unique vector_id (`WEB_{timestamp}_{query_hash}`) that serves as the session identifier; user authentication via SSO/SAML with unique user identifiers (JWT claims) | Vector ID in every trace event; JWT subject claim in access logs |

**Audit Trail Record Format:**
```json
{
  "timestamp": "2026-02-27T14:30:00.000Z",
  "vector_id": "WEB_1740667800_a3f2b1c4",
  "user_id": "user_001@organization.com",
  "session_id": "sess_abc123",
  "action": "research_initiated",
  "query_hash": "sha256:a3f2b1c4d5e6f7...",
  "depth": "standard",
  "ip_address": "192.168.1.100"
}
```

#### 2.1.2 Emergency Access Procedure (Required)

| Requirement | POLARIS Implementation | Evidence |
|-------------|------------------------|----------|
| Establish procedures for obtaining necessary ePHI during an emergency | Admin role has unrestricted access to all research outputs and trace files; checkpoint-and-resume architecture ensures no data loss during system interruption; emergency access logged with elevated privilege flag | Admin access audit log; checkpoint recovery in `state/progress_ledger.jsonl` |

#### 2.1.3 Automatic Logoff (Addressable)

| Requirement | POLARIS Implementation | Evidence |
|-------------|------------------------|----------|
| Implement electronic procedures that terminate an electronic session after a predetermined time of inactivity | JWT token expiration (configurable TTL); SSE connection timeout with auto-disconnect; session state persisted to allow safe logoff without data loss | JWT configuration; SSE timeout parameters |

#### 2.1.4 Encryption and Decryption (Addressable)

| Requirement | POLARIS Implementation | Evidence |
|-------------|------------------------|----------|
| Implement a mechanism to encrypt and decrypt ePHI | All external API communications over HTTPS/TLS 1.2+; SQLite caches support encryption at rest (via SQLCipher when deployed); sovereign mode eliminates external data transmission entirely | HTTPS configuration; sovereign deployment mode documentation |

---

### 2.2 Audit Controls (Section 164.312(b))

**Standard:** Implement hardware, software, and/or procedural mechanisms that record and examine activity in information systems that contain or use electronic protected health information.

#### 2.2.1 POLARIS Audit Trail Architecture

POLARIS implements a multi-layer audit trail that records every significant operation:

**Layer 1: JSONL Pipeline Trace** (Machine-Parseable)

Location: `logs/pg_trace_{vector_id}.jsonl`
Events per run: 1,302+ structured events
Format: One JSON object per line

```json
{
  "timestamp": "2026-02-27T14:30:01.234Z",
  "vector_id": "WEB_1740667800_a3f2b1c4",
  "node": "search",
  "event_type": "fetch",
  "data": {
    "url": "https://www.cdc.gov/...",
    "status_code": 200,
    "content_length": 8432,
    "fetch_method": "jina_reader",
    "duration_ms": 1250.3
  },
  "duration_ms": 1250.3
}
```

**Eight Event Types Tracked:**

| Event Type | Description | HIPAA Relevance |
|------------|-------------|-----------------|
| `node_start` | Pipeline node begins execution | Audit trail of processing stages |
| `node_end` | Pipeline node completes with duration and outcome metrics | Processing completion verification |
| `fetch` | External content retrieval with URL, status code, content length | Data ingestion record |
| `llm_call` | LLM API invocation with model, token count, cost | AI processing record |
| `quality_gate` | Quality threshold evaluation with pass/fail result | Data quality assurance |
| `evidence` | Evidence extraction from source with provenance | Source attribution record |
| `verification` | NLI claim verification verdict (SUPPORTED/NOT_SUPPORTED) | Factual accuracy validation |
| `synthesis` | Report generation operations | Output creation record |

**Layer 2: Session Log** (Human-Readable)

Location: `logs/session_log.md`
Format: Chronological markdown with structured entries

```markdown
[2026-02-27 14:30:00]
- ACTION: Research pipeline initiated for healthcare query
- RATIONALE: Standard depth research requested via web UI
- AFFECTED_FILES: outputs/polaris_graph/WEB_1740667800_a3f2b1c4.json
- EVIDENCE: Pipeline started, vector_id assigned
- STATUS: In progress
- NEXT_STEP: Plan node execution
```

**Layer 3: Cost Ledger** (Financial Audit)

Location: `logs/pg_cost_ledger.jsonl`
Format: Per-operation cost records with session aggregation

```json
{
  "timestamp": "2026-02-27T14:30:05.000Z",
  "session_id": "WEB_1740667800_a3f2b1c4",
  "operation": "llm_call",
  "model": "moonshotai/kimi-k2.5",
  "input_tokens": 4200,
  "output_tokens": 1800,
  "cost_usd": 0.0054,
  "cumulative_cost_usd": 0.0054
}
```

**Layer 4: Progress Ledger** (State Persistence)

Location: `state/progress_ledger.jsonl`
Format: Append-only execution state for crash recovery

```json
{
  "timestamp": "2026-02-27T14:30:10.000Z",
  "vector_id": "WEB_1740667800_a3f2b1c4",
  "phase": "search",
  "status": "completed",
  "metrics": {
    "urls_attempted": 150,
    "urls_success": 112,
    "content_fetched_bytes": 1243567
  }
}
```

#### 2.2.2 Audit Log Retention

| Log Type | Default Retention | HIPAA Minimum | Configuration |
|----------|-------------------|---------------|---------------|
| JSONL Trace | Indefinite (append-only) | 6 years (Section 164.530(j)) | Configurable via retention policy |
| Session Log | Indefinite (append-only) | 6 years | Configurable via retention policy |
| Cost Ledger | Indefinite (append-only) | 6 years | Configurable via retention policy |
| Progress Ledger | Indefinite (append-only) | 6 years | Configurable via retention policy |
| Output JSON | Indefinite | 6 years | Configurable via retention policy |

#### 2.2.3 Audit Log Integrity

| Control | Implementation |
|---------|----------------|
| Append-only format | JSONL files are append-only; no in-place modification of historical events |
| SHA-256 fingerprinting | Vector input fingerprinted at Phase 0; audit certificate includes hash of inputs and outputs |
| Timestamp consistency | All timestamps in UTC ISO 8601 format from `datetime.now(timezone.utc)` |
| Event sequencing | Monotonic event ordering within each trace file; node_start always precedes node_end |

---

### 2.3 Integrity Controls (Section 164.312(c)(1))

**Standard:** Implement policies and procedures to protect electronic protected health information from improper alteration or destruction.

#### 2.3.1 Mechanism to Authenticate ePHI (Addressable)

| Requirement | POLARIS Implementation | Evidence |
|-------------|------------------------|----------|
| Implement electronic mechanisms to corroborate that ePHI has not been altered or destroyed in an unauthorized manner | SHA-256 fingerprint of vector input at pipeline initialization; content hash (content_hash field) on every indexed chunk; Pydantic schema validation on all phase handoffs rejects malformed data | Fingerprint in Phase 0 output; content_hash in chunk metadata; schema validation errors in trace |

**Evidence Chain Integrity:**

Every factual claim in a POLARIS report has a verifiable integrity chain:

```
Claim in Report
  ├── evidence_id: "ev_abc123"
  │     ├── source_url: "https://www.cdc.gov/..."
  │     ├── content_hash: "sha256:7f83b..."
  │     ├── fetch_timestamp: "2026-02-27T14:30:05Z"
  │     ├── fetch_method: "jina_reader"
  │     ├── quality_tier: "GOLD"
  │     └── tier_composite_score: 0.7823
  ├── verification_verdict: "SUPPORTED"
  │     ├── verification_method: "nli_minicheck"
  │     ├── confidence: 0.92
  │     └── cross_source_verified: true
  └── citation: "[1] CDC (2025). Water Quality Monitoring..."
        ├── bibliography_url: "https://www.cdc.gov/..."
        └── access_date: "2026-02-27"
```

#### 2.3.2 Data Validation Controls

| Validation Layer | Implementation | Error Handling |
|------------------|----------------|----------------|
| Input Validation | Pydantic `ResearchRequest` model: query 5-2,000 chars, depth enum (quick/standard/deep) | 422 Unprocessable Entity with field-level error messages |
| Phase Contract Validation | Pydantic schemas for every inter-phase JSON contract (`QueryPlan`, `VerificationBatch`, `ReportOutline`, etc.) | Pipeline halt with schema validation error in trace |
| Evidence Quality Validation | 5-signal composite scoring with veto rules; paywall detection; junk content detection; substance scoring | Evidence downgraded to BRONZE or rejected; logged in trace |
| Output Validation | Quality gates on final output: word count >= 2,000, citations >= 5, faithfulness >= 0.70 | CASE_2 retry or CASE_4 halt with escalation |

---

### 2.4 Transmission Security (Section 164.312(e)(1))

**Standard:** Implement technical security measures to guard against unauthorized access to electronic protected health information that is being transmitted over an electronic communications network.

#### 2.4.1 Integrity Controls (Addressable)

| Requirement | POLARIS Implementation | Evidence |
|-------------|------------------------|----------|
| Implement security measures to ensure that electronically transmitted ePHI is not improperly modified without detection | All external API communications use HTTPS/TLS 1.2+; content hashing on fetched documents detects modification; Pydantic validation on API responses rejects malformed data | HTTPS enforcement in client configuration; content_hash validation |

#### 2.4.2 Encryption (Addressable)

| Requirement | POLARIS Implementation | Evidence |
|-------------|------------------------|----------|
| Implement a mechanism to encrypt ePHI whenever deemed appropriate | All external API calls use HTTPS (TLS 1.2+): OpenRouter, Serper, Semantic Scholar, Jina Reader, Exa, Tavily; sovereign mode eliminates all external transmission | Client configuration enforcing HTTPS; sovereign mode flag |

**Data Flow Security Matrix:**

| Data Flow | Protocol | Encryption | Sovereign Mode |
|-----------|----------|------------|----------------|
| Browser to POLARIS Server | HTTPS | TLS 1.2+ | Same (local network) |
| POLARIS to LLM Provider (OpenRouter) | HTTPS | TLS 1.2+ | Eliminated (local vLLM) |
| POLARIS to Search APIs (Serper, Exa, Tavily) | HTTPS | TLS 1.2+ | Eliminated (local SearxNG) |
| POLARIS to Academic APIs (Semantic Scholar, OpenAlex) | HTTPS | TLS 1.2+ | Eliminated (local corpus) |
| POLARIS to Content Fetch (Jina Reader, Firecrawl) | HTTPS | TLS 1.2+ | Eliminated (local trafilatura) |
| POLARIS to Vector DB (ChromaDB) | In-process | N/A (no network) | Same |
| POLARIS to NLI Model (MiniCheck) | In-process | N/A (local GPU) | Same |
| POLARIS to Hallucination Model (LettuceDetect) | In-process | N/A (local GPU) | Same |

---

## 3. HIPAA-Specific Audit Event Format

For HIPAA-regulated deployments, POLARIS audit events should be augmented with the following fields:

### 3.1 Standard Audit Event Schema

```json
{
  "event_id": "evt_001_20260227T143001",
  "timestamp": "2026-02-27T14:30:01.234Z",
  "event_type": "data_access",
  "vector_id": "WEB_1740667800_a3f2b1c4",
  "user_id": "user_001@coveredentity.org",
  "user_role": "researcher",
  "source_ip": "192.168.1.100",
  "action": "content_fetch",
  "resource": "https://pubmed.ncbi.nlm.nih.gov/12345678/",
  "outcome": "success",
  "data_classification": "research_source",
  "phi_indicator": false,
  "details": {
    "content_length": 8432,
    "content_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
    "fetch_method": "jina_reader",
    "quality_tier": "GOLD",
    "node": "analyze",
    "pipeline_iteration": 1
  }
}
```

### 3.2 Audit Event Categories for HIPAA

| Category | Event Types | Description |
|----------|-------------|-------------|
| **Authentication** | login, logout, session_start, session_end, token_refresh | User access lifecycle |
| **Authorization** | access_granted, access_denied, role_change, privilege_escalation | Access control decisions |
| **Data Access** | content_fetch, evidence_extract, report_view, export_pdf | Research data access |
| **Data Processing** | llm_call, nli_verify, hallucination_audit, synthesis | AI processing operations |
| **Quality Control** | quality_gate_pass, quality_gate_fail, case_escalation | Data quality decisions |
| **System** | pipeline_start, pipeline_end, pipeline_cancel, error, checkpoint | System lifecycle events |
| **Export** | pdf_export, json_export, audit_certificate | Data output events |

### 3.3 PHI Detection (When Applicable)

For healthcare deployments where fetched source content may incidentally contain PHI:

| Control | Implementation |
|---------|----------------|
| Content Classification | Source content from medical databases (PubMed, clinical trials) flagged with `data_classification: "medical_source"` |
| Access Logging | All access to medical-classified content logged with user_id, timestamp, and purpose |
| Minimum Necessary | Evidence extraction captures only research-relevant claims, not full patient records |
| Content Redaction | Configurable redaction patterns for common PHI formats (SSN, MRN, DOB) in fetched content |
| Retention Enforcement | Medical-classified content subject to organization-defined retention policies |

---

## 4. Audit Report Generation

### 4.1 Standard HIPAA Audit Report

POLARIS can generate a HIPAA-formatted audit report for any research run:

```
HIPAA AUDIT REPORT
==================
Report Generated: 2026-02-27T15:00:00Z
Examination Period: 2026-02-27T14:30:00Z to 2026-02-27T15:30:00Z

RESEARCH SESSION
  Vector ID: WEB_1740667800_a3f2b1c4
  User: user_001@coveredentity.org
  Role: researcher
  Query Hash: sha256:a3f2b1c4...
  Depth: standard
  Duration: 62 minutes

DATA ACCESS SUMMARY
  External Sources Fetched: 112
  Content Bytes Retrieved: 1,243,567
  Medical Sources Accessed: 23 (PubMed, clinical trials)
  Evidence Pieces Extracted: 847
  Claims Verified: 847 (100% coverage, no sampling)

QUALITY ASSURANCE
  Faithfulness Score: 0.805 (80.5%)
  Quality Gate Outcome: CASE_1 (PASS)
  Iterations: 2
  Hallucination Audit: 13/13 sections audited

EVIDENCE TIER DISTRIBUTION
  GOLD: 127 (15.0%)
  SILVER: 312 (36.8%)
  BRONZE: 408 (48.2%)

OUTPUT INTEGRITY
  Report Words: 11,583
  Verified Citations: 191
  Unique Sources: 18
  Output Hash: sha256:e7f3a2b1...
  Audit Certificate: Included in PDF export

ANOMALIES
  None detected.
```

### 4.2 Periodic Compliance Summary

For HIPAA compliance officers, POLARIS can generate periodic summaries:

| Metric | Period Aggregate | Purpose |
|--------|------------------|---------|
| Total Research Sessions | Count per week/month | Usage monitoring |
| Unique Users | Distinct user count | Access scope |
| Medical Sources Accessed | Count of PubMed/clinical sources | PHI exposure assessment |
| Quality Gate Failures | Count of CASE_3 and CASE_4 | Data quality monitoring |
| Average Faithfulness | Mean across all runs | Accuracy trending |
| Export Events | PDF/JSON export count | Data distribution tracking |
| Access Denials | 401/403 response count | Security incident monitoring |

---

## 5. Implementation Checklist

| Control | Status | Responsibility | Notes |
|---------|--------|----------------|-------|
| JSONL pipeline tracing enabled | Active (default on) | System | `PG_TRACING_ENABLED=1` |
| Session logging enabled | Active (always on) | System | Append-only `logs/session_log.md` |
| Cost ledger enabled | Active | System | `logs/pg_cost_ledger.jsonl` |
| User authentication (SSO/SAML) | Planned (Phase 2B) | Deployer | Required for HIPAA deployment |
| RBAC enforcement | Planned (Phase 2B) | Deployer | Required for HIPAA deployment |
| Encryption at rest | Deployer-configured | Deployer | SQLCipher for SQLite, disk encryption for outputs |
| Encryption in transit | Active (HTTPS enforced) | System | All external APIs use HTTPS |
| PHI detection/redaction | Configurable | Deployer | Enable for healthcare deployments |
| Audit log retention (6 years) | Deployer-configured | Deployer | Configure per organizational policy |
| Access review procedures | Organizational | Deployer | Required for HIPAA compliance program |
| Incident response procedures | Organizational | Deployer | Required for HIPAA compliance program |
| Business Associate Agreement | Organizational | Deployer/Vendor | Required when POLARIS processes PHI on behalf of Covered Entity |

---

## 6. Sovereign Deployment Advantages for HIPAA

POLARIS sovereign deployment mode provides significant advantages for HIPAA-regulated organizations:

| Advantage | Description |
|-----------|-------------|
| **Zero External Data Transmission** | Air-gapped mode eliminates all external API calls; no research data leaves customer infrastructure |
| **Local NLI Verification** | MiniCheck model runs on local GPU; no claim text sent to external services for verification |
| **Local Hallucination Detection** | LettuceDetect runs on local GPU; no report content sent externally for quality audit |
| **Customer-Controlled Infrastructure** | All compute, storage, and networking under customer IT control |
| **No Vendor Data Access** | In sovereign mode, POLARIS vendor has zero access to customer research data |
| **Complete Audit Trail Ownership** | All trace files, logs, and outputs stored on customer-controlled storage |
| **BAA Simplification** | Fewer Business Associate Agreements needed when external vendor dependencies are eliminated |

---

*This document provides a framework for mapping POLARIS audit trail capabilities to HIPAA Security Rule technical safeguards. Organizations must supplement this with organizational policies, physical safeguard documentation, and administrative safeguard documentation to achieve full HIPAA Security Rule compliance. Consult with a HIPAA compliance specialist for deployment-specific requirements.*
