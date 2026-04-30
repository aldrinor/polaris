# SOC 2 Type II Evidence Mapping

## POLARIS Sovereign Deep Research Platform

**Document Version:** 1.0
**Classification:** Compliance Evidence Map — SOC 2 Type II (AICPA Trust Service Criteria 2017)
**Applicable Criteria:** Common Criteria (CC1-CC9), Availability, Processing Integrity, Confidentiality, Privacy
**Last Updated:** 2026-02-27

---

## 1. Overview

This document maps POLARIS Sovereign Deep Research Platform capabilities to the AICPA Trust Service Criteria used in SOC 2 Type II examinations. For each criterion, the mapping identifies the specific POLARIS control, the evidence artifact that demonstrates the control, and the location of that evidence.

POLARIS generates 1,302+ structured trace events per research run, maintains complete evidence chains from source document to final claim, and supports air-gapped sovereign deployment — providing a robust foundation for SOC 2 compliance.

---

## 2. Common Criteria (CC) Mapping

### CC1 — Control Environment

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC1.1 | Organization demonstrates commitment to integrity and ethical values | System enforces "No Fake Working" policy (LAW II): no placeholders, no mocked data, no silent downgrades. Preflight static analysis (`scripts/pg_preflight_v2.py`) rejects forbidden patterns | `scripts/pg_preflight_v2.py` output; `ground_rules.md` Section: Reward Hacking Prevention |
| CC1.2 | Board of directors demonstrates independence | N/A — Organizational control (outside POLARIS scope) | Customer responsibility |
| CC1.3 | Management establishes structures, reporting lines, and authorities | RBAC role definitions: Researcher, Operator, Manager, Auditor, Admin with defined access levels and oversight responsibilities | `docs/todo_list.md` Phase 2B.2 — RBAC specification |
| CC1.4 | Organization demonstrates commitment to competence | Automated quality gates enforce minimum competence thresholds at every pipeline node; no manual override without explicit audit trail | Quality gate configuration in `src/polaris_graph/state.py`; gate outcomes in JSONL trace |
| CC1.5 | Organization enforces accountability | Every pipeline action logged with timestamp, node identifier, duration, and outcome in machine-parseable JSONL format | `logs/pg_trace_{vector_id}.jsonl` — 1,302+ events per run |

### CC2 — Communication and Information

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC2.1 | Entity obtains/generates relevant quality information | 5-signal evidence scoring (Semantic Relevance, Source Authority, Content Density, Freshness, Factual Grounding) generates quality metadata for every evidence piece | Evidence records in `outputs/polaris_graph/{vector_id}.json` with tier_composite_score |
| CC2.2 | Entity internally communicates information | Real-time SSE event streaming from pipeline to operator dashboard; JSONL cost ledger tracks spending | SSE endpoint `/api/events`; `logs/pg_cost_ledger.jsonl` |
| CC2.3 | Entity communicates with external parties | Audit certificate in PDF export includes SHA-256 hash, query, vector ID, claims count, evidence count, sources, word count, timestamp | PDF export audit certificate section |

### CC3 — Risk Assessment

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC3.1 | Entity specifies objectives with sufficient clarity | Research query validated (5-2,000 characters); depth preset (quick/standard/deep) with defined time budgets; vector ID format enforced | `ResearchRequest` Pydantic model in `scripts/live_server.py`; `DEPTH_PRESETS` configuration |
| CC3.2 | Entity identifies risks to achievement of objectives | Quality gates at every pipeline node with defined thresholds and failure actions; gating cases (CASE_1 through CASE_4) for evidence sufficiency assessment | Quality gate table in `architecture.md` Section 9.2; gating case definitions in Section 9.3 |
| CC3.3 | Entity considers potential for fraud | Preflight static analysis (`scripts/pg_preflight_v2.py`) detects and rejects: silent exception handling, hard-coded values, placeholder implementations, sleep-based simulation, TODO/FIXME comments | Preflight scan results; forbidden pattern definitions in `ground_rules.md` |
| CC3.4 | Entity identifies and assesses changes | Session log (`logs/session_log.md`) provides chronological audit trail of all changes; file directory (`docs/file_directory.md`) maintains hierarchical inventory | `logs/session_log.md`; `docs/file_directory.md` |

