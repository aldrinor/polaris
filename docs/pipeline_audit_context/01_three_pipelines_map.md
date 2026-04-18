# Three pipelines — file-level map

Source of truth: `docs/live_code_audit.md` (static import-closure
analysis producing 23-file pipeline A + reachable pipeline B graph +
frozen pipeline C).

## Pipeline A — honest-rebuild sweep (active, audited)

Entry: `python -m scripts.run_honest_sweep_r3 [--only <slug>] [--out-root <dir>]`

Flow:

```
scripts/run_honest_sweep_r3.py
  └── src/polaris_graph/nodes/scope_gate.py ──► abort_scope_rejected?
  └── src/polaris_graph/retrieval/live_retriever.py
       ├── src/polaris_graph/retrieval/domain_backends.py
       ├── src/polaris_graph/retrieval/tier_classifier.py
       ├── src/polaris_graph/retrieval/scope_query_validator.py
       ├── src/polaris_graph/retrieval/prefetch_offtopic_filter.py
       └── src/polaris_graph/retrieval/fetch_limiter.py
  └── src/polaris_graph/nodes/corpus_adequacy_gate.py ──► abort_corpus_inadequate?
  └── src/polaris_graph/nodes/corpus_approval_gate.py ──► abort_corpus_approval_denied?
  └── src/polaris_graph/retrieval/contradiction_detector.py
  └── src/polaris_graph/nodes/completeness_checker.py
  └── src/polaris_graph/generator/multi_section_generator.py
       ├── src/polaris_graph/generator/live_deepseek_generator.py
       └── src/polaris_graph/generator/provenance_generator.py
            └── strict_verify → abort_no_verified_sections?
  └── src/polaris_graph/evaluator/live_qwen_judge.py
  └── src/polaris_graph/evaluator/external_evaluator.py
  └── src/polaris_graph/llm/openrouter_client.py (everywhere)
  └── src/polaris_graph/agents/nli_verifier.py (optional, PG_NLI_ENABLED)
  └── src/polaris_graph/tracing.py (JSONL trace writer)
  └── src/providers/llm_provider.py
```

Also included in pipeline A's 23 live files:
- `scripts/run_r6_validation.py` — 4-query revalidation
- `scripts/codex_loop_parse.py` — Codex verdict frontmatter parser
- `scripts/audit_live_code.py` — import-closure analysis (this audit's tool)

## Pipeline B — UI web server (active, NOT yet audited)

Entry: `uvicorn scripts.live_server:app` (Docker default via `serve`)

Primary file: `scripts/live_server.py` (214KB). FastAPI + SSE, handles:
- auth routes (from `src/auth/auth_routes.py`, `src/auth/auth_middleware.py`)
- single-vector research via subprocess / async calls
- dashboard rendering, trace viewers, evidence popovers
- upload ingestion (`src/polaris_graph/document_ingester.py`)
- checkpoint management (`src/polaris_graph/checkpoint_manager.py`)
- memory (`src/polaris_graph/memory/{campaign_store,content_cache,cross_vector}.py`)

Research execution: routes to one of:
- `src/polaris_graph/graph.py::build_and_run` (v1)
- `src/polaris_graph/graph_v2.py::build_and_run` (v2, CRAG)
- `src/polaris_graph/graph_v3.py::build_and_run_v3` (v3, ReAct agent)

**NONE of these share the pipeline-A strict_verify / corpus-approval /
delimiter-sanitization invariants.** This is a known parity gap — see
`docs/todo_list.md`.

## Pipeline C — legacy CLI research (FROZEN since 2026-03-16)

Entry: `python -m scripts.full_cycle` (Docker `research` subcommand)

Flow (per source code, CURRENTLY BROKEN):
```
scripts/full_cycle.py
  └── src/orchestration/graph.py::run_research
  └── scripts/run_ragas_v3.py  ←  DOES NOT EXIST (ImportError)
  └── scripts/final_audit.py   ←  DOES NOT EXIST (ImportError)
  └── src/audit/automated_deep_audit.py::AutomatedDeepAudit
```

`src/orchestration/FROZEN_SINCE_2026-03-16.md` contains the
retire/repair/leave decision tree. Until a decision is made, this
pipeline is read-only by convention.

## Recent commit activity per subsystem (last 60 days)

| Subsystem | Commits | Last commit | Pipeline |
|---|---|---|---|
| `src/polaris_graph/` | 159 | 2026-04-18 | A + B |
| `src/tools/` | 8 | 2026-04-12 | B |
| `src/agents/` | 5 | 2026-04-16 | A (via nli_verifier) + B |
| `src/audit/` | 3 | 2026-04-16 | B |
| `src/config/` | 2 | 2026-04-16 | shared |
| `src/orchestration/` | 1 | 2026-03-16 | **C (frozen)** |
| `src/auth/` (non-core) | 1 | 2026-03-16 | B |
| `src/benchmarks/` | 1 | 2026-03-16 | — |
| `src/llm/` (non-polaris_graph) | 1 | 2026-03-16 | — |
| `src/memory/` (non-polaris_graph) | 1 | 2026-03-16 | — |
| `src/quality/` | 1 | 2026-03-16 | — |
| `src/schemas/` (non-polaris_graph) | 1 | 2026-03-16 | — |
| `src/search/` | 1 | 2026-03-16 | — |
| `src/state/` | 0 | — | — |

## What to audit per pipeline

- **Pipeline A**: deep audit across all 12 dimensions (this is the
  product's hardened path). Focus on design issues since code-level
  defenses are already battle-tested via rounds 1-5.
- **Pipeline B**: identify which pipeline-A invariants are missing
  and what the risk is. Do not deep-audit UI JavaScript/templates.
- **Pipeline C**: confirm the Docker `research` subcommand is broken
  (missing scripts). Do not deep-audit the frozen code — the
  disposition decision is user-facing, not code-level.
