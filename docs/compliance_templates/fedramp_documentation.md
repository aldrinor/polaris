# FedRAMP Documentation Template

## POLARIS Sovereign Deep Research Platform

**Framework**: FedRAMP (Federal Risk and Authorization Management Program)
**Baseline**: Moderate (recommended for government research applications)
**Last Updated**: 2026-02-27
**Document Status**: System Security Plan (SSP) outline and control mapping template

---

## 1. System Description

### 1.1 System Name and Identifier

| Field | Value |
|-------|-------|
| System Name | POLARIS Sovereign Deep Research Platform |
| System Identifier | [CUSTOMER TO COMPLETE] |
| System Owner | [CUSTOMER TO COMPLETE] |
| Authorizing Official | [CUSTOMER TO COMPLETE] |
| Impact Level | Moderate (recommended) |

### 1.2 System Function

POLARIS is an autonomous deep research platform that generates comprehensive, cited research reports. It processes user research queries through an 8-node pipeline that searches public sources, extracts evidence, verifies claims against source content using Natural Language Inference, and synthesizes reports with full bibliographic provenance.

### 1.3 Deployment Architecture

**Required for FedRAMP**: Sovereign mode deployment (air-gapped or FedRAMP-authorized cloud).

| Component | Location | Boundary |
|-----------|----------|----------|
| POLARIS application server | Customer data center / GovCloud | Authorization boundary |
| vLLM inference server | Customer GPU cluster | Authorization boundary |
| SearxNG search engine | Customer data center | Authorization boundary |
| ChromaDB vector store | Local filesystem | Authorization boundary |
| SQLite caches | Local filesystem | Authorization boundary |
| Web dashboard | Browser (client-side) | External to boundary |

### 1.4 Data Flow Summary

```
User (Browser)
  |
  | HTTPS (TLS 1.3)
  v
POLARIS FastAPI Server (Port 8000)
  |
  | Internal (loopback/VPN)
  v
vLLM Inference Server (Port 8080)    SearxNG (Port 8888)
  |                                      |
  | All within authorization boundary    |
  +--------------------------------------+
  |
  v
Local Storage: outputs/, state/, logs/
```

---

## 2. Control Family Mapping

### AC — Access Control

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| AC-1 | Access control policy and procedures | Three-tier RBAC: Researcher (read), Operator (monitor), Admin (configure). Documented in `docs/architecture_diagram.md` |
| AC-2 | Account management | Session-scoped authentication; per-client SSE cursor isolation; no persistent sessions after logout |
| AC-3 | Access enforcement | Endpoint-level permission matrix enforced at API layer; Researcher cannot access `/api/pipeline/config` or `/api/cost` |
| AC-4 | Information flow enforcement | Sovereign mode: zero data egress; pipeline nodes communicate only through in-memory `ResearchState` TypedDict; outputs written to local filesystem only |
| AC-5 | Separation of duties | Researcher view hides operator internals (token costs, model names, batch sizes, trace events); Admin required for configuration changes |
| AC-6 | Least privilege | Each role has minimum necessary access; API keys scoped to specific services |
| AC-7 | Unsuccessful logon attempts | [CUSTOMER TO IMPLEMENT: Account lockout after N failed attempts] |
| AC-8 | System use notification | [CUSTOMER TO IMPLEMENT: Login banner with authorized use warning] |
| AC-11 | Session lock | [CUSTOMER TO IMPLEMENT: Dashboard session timeout and lock] |
| AC-14 | Permitted actions without identification | Health check endpoint (`/health`) is the only unauthenticated endpoint |
| AC-17 | Remote access | All access via HTTPS to dashboard; sovereign mode restricts to intranet only |
| AC-22 | Publicly accessible content | Reports are not publicly accessible; all outputs behind authentication |

### AT — Awareness and Training

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| AT-1 | Security awareness training policy | [CUSTOMER TO IMPLEMENT: Training program for POLARIS users and operators] |
| AT-2 | Security awareness training | [CUSTOMER TO IMPLEMENT: Annual security awareness training covering POLARIS data handling] |
| AT-3 | Role-based security training | [CUSTOMER TO IMPLEMENT: Role-specific training for Researcher, Operator, Admin roles] |