### CC4 — Monitoring Activities

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC4.1 | Entity selects, develops, and performs ongoing evaluations | Pipeline tracer emits 8 event types (node_start, node_end, fetch, llm_call, quality_gate, evidence, verification, synthesis) for every operation; operator dashboard provides real-time monitoring | `src/polaris_graph/tracing.py` — PipelineTracer class; dashboard at `/api/events` |
| CC4.2 | Entity evaluates and communicates deficiencies | Quality gate failures trigger defined actions: retry (insufficient queries), warn (low fetch rate), CASE_2 (partial evidence iteration), CASE_4 (critical failure escalation) | JSONL trace events with quality_gate event_type; gating case outcomes |

### CC5 — Control Activities

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC5.1 | Entity selects and develops control activities | 8-node pipeline with explicit quality gates; NLI verification of all claims (no sampling); 5-signal evidence scoring; domain blocklist; paywall detection | Pipeline architecture in `architecture.md`; control implementation in `src/polaris_graph/agents/` |
| CC5.2 | Entity deploys control activities through policies | Zero hard-coding policy (LAW VI): all parameters from configuration files, CLI arguments, or environment variables; 40+ environment variables explicitly defined | `.env` file; `src/polaris_graph/state.py` — all config from `os.getenv()` |
| CC5.3 | Entity deploys controls over technology infrastructure | Air-gapped sovereign deployment mode disables ALL external API calls; local NLI inference; local embedding generation; local hallucination detection | `POLARIS_DEPLOYMENT_MODE=sovereign` configuration; fail-loud on external requests |

### CC6 — Logical and Physical Access Controls

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC6.1 | Entity implements logical access security | API key authentication for external services (OPENROUTER_API_KEY, SERPER_API_KEY, SEMANTIC_SCHOLAR_API_KEY); SSO/SAML integration planned (Okta, Azure AD, Google Workspace) | `.env` configuration; Phase 2B.1 RBAC specification |
| CC6.2 | Entity registers and authorizes new users | User registration and role assignment through admin panel; JWT token-based session management | Phase 2B.1-2B.3 implementation plan |
| CC6.3 | Entity manages access credentials | API keys stored in `.env` file (not hard-coded); environment variable isolation between cloud and sovereign deployment modes | `.env` file excluded from version control via `.gitignore` |
| CC6.6 | Entity manages system accounts | Single-concurrency pipeline lock prevents unauthorized concurrent access; per-user isolation in multi-user mode | `PipelineRunner` async lock in `scripts/live_server.py` |
| CC6.7 | Entity restricts access to information assets | Role-based access: Researcher (use), Manager (review), Admin (configure), Auditor (read-only trace); per-user result storage isolation | RBAC role definitions in Phase 2B.2 |
| CC6.8 | Entity prevents or detects unauthorized access | Rate limiting on API endpoints; input validation on all user-facing endpoints; vector_id format validation | Phase I.1 rate limiting; `ResearchRequest` Pydantic validation |

### CC7 — System Operations

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC7.1 | Entity manages infrastructure changes | Version-controlled codebase; session log tracks all operational changes with timestamps, rationale, and affected files | `logs/session_log.md` — append-only audit trail |
| CC7.2 | Entity monitors system components | Pipeline tracer with 1,302+ events per run; Rich dashboard for real-time progress; health check endpoint (`GET /health`) | JSONL trace files; `/health` endpoint response |
| CC7.3 | Entity evaluates changes to system components | Preflight static analysis on every change; quality gates validated on test runs; regression test suite | `scripts/pg_preflight_v2.py`; `tests/` directory |
| CC7.4 | Entity designs, develops, and implements changes | Mandatory documentation synchronization (LAW I): changes to project scope immediately update todo list, session log, file directory, and restart instructions | `docs/todo_list.md`; `state/restart_instructions.md` |

### CC8 — Change Management

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC8.1 | Entity authorizes, designs, develops, and implements changes | Anti-degradation protocol: any requirement that cannot be met requires explicit written approval before fallback implementation; degradation proposals logged in bug log | `logs/bug_log.md` — Degradation Proposal entries |

