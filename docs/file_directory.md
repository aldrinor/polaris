# POLARIS File Directory

**Last Updated**: 2026-05-05 (post-Cleanup-PR-8; substantive update from 2026-04-18 baseline)
**Status**: 305 tests passing against pipeline A. Repo cleaned across two cleanup waves:
- **2026-04-18 wave:** 162 orphans archived, 37 stale docs archived, 56MB of working-tree scratch moved to `archive/2026-04-18-pre-audit-cleanup/`.
- **2026-05-05 wave (Cleanup-PR-1..PR-8 per `state/polaris_restart/cleanup_audit.md` Codex APPROVE iter 21):**
  - PR-1: 39 pytest tmpdirs deleted (Apply); 109 ACL-blocked dirs catalogued in `state/polaris_restart/cleanup_delete_failures.txt` for elevated reclaim.
  - PR-2: 19 top-level Codex verdict briefs (m_int / m_live / m_prod / md9 series) → `archive/2026-05-05/codex_verdict_briefs_*/`.
  - PR-3a/b/c: 190+44 = 234 review briefs from `.codex/_archive_pre_v6_2/` + top-level superseded briefs → `archive/2026-05-05/codex_archive_pre_v6_2_pr3{a,b,c}/` + `archive/2026-05-05/codex_briefs_pr3c_misc/`.
  - PR-4: atomic rename `.codex/REVIEW_BRIEF_FORMAT_v2.md` → `REVIEW_BRIEF_FORMAT.md` and `AUDIT_CYCLE_PROTOCOL_v2.md` → `AUDIT_CYCLE_PROTOCOL.md` + 8 active referencing files updated.
  - PR-5: atomic rename `scripts/pg_preflight_v2.py` → `pg_preflight.py` + 6 active referencing files updated.
  - PR-6: atomic doc rename `docs/full_online_plan_FINAL.md` → `full_online_plan.md` (6 active refs) + `carney_delivery_plan_FINAL` → `carney_delivery_plan_v6_2` ref-only update (1 file).
  - PR-7: 11 `state/autoloop_handover_*.md` → `archive/2026-05-05/state_autoloop_handovers/`.
  - PR-8 (this commit): `docs/file_directory.md` updated to reflect post-cleanup state.

Manifest with merkle hashes + per-file SHAs for every Cleanup-PR-1 deletion at `state/polaris_restart/cleanup_manifest.md` + `cleanup_manifest_sidecars/del_NNN.{per_file,permission_denied}.txt` (296 sidecar files).

**This document describes only ACTIVE code.** For the static
import-closure analysis that produced this view, see
`docs/live_code_audit.md`. For the full file inventory the audit
produced, see `docs/live_code_audit.json`.

---

## 1. Root-level files

| File | Purpose |
|------|---------|
| `README.md` | Project overview + quick start (rewritten 2026-04-18) |
| `architecture.md` | Current-state architecture (rewritten 2026-04-18) |
| `CLAUDE.md` | Operational directives (non-negotiable) |
| `ground_rules.md` | Engineering ground rules |
| `requirements.txt` | Python deps |
| `pytest.ini` | Pytest config |
| `Dockerfile` | Python 3.11-slim + WeasyPrint + uvicorn |
| `docker-compose.yml` | `web`, `chromadb`, `searxng` (sovereign profile), `vllm` (sovereign profile) |
| `docker-compose.override.yml` | Local overrides — gitignored |
| `.env` | Secrets + env-var config — gitignored |
| `.env.example` | Template showing required variables |
| `.gitignore` | Updated 2026-04-18 to block scratch-dir accumulation |

---

## 2. Source tree — `src/`

### Active subsystems