### AU — Audit and Accountability

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| AU-1 | Audit policy and procedures | POLARIS generates multi-layer audit trail automatically: JSONL trace, cost ledger, application log, evidence registry |
| AU-2 | Audit events | 10 event types captured: query submission, pipeline start/stop, search execution, content fetch, evidence extraction, claim verification, quality gate decision, report generation, error/failure, cost record |
| AU-3 | Content of audit records | Each record contains: timestamp (ISO 8601), event type, node name, vector ID, iteration count, action details, input/output counts, duration, model identifier, cost |
| AU-4 | Audit storage capacity | JSONL files on local filesystem; ~1-5 MB per research run; configurable retention |
| AU-5 | Response to audit processing failures | Pipeline logs errors to `polaris_graph.log` and continues; CASE_4 halts on critical failures |
| AU-6 | Audit review, analysis, reporting | Operator dashboard shows real-time events; cost ledger enables spend analysis; trace files support post-hoc analysis |
| AU-7 | Audit reduction and report generation | JSONL format enables filtering by event_type, node, vector_id; trace events indexed by timestamp |
| AU-8 | Time stamps | All events timestamped with UTC ISO 8601; pipeline tracks start/end time for every node |
| AU-9 | Protection of audit information | JSONL files are append-only; filesystem permissions restrict write access to POLARIS process only |
| AU-11 | Audit record retention | Configurable; FedRAMP Moderate requires minimum 3 years online, 6 years total |
| AU-12 | Audit generation | Automated by `src/polaris_graph/tracing.py`; no manual intervention required; every pipeline node generates trace events |

### CA — Security Assessment and Authorization

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| CA-1 | Security assessment policy | [CUSTOMER TO IMPLEMENT: Annual assessment schedule] |
| CA-2 | Security assessments | [CUSTOMER TO IMPLEMENT: 3PAO assessment of POLARIS deployment] |
| CA-3 | System interconnections | Sovereign mode: no external interconnections. Cloud mode: documented API connections to OpenRouter, Serper, S2, Exa, Jina |
| CA-5 | Plan of action and milestones | [CUSTOMER TO IMPLEMENT: POA&M tracking for identified vulnerabilities] |
| CA-7 | Continuous monitoring | Real-time dashboard monitoring; JSONL audit trail; cost budget guard ($150 default); circuit breaker for provider failures |

### CM — Configuration Management

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| CM-1 | Configuration management policy | All configuration externalized via environment variables (100+ documented); LAW VI: Zero Hard-Coding |
| CM-2 | Baseline configuration | `.env` file defines complete system configuration; `requirements.txt` pins dependency versions |
| CM-3 | Configuration change control | All `.env` changes documented with FIX-xxx comments; git version control for code changes; session log captures all decisions |
| CM-4 | Security impact analysis | Configuration changes include rationale in `.env` comments (e.g., "FIX-057: Increased from 150 to 180 -- accommodates safety timeouts") |
| CM-5 | Access restrictions for change | Admin role required for configuration changes; `.env` file protected by filesystem permissions |
| CM-6 | Configuration settings | Documented in `docs/deployment_guide.md` Section 6 with defaults and descriptions for all 100+ variables |
| CM-7 | Least functionality | Sovereign mode disables all non-essential services (Exa, Jina, Firecrawl, PageRank); only core pipeline components enabled |
| CM-8 | Information system component inventory | `docs/file_directory.md` catalogs all system components; `requirements.txt` lists all dependencies |

### CP — Contingency Planning

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| CP-1 | Contingency planning policy | [CUSTOMER TO IMPLEMENT: Contingency plan for POLARIS service disruption] |
| CP-2 | Contingency plan | LangGraph checkpoint/resume enables pipeline recovery; state files portable across hardware |
| CP-4 | Contingency plan testing | [CUSTOMER TO IMPLEMENT: Annual contingency plan test] |
| CP-6 | Alternate storage site | [CUSTOMER TO IMPLEMENT: Backup storage for `outputs/`, `state/`, `logs/`] |
| CP-7 | Alternate processing site | Sovereign deployment can be replicated to secondary data center with identical configuration |
| CP-9 | Information system backup | All persistent state in filesystem directories; standard backup tools (rsync, snapshot) applicable |
| CP-10 | Information system recovery and reconstitution | Checkpoint manager restores pipeline to last completed node; `state/restart_instructions.md` documents recovery procedure |

### IA — Identification and Authentication

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| IA-1 | Identification and authentication policy | [CUSTOMER TO IMPLEMENT: Authentication policy for POLARIS access] |
| IA-2 | Identification and authentication (organizational users) | [CUSTOMER TO IMPLEMENT: SSO/MFA integration for dashboard and API access] |
| IA-5 | Authenticator management | API keys in `.env` (never in source code); masked in logs (first 8 chars only) |
| IA-8 | Identification and authentication (non-organizational users) | [CUSTOMER TO IMPLEMENT: Guest access policy, if applicable] |