### CC9 — Risk Mitigation

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| CC9.1 | Entity identifies and assesses risks from vendors | Vendor dependency mapping: OpenRouter (LLM), Serper (search), Semantic Scholar (academic), Jina (content fetch), Exa (search), Tavily (search); each has documented local alternative for sovereign mode | Architecture documentation; sovereign deployment guide |
| CC9.2 | Entity assesses and manages vendor risks | All external providers have local alternatives: OpenRouter -> vLLM, Serper -> SearxNG, cloud models -> local MiniCheck/LettuceDetect; air-gapped mode eliminates all vendor dependencies | `POLARIS_DEPLOYMENT_MODE` configuration |

---

## 3. Availability Criteria

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| A1.1 | Entity maintains availability commitments | Health check endpoint returns status, version, uptime; SSE auto-reconnection; pipeline resumability via job-queue checkpoints + per-run timestamped output dirs | `/health` endpoint; `state/pg_batch_progress.sqlite`; `state/cost_ledger.json`; per-run `outputs/<phase>/run_<timestamp>/` |
| A1.2 | Entity manages capacity | Configurable concurrency controls: web_concurrency=20, academic_concurrency=1, analysis_concurrency=12, verify_concurrency=20, section_write_concurrency=4; evidence caps prevent unbounded growth (1,500 verify, 1,000 synthesis) | Environment variable configuration in `src/polaris_graph/state.py` |
| A1.3 | Entity recovers from disruptions | Checkpoint-and-resume architecture: SQLite-backed batch progress (`pg_batch_progress.sqlite`), JSON cost ledger (append-only), per-run timestamped output dirs (`outputs/.../run_<ts>/`); Docker restart policies; M-INT-0b model_pin replay for deterministic re-run | `src/polaris_graph/audit_ir/job_runner.py`; `src/polaris_graph/audit_ir/model_pin.py`; `state/pg_batch_progress.sqlite`; `state/cost_ledger.json` |

---

## 4. Processing Integrity Criteria

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| PI1.1 | Entity obtains or generates complete and accurate data | All 175 vectors validated (system halts if count != 175); Pydantic schema validation on every phase handoff; no silent fallbacks | Vector count invariant in `architecture.md` Section 9.1; Pydantic schemas in `src/polaris_graph/schemas.py` |
| PI1.2 | Entity implements processing activities as designed | JSON contract communication between pipeline phases; each phase reads ONLY from previous phase output, writes ONLY to its designated output directory (LAW VII) | CLI Isolation Protocol in `ground_rules.md` Phase 4 |
| PI1.3 | Entity ensures processing is complete, accurate, and timely | Quality gates enforce minimum thresholds: queries >= 20, fetch success >= 60%, evidence >= 10, faithfulness >= 0.70, words >= 2,000, citations >= 5; execution time budget (60 min default) | Quality gate table in `architecture.md` Section 9.2 |
| PI1.4 | Entity detects errors in processing | NLI verification checks EVERY claim (no sampling); LettuceDetect flags sections with > 30% hallucination ratio; cross-source verification breaks circular self-verification | Verification node output; hallucination audit results in trace |
| PI1.5 | Entity implements activities to address errors | Iterative refinement (up to 3 iterations): gap search targets weak areas; section rewriting for flagged hallucinations; CASE_2 triggers additional search; CASE_4 halts for human review | Iteration count and gap analysis in JSONL trace |

---

## 5. Confidentiality Criteria

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| C1.1 | Entity identifies confidential information | Research queries and results stored per-user with vector_id isolation; API keys stored in `.env` (excluded from version control); no PII collection by default | `.gitignore` excluding `.env`; per-user result storage |
| C1.2 | Entity disposes of confidential information | Configurable data retention policies; SQLite caches with configurable TTL; outputs directory can be purged per customer policy | Cache configuration; retention policy documentation |

---

## 6. Privacy Criteria