| Path | Role | Pipelines | Notes |
|------|------|-----------|-------|
| `src/polaris_graph/nodes/` | Pre-generation gates | A | `scope_gate`, `corpus_approval_gate`, `corpus_adequacy_gate`, `completeness_checker` |
| `src/polaris_graph/retrieval/` | Source retrieval + tiering | A | `live_retriever`, `tier_classifier`, `domain_backends`, `scope_query_validator`, `contradiction_detector`, `prefetch_offtopic_filter`, `fetch_limiter` |
| `src/polaris_graph/authority/` | Field-agnostic computed source-authority model (Phase 0a, GH #983) | A | `authority_model` (entry `score_source_authority`), `citation_graph`/`institutional`/`junk_detection`/`corroboration`/`recency` (signals A-E), `source_class` (enums + `AuthoritySignals`/`AuthorityResult`), `clinical_view` (primitives->T1-T7 renderer), `data_loader` (fail-loud loader for `config/authority/*`). Drop-in behind `PG_USE_AUTHORITY_MODEL` (default OFF); ZERO host literals in code (all knowledge in versioned `config/authority/*`). `credibility_judge_caller` (P2 credibility SCORING judge caller) HARDENED I-arch-007 #1264: per-call total-deadline + force-close ported from `entailment_judge._post_with_total_deadline` (`PG_CREDIBILITY_JUDGE_TOTAL_S`) — kills the residual sync-POST trickle-keep-alive hang that an httpx read-gap alone could not bound. |
| `src/polaris_graph/generator/` | Prose generation + strict verify | A | `multi_section_generator`, `live_deepseek_generator`, `provenance_generator`, `weighted_enrichment` (I-arch-007 #1264 BREADTH item-2: `select_unbound_supports_by_weight` surfaces the FULL ordered list — no cap/target/top-N — of weighted, span-verified UNBOUND isolated-SUPPORTS basket members into one field-agnostic enrichment section that flows through the UNCHANGED strict_verify; relevance-gated on the EXISTING `PG_RELEVANCE_FLOOR`; `PG_BREADTH_ENRICHMENT_ENABLED` default-off / slate force-on), `generation_snapshot` (I-arch-007 ITEM5 default-off resume checkpoint with recursive-guard) |
| `src/polaris_graph/evaluator/` | External evaluator (different-family judge) | A | `external_evaluator`, `live_judge` |
| `src/polaris_graph/roles/` | 4-role eval seam (sweep -> 4-role) | A | `sweep_integration.run_four_role_evaluation` now parallelizes per-claim COMPUTE in a thread pool sized by `PG_FOUR_ROLE_CLAIM_WORKERS` (default 6; `1` preserves exact sequential behaviour); ALL reduction/D8-policy/coverage-credit/KG-write/run-budget-cap stays on the PARENT thread in ORIGINAL claim order (input-order deterministic; LAW VI worker count from env only). `openrouter_role_transport` HARDENED I-arch-007 #1264: per-call total-deadline + force-close (`PG_ROLE_TRANSPORT_TOTAL_S`) ported from `entailment_judge`, using a THREAD-LOCAL httpx client so a force-close only touches the calling worker — fixes the Codex-caught cascade where one force-close on a SHARED client wedged all 6 concurrent 4-role workers. `sentinel_adapter` (I-arch-007 ITEM4) degrades-and-continues on a transport fault instead of blocking the run. |
| `src/polaris_graph/llm/` | OpenRouter gateway | A, B | `openrouter_client` enforces two-family segregation, budget guard, cost imputation |
| `src/polaris_graph/agents/` | Agent helpers | A | `nli_verifier` |
| `src/polaris_graph/graph.py` | LangGraph v1 | B | UI pipeline variant |
| `src/polaris_graph/graph_v2.py` | LangGraph v2 (CRAG) | B | UI pipeline variant |
| `src/polaris_graph/graph_v3.py` | LangGraph v3 (ReAct) | B | UI pipeline variant |
| `src/polaris_graph/memory/` | Campaign/cross-vector/content cache | B | UI state |
| `src/polaris_graph/document_ingester.py` | Upload ingestion | B | |
| `src/polaris_graph/checkpoint_manager.py` | LangGraph checkpointer | B | |
| `src/polaris_graph/tracing.py` | JSONL trace writer | A | |
| `src/auth/` | Auth routes + middleware | B | |
| `src/tools/` | Active tool clients (8 commits in last 60 days) | B | |
| `src/tools/core_client.py` | CORE (core.ac.uk) v3 legal-OA full-text fetch by DOI (I-faith-002, GH #1035) | A | `fetch_core_oa_fulltext(doi)` returns `(content, source_url)` or `("", "")`; EXACT-DOI guard rejects fuzzy wrong-paper hits; never raises (caller falls back to abstract). CORE-first access path (gated `PG_CORE_ENABLED`, default on) replacing Sci-Hub, which is now disabled by default (`PG_SCIHUB_ENABLED` default "0"). |
| `src/audit/` | Automated deep audit | B | |
| `src/config/` | Config loaders | A, B | |
| `src/providers/llm_provider.py` | Provider abstraction | A | |

### Frozen subsystems (NOT under active maintenance)

| Path | Last commit | Status |
|------|-------------|--------|
| `src/orchestration/` | 2026-03-16 | FROZEN — see `src/orchestration/FROZEN_SINCE_2026-03-16.md`. Pipeline C. |
| `src/auth/` (non-core files) | 2026-03-16 | Frozen but imported by pipeline B |
| `src/benchmarks/` | 2026-03-16 | Frozen |
| `src/llm/` (non-polaris_graph) | 2026-03-16 | Frozen |
| `src/memory/` (non-polaris_graph) | 2026-03-16 | Frozen |
| `src/quality/` | 2026-03-16 | Frozen |
| `src/schemas/` (non-polaris_graph) | 2026-03-16 | Frozen |
| `src/search/` | 2026-03-16 | Frozen |
| `src/state/` | 2026-03-16 | Frozen |
| `src/utils/` | mixed | Partially frozen — `circuit_breaker`, `quality_metrics`, `result_cache` still imported by tests |

Archived 75 orphaned src/ files to `archive/2026-04-18-pre-audit-cleanup/src/`
on 2026-04-18 (plus the 4 that turned out to still be imported dynamically
were restored immediately).

---

## 3. Scripts — `scripts/`

### Active orchestrators

| Script | Role | Pipeline |
|--------|------|----------|
| `run_honest_sweep_r3.py` | 8-query sweep orchestrator (main entry) | A |
| `run_r6_validation.py` | 4-query revalidation slice | A |
| `run_honest_on_prerebuild_corpus.py` | Sweep against historical corpora | A |
| `run_live_honest_cycle.py` | Single-cycle driver | A |
| `run_honest_full_cycle.py` | Full-cycle driver | A |
| `live_server.py` | FastAPI UI server (214KB) | B |
| `full_cycle.py` | Legacy CLI research driver (has broken imports) | C — FROZEN |

### Active utilities

| Script | Role |
|--------|------|
| `audit_live_code.py` | Static import-closure analysis (produces `docs/live_code_audit.*`) |
| `codex_loop_parse.py` | Parse Codex verdict frontmatter |
| `compare_live_vs_pg_lb_sa_02.py` | Delta diagnostics |
| `migrate_old_runs.py` | Migrate pre-rebuild run JSONs |
| `tier_classifier_spotcheck.py` | Tier-classifier correctness probe |

### Preflight / smoke

- `pg_preflight.py` — environment check (Docker `preflight` subcommand)
- `pg_smoke_test.py`, `pg_integration_smoke.py`, `pg_loopback_smoke.py`, `pg_search_full_smoke.py`
- `pg_session_fix_verify.py`, `pg_subagent_validate.py`

### Ad-hoc / one-off (still in tree, should graduate to tests or be archived)

There are ~80 remaining scripts that are single-use test runners,
one-off validation drivers, dispatcher/serve variants, auto-pilot
helpers, etc. These survived the Phase A archive because they contain
`if __name__ == "__main__":` (making them "reachable" by my
static-analysis criterion). Candidates for future cleanup:

- `loopback_*.py` family (dispatcher, auto_*, extend_quotes, status,
  run_all_10, reason_autopilot) — 15+ files
- `pg_micro_test_*`, `pg_empirical_*`, `pg_smoke_*` families — many
  are superseded by the tests/ suite
- `debug_*.py` (if any remain), `monitor_*.py`, `audit_*.py` family

Full list of what's in `scripts/` now: `ls scripts/*.py | wc -l` → 130.

---

## 4. Tests — `tests/`

| Path | Contents |
|------|----------|
| `tests/polaris_graph/` | 305 tests covering pipeline A + invariants B-1..B-5 |
| `tests/polaris_graph/fixtures/` | (if present) pinned fixtures for deterministic tests |

Run all: `python -m pytest tests/polaris_graph/ -v`

Selected files:

- `test_b1_semantic_grounding.py` — 11 tests for the content-word-overlap invariant
- `test_b2_corpus_approval_enforcement.py` — 5 tests for corpus-approval enforcement
- `test_b3_no_verified_sections.py` — 7 tests for zero-verified-sections abort
- `test_b4_budget_imputation.py` — 8 tests for budget cap under missing/negative `usage.cost`
- `test_b5_delimiter_breakout.py` — 36 tests for delimiter sanitization + Unicode evasions + byte preservation
- `test_regression_pg_lb_sa_02_defects.py` — prior-defect pinning
- ~90 other tests covering nodes, retrieval, generator, evaluator, tier classifier, etc.

---

## 5. Config — `config/`

| Path | Purpose |
|------|---------|
| `config/settings/*.yaml` | Active configuration (thresholds, model choices, retrieval caps) |
| `config/scope_templates/` | Per-domain scope protocol templates (clinical, tech, DD, policy) |
| `config/completeness_checklists/` | Per-domain completeness checklists |
| `config/searxng/` | SearXNG instance config (sovereign mode) |

---

## 6. Docs — `docs/`

| File | Purpose |
|------|---------|
| `file_directory.md` | THIS file — inventory of active code |
| `todo_list.md` | Prioritized backlog |
| `runbook.md` | How to run each pipeline end-to-end |
| `web/s_tier_design_system.md` | Canonical S-tier UI design system (tokens, signature move, per-PR dual-visual+e2e protocol, build order) — #829 |
| `live_code_audit.md` | Static import-closure analysis (human-readable) |
| `live_code_audit.json` | Same, machine-readable |
| `compliance/` | Compliance reference materials |
| `compliance_templates/` | Compliance templates |

37 stale docs (architecture_v{2,3,4}*, pg_test_*_audit, pitch_decks,
deployment plans, survey docs, etc.) archived to
`archive/2026-04-18-pre-audit-cleanup/docs/` on 2026-04-18.

---

## 7. Runtime dirs — all gitignored

| Path | Contents |
|------|----------|
| `outputs/` | Runtime artifacts. Exception: `outputs/codex_findings/` is version-controlled (audit record). |
| `logs/` | `pg_cost_ledger.jsonl`, `session_log.md`, `bug_log.md`, per-run logs |
| `state/` | Pipeline state files (checkpoints, ledger, last_pointer). Tracked governance subdirs: `state/polaris_restart/` (issue-driven workflow), `state/polaris_statistical_contract/` (Carney safety contract — Claude+Codex paired-LLM authorship, see §11 below). |
| `data/` | Reproducible benchmarks and documents |
| `models/` | ML weights (multi-GB) |
| `memory/chroma_db/` | ChromaDB vector store (pipeline B) |
| `.pytest_cache/` | Pytest cache |

---

## 8. Audit-loop infrastructure — `.codex/`, `outputs/codex_findings/`

| Path | Purpose |
|------|---------|
| `.codex/LOOP_PROTOCOL.md` | Loop state machine and anti-circle-jerk rules |
| `.codex/REVIEW_BRIEF.md` | Round-1 initial brief (template for others) |
| `.codex/ROUND_N_BRIEF_TEMPLATE.md` | Per-round brief template |
| `.codex/config.toml` | Project-local Codex config (inherits OAuth) |
| `.codex/loop_state.json` | Persistent loop state |
| `.codex/round_{2,3,4,5}/BRIEF.md` | Per-round briefs |
| `outputs/codex_findings/round_{1..5}/findings.md` | Codex output (verdict + findings) |
| `outputs/codex_findings/round_{1..5}/claude_response.md` | Claude's response |

---

## 9. Archive — `archive/`

Gitignored. Historical snapshots. Notable recent subdirs:

- `archive/2026-04-18-pre-audit-cleanup/` — this cleanup's artifacts
  - `scripts/` — 61 archived one-off/debug scripts
  - `src/` — 71 archived orphan modules
  - `docs/` — 37 archived stale design/audit/marketing docs
  - `root_junk/` — 12 archived root-level files (audit_*.txt, current_ui*.png, mojibake filename)
  - `nested_legacy/POLARIS_APEX/` — old nested repo copy
  - `loopback/`, `tmp/`, `wiki/`, `cache/` — scratch dirs

- `archive/2026-Q2_deprecated_phases/`, `archive/docs_historical_2026012{7,9}/`,
  `archive/logs_historical_*` — earlier cleanups

---

## 10. Deprecated references you may encounter

The following appear in some remaining scripts or old doc strings but
point to non-existent paths / deprecated concepts. Treat as stale:

- `src/phases/` — the P0-P12 directory structure. Removed before
  2026-04-18. The README's old "13-phase pipeline" description was
  fiction as of this cleanup.
- `src/runner.py` — referenced in old README, does not exist.
- `scripts/preflight.py`, `scripts/flight_test.py`,
  `scripts/postflight_audit.py` — referenced in old README, do not
  exist. Use `scripts/pg_preflight.py` instead.
- `scripts/final_audit.py`, `scripts/run_ragas_v3.py` — referenced
  by `scripts/full_cycle.py` (pipeline C). Do not exist; pipeline C
  is broken until these are either restored or removed.
- "Kimi K2.5 1T" — historical generator. The locked architecture for the
  Carney demo is the 4-role stack in
  `config/architecture/polaris_runtime_lock.yaml` (I-meta-001 #933):
  Generator (DeepSeek V4 Pro) + Mirror (GLM-5.1) + Sentinel (MiniMax-M2,
  decomposition mode) + Judge (Qwen3.6-35B-A3B) — four DISTINCT open-weight
  lineages (deepseek/glm/minimax/qwen), all permissive licenses. I-run11-004
  (#1046) re-picked Mirror Cohere Command A+ -> GLM-5.1 (Cohere is not on
  OpenRouter) and replaced the broken Granite-Guardian Sentinel (over-rejected
  grounded clinical claims -> run-12 coverage 0.286) with the CERTIFIED
  MiniMax-M2 claim-decomposition+span-coverage detector (0 false-accepts on 28
  fabrications across 5 error types). The earlier 2-LLM framing (DeepSeek V4 Pro
  generator + Gemma 4 31B evaluator) is superseded; earlier pipelines used
  DeepSeek V3.2-Exp + Qwen3-8B.
- "175 vectors exactly" — old invariant from P0-P12. Not applicable
  to any currently-active pipeline.

See `archive/2026-04-18-pre-audit-cleanup/docs/architecture_legacy_2026-01-31.md`
for the document that described these now-deprecated concepts.

## v6 backend skeleton (added 2026-05-01, Phase 0 Task 0.5)

```
src/polaris_v6/                     # POLARIS v6.2 backend
├── __init__.py                     # __version__ = "6.2.0"
├── api/
│   ├── __init__.py                 # FastAPI router aggregation
│   └── health.py                   # GET /health (liveness/readiness)
├── observability/
│   ├── __init__.py
│   └── otel_init.py                # OTEL SDK init, fail-loudly on misconfig (Errata E-2)
└── queue/
    └── __init__.py                 # Dramatiq queue substrate (actors pending)

tests/v6/
├── __init__.py
└── test_otel_init.py               # 4 tests: env missing | legacy gen_ai_dev rejected | correct value | csv list
```

`requirements-v6.txt` at repo root: pinned production dependencies for
v6 (FastAPI 0.136, Pydantic 2.11, Dramatiq 2.1, OTEL 1.30, semconv
0.51b0, pytest 8.4, ruff 0.7).

## Carney demo readiness docs (added 2026-05-15)

- `docs/polaris_locked_scope.md` — the scope lock (LLM, architecture, 8
  templates, 15 features); single anti-drift source of truth. Codex-APPROVED
  (I-rdy-001 / #497).

The Carney-demo execution plan, gap register, GPU-sovereignty research and
vendor-outreach notes are session-state working docs under `state/`
(gitignored per §5); they are not part of the tracked file inventory.

---

## 11. Statistical Safety Contract — `state/polaris_statistical_contract/` (added 2026-05-27)

PRIORITY governance artifact for Carney readiness. v3.3 = methodology-locked pre-registration draft, hash-pinned. Authored by Claude (Opus 4.7) + Codex (5.5) paired-LLM across 4 review rounds, no external statistician (operator directive 2026-05-27).

| Path | Purpose |
|------|---------|
| `state/polaris_statistical_contract/v3_3/contract.md` | The locked contract: 4 safety gates (A=per-stratum claim-level, B=per-report customer, C=drift, D=classifier) + 1 validity gate (E=SME κ) + 4 prerequisites (P1=retrieval recall, P2=extraction recall, P3=contamination, P4=amendments) + §10 claim-license + §10.0 anti-overclaim layer (18 forbidden phrases) |
| `state/polaris_statistical_contract/v3_3/contract.sha256` | SHA256 hash-pin: `75c9eb94a25450aca9e3b90b2272a5404e71c259203fdf465a38278bdd0d98a3` |
| `state/polaris_statistical_contract/v3_3/LOCK_MANIFEST.md` | Lock procedure status, authorship trail |
| `state/polaris_statistical_contract/v3_3/codex_review_trail/` | 6 files: deep-dialogue → design-partner v1 → 3 round audits → final lock verdict |
| `state/polaris_statistical_contract/v3_3/codex_review_trail.sha256` | SHA256 hashes of the trail |

**Status**: v3.3 methodology + formulas + governance locked. v3.4 (numerical lock) pending Phase 0a.

**Master GH issue**: #917. Sub-issues: #918 (v3.3 lock), #919 (Phase 0a.0 design).

**Memory**: `paired_llm_authorship_no_statistician_2026_05_27.md`.

## 12. DR head-to-head benchmark harness — `scripts/dr_benchmark/` + `tests/dr_benchmark/` (added 2026-05-28)

PRIORITY (I-safety-002b / #925). Benchmarks POLARIS as a deep-research tool vs ChatGPT/Gemini/Perplexity DR, §-1.1 claim-by-claim. Plan: `.codex/I-safety-002b/execution_plan_pathB.md` (Codex APPROVE iter 5).

| Path | Purpose |
|------|---------|
| `scripts/dr_benchmark/run_gate_b.py` (added 2026-06-01, I-meta-008 #1014) | **The sole CLI entrypoint that fires the native 4-role evaluation seam** (V4-Pro generator + Cohere mirror + Granite sentinel + Qwen judge). NO SPEND / NO NETWORK at import. `--only <slug>` runs one LOCKED golden DRB-EN question; `--all` runs all 5 sequentially (one at a time, §8.4); `--list` (= `--dry-run`) previews the resolved questions / transport mode / role slugs+families with NO spend, NO network, and NO env mutation (snapshots+restores `os.environ`). Real runs delegate per-question to `run_gate_b_query` (env-flips + fail-loud preflight before any token + `run_one_query`). Resolves questions by FILTERING the existing `SWEEP_QUERIES` registration (single source of truth — no hardcoded slug->question fallback). Locked slugs: `drb_72_ai_labor`, `drb_75_metal_ions_cvd`, `drb_76_gut_microbiota_crc`, `drb_78_parkinsons_dbs`, `drb_90_adas_liability`. Codex APPROVE (0 P0/P1). NOTE: `run_honest_sweep_r3.py --pathB-gate` is the LEGACY single-judge path, NOT the 4-role seam. |
| `scripts/dr_benchmark/pathB_run_gate.py` | Fatal preflight+post-run enforcement: whole-surface secret-redacted `effective_config.json`, per-role served-identity surrogate, `OPENROUTER_ALLOW_FALLBACKS=false` + singleton routing, fatal retrieval-capability preflight + backends-attempted assertion, all-LLM-paths completeness. 14 fixtures. |
| `scripts/dr_benchmark/medhallu_adapter.py` | Scorer primitives (pairing, source-isolation, aggregation, confusion/F1). MedHallu retired to verifier-component-only proxy (NOT a deep-research benchmark). 12 fixtures. |
| `scripts/dr_benchmark/medhallu_runner.py` | MedHallu entailment-layer runner (component sanity-check only). |
| `tests/dr_benchmark/` | 26 fixtures green (gate + adapter), validated BEFORE any model run. |
| (pending) `src/polaris_graph/benchmark/claim_audit_scorer.py` | Two-lane audit ledger (faithfulness + pre-registered rubric coverage) — REPLACES the §-1.1-banned/rigged `dimension_scorers.py`/`beat_both_scorer.py`. |
| `src/polaris_graph/benchmark/extended_metrics.py` (added 2026-06-11, I-perm-024 #1216) | Five claim-by-claim beat-both metrics (faithfulness_precision, citation_support_rate, diversity_score [DIAGNOSTIC-only], required_entity_recall, safety_floor_recall) computed STRICTLY from audited `ClaimRow`/`RubricElement` typed inputs — never raw report text (§-1.1 structural guarantee). Wired LIVE into `score_run.py` behind default-OFF `PG_BENCH_EXTENDED_METRICS`. |
| `src/polaris_graph/benchmark/claim_dedup.py` (added 2026-06-11, I-perm-024 #1216) | Claimify-style near-duplicate claim collapse with the identical-subject-set guard (`_subjects_differ`): only merges claims with IDENTICAL subject-token sets + compatible numeric signature, so distinct clinical entities (CD4+/CD4-, IL-1α/IL-1β, SGLT2/DPP4) are NEVER merged. |
| `config/dr_benchmark/safety_floor_elements_v3.json` (added 2026-06-11, I-perm-024 #1216) | Pre-registered per-question safety-floor element ids (pinned to the frozen rubric sha) for `safety_floor_recall`. Q75/76/78 clinical-safety ids; Q72/90 empty (non-clinical). |
| `src/polaris_graph/generator/required_entity_ledger.py` (added 2026-06-11, I-perm-021 #1213) | Report-level required-entity completeness accounting + honest "Coverage gaps" disclosure (inclusion + disclosure only; NO re-generation). `verified_covered_ids()` credits coverage ONLY for claims whose 4-role FINAL verdict==VERIFIED; assigns no new credit, touches no gate. Default-OFF `PG_REQUIRED_ENTITY_LEDGER`, fail-soft, native-template-only. |
| `src/polaris_graph/retrieval/evidence_selector.py` — I-perm-023 (#1215) addition | Constrained-greedy diversity pass `_apply_coverage_diversification` (default-OFF `PG_SELECT_CONSTRAINED_GREEDY`): a post-floor, same-tier, COVERAGE-MONOTONE, domain-cap-aware diversification on the safety-category + evidence-class (+ jurisdiction) axes the floor stack does not cover. Forward guard (no-op until pool>cap); touches no floor (parity by construction). |

**NOTE**: the legacy `src/polaris_graph/benchmark/dimension_scorers.py` + `beat_both_scorer.py` ("BEAT-BOTH", 7-dimension) are §-1.1-INVALID (count/pattern/string-match scoring + POLARIS auto-win dimensions) — DO NOT use as a benchmark scorer; being replaced by `claim_audit_scorer.py`.

- `scripts/diagnostics/sentinel_groundedness_probe.py` / `sentinel_multifixture_smoke.py` — I-run11-002 (#1044) live OpenRouter groundedness-discrimination probes for the benchmark Sentinel (granite + non-inverted GROUNDED/UNGROUNDED prompt). Sovereign self-host Guardian path (inverted yes=risk) unchanged.

## Permanent-fix program docs (2026-06-10, the 9 issues, operator-directed)
- `docs/permanent_fix_9_issues.md` — CHARTER: the 9 pinned issues (I-perm-001..009, GitHub #1194-#1203), the withhold→always-release+label reframe, per-issue process.
- `docs/permanent_fix_migration_blueprint.md` — the architecture migration design (frontier-cited + code-grounded; target architecture, cross-cutting decisions, per-issue migration, build order, serious-smoke spec, 6 Codex tensions).
- `outputs/audits/beatboth8/MASTER_FIX_PLAN.md` — the original 8-bug consolidation + behavioral-smoke design (superseded/expanded by the 9-issue charter).
- `outputs/audits/beatboth8/FAILURE_AUDIT.md`, `REMAINING_RISKS.md`, `drb_76/DRB76_FORENSIC.md` — the §-1.1 forensics the program is built on.