### IR — Incident Response

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| IR-1 | Incident response policy | [CUSTOMER TO IMPLEMENT: POLARIS-specific incident response procedures] |
| IR-2 | Incident response training | [CUSTOMER TO IMPLEMENT: Training for operators on POLARIS failure modes] |
| IR-4 | Incident handling | Built-in incident detection: CASE_4 (critical failure), budget exceeded, circuit breaker activation. All generate log entries |
| IR-5 | Incident monitoring | Real-time SSE events; operator dashboard; application log with severity levels |
| IR-6 | Incident reporting | [CUSTOMER TO IMPLEMENT: Reporting procedures for POLARIS security incidents] |

### MA — Maintenance

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| MA-1 | System maintenance policy | [CUSTOMER TO IMPLEMENT: Maintenance schedule for POLARIS server and GPU hardware] |
| MA-2 | Controlled maintenance | Version upgrades documented in `docs/deployment_guide.md` Section 11; rollback procedure included |
| MA-5 | Maintenance personnel | [CUSTOMER TO IMPLEMENT: Authorization for maintenance personnel] |

### MP — Media Protection

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| MP-1 | Media protection policy | [CUSTOMER TO IMPLEMENT: Policy for media containing POLARIS outputs] |
| MP-2 | Media access | Output files protected by filesystem permissions; sovereign mode keeps all data on-premises |
| MP-6 | Media sanitization | [CUSTOMER TO IMPLEMENT: Secure deletion procedures for POLARIS data] |

### PE — Physical and Environmental Protection

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| PE-1 through PE-20 | Physical security controls | [CUSTOMER TO IMPLEMENT: All physical security controls for data center housing POLARIS sovereign deployment] |

### PL — Planning

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| PL-1 | Security planning policy | This document serves as the SSP outline for POLARIS |
| PL-2 | System security plan | This document plus `docs/architecture_diagram.md`, `docs/deployment_guide.md` |
| PL-4 | Rules of behavior | [CUSTOMER TO IMPLEMENT: Acceptable use policy for POLARIS] |

### PS — Personnel Security

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| PS-1 through PS-8 | Personnel security controls | [CUSTOMER TO IMPLEMENT: Personnel security controls for POLARIS users and administrators] |

### RA — Risk Assessment

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| RA-1 | Risk assessment policy | [CUSTOMER TO IMPLEMENT: Risk assessment methodology for POLARIS] |
| RA-2 | Security categorization | Recommended: MODERATE impact level for government research applications |
| RA-3 | Risk assessment | Pipeline quality metrics provide continuous risk assessment: faithfulness score, evidence tier distribution, source diversity |
| RA-5 | Vulnerability scanning | [CUSTOMER TO IMPLEMENT: Regular vulnerability scanning of POLARIS application and dependencies] |

### SA — System and Services Acquisition

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| SA-1 | System and services acquisition policy | [CUSTOMER TO IMPLEMENT] |
| SA-4 | Acquisition process | All dependencies documented in `requirements.txt`; open-source components with verified licenses |
| SA-9 | External information system services | Sovereign mode: no external services. Cloud mode: documented API dependencies with sovereign alternatives |
| SA-11 | Developer security testing | Automated testing: `scripts/preflight.py` (40 tests); `tests/` directory with unit and integration tests |

### SC — System and Communications Protection

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| SC-1 | System and communications protection policy | [CUSTOMER TO IMPLEMENT] |
| SC-7 | Boundary protection | Sovereign mode: air-gapped network; firewall DROP all outbound; only loopback and intranet allowed |
| SC-8 | Transmission confidentiality | TLS 1.3 for all communications: browser-to-server, server-to-vLLM, server-to-SearxNG |
| SC-12 | Cryptographic key management | API keys in `.env` protected by filesystem permissions; TLS certificates managed by standard PKI |
| SC-13 | Cryptographic protection | TLS 1.3 for transit; dm-crypt/BitLocker for storage; SHA256 for content integrity |
| SC-28 | Protection of information at rest | [CUSTOMER TO IMPLEMENT: Full-disk encryption for POLARIS server storage] |

### SI — System and Information Integrity

| Control | Description | POLARIS Implementation |
|---------|-------------|----------------------|
| SI-1 | System and information integrity policy | Pipeline integrity enforced by quality gates, NLI verification, and schema validation |
| SI-2 | Flaw remediation | Dependencies tracked in `requirements.txt`; regular updates per `docs/deployment_guide.md` Section 11 |
| SI-3 | Malicious code protection | [CUSTOMER TO IMPLEMENT: Host-level AV/EDR] |
| SI-4 | Information system monitoring | Real-time SSE dashboard; JSONL trace logging; cost budget monitoring; circuit breaker monitoring |
| SI-5 | Security alerts, advisories, directives | [CUSTOMER TO IMPLEMENT: Subscribe to security advisories for Python, LangGraph, PyTorch dependencies] |
| SI-10 | Information input validation | Pydantic schema validation on all API inputs; query length 5-2000 chars; depth preset enum validation |
| SI-12 | Information handling and retention | All outputs in local filesystem; configurable retention; no automatic data sharing |

