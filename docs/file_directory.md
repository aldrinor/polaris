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
| `src/polaris_graph/generator/` | Prose generation + strict verify | A | `multi_section_generator`, `live_deepseek_generator`, `provenance_generator` |
| `src/polaris_graph/evaluator/` | External evaluator (different-family judge) | A | `external_evaluator`, `live_qwen_judge` |
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
| `state/` | Pipeline state files (checkpoints, ledger, last_pointer) |
| `data/` | Reproducible benchmarks and documents |
| `models/` | ML weights (multi-GB) |
| `memory/chroma_db/` | ChromaDB vector store (pipeline B) |
| `.pytest_cache/` | Pytest cache |

---

## 8. Audit-loop infrastructure — `.codex/`, `outputs/codex_findings/`

| Path | Purpose |
|------|---------|
| `.codex/LOOP_PROTOCOL.md` | Loop state machine and anti-circle-jerk rules |
| `.codex/AUDIT_CYCLE_PROTOCOL.md` | Audit cycle protocol (current) |
| `.codex/REVIEW_BRIEF_FORMAT.md` / `_v2.md` | Current per-Issue review brief templates |
| `.codex/codex_red_team_checklist.md` | Red-team checklist (current) |
| `.codex/config.toml` | Project-local Codex config (inherits OAuth) |
| `.codex/I-<prefix>-NNN/` | Per-Issue dirs (issue-driven workflow — `.codex/I-eval-*`, `.codex/I-bug-*`, etc.) |
| `.codex/slices/` | Slice 001-005 architecture proposals + golden fixtures (load-bearing — referenced by tests) |
| `archive/2026-05-11-root-hygiene/codex_historical/` | Historical pre-issue-driven .codex artifacts (REVIEW_BRIEF.md, ROUND_N_BRIEF_TEMPLATE.md, loop_state.json, round_{2,3,4,5}/, continuous/, deep_dive_round_*/, m28..m63, v17..v30, etc.) — relocated by I-hygiene-001 GH#432 |
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
- "Kimi K2.5 1T" — historical generator. Current generator is
  DeepSeek V3.2-Exp. Current evaluator is Qwen3-8B.
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

---

## 2026-05-11 I-hygiene-001 cleanup (GH#432)

Historical clutter archived under `archive/2026-05-11-root-hygiene/`:

- `root/` — pytest temp dirs, manual probe scratch, Codex review temp dirs
- `codex_historical/` — 230 historical `.codex/` review outputs (m28-m63 audit briefs, v17-v30 plan/audit briefs, phase_c/d plans, pr_b/d/e review files, continuous/, deep_dive_round_*/, walkthrough_*/, round_*/, runs/, slices NOT archived per load-bearing finding, strategic_review_high_quality/, task_briefs/, next_issue_pick*/)

POLARIS root now contains only essential project structure (see §"Standard Repository Layout" in CLAUDE.md §5). `.gitignore` is hardened with anchored patterns to prevent re-accumulation.

**91 root dirs perm-locked** at cleanup time (Windows ACL — created by elevated process). Documented at `state/polaris_restart/i_hygiene_001_force_move_failures.txt`. All are `.gitignored`. User-side post-reboot or elevated-admin removal required to physically clean disk.

Cleanup manifest: `state/polaris_restart/i_hygiene_001_cleanup_manifest.md` (372 rows).
Reference sweep results: `state/polaris_restart/i_hygiene_001_reference_sweep.md` (58 hits, 0 runtime breaks, 8 stale doc/comment refs deferred).