| Criterion | Requirement | POLARIS Control | Evidence Artifact |
|-----------|-------------|-----------------|-------------------|
| P1.1 | Entity provides notice about privacy practices | Research queries validated and stored with minimal metadata; no behavioral tracking; no user profiling | Input validation in `ResearchRequest` model |
| P3.1 | Entity collects personal information only for identified purposes | POLARIS collects only: research query text (5-2,000 characters), depth preference, optional application/region context; no names, emails, or PII required for research | `ResearchRequest` schema definition |
| P4.1 | Entity limits use of personal information | Research data used exclusively for generating the requested research report; no cross-user data sharing; no model training on user data | Architecture documentation; data flow diagrams |
| P6.1 | Entity provides effective mechanisms for disposal | Output files are standard JSON; can be deleted by customer IT per retention policy; no proprietary data formats that prevent disposal | Standard file formats; no vendor lock-in |
| P8.1 | Entity monitors compliance with privacy commitments | Audit trail records all data access and processing with timestamps; per-run trace files enable forensic review of data handling | JSONL trace files per research run |

---

## 7. Evidence Collection Schedule

For SOC 2 Type II examination, the following evidence should be collected over the examination period:

| Evidence Type | Collection Frequency | Storage Location | Retention Period |
|---------------|----------------------|------------------|------------------|
| JSONL Trace Files | Per research run (1,302+ events each) | `logs/pg_trace_{vector_id}.jsonl` | Minimum 12 months |
| Session Logs | Continuous (append-only) | `logs/session_log.md` | Minimum 12 months |
| Cost Ledger | Per research run | `logs/pg_cost_ledger.jsonl` | Minimum 12 months |
| Quality Gate Outcomes | Per research run | Embedded in trace files (quality_gate event type) | Minimum 12 months |
| Preflight Scan Results | Per code change | `scripts/pg_preflight_v2.py` output | Minimum 12 months |
| Bug Log | Continuous (active tracking) | `logs/bug_log.md` | Minimum 12 months |
| Configuration Snapshots | Per deployment | `.env` (redacted), `config/settings/*.yaml` | Minimum 12 months |
| Access Logs | Continuous | Server access logs | Minimum 12 months |
| Faithfulness Scores | Per research run | Embedded in output JSON (faithfulness_score field) | Minimum 12 months |
| Evidence Tier Distribution | Per research run | Embedded in output JSON (GOLD/SILVER/BRONZE counts) | Minimum 12 months |

---

## 8. Auditor Guidance

### 8.1 Key Artifacts for Examination

1. **JSONL Trace File** (`logs/pg_trace_{vector_id}.jsonl`): Machine-parseable record of every pipeline operation. Each line is a JSON object with timestamp, vector_id, node, event_type, data, and duration_ms fields. Typical run produces 1,302+ events.

2. **Output JSON** (`outputs/polaris_graph/{vector_id}.json`): Complete research output including report text, evidence database, verification results, bibliography, quality metrics, and cost summary.

3. **Preflight Report** (`scripts/pg_preflight_v2.py` output): Static analysis results showing absence of forbidden patterns (silent exceptions, hard-coded values, placeholders, mock data in production).

4. **Session Log** (`logs/session_log.md`): Chronological audit trail of all operational decisions, changes, and their rationale.

### 8.2 Testing Procedures

| Test | Procedure | Expected Result |
|------|-----------|-----------------|
| Processing Integrity | Submit known research query, compare output against manual research | Faithfulness >= 70%, citations traceable to real sources |
| Quality Gate Enforcement | Submit query designed to produce low evidence (obscure topic) | Pipeline triggers CASE_2 (retry) or CASE_3 (gap report), does not produce unfounded claims |
| Access Control | Attempt API call without authentication (when RBAC enabled) | 401 Unauthorized response |
| Data Sovereignty | Enable sovereign mode, disable internet, submit query | Pipeline uses only local models and search; no external requests attempted |
| Audit Trail Completeness | Review trace file for complete node lifecycle | Every node_start has matching node_end; no gaps in event sequence |
| Error Handling | Force LLM timeout during verification | Retry with backoff (3 attempts); batch-level retry; graceful degradation to available results |

---

*This evidence map is designed to support SOC 2 Type II examination preparation. Organizations should work with their SOC 2 auditor to confirm evidence sufficiency and adapt controls to their specific operational context.*