---

## 3. Continuous Monitoring Requirements

### 3.1 ConMon Activities

| Activity | Frequency | Tool/Method |
|----------|-----------|------------|
| Vulnerability scanning | Monthly | [CUSTOMER TO IMPLEMENT: Nessus, Qualys, or equivalent] |
| Configuration audit | Monthly | Compare `.env` against approved baseline |
| Access review | Quarterly | Review user roles and access logs |
| Penetration testing | Annual | [CUSTOMER TO IMPLEMENT: 3PAO or internal red team] |
| Security assessment | Annual | [CUSTOMER TO IMPLEMENT: 3PAO assessment] |
| Plan of action review | Monthly | [CUSTOMER TO IMPLEMENT: POA&M status update] |
| Audit log review | Weekly | Review `logs/polaris_graph.log` and trace files |
| Cost monitoring | Per run | Review `logs/pg_cost_ledger.jsonl` |

### 3.2 Automated ConMon from POLARIS

| Metric | Collection Method | Alert Threshold |
|--------|------------------|-----------------|
| Pipeline faithfulness | Automatic per run | < 70% triggers CASE_2/3 |
| LLM cost per run | Cost ledger JSONL | > $150 budget guard |
| Provider availability | Circuit breaker | 5 consecutive failures |
| Pipeline duration | Trace timestamps | > 180 minutes timeout |
| Evidence quality | Tier distribution | > 50% BRONZE triggers warning |

---

## 4. Incident Response Procedures Template

### 4.1 POLARIS-Specific Incident Categories

| Category | Description | Severity | Response |
|----------|-------------|----------|----------|
| Data egress (sovereign) | Data left authorization boundary | Critical | Isolate server, investigate, report |
| Hallucination incident | Report contains fabricated claims passed verification | High | Quarantine report, investigate NLI bypass, retract if distributed |
| API key compromise | API credentials exposed | High | Rotate keys, audit usage, investigate source |
| Pipeline CASE_4 | Critical failure in pipeline | Medium | Investigate root cause, log in bug_log.md |
| Budget exceeded | LLM costs exceeded budget guard | Low | Review cost ledger, adjust budget or reduce query volume |
| Provider outage | External API unavailable | Low (sovereign: N/A) | Circuit breaker activates; wait for recovery |

### 4.2 Incident Response Steps

1. **Detection**: Automated (CASE_4, budget guard, circuit breaker) or manual (operator dashboard, log review)
2. **Analysis**: Review trace.jsonl for the affected vector_id; identify the failing node and root cause
3. **Containment**: Cancel pipeline if running; isolate affected outputs
4. **Eradication**: Fix root cause (configuration change, code fix, or environmental remediation)
5. **Recovery**: Re-run pipeline with corrected configuration; verify output quality
6. **Post-incident**: Document in `logs/bug_log.md`; update risk assessment; brief stakeholders

---

## 5. System Security Plan (SSP) Outline

### Document Structure for FedRAMP Submission

| Section | Content | POLARIS Source |
|---------|---------|---------------|
| 1. System Identification | Name, owner, categorization | Section 1 of this document |
| 2. System Description | Function, architecture, data flow | `docs/architecture_diagram.md` |
| 3. System Environment | Hardware, software, network | `docs/deployment_guide.md` |
| 4. System Interconnections | External API dependencies (or none for sovereign) | `docs/architecture_diagram.md` Section 5-6 |
| 5. Applicable Laws and Regulations | FedRAMP, FISMA, agency-specific | [CUSTOMER TO COMPLETE] |
| 6. Minimum Security Controls | Control implementation details | Section 2 of this document |
| 7. Continuous Monitoring | ConMon plan and procedures | Section 3 of this document |
| 8. Incident Response | IR procedures | Section 4 of this document |
| 9. Configuration Management | CM plan | `.env` documentation, `docs/deployment_guide.md` Section 6 |
| 10. Contingency Plan | CP plan | LangGraph checkpointing, recovery procedures |
| 11. User Guide | Operator and user documentation | `docs/` directory |
| 12. POA&M | Known vulnerabilities and remediation plan | [CUSTOMER TO COMPLETE] |

---

## 6. Document Maintenance

| Activity | Frequency | Responsible |
|----------|-----------|-------------|
| SSP update | Annual or on significant change | System Owner |
| Control assessment | Annual | 3PAO |
| ConMon report | Monthly | ISSO |
| POA&M update | Monthly | System Owner |
| Authorization review | Every 3 years | Authorizing Official |
